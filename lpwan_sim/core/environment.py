"""2-D grid environment for placing devices and obstacles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .device import Gateway, NoiseSource, Transmitter


# ---------------------------------------------------------------------------
# Material presets: material name → attenuation in dB
# ---------------------------------------------------------------------------
MATERIAL_ATTENUATION: Dict[str, float] = {
    "drywall": 3.0,
    "wood": 4.0,
    "glass": 2.0,
    "concrete": 12.0,
    "brick": 10.0,
    "metal": 20.0,
}


@dataclass
class Wall:
    """Simple obstacle defined by two endpoints and an attenuation factor (dB).

    .. deprecated:: Use :class:`Obstacle` for new code.  Kept for backwards
       compatibility.
    """

    x1: float
    y1: float
    x2: float
    y2: float
    attenuation_db: float = 10.0


@dataclass
class Obstacle:
    """Line-segment obstacle with material label.

    Parameters
    ----------
    start_point : Tuple[float, float]
        (x1, y1) of the segment.
    end_point : Tuple[float, float]
        (x2, y2) of the segment.
    attenuation_db : float
        Signal attenuation when crossing this obstacle (dB).
    material : str
        Human-readable material label (e.g. ``"concrete"``).
    """

    start_point: Tuple[float, float]
    end_point: Tuple[float, float]
    attenuation_db: float = 10.0
    material: str = "concrete"

    @classmethod
    def from_material(
        cls,
        start_point: Tuple[float, float],
        end_point: Tuple[float, float],
        material: str,
    ) -> "Obstacle":
        """Create an obstacle using a preset material attenuation.

        Parameters
        ----------
        start_point : Tuple[float, float]
        end_point : Tuple[float, float]
        material : str
            One of the keys in :data:`MATERIAL_ATTENUATION`.

        Raises
        ------
        ValueError
            If *material* is not a known preset.
        """
        att = MATERIAL_ATTENUATION.get(material.lower())
        if att is None:
            raise ValueError(
                f"Unknown material '{material}'. Choose from: "
                + ", ".join(sorted(MATERIAL_ATTENUATION))
            )
        return cls(
            start_point=start_point,
            end_point=end_point,
            attenuation_db=att,
            material=material.lower(),
        )


def segments_intersect(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
) -> bool:
    """Return *True* if line segment (p1→p2) intersects segment (p3→p4).

    Uses the standard cross-product orientation test.
    """

    def _cross(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True

    # Collinear / on-segment checks
    def _on_segment(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> bool:
        return min(o[0], b[0]) <= a[0] <= max(o[0], b[0]) and min(o[1], b[1]) <= a[1] <= max(o[1], b[1])

    if d1 == 0.0 and _on_segment(p3, p1, p4):
        return True
    if d2 == 0.0 and _on_segment(p3, p2, p4):
        return True
    if d3 == 0.0 and _on_segment(p1, p3, p2):
        return True
    if d4 == 0.0 and _on_segment(p1, p4, p2):
        return True
    return False


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
        self.obstacles: List[Obstacle] = []

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

    def add_obstacle(self, obstacle: Obstacle) -> None:
        """Add an :class:`Obstacle` to the environment."""
        self.obstacles.append(obstacle)

    # ------------------------------------------------------------------
    # Obstacle / intersection helpers
    # ------------------------------------------------------------------

    def obstacle_attenuation(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Cumulative attenuation (dB) from obstacles crossed on the segment (x1,y1)→(x2,y2)."""
        total = 0.0
        p1 = (x1, y1)
        p2 = (x2, y2)
        for obs in self.obstacles:
            if segments_intersect(p1, p2, obs.start_point, obs.end_point):
                total += obs.attenuation_db
        return total

    def obstacle_attenuation_grid(self, x: float, y: float) -> np.ndarray:
        """Return grid of cumulative obstacle attenuation (dB) from point (x, y) to every cell.

        .. note::
            This is O(cells × obstacles) — fine for moderate grid sizes.
        """
        att = np.zeros(self.shape, dtype=np.float64)
        if not self.obstacles:
            return att
        for i in range(att.shape[0]):
            for j in range(att.shape[1]):
                gx = float(self.grid_x[i, j])
                gy = float(self.grid_y[i, j])
                att[i, j] = self.obstacle_attenuation(x, y, gx, gy)
        return att

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def distance_grid(self, x: float, y: float) -> np.ndarray:
        """Return array of distances (m) from point (x, y) to every grid cell."""
        return np.sqrt((self.grid_x - x) ** 2 + (self.grid_y - y) ** 2).clip(min=self.resolution)

    @property
    def shape(self) -> tuple[int, int]:
        return self.grid_x.shape  # type: ignore[return-value]
