#!/usr/bin/env python3
"""Compare LoRaWAN vs NB-IoT vs Wi-Fi HaLow in the same environment."""

from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Obstacle, Simulation
from lpwan_sim.protocols import LoRaWAN, NBIoT, WiFiHaLow
from lpwan_sim.visualization import plot_comparison


def _build_env(protocol, gw_kwargs):
    """Create a 500 × 500 m environment with one gateway and shared obstacles."""
    env = Environment(width=500, height=500, resolution=5)
    env.add_gateway(Gateway(x=250, y=250, protocol=protocol, label=protocol.name, **gw_kwargs))
    env.add_transmitter(Transmitter(x=50, y=50, protocol=protocol, tx_power_dbm=protocol.max_tx_power_dbm, label="S1"))
    env.add_transmitter(Transmitter(x=450, y=450, protocol=protocol, tx_power_dbm=protocol.max_tx_power_dbm, label="S2"))

    # Shared obstacles
    env.add_obstacle(Obstacle.from_material((200, 0), (200, 500), "concrete"))
    env.add_obstacle(Obstacle.from_material((300, 0), (300, 500), "brick"))
    return env


def main() -> None:
    lora = LoRaWAN(region="EU868", spreading_factor=12)
    nbiot = NBIoT(band="B20")
    halow = WiFiHaLow(channel_width_mhz=1, mcs=0)

    configs = {
        "LoRaWAN SF12": (lora, {"sensitivity_dbm": lora.sensitivity_dbm, "antenna_gain_dbi": 6.0}),
        "NB-IoT B20": (nbiot, {"sensitivity_dbm": nbiot.sensitivity_dbm, "antenna_gain_dbi": 8.0}),
        "Wi-Fi HaLow": (halow, {"sensitivity_dbm": halow.sensitivity_dbm, "antenna_gain_dbi": 3.0}),
    }

    results = {}
    for label, (proto, gw_kw) in configs.items():
        env = _build_env(proto, gw_kw)
        sim = Simulation(env, pathloss_model="log-distance", pathloss_exponent=2.7)
        res = sim.run()
        results[label] = (res, env)
        stats = sim.coverage_stats(res, sensitivity_dbm=proto.sensitivity_dbm)
        print(f"{label}: coverage={stats['coverage_pct']}%, mean_rssi={stats['mean_rssi_dbm']} dBm")

    plot_comparison(results, metric="rssi", save_path="comparison_rssi.png")
    plot_comparison(results, metric="snr", save_path="comparison_snr.png")
    print("Saved: comparison_rssi.png, comparison_snr.png")


if __name__ == "__main__":
    main()
