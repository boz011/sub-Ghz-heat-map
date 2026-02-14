#!/usr/bin/env python3
"""NB-IoT urban deployment scenario.

Simulates a cell tower serving multiple IoT sensors in a 1 km × 1 km urban area
with concrete building walls and a noise source.
"""

from lpwan_sim.core import Environment, Transmitter, Gateway, NoiseSource, Obstacle, Simulation
from lpwan_sim.protocols import NBIoT
from lpwan_sim.visualization import plot_rssi, plot_snr, plot_coverage_overlay


def main() -> None:
    nbiot = NBIoT(band="B20", tone_mode="single-15")

    env = Environment(width=1000, height=1000, resolution=10)

    # Cell tower at centre
    gw = Gateway(x=500, y=500, protocol=nbiot, sensitivity_dbm=nbiot.sensitivity_dbm,
                 antenna_gain_dbi=8.0, label="Cell-Tower")
    env.add_gateway(gw)

    # Sensors spread around the area
    positions = [(100, 100), (900, 100), (100, 900), (900, 900),
                 (300, 500), (700, 500), (500, 200), (500, 800)]
    for i, (x, y) in enumerate(positions):
        env.add_transmitter(Transmitter(x=x, y=y, protocol=nbiot,
                                        tx_power_dbm=23, label=f"Sensor-{i+1}"))

    # Concrete building walls
    env.add_obstacle(Obstacle.from_material((200, 300), (200, 700), "concrete"))
    env.add_obstacle(Obstacle.from_material((800, 300), (800, 700), "concrete"))
    env.add_obstacle(Obstacle.from_material((400, 400), (600, 400), "brick"))

    # Noise source (industrial equipment)
    env.add_noise_source(NoiseSource(x=450, y=450, power_dbm=10,
                                     frequency_mhz=791, bandwidth_khz=180, label="EMI"))

    sim = Simulation(env, pathloss_model="log-distance", pathloss_exponent=3.2,
                     noise_floor_dbm=-120)
    result = sim.run()

    stats = sim.coverage_stats(result, sensitivity_dbm=nbiot.sensitivity_dbm)
    print("NB-IoT Urban Deployment")
    print("=" * 40)
    for k, v in stats.items():
        print(f"  {k:>20s}: {v}")

    plot_rssi(result, env, save_path="nbiot_rssi.png")
    plot_snr(result, env, save_path="nbiot_snr.png")
    plot_coverage_overlay(result, env, sensitivity_dbm=nbiot.sensitivity_dbm,
                          save_path="nbiot_coverage.png")
    print("Saved: nbiot_rssi.png, nbiot_snr.png, nbiot_coverage.png")


if __name__ == "__main__":
    main()
