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

# ============================================================================
# Simulation engine
# ============================================================================

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


def _apply_obstacle_shadows(result, config, device_info):
    """Post-process RSSI grid: subtract obstacle attenuation for shadowed cells."""
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
    
    # Build obstacle rectangles in meters
    obs_rects = []
    for obs in config.obstacles:
        ox = obs.position.x * 1000
        oy = obs.position.y * 1000
        ow = obs.width_km * 1000
        oh = obs.height_km * 1000
        mat = obs.material
        if obs.type == "house":
            att = MATERIAL_DB.get("brick", 10.0)
        elif obs.type == "water":
            att = MATERIAL_DB.get("water", 12.0)
        elif obs.type == "forest":
            att = MATERIAL_DB.get("foliage", 8.0)
        elif obs.type == "water_tower":
            att = MATERIAL_DB.get("water_tower", 15.0)
        else:
            att = MATERIAL_DB.get(mat, 10.0)
        obs_rects.append((ox, oy, ow, oh, att))
    
    # For each grid cell, find nearest transmitter, check obstacle intersection
    attenuation_grid = np.zeros((rows, cols), dtype=np.float64)
    
    for i in range(rows):
        cell_y = i * res_m + res_m / 2
        for j in range(cols):
            cell_x = j * res_m + res_m / 2
            
            # Find nearest transmitter
            best_tx = None
            best_dist_sq = float('inf')
            for tx_x, tx_y in tx_positions:
                dsq = (cell_x - tx_x)**2 + (cell_y - tx_y)**2
                if dsq < best_dist_sq:
                    best_dist_sq = dsq
                    best_tx = (tx_x, tx_y)
            
            if best_tx is None:
                continue
            
            # Check each obstacle for line-of-sight intersection
            total_att = 0.0
            for ox, oy, ow, oh, att in obs_rects:
                # Skip if cell is inside the obstacle
                if ox <= cell_x <= ox + ow and oy <= cell_y <= oy + oh:
                    total_att += att * 2  # inside obstacle = double attenuation
                    continue
                if _line_intersects_rect(best_tx[0], best_tx[1], cell_x, cell_y, ox, oy, ow, oh):
                    total_att += att
            
            attenuation_grid[i, j] = total_att
    
    # Apply attenuation
    result.best_rssi -= attenuation_grid
    # Also apply to per-transmitter RSSI
    for key in result.rssi:
        result.rssi[key] -= attenuation_grid


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
    sim = Simulation(env, pathloss_model="log-distance", pathloss_exponent=2.7)
    result = sim.run()
    
    # ── Post-process: apply obstacle shadow attenuation to RSSI grid ──
    _apply_obstacle_shadows(result, config, device_info)
    
    # Overall coverage stats
    stats = sim.coverage_stats(result, sensitivity_dbm=-137.0)
    
    # Per-tech stats: compute from per-transmitter RSSI/SNR
    per_tech_stats = {}
    tech_sensitivities = {"halow": -95.0, "lorawan": -137.0, "nbiot": -125.0}
    
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
            sens = tech_sensitivities[tech]
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
