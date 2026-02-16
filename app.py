"""FastAPI web app for interactive LPWAN simulation."""

import math
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional
import numpy as np

from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Simulation
from lpwan_sim.core.environment import Obstacle, MATERIAL_ATTENUATION
from lpwan_sim.protocols import LoRaWAN, NBIoT, WiFiHaLow

app = FastAPI(title="LPWAN Simulator")

# ============================================================================
# Material attenuation map (dB)
# ============================================================================
MATERIAL_DB = {
    "wood": 4.0,
    "glass": 3.0,
    "cement": 12.0,
    "metal": 25.0,
    "brick": 10.0,
    "water": 12.0,
    "foliage": 8.0,
    "water_tower": 15.0,
}

# ============================================================================
# HaLow US channel map (802.11ah, 902-928 MHz)
# ============================================================================
HALOW_US_CHANNELS = {
    1: {"channels": list(range(1, 52, 2)), "bw_mhz": 1},
    2: {"channels": list(range(2, 51, 4)), "bw_mhz": 2},
    4: {"channels": [4, 12, 20, 28, 36, 44], "bw_mhz": 4},
    8: {"channels": [8, 24, 40], "bw_mhz": 8},
    16: {"channels": [16, 48], "bw_mhz": 16},
}

def halow_center_freq(channel: int) -> float:
    return 902.0 + channel * 0.5

# ============================================================================
# Height gain correction: extra_gain = 6 * log10(height / 1m)
# ============================================================================
def height_gain_db(height_m: float, reference_m: float = 1.0) -> float:
    if height_m <= reference_m:
        return 0.0
    return 6.0 * math.log10(height_m / reference_m)

# ============================================================================
# Data models
# ============================================================================

class Point(BaseModel):
    x: float
    y: float

class RectObstacle(BaseModel):
    id: str
    type: str
    position: Point
    width_km: float
    height_km: float
    material: str = "wood"

class SimConfig(BaseModel):
    width_km: float = 5.0
    height_km: float = 5.0
    resolution_m: float = 50.0
    devices: List[dict] = []
    obstacles: List[RectObstacle] = []
    environment_type: str = "urban"
    shadow_fading: bool = True
    multipath_fading: bool = True

# ============================================================================
# Simulation engine
# ============================================================================

# ============================================================================
# Per-technology receiver sensitivity and noise figure
# ============================================================================
TECH_SENSITIVITY = {
    "halow": -95.0,
    "lorawan": {
        7: -123.0, 8: -126.0, 9: -129.0,
        10: -132.0, 11: -134.5, 12: -137.0,
    },
    "nbiot": -125.0,
}

TECH_NOISE_FIGURE = {
    "halow": 6.0,
    "lorawan": 6.0,
    "nbiot": 5.0,
}

ENV_PATH_LOSS_EXPONENT = {
    "urban": 2.7,
    "suburban": 2.4,
    "rural": 2.0,
}

def rect_to_obstacle_segments(obs: RectObstacle) -> List[Obstacle]:
    x1 = obs.position.x * 1000
    y1 = obs.position.y * 1000
    x2 = x1 + obs.width_km * 1000
    y2 = y1 + obs.height_km * 1000
    att = MATERIAL_DB.get(obs.material, 10.0)
    
    if obs.type == "house":
        att = MATERIAL_DB.get("brick", 10.0)
    elif obs.type == "water":
        att = MATERIAL_DB.get("water", 12.0)
    elif obs.type == "forest":
        att = MATERIAL_DB.get("foliage", 8.0)
    elif obs.type == "water_tower":
        att = MATERIAL_DB.get("water_tower", 15.0)
    
    segments = [
        Obstacle(start_point=(x1, y1), end_point=(x2, y1), attenuation_db=att, material=obs.material),
        Obstacle(start_point=(x2, y1), end_point=(x2, y2), attenuation_db=att, material=obs.material),
        Obstacle(start_point=(x2, y2), end_point=(x1, y2), attenuation_db=att, material=obs.material),
        Obstacle(start_point=(x1, y2), end_point=(x1, y1), attenuation_db=att, material=obs.material),
    ]
    return segments

