#!/usr/bin/env python3
"""Wi-Fi HaLow smart-home / campus scenario.

200 × 200 m campus with interior walls and multiple access points.
"""

from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Obstacle, Simulation
from lpwan_sim.protocols import WiFiHaLow
from lpwan_sim.visualization import plot_rssi, plot_snr, plot_coverage_overlay


def main() -> None:
    halow = WiFiHaLow(channel_width_mhz=2, mcs=2)

    env = Environment(width=200, height=200, resolution=2)

    # Two access points
    env.add_gateway(Gateway(x=60, y=100, protocol=halow, sensitivity_dbm=halow.sensitivity_dbm,
                            antenna_gain_dbi=3.0, label="AP-1"))
    env.add_gateway(Gateway(x=140, y=100, protocol=halow, sensitivity_dbm=halow.sensitivity_dbm,
                            antenna_gain_dbi=3.0, label="AP-2"))

    # Smart-home sensors
    for i, (x, y) in enumerate([(20, 20), (180, 20), (20, 180), (180, 180),
                                 (100, 50), (100, 150)]):
        env.add_transmitter(Transmitter(x=x, y=y, protocol=halow,
                                        tx_power_dbm=10, label=f"Dev-{i+1}"))

    # Interior walls
    env.add_obstacle(Obstacle.from_material((100, 0), (100, 80), "drywall"))
    env.add_obstacle(Obstacle.from_material((100, 120), (100, 200), "drywall"))
    env.add_obstacle(Obstacle.from_material((50, 100), (80, 100), "wood"))
    env.add_obstacle(Obstacle.from_material((120, 100), (150, 100), "glass"))

    sim = Simulation(env, pathloss_model="log-distance", pathloss_exponent=2.5,
                     noise_floor_dbm=-120)
    result = sim.run()

    stats = sim.coverage_stats(result, sensitivity_dbm=halow.sensitivity_dbm)
    print("Wi-Fi HaLow Campus Deployment")
    print("=" * 40)
    for k, v in stats.items():
        print(f"  {k:>20s}: {v}")

    plot_rssi(result, env, save_path="halow_rssi.png")
    plot_coverage_overlay(result, env, sensitivity_dbm=halow.sensitivity_dbm,
                          save_path="halow_coverage.png")
    print("Saved: halow_rssi.png, halow_coverage.png")


if __name__ == "__main__":
    main()
