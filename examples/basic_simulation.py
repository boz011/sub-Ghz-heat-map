#!/usr/bin/env python3
"""Basic LPWAN simulation example.

Creates a 500×500 m environment, places a LoRaWAN gateway, three end devices,
and one noise source, then runs the simulation and generates heatmaps.
"""

from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Simulation
from lpwan_sim.protocols import LoRaWAN
from lpwan_sim.visualization import plot_rssi, plot_snr, plot_interference


def main() -> None:
    # --- Protocol ---
    lora_eu = LoRaWAN(region="EU868", spreading_factor=12)

    # --- Environment (500 m × 500 m, 5 m resolution) ---
    env = Environment(width=500, height=500, resolution=5)

    # --- Gateway at centre ---
    gw = Gateway(x=250, y=250, protocol=lora_eu, sensitivity_dbm=lora_eu.sensitivity_dbm,
                 antenna_gain_dbi=6.0, label="GW-1")
    env.add_gateway(gw)

    # --- End devices ---
    env.add_transmitter(Transmitter(x=50, y=50, protocol=lora_eu, tx_power_dbm=14, label="Sensor-A"))
    env.add_transmitter(Transmitter(x=400, y=100, protocol=lora_eu, tx_power_dbm=14, label="Sensor-B"))
    env.add_transmitter(Transmitter(x=300, y=450, protocol=lora_eu, tx_power_dbm=14, label="Sensor-C"))

    # --- Noise source ---
    env.add_noise_source(NoiseSource(x=200, y=200, power_dbm=5, frequency_mhz=868, bandwidth_khz=125, label="Jammer"))

    # --- Simulate ---
    sim = Simulation(env, pathloss_model="log-distance", pathloss_exponent=2.7, noise_floor_dbm=-120)
    result = sim.run()

    # --- Coverage stats ---
    stats = sim.coverage_stats(result, sensitivity_dbm=lora_eu.sensitivity_dbm)
    print("=" * 50)
    print("LPWAN Simulation — Coverage Report")
    print("=" * 50)
    for k, v in stats.items():
        print(f"  {k:>20s}: {v}")
    print("=" * 50)

    # --- Heatmaps ---
    plot_rssi(result, env, save_path="rssi_heatmap.png")
    plot_snr(result, env, save_path="snr_heatmap.png")
    plot_interference(result, env, save_path="interference_heatmap.png")
    print("Heatmaps saved: rssi_heatmap.png, snr_heatmap.png, interference_heatmap.png")


if __name__ == "__main__":
    main()
