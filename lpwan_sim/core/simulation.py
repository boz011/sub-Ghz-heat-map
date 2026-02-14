"""Run a simulation: compute RSSI, interference, and SNR grids."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .device import Gateway, NoiseSource, Transmitter
from .environment import Environment
from ..propagation.pathloss import free_space_path_loss, log_distance_path_loss
from ..propagation.interference import noise_power_dbm


@dataclass
class SimulationResult:
    """Holds computed grids for one simulation run."""

    rssi: Dict[str, np.ndarray] = field(default_factory=dict)
    """RSSI grid per transmitter label."""
    interference: np.ndarray = field(default_factory=lambda: np.array([]))
    """Total interference power (dBm) at each grid point."""
    snr: Dict[str, np.ndarray] = field(default_factory=dict)
    """SNR grid per transmitter label (dB)."""
    best_rssi: np.ndarray = field(default_factory=lambda: np.array([]))
    """Best (max) RSSI across all transmitters at each point."""
    best_snr: np.ndarray = field(default_factory=lambda: np.array([]))


class Simulation:
    """Compute RSSI, interference, and SNR over an :class:`Environment`.

    Parameters
    ----------
    env : Environment
        The environment to simulate.
    pathloss_model : str
        ``"fspl"`` or ``"log-distance"`` (default ``"log-distance"``).
    pathloss_exponent : float
        Path-loss exponent for log-distance model (default 2.7 — urban).
    noise_floor_dbm : float
        Thermal noise floor in dBm (default -120).
    """

    def __init__(
        self,
        env: Environment,
        pathloss_model: str = "log-distance",
        pathloss_exponent: float = 2.7,
        noise_floor_dbm: float = -120.0,
    ) -> None:
        self.env = env
        self.pathloss_model = pathloss_model
        self.pathloss_exponent = pathloss_exponent
        self.noise_floor_dbm = noise_floor_dbm

    # ------------------------------------------------------------------
    def _path_loss(self, distance: np.ndarray, freq_mhz: float) -> np.ndarray:
        if self.pathloss_model == "fspl":
            return free_space_path_loss(distance, freq_mhz)
        return log_distance_path_loss(distance, freq_mhz, n=self.pathloss_exponent)

    # ------------------------------------------------------------------
    def run(self) -> SimulationResult:
        """Execute the simulation and return results."""
        env = self.env
        result = SimulationResult()

        # --- RSSI per transmitter ---
        rssi_stack: List[np.ndarray] = []
        for idx, tx in enumerate(env.transmitters):
            dist = env.distance_grid(tx.x, tx.y)
            freq = tx.protocol.frequency_mhz
            pl = self._path_loss(dist, freq)
            rssi = tx.eirp_dbm - pl
            label = tx.label or f"tx_{idx}"
            result.rssi[label] = rssi
            rssi_stack.append(rssi)

        if rssi_stack:
            result.best_rssi = np.maximum.reduce(rssi_stack)
        else:
            result.best_rssi = np.full(env.shape, self.noise_floor_dbm)

        # --- Interference ---
        interf_mw = np.zeros(env.shape)
        for ns in env.noise_sources:
            dist = env.distance_grid(ns.x, ns.y)
            pl = self._path_loss(dist, ns.frequency_mhz)
            power = ns.power_dbm - pl  # received interference dBm
            interf_mw += 10.0 ** (power / 10.0)

        # Add thermal noise floor
        interf_mw += 10.0 ** (self.noise_floor_dbm / 10.0)
        result.interference = 10.0 * np.log10(interf_mw)

        # --- SNR per transmitter ---
        snr_stack: List[np.ndarray] = []
        for label, rssi in result.rssi.items():
            snr = rssi - result.interference
            result.snr[label] = snr
            snr_stack.append(snr)

        if snr_stack:
            result.best_snr = np.maximum.reduce(snr_stack)
        else:
            result.best_snr = np.zeros(env.shape)

        return result

    # ------------------------------------------------------------------
    def coverage_stats(
        self, result: SimulationResult, sensitivity_dbm: float = -137.0
    ) -> dict:
        """Return basic coverage statistics.

        Parameters
        ----------
        result : SimulationResult
        sensitivity_dbm : float
            Minimum RSSI to consider a point covered.
        """
        total = result.best_rssi.size
        covered = int(np.sum(result.best_rssi >= sensitivity_dbm))
        return {
            "total_points": total,
            "covered_points": covered,
            "coverage_pct": round(100.0 * covered / total, 2) if total else 0.0,
            "mean_rssi_dbm": round(float(np.mean(result.best_rssi)), 2),
            "mean_snr_db": round(float(np.mean(result.best_snr)), 2),
        }