def get_device_freq_mhz(dev: dict) -> float:
    dtype = dev.get("type", "")
    if dtype.startswith("halow"):
        ch = dev.get("channel", 2)
        return halow_center_freq(ch)
    elif dtype.startswith("lorawan"):
        region = dev.get("region", "US915")
        return 915.0 if region == "US915" else 868.0
    elif dtype.startswith("nbiot"):
        band = dev.get("band", "B5")
        band_freq = {"B1": 2140.0, "B3": 1805.0, "B5": 869.0, "B8": 925.0, "B20": 791.0, "B28": 758.0}
        return band_freq.get(band, 869.0)
    elif dtype == "power_meter":
        return dev.get("frequency_mhz", 925.0)
    return 900.0

def freqs_overlap(f1: float, bw1_khz: float, f2: float, bw2_khz: float) -> bool:
    low1 = f1 - bw1_khz / 2000.0
    high1 = f1 + bw1_khz / 2000.0
    low2 = f2 - bw2_khz / 2000.0
    high2 = f2 + bw2_khz / 2000.0
    return low1 < high2 and low2 < high1

def _line_intersects_rect(x1, y1, x2, y2, rx, ry, rw, rh):
    """Check if line segment (x1,y1)-(x2,y2) intersects rectangle (rx,ry,rw,rh)."""
    # Cohen-Sutherland style clipping test
    def _outcode(x, y):
        c = 0
        if x < rx: c |= 1
        elif x > rx + rw: c |= 2
        if y < ry: c |= 4
        elif y > ry + rh: c |= 8
        return c
    
    c1, c2 = _outcode(x1, y1), _outcode(x2, y2)
    for _ in range(10):
        if (c1 | c2) == 0:
            return True  # both inside
        if (c1 & c2) != 0:
            return False  # both outside same side
        c = c1 if c1 else c2
        dx, dy = x2 - x1, y2 - y1
        if c & 1:
            y = y1 + dy * (rx - x1) / dx if dx else y1; x = rx
        elif c & 2:
            y = y1 + dy * (rx + rw - x1) / dx if dx else y1; x = rx + rw
        elif c & 4:
            x = x1 + dx * (ry - y1) / dy if dy else x1; y = ry
        else:
            x = x1 + dx * (ry + rh - y1) / dy if dy else x1; y = ry + rh
        if c == c1:
            x1, y1, c1 = x, y, _outcode(x, y)
        else:
            x2, y2, c2 = x, y, _outcode(x, y)
    return False


def _ray_intersects_rect_vectorized(tx_x, tx_y, cell_xs, cell_ys, rx, ry, rw, rh):
    """Vectorized: for each cell, check if ray from (tx_x,tx_y) to (cell_x,cell_y) intersects rect.
    Returns boolean array of shape (N,)."""
    N = len(cell_xs)
    result = np.zeros(N, dtype=bool)
    
    # Parametric ray: P = tx + t*(cell - tx), t in [0,1]
    dx = cell_xs - tx_x
    dy = cell_ys - tx_y
    
    # Check each of 4 edges
    # Left edge: x = rx
    mask = np.abs(dx) > 1e-6
    t_left = np.full(N, -1.0)
    t_left[mask] = (rx - tx_x) / dx[mask]
    y_at_left = tx_y + t_left * dy
    hit_left = (t_left > 0.01) & (t_left < 0.99) & (y_at_left >= ry) & (y_at_left <= ry + rh)
    
    # Right edge: x = rx + rw  
    t_right = np.full(N, -1.0)
    t_right[mask] = (rx + rw - tx_x) / dx[mask]
    y_at_right = tx_y + t_right * dy
    hit_right = (t_right > 0.01) & (t_right < 0.99) & (y_at_right >= ry) & (y_at_right <= ry + rh)
    
    # Top edge: y = ry
    mask2 = np.abs(dy) > 1e-6
    t_top = np.full(N, -1.0)
    t_top[mask2] = (ry - tx_y) / dy[mask2]
    x_at_top = tx_x + t_top * dx
    hit_top = (t_top > 0.01) & (t_top < 0.99) & (x_at_top >= rx) & (x_at_top <= rx + rw)
    
    # Bottom edge: y = ry + rh
    t_bot = np.full(N, -1.0)
    t_bot[mask2] = (ry + rh - tx_y) / dy[mask2]
    x_at_bot = tx_x + t_bot * dx
    hit_bot = (t_bot > 0.01) & (t_bot < 0.99) & (x_at_bot >= rx) & (x_at_bot <= rx + rw)
    
    result = hit_left | hit_right | hit_top | hit_bot
    
    # Also check if cell is inside the rect
    inside = (cell_xs >= rx) & (cell_xs <= rx + rw) & (cell_ys >= ry) & (cell_ys <= ry + rh)
    
    return result, inside


