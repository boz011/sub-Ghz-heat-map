"""Tests for the Environment class."""

import numpy as np
import pytest

from lpwan_sim.core.environment import Environment, Wall
from lpwan_sim.core.device import Transmitter, Gateway, NoiseSource
from lpwan_sim.protocols.lorawan import LoRaWAN


def test_grid_shape():
    env = Environment(100, 50, resolution=5)
    assert env.shape == (10, 20)


def test_distance_grid_center():
    env = Environment(100, 100, resolution=1)
    dg = env.distance_grid(50, 50)
    # The centre cell should have distance == resolution (clipped)
    assert dg[50, 50] == pytest.approx(1.0)


def test_add_devices():
    env = Environment(100, 100)
    proto = LoRaWAN()
    env.add_transmitter(Transmitter(10, 20, proto))
    env.add_gateway(Gateway(50, 50, proto))
    env.add_noise_source(NoiseSource(30, 30, power_dbm=-10))
    assert len(env.transmitters) == 1
    assert len(env.gateways) == 1
    assert len(env.noise_sources) == 1


def test_wall():
    env = Environment(100, 100)
    w = Wall(10, 0, 10, 100, attenuation_db=15)
    env.add_wall(w)
    assert len(env.walls) == 1
    assert env.walls[0].attenuation_db == 15.0
