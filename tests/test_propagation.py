"""Tests for propagation models."""

import numpy as np
import pytest

from lpwan_sim.propagation.pathloss import (
    free_space_path_loss,
    log_distance_path_loss,
    okumura_hata,
)
from lpwan_sim.propagation.interference import noise_power_dbm, overlap_factor


class TestFSPL:
    def test_1km_868mhz(self):
        # FSPL at 1 km, 868 MHz ≈ 91.2 dB
        pl = float(free_space_path_loss(1000.0, 868.0))
        assert 90.0 < pl < 93.0

    def test_increases_with_distance(self):
        pl1 = float(free_space_path_loss(100.0, 868.0))
        pl2 = float(free_space_path_loss(1000.0, 868.0))
        assert pl2 > pl1


class TestLogDistance:
    def test_equals_fspl_at_d0(self):
        pl_log = float(log_distance_path_loss(1.0, 868.0, n=2.0, d0=1.0))
        pl_fspl = float(free_space_path_loss(1.0, 868.0))
        assert pl_log == pytest.approx(pl_fspl, abs=0.1)

    def test_higher_exponent_more_loss(self):
        pl_low = float(log_distance_path_loss(500.0, 868.0, n=2.0))
        pl_high = float(log_distance_path_loss(500.0, 868.0, n=3.5))
        assert pl_high > pl_low


class TestOkumuraHata:
    def test_urban_gt_suburban(self):
        d = 5000.0
        urban = float(okumura_hata(d, 868.0, area="urban"))
        suburban = float(okumura_hata(d, 868.0, area="suburban"))
        assert urban > suburban


class TestNoise:
    def test_thermal_noise(self):
        # 125 kHz BW at 290K → ≈ -120.98 dBm
        n = noise_power_dbm(125_000.0)
        assert -124.0 < n < -122.0


class TestOverlap:
    def test_full_overlap(self):
        assert overlap_factor(868.0, 125.0, 868.0, 125.0) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert overlap_factor(868.0, 125.0, 915.0, 125.0) == pytest.approx(0.0)