def _apply_obstacle_shadows(result, config, device_info):
    """Post-process RSSI grid: subtract obstacle attenuation for shadowed cells.
    Vectorized with numpy for performance on large grids."""
    if not config.obstacles:
        return
    
    rows, cols = result.best_rssi.shape
    res_m = config.resolution_m
    
    # Collect transmitter positions in meters (exclude power_meters)
    tx_positions = []
    for freq, bw, x_m, y_m, pwr, tech in device_info:
        if tech != "power_meter":
            tx_positions.append((x_m, y_m))
    
    if not tx_positions:
        return
    
    tx_arr = np.array(tx_positions)  # shape (num_tx, 2)
    
    # Build obstacle rectangles in meters
    obs_rects = []
    for obs in config.obstacles:
        ox = obs.position.x * 1000
        oy = obs.position.y * 1000
        ow = obs.width_km * 1000
        oh = obs.height_km * 1000
        if obs.type == "house":
            att = MATERIAL_DB.get("brick", 10.0)
        elif obs.type == "water":
            att = MATERIAL_DB.get("water", 12.0)
        elif obs.type == "forest":
            att = MATERIAL_DB.get("foliage", 8.0)
        elif obs.type == "water_tower":
            att = MATERIAL_DB.get("water_tower", 15.0)
        else:
            att = MATERIAL_DB.get(obs.material, 10.0)
        obs_rects.append((ox, oy, ow, oh, att))
    
    # Build cell coordinate grids
    cell_ys = np.arange(rows) * res_m + res_m / 2
    cell_xs = np.arange(cols) * res_m + res_m / 2
    cx_grid, cy_grid = np.meshgrid(cell_xs, cell_ys)
    cx_flat = cx_grid.ravel()
    cy_flat = cy_grid.ravel()
    N = len(cx_flat)
    
    # For EACH transmitter, compute its obstacle attenuation grid,
    # then apply to that transmitter's per-label RSSI.
    # Map TX positions to their labels
    tx_label_map = {}  # (tx_x, tx_y) -> [label, ...]
    for freq, bw, x_m, y_m, pwr, tech in device_info:
        if tech == "power_meter":
            continue
        # Find matching label from config devices
        for dev in config.devices:
            dev_x = dev["position"]["x"] * 1000
            dev_y = dev["position"]["y"] * 1000
            if abs(dev_x - x_m) < 1 and abs(dev_y - y_m) < 1:
                lbl = dev.get("label", "")
                key = (x_m, y_m)
                if key not in tx_label_map:
                    tx_label_map[key] = []
                tx_label_map[key].append(lbl)
                break
    
    # Compute per-TX attenuation and apply to per-label RSSI grids
    for (tx_x, tx_y), labels in tx_label_map.items():
        att_flat = np.zeros(N, dtype=np.float64)
        
        for ox, oy, ow, oh, att in obs_rects:
            hits, inside = _ray_intersects_rect_vectorized(tx_x, tx_y, cx_flat, cy_flat, ox, oy, ow, oh)
            att_flat[inside] += att * 2
            att_flat[hits & ~inside] += att
        
        att_grid = att_flat.reshape(rows, cols)
        
        # Apply to each per-label RSSI grid belonging to this TX
        for lbl in labels:
            if lbl in result.rssi:
                result.rssi[lbl] -= att_grid
            if lbl in result.snr:
                result.snr[lbl] -= att_grid
    
    # Recompute best_rssi from the now-attenuated per-TX grids
    if result.rssi:
        all_rssi = list(result.rssi.values())
        result.best_rssi = np.maximum.reduce(all_rssi)
    if result.snr:
        all_snr = list(result.snr.values())
        result.best_snr = np.maximum.reduce(all_snr)


