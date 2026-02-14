"""Basic gateway placement optimisation."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from ..core.environment import Environment
from ..core.device import Gateway
from ..core.simulation import Simulation
from ..protocols.base import Protocol


def suggest_gateway_position(
    env: Environment,
    protocol: Protocol,
    sensitivity_dbm: float = -137.0,
    step: float | None = None,
) -> Tuple[float, float, float]:
    """Brute-force search for the gateway position that maximises coverage.

    Returns ``(best_x, best_y, coverage_pct)``.
    """
    step = step or env.resolution * 5
    best: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    for cx in np.arange(0, env.width, step):
        for cy in np.arange(0, env.height, step):
            # Temporarily add a gateway and simulate
            gw = Gateway(x=float(cx), y=float(cy), protocol=protocol, sensitivity_dbm=sensitivity_dbm)
            env_copy_gw = list(env.gateways)
            env.gateways = [gw]
            sim = Simulation(env)
            res = sim.run()
            stats = sim.coverage_stats(res, sensitivity_dbm=sensitivity_dbm)
            env.gateways = env_copy_gw

            if stats["coverage_pct"] > best[2]:
                best = (float(cx), float(cy), stats["coverage_pct"])

    return best
