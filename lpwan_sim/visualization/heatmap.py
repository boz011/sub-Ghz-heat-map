"""Matplotlib heatmap visualizations for RSSI, SNR, and interference."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

from ..core.environment import Environment
from ..core.simulation import SimulationResult


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _draw_obstacles(ax: plt.Axes, env: Environment) -> None:  # type: ignore[name-defined]
    """Draw obstacle line segments and label them with material name."""
    for obs in env.obstacles:
        x1, y1 = obs.start_point
        x2, y2 = obs.end_point
        ax.plot([x1, x2], [y1, y2], linewidth=2.5, color="white", linestyle="-")
        ax.plot([x1, x2], [y1, y2], linewidth=1.5, color="black", linestyle="--")
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.annotate(
            obs.material,
            (mx, my),
            fontsize=7,
            color="white",
            fontweight="bold",
            ha="center",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.15", fc="black", alpha=0.6),
        )


def _annotate_devices(ax: plt.Axes, env: Environment) -> None:  # type: ignore[name-defined]
    for tx in env.transmitters:
        ax.plot(tx.x, tx.y, "^", color="lime", markersize=10, markeredgecolor="black", label=tx.label or "TX")
    for gw in env.gateways:
        ax.plot(gw.x, gw.y, "s", color="cyan", markersize=12, markeredgecolor="black", label=gw.label or "GW")
    for ns in env.noise_sources:
        ax.plot(ns.x, ns.y, "x", color="red", markersize=10, markeredgewidth=3, label=ns.label or "Noise")


def _base_heatmap(
    data: np.ndarray,
    env: Environment,
    title: str,
    cbar_label: str,
    cmap: str = "viridis",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    save_path: Optional[str | Path] = None,
    figsize: tuple[int, int] = (10, 8),
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    fig, ax = plt.subplots(figsize=figsize)
    extent = [0, env.width, 0, env.height]
    im = ax.imshow(
        data, origin="lower", extent=extent, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax
    )
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    _draw_obstacles(ax, env)
    _annotate_devices(ax, env)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title(title)
    if grid_lines:
        ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def plot_rssi(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot best-RSSI heatmap."""
    return _base_heatmap(
        result.best_rssi, env, "RSSI Heatmap", "RSSI (dBm)",
        cmap="inferno", save_path=save_path, grid_lines=grid_lines,
    )


def plot_snr(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot best-SNR heatmap."""
    return _base_heatmap(
        result.best_snr, env, "SNR Heatmap", "SNR (dB)",
        cmap="RdYlGn", save_path=save_path, grid_lines=grid_lines,
    )


def plot_interference(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot total interference heatmap."""
    return _base_heatmap(
        result.interference, env, "Interference Map", "Power (dBm)",
        cmap="hot", save_path=save_path, grid_lines=grid_lines,
    )


def plot_coverage_overlay(
    result: SimulationResult,
    env: Environment,
    sensitivity_dbm: float = -137.0,
    save_path: Optional[str | Path] = None,
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    """Binary covered / not-covered map with obstacles drawn."""
    covered = (result.best_rssi >= sensitivity_dbm).astype(np.float64)
    return _base_heatmap(
        covered, env, "Coverage Overlay", "Covered",
        cmap="RdYlGn", vmin=0, vmax=1,
        save_path=save_path, grid_lines=grid_lines,
    )


def plot_comparison(
    results: Dict[str, Tuple[SimulationResult, Environment]],
    metric: str = "rssi",
    save_path: Optional[str | Path] = None,
    figsize: Optional[Tuple[int, int]] = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Side-by-side subplots comparing multiple protocols / scenarios.

    Parameters
    ----------
    results : dict
        ``{label: (SimulationResult, Environment)}``
    metric : str
        ``"rssi"`` or ``"snr"``.
    """
    n = len(results)
    if figsize is None:
        figsize = (6 * n, 5)
    fig, axes = plt.subplots(1, n, figsize=figsize)
    if n == 1:
        axes = [axes]

    cmap = "inferno" if metric == "rssi" else "RdYlGn"
    for ax, (label, (res, env)) in zip(axes, results.items()):
        data = res.best_rssi if metric == "rssi" else res.best_snr
        extent = [0, env.width, 0, env.height]
        im = ax.imshow(data, origin="lower", extent=extent, cmap=cmap, aspect="auto")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        _draw_obstacles(ax, env)
        _annotate_devices(ax, env)
        ax.set_title(label)
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")

    fig.suptitle(f"{metric.upper()} Comparison", fontsize=14)
    fig.tight_layout()
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig


def plot_placement_suggestions(
    env: Environment,
    suggestions: List[Dict],
    save_path: Optional[str | Path] = None,
    grid_lines: bool = False,
) -> plt.Figure:  # type: ignore[name-defined]
    """Show suggested gateway positions with scores on the environment.

    Parameters
    ----------
    suggestions : list of dict
        Each dict has keys ``"x"``, ``"y"``, ``"score"``, ``"rank"``.
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    extent = [0, env.width, 0, env.height]
    # Light background
    bg = np.ones(env.shape) * 0.9
    ax.imshow(bg, origin="lower", extent=extent, cmap="gray", aspect="auto", vmin=0, vmax=1)
    _draw_obstacles(ax, env)
    _annotate_devices(ax, env)

    for s in suggestions:
        ax.plot(s["x"], s["y"], "D", color="magenta", markersize=14, markeredgecolor="black")
        ax.annotate(
            f"#{s['rank']} ({s['score']:.1f})",
            (s["x"], s["y"]),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=9,
            fontweight="bold",
            color="magenta",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8),
        )

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title("Gateway Placement Suggestions")
    if grid_lines:
        ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig
