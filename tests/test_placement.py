"""Tests for placement optimiser."""

import pytest

from lpwan_sim.core.environment import Environment
from lpwan_sim.core.device import Transmitter, Gateway
from lpwan_sim.protocols.lorawan import LoRaWAN
from lpwan_sim.analysis.placement import (
    suggest_gateway_position,
    suggest_gateway_positions,
    coverage_score,
)


@pytest.fixture
def small_env():
    """Small environment for fast tests."""
    env = Environment(50, 50, resolution=10)
    proto = LoRaWAN(spreading_factor=12)
    env.add_transmitter(Transmitter(x=25, y=25, protocol=proto, tx_power_dbm=14, label="tx"))
    return env, proto


class TestCoverageScore:
    def test_returns_float(self, small_env):
        env, proto = small_env
        gw = Gateway(x=25, y=25, protocol=proto, sensitivity_dbm=proto.sensitivity_dbm)
        score = coverage_score(env, [gw], sensitivity_dbm=proto.sensitivity_dbm)
        assert isinstance(score, float)

    def test_centre_beats_corner(self, small_env):
        env, proto = small_env
        gw_centre = Gateway(x=25, y=25, protocol=proto, sensitivity_dbm=proto.sensitivity_dbm)
        gw_corner = Gateway(x=0, y=0, protocol=proto, sensitivity_dbm=proto.sensitivity_dbm)
        s_centre = coverage_score(env, [gw_centre], sensitivity_dbm=proto.sensitivity_dbm)
        s_corner = coverage_score(env, [gw_corner], sensitivity_dbm=proto.sensitivity_dbm)
        assert s_centre >= s_corner


class TestSuggestGatewayPosition:
    def test_returns_tuple(self, small_env):
        env, proto = small_env
        result = suggest_gateway_position(env, proto, step=25)
        assert len(result) == 3
        x, y, pct = result
        assert 0 <= x <= env.width
        assert 0 <= y <= env.height
        assert 0 <= pct <= 100


class TestSuggestGatewayPositions:
    def test_single_gateway(self, small_env):
        env, proto = small_env
        results = suggest_gateway_positions(env, proto, n_gateways=1, coarse_step=25)
        assert len(results) == 1
        assert results[0]["rank"] == 1
        assert "x" in results[0]
        assert "y" in results[0]
        assert "score" in results[0]

    def test_multi_gateway(self, small_env):
        env, proto = small_env
        results = suggest_gateway_positions(env, proto, n_gateways=2, coarse_step=25)
        assert len(results) == 2
        assert results[0]["rank"] == 1
        assert results[1]["rank"] == 2

    def test_positions_in_bounds(self, small_env):
        env, proto = small_env
        results = suggest_gateway_positions(env, proto, n_gateways=1, coarse_step=25)
        for r in results:
            assert 0 <= r["x"] <= env.width
            assert 0 <= r["y"] <= env.height