def run_simulation(config: SimConfig) -> Dict:
    width_m = config.width_km * 1000
    height_m = config.height_km * 1000
    
    env = Environment(width=width_m, height=height_m, resolution=config.resolution_m)
    
    for obs in config.obstacles:
        for seg in rect_to_obstacle_segments(obs):
            env.add_obstacle(seg)
    
    device_info = []  # (freq_mhz, bw_khz, x_m, y_m, tx_power, tech_key)
    
    # Per-tech RSSI tracking
    tech_rssi = {"halow": [], "lorawan": [], "nbiot": []}
    tech_snr = {"halow": [], "lorawan": [], "nbiot": []}
    
    # Counters for detailed stats
    counts = {
        "halow_ap": 0, "halow_endpoint": 0,
        "lorawan_gateway": 0, "lorawan_endpoint": 0,
        "nbiot_base": 0, "nbiot_endpoint": 0,
        "power_meter": 0,
    }
    
    for dev in config.devices:
        x_m = dev["position"]["x"] * 1000
        y_m = dev["position"]["y"] * 1000
        dtype = dev.get("type", "")
        label = dev.get("label", dtype)
        elevation_m = dev.get("elevation_m", 1.0)
        h_gain = height_gain_db(elevation_m)
        
        counts[dtype] = counts.get(dtype, 0) + 1
        
        if dtype == "power_meter":
            # Power meter is purely a noise source, not a transmitter
            freq = dev.get("frequency_mhz", 925.0)
            bw_khz = dev.get("bandwidth_khz", 50000.0)
            pwr = dev.get("tx_power_dbm", 20.0)
            # Boost power meter noise effect (+15 dB) for visible interference
            ns = NoiseSource(x=x_m, y=y_m, power_dbm=pwr + 15,
                           frequency_mhz=freq, bandwidth_khz=bw_khz,
                           label=label)
            env.add_noise_source(ns)
            device_info.append((freq, bw_khz, x_m, y_m, pwr, "power_meter"))
            continue
        
        if dtype == "halow_ap":
            ch_w = dev.get("channel_width_mhz", 2.0)
            ch = dev.get("channel", 2)
            mcs = dev.get("mcs", 2)
            freq = halow_center_freq(ch)
            proto = WiFiHaLow(channel_width_mhz=ch_w, mcs=mcs, frequency_mhz=freq)
            gain = dev.get("antenna_gain_dbi", 3.0) + h_gain
            tx_power = dev.get("tx_power_dbm", 30.0)
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=tx_power,
                           antenna_gain_dbi=gain, label=label)
            env.add_transmitter(tx)
            device_info.append((freq, ch_w * 1000, x_m, y_m, tx_power, "halow"))
            
        elif dtype == "halow_endpoint":
            ch_w = dev.get("channel_width_mhz", 2.0)
            ch = dev.get("channel", 2)
            mcs = dev.get("mcs", 2)
            freq = halow_center_freq(ch)
            proto = WiFiHaLow(channel_width_mhz=ch_w, mcs=mcs, frequency_mhz=freq)
            tx_power = dev.get("tx_power_dbm", 10.0)
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=tx_power,
                           antenna_gain_dbi=h_gain, label=label)
            env.add_transmitter(tx)
            device_info.append((freq, ch_w * 1000, x_m, y_m, tx_power, "halow"))
            
        elif dtype == "lorawan_gateway":
            region = dev.get("region", "US915")
            sf = dev.get("spreading_factor", 12)
            bw = dev.get("bandwidth_khz", 125.0)
            proto = LoRaWAN(region=region, spreading_factor=sf, bandwidth_khz=bw)
            gain = dev.get("antenna_gain_dbi", 6.0) + h_gain
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=14.0,
                           antenna_gain_dbi=gain, label=label)
            env.add_transmitter(tx)
            device_info.append((proto.frequency_mhz, bw, x_m, y_m, 14.0, "lorawan"))
            
        elif dtype == "lorawan_endpoint":
            region = dev.get("region", "US915")
            sf = dev.get("spreading_factor", 12)
            bw = dev.get("bandwidth_khz", 125.0)
            proto = LoRaWAN(region=region, spreading_factor=sf, bandwidth_khz=bw)
            tx_power = dev.get("tx_power_dbm", 14.0)
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=tx_power,
                           antenna_gain_dbi=h_gain, label=label)
            env.add_transmitter(tx)
            device_info.append((proto.frequency_mhz, bw, x_m, y_m, tx_power, "lorawan"))
            
        elif dtype == "nbiot_base":
            band = dev.get("band", "B5")
            tone = dev.get("tone_mode", "single-15")
            proto = NBIoT(band=band, tone_mode=tone)
            gain = dev.get("antenna_gain_dbi", 8.0)
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=23.0,
                           antenna_gain_dbi=gain, label=label)
            env.add_transmitter(tx)
            device_info.append((proto.frequency_mhz, proto.bandwidth_khz, x_m, y_m, 23.0, "nbiot"))
            
        elif dtype == "nbiot_endpoint":
            band = dev.get("band", "B5")
            tone = dev.get("tone_mode", "single-15")
            proto = NBIoT(band=band, tone_mode=tone)
            tx_power = dev.get("tx_power_dbm", 23.0)
            tx = Transmitter(x=x_m, y=y_m, protocol=proto, tx_power_dbm=tx_power, label=label)
            env.add_transmitter(tx)
            device_info.append((proto.frequency_mhz, proto.bandwidth_khz, x_m, y_m, tx_power, "nbiot"))
    
    # Inter-device interference
    for i, (f1, bw1, x1, y1, pwr1, tech1) in enumerate(device_info):
        for j, (f2, bw2, x2, y2, pwr2, tech2) in enumerate(device_info):
            if i == j:
                continue
            if tech1 == "power_meter" or tech2 == "power_meter":
                continue  # power meters already added as noise sources
            if freqs_overlap(f1, bw1, f2, bw2):
                ns = NoiseSource(x=x1, y=y1, power_dbm=pwr1 - 10,
                               frequency_mhz=f1, bandwidth_khz=bw1,
                               label=f"interf_{i}_{j}")
                env.add_noise_source(ns)
    
    # Run simulation
    pl_exp = ENV_PATH_LOSS_EXPONENT.get(config.environment_type, 2.7)
    shadow_std = 4.0 if config.shadow_fading else 0.0
    sim = Simulation(
        env,
        pathloss_model="log-distance",
        pathloss_exponent=pl_exp,
        shadow_fading_std=shadow_std,
        multipath_fading=config.multipath_fading,
    )
    result = sim.run()
    
    # ── Post-process: apply obstacle shadow attenuation to RSSI grid ──
    _apply_obstacle_shadows(result, config, device_info)
    
    # Overall coverage stats (use worst-case sensitivity across all techs present)
    stats = sim.coverage_stats(result, sensitivity_dbm=-137.0)
    
    # Per-tech stats: compute from per-transmitter RSSI/SNR
    per_tech_stats = {}
    
    for tech in ["halow", "lorawan", "nbiot"]:
        tech_rssi_arrays = []
        tech_snr_arrays = []
        for label_key, rssi_grid in result.rssi.items():
            # Match by label prefix
            for dev in config.devices:
                if dev.get("label", "") == label_key:
                    dk = dev.get("type", "")
                    if dk.startswith(tech):
                        tech_rssi_arrays.append(rssi_grid)
                        if label_key in result.snr:
                            tech_snr_arrays.append(result.snr[label_key])
                    break
        
        if tech_rssi_arrays:
            best_rssi = np.maximum.reduce(tech_rssi_arrays)
            best_snr = np.maximum.reduce(tech_snr_arrays) if tech_snr_arrays else np.zeros_like(best_rssi)
            # Per-tech sensitivity (for LoRaWAN, use worst SF present or default SF12)
            tech_sens = TECH_SENSITIVITY.get(tech, -137.0)
            if isinstance(tech_sens, dict):
                # Find max SF used by this tech's devices
                max_sf = 12
                for dev in config.devices:
                    if dev.get("type", "").startswith(tech):
                        max_sf = max(max_sf, dev.get("spreading_factor", 12))
                sens = tech_sens.get(max_sf, -137.0)
            else:
                sens = tech_sens
            total = best_rssi.size
            covered = int(np.sum(best_rssi >= sens))
            per_tech_stats[tech] = {
                "coverage_pct": round(100.0 * covered / total, 2) if total else 0.0,
                "mean_rssi_dbm": round(float(np.mean(best_rssi)), 2),
                "mean_snr_db": round(float(np.mean(best_snr)), 2),
            }
    
    return {
        "width_km": config.width_km,
        "height_km": config.height_km,
        "resolution_m": config.resolution_m,
        "rssi_grid": result.best_rssi.tolist(),
        "snr_grid": result.best_snr.tolist(),
        "interference_grid": result.interference.tolist(),
        "grid_shape": list(result.best_rssi.shape),
        "stats": stats,
        "per_tech_stats": per_tech_stats,
        "device_counts": counts,
    }

# ============================================================================
# API endpoints
# ============================================================================

@app.post("/api/simulate")
async def simulate(config: SimConfig):
    try:
        result = run_simulation(config)
        return {"ok": True, "result": result}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}

@app.get("/api/halow-channels")
async def halow_channels():
    return HALOW_US_CHANNELS

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
