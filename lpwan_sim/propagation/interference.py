"""Interference and noise-floor helpers."""

from __future__ import annotations

import numpy as np


def noise_power_dbm(bandwidth_hz: float, temperature_k: float = 290.0) -> float:
    """Thermal noise power in dBm.

    N = k·T·B  →  N(dBm) = 10·log10(k·T·B) + 30
    """
    k_b = 1.380649e-23  # Boltzmann constant (J/K)
    n_watts = k_b * temperature_k * bandwidth_hz
    return 10.0 * np.log10(n_watts) + 30.0


def overlap_factor(
    f1_mhz: float, bw1_khz: float, f2_mhz: float, bw2_khz: float
) -> float:
    """Spectral overlap ratio (0–1) between two channels.

    Returns the fraction of channel 2's bandwidth that overlaps with channel 1.
    """
    lo1 = f1_mhz - bw1_khz / 2000.0
    hi1 = f1_mhz + bw1_khz / 2000.0
    lo2 = f2_mhz - bw2_khz / 2000.0
    hi2 = f2_mhz + bw2_khz / 2000.0
    overlap = max(0.0, min(hi1, hi2) - max(lo1, lo2))
    width2 = bw2_khz / 1000.0
    return overlap / width2 if width2 > 0 else 0.0
