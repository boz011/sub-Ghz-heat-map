"""Coverage analysis utilities."""

from __future__ import annotations

import numpy as np

from ..core.simulation import SimulationResult


def coverage_map(result: SimulationResult, sensitivity_dbm: float = -137.0) -> np.ndarray:
    """Boolean grid: True where best RSSI ≥ sensitivity."""
    return result.best_rssi >= sensitivity_dbm


def coverage_by_gateway(result: SimulationResult, sensitivity_dbm: float = -137.0) -> dict[str, float]:
    """Per-transmitter coverage percentage."""
    out: dict[str, float] = {}
    for label, rssi in result.rssi.items():
        total = rssi.size
        covered = int(np.sum(rssi >= sensitivity_dbm))
        out[label] = round(100.0 * covered / total, 2) if total else 0.0
    return out
