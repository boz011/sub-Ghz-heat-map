# 📡 LPWAN Simulator

A Python toolkit for simulating LPWAN (Low-Power Wide-Area Network) wireless environments. Model signal propagation, calculate SNR, analyse coverage, and generate publication-ready heatmaps — all on a configurable 2-D grid.

## Features

- **Multi-protocol support** — LoRaWAN (EU868/US915), NB-IoT (B1–B28), Wi-Fi HaLow (802.11ah)
- **Propagation models** — Free-space path loss, log-distance, Okumura-Hata (urban/suburban/rural)
- **Interference modelling** — Place noise sources with arbitrary power, frequency, and bandwidth
- **Coverage analysis** — RSSI & SNR per grid point, coverage percentage, per-transmitter breakdown
- **Gateway placement** — Brute-force optimiser to find the best gateway location
- **Heatmap visualization** — RSSI, SNR, and interference maps via matplotlib (PNG export)

## Installation

```bash
# Clone and install in editable mode
git clone https://github.com/boz011/sub-Ghz-heat-map.git
cd sub-Ghz-heat-map
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Simulation
from lpwan_sim.protocols import LoRaWAN
from lpwan_sim.visualization import plot_rssi

# Set up
lora = LoRaWAN(region="EU868", spreading_factor=12)
env = Environment(width=500, height=500, resolution=5)
env.add_gateway(Gateway(250, 250, lora, label="GW"))
env.add_transmitter(Transmitter(50, 50, lora, label="Sensor-A"))
env.add_noise_source(NoiseSource(200, 200, power_dbm=5))

# Simulate
sim = Simulation(env)
result = sim.run()
print(sim.coverage_stats(result))

# Visualize
plot_rssi(result, env, save_path="rssi.png")
```

See [`examples/basic_simulation.py`](examples/basic_simulation.py) for a complete walkthrough.

## Screenshots

> *Coming soon — run the example to generate your own!*

## Roadmap

| Phase | Scope |
|-------|-------|
| **1 (current)** | Core simulation engine, protocols, propagation models, heatmaps |
| **2** | Obstacles & walls with attenuation, ray-tracing, multi-floor |
| **3** | Web UI (FastAPI + interactive map), real-time parameter tuning |

## Project Structure

```
lpwan_sim/
├── core/           # Environment, devices, simulation engine
├── protocols/      # LoRaWAN, NB-IoT, Wi-Fi HaLow parameters
├── propagation/    # Path-loss models & interference
├── analysis/       # Coverage analysis & placement optimisation
└── visualization/  # Matplotlib heatmap generation
```

## License

MIT — see [LICENSE](LICENSE).
