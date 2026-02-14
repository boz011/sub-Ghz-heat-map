"""Gateway placement optimisation."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from ..core.environment import Environment
from ..core.device import Gateway
from ..core.simulation import Simulation
from ..protocols.base import Protocol


# ------------------------------------------------------------------
# Coverage score
# ------------------------------------------------------------------

def coverage_score(
    env: Environment,
    gateways: List[Gateway],
    pathloss_model: str = "log-distance",
    pathloss_exponent: float = 2.7,
    noise_floor_dbm: float = -120.0,
    sensitivity_dbm: float = -137.0,
    w_coverage: float = 1.0,
    w_mean_snr: float = 0.1,
    w_min_snr: float = 0.05,
) -> float:
    """Compute a weighted coverage score for a set of gateways.

    Score = w_coverage * coverage_pct + w_mean_snr * mean_snr + w_min_snr * min_snr
    """
    saved_gw = list(env.gateways)
    env.gateways = list(gateways)

    # We need at least one transmitter to produce RSSI; use gateways as
    # "virtual transmitters" for coverage evaluation.
    from ..core.device import Transmitter
    virtual_txs = []
    for gw in gateways:
        virtual_txs.append(Transmitter(
            x=gw.x, y=gw.y, protocol=gw.protocol,
            tx_power_dbm=gw.protocol.max_tx_power_dbm,
            antenna_gain_dbi=gw.antenna_gain_dbi,
        ))

    saved_tx = list(env.transmitters)
    env.transmitters = virtual_txs

    sim = Simulation(env, pathloss_model=pathloss_model,
                     pathloss_exponent=pathloss_exponent,
                     noise_floor_dbm=noise_floor_dbm)
    res = sim.run()
    stats = sim.coverage_stats(res, sensitivity_dbm=sensitivity_dbm)

    cov_pct = stats["coverage_pct"]
    mean_snr = stats["mean_snr_db"]
    min_snr = float(np.min(res.best_snr))

    env.gateways = saved_gw
    env.transmitters = saved_tx

    return w_coverage * cov_pct + w_mean_snr * mean_snr + w_min_snr * min_snr


# ------------------------------------------------------------------
# Legacy brute-force (kept for backwards compat)
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Gradient-based / hill-climb placement
# ------------------------------------------------------------------

def suggest_gateway_positions(
    env: Environment,
    protocol: Protocol,
    n_gateways: int = 1,
    sensitivity_dbm: float = -137.0,
    coarse_step: float | None = None,
    fine_step: float | None = None,
    fine_radius: float | None = None,
    pathloss_model: str = "log-distance",
    pathloss_exponent: float = 2.7,
    noise_floor_dbm: float = -120.0,
    w_coverage: float = 1.0,
    w_mean_snr: float = 0.1,
    w_min_snr: float = 0.05,
) -> List[Dict]:
    """Suggest positions for *n_gateways* using coarse grid search + hill-climb refinement.

    Returns a list of dicts sorted by score (best first):
    ``[{"rank": 1, "x": ..., "y": ..., "score": ...}, ...]``
    """
    coarse_step = coarse_step or env.resolution * 5
    fine_step = fine_step or env.resolution
    fine_radius = fine_radius or coarse_step

    placed: List[Gateway] = []
    suggestions: List[Dict] = []

    score_kwargs = dict(
        pathloss_model=pathloss_model,
        pathloss_exponent=pathloss_exponent,
        noise_floor_dbm=noise_floor_dbm,
        sensitivity_dbm=sensitivity_dbm,
        w_coverage=w_coverage,
        w_mean_snr=w_mean_snr,
        w_min_snr=w_min_snr,
    )

    for gw_idx in range(n_gateways):
        # --- Coarse grid search ---
        best_pos = (0.0, 0.0)
        best_score = -np.inf

        for cx in np.arange(0, env.width, coarse_step):
            for cy in np.arange(0, env.height, coarse_step):
                candidate = Gateway(
                    x=float(cx), y=float(cy), protocol=protocol,
                    sensitivity_dbm=sensitivity_dbm,
                )
                score = coverage_score(env, placed + [candidate], **score_kwargs)
                if score > best_score:
                    best_score = score
                    best_pos = (float(cx), float(cy))

        # --- Hill-climb refinement ---
        cx, cy = best_pos
        for fx in np.arange(
            max(0, cx - fine_radius), min(env.width, cx + fine_radius), fine_step
        ):
            for fy in np.arange(
                max(0, cy - fine_radius), min(env.height, cy + fine_radius), fine_step
            ):
                candidate = Gateway(
                    x=float(fx), y=float(fy), protocol=protocol,
                    sensitivity_dbm=sensitivity_dbm,
                )
                score = coverage_score(env, placed + [candidate], **score_kwargs)
                if score > best_score:
                    best_score = score
                    best_pos = (float(fx), float(fy))

        final_gw = Gateway(
            x=best_pos[0], y=best_pos[1], protocol=protocol,
            sensitivity_dbm=sensitivity_dbm,
        )
        placed.append(final_gw)
        suggestions.append({
            "rank": gw_idx + 1,
            "x": best_pos[0],
            "y": best_pos[1],
            "score": round(best_score, 2),
        })

    return suggestions
