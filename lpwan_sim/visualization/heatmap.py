"""Matplotlib heatmap visualizations for RSSI, SNR, and interference."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np

from ..core.environment import Environment
from ..core.simulation import SimulationResult


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
) -> plt.Figure:  # type: ignore[name-defined]
    fig, ax = plt.subplots(figsize=figsize)
    extent = [0, env.width, 0, env.height]
    im = ax.imshow(
        data, origin="lower", extent=extent, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax
    )
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    _annotate_devices(ax, env)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig


def plot_rssi(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot best-RSSI heatmap."""
    return _base_heatmap(result.best_rssi, env, "RSSI Heatmap", "RSSI (dBm)", cmap="inferno", save_path=save_path)


def plot_snr(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot best-SNR heatmap."""
    return _base_heatmap(result.best_snr, env, "SNR Heatmap", "SNR (dB)", cmap="RdYlGn", save_path=save_path)


def plot_interference(
    result: SimulationResult,
    env: Environment,
    save_path: Optional[str | Path] = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Plot total interference heatmap."""
    return _base_heatmap(result.interference, env, "Interference Map", "Power (dBm)", cmap="hot", save_path=save_path)
