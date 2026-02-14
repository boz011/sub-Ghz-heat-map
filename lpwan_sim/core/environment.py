"""2-D grid environment for placing devices and obstacles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from .device import Gateway, NoiseSource, Transmitter


@dataclass
class Wall:
    """Simple obstacle defined by two endpoints and an attenuation factor (dB)."""

    x1: float
    y1: float
    x2: float
    y2: float
    attenuation_db: float = 10.0


class Environment:
    """2-D simulation area with configurable resolution.

    Parameters
    ----------
    width : float
        Width of the area in metres.
    height : float
        Height of the area in metres.
    resolution : float
        Grid cell size in metres (default 1 m).
    """

    def __init__(self, width: float, height: float, resolution: float = 1.0) -> None:
        self.width = width
        self.height = height
        self.resolution = resolution

        self.transmitters: List[Transmitter] = []
        self.gateways: List[Gateway] = []
        self.noise_sources: List[NoiseSource] = []
        self.walls: List[Wall] = []

        # Grid coordinate arrays (metres)
        self.xs: np.ndarray = np.arange(0, width, resolution)
        self.ys: np.ndarray = np.arange(0, height, resolution)
        self.grid_x: np.ndarray
        self.grid_y: np.ndarray
        self.grid_x, self.grid_y = np.meshgrid(self.xs, self.ys)

    # ------------------------------------------------------------------
    # Placement helpers
    # ------------------------------------------------------------------

    def add_transmitter(self, tx: Transmitter) -> None:
        self.transmitters.append(tx)

    def add_gateway(self, gw: Gateway) -> None:
        self.gateways.append(gw)

    def add_noise_source(self, ns: NoiseSource) -> None:
        self.noise_sources.append(ns)

    def add_wall(self, wall: Wall) -> None:
        self.walls.append(wall)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def distance_grid(self, x: float, y: float) -> np.ndarray:
        """Return array of distances (m) from point (x, y) to every grid cell."""
        return np.sqrt((self.grid_x - x) ** 2 + (self.grid_y - y) ** 2).clip(min=self.resolution)

    @property
    def shape(self) -> tuple[int, int]:
        return self.grid_x.shape  # type: ignore[return-value]
