"""Path-loss models: FSPL, log-distance, Okumura-Hata."""

from __future__ import annotations

import numpy as np


def free_space_path_loss(distance_m: np.ndarray | float, freq_mhz: float) -> np.ndarray:
    """Free-Space Path Loss (Friis).

    FSPL(dB) = 20·log10(d) + 20·log10(f) + 32.44
    where *d* in km, *f* in MHz.
    """
    d_km = np.asarray(distance_m, dtype=np.float64) / 1000.0
    d_km = np.clip(d_km, 1e-6, None)
    return 20.0 * np.log10(d_km) + 20.0 * np.log10(freq_mhz) + 32.44  # type: ignore[return-value]


def log_distance_path_loss(
    distance_m: np.ndarray | float,
    freq_mhz: float,
    n: float = 2.7,
    d0: float = 1.0,
) -> np.ndarray:
    """Log-distance path-loss model.

    PL(d) = PL(d0) + 10·n·log10(d/d0)

    PL(d0) is computed via FSPL at reference distance *d0*.
    """
    pl0 = float(free_space_path_loss(d0, freq_mhz))
    d = np.asarray(distance_m, dtype=np.float64)
    d = np.clip(d, d0, None)
    return pl0 + 10.0 * n * np.log10(d / d0)  # type: ignore[return-value]


def okumura_hata(
    distance_m: np.ndarray | float,
    freq_mhz: float,
    h_bs: float = 30.0,
    h_ms: float = 1.5,
    area: str = "urban",
) -> np.ndarray:
    """Okumura-Hata path-loss model (150–1500 MHz, 1–20 km).

    Parameters
    ----------
    h_bs : float  Base-station antenna height (m).
    h_ms : float  Mobile-station antenna height (m).
    area : str    ``"urban"`` | ``"suburban"`` | ``"rural"``.
    """
    f = freq_mhz
    d_km = np.asarray(distance_m, dtype=np.float64) / 1000.0
    d_km = np.clip(d_km, 0.01, None)

    # Correction factor for mobile antenna height (medium-small city)
    a_hm = (1.1 * np.log10(f) - 0.7) * h_ms - (1.56 * np.log10(f) - 0.8)

    L_urban = (
        69.55
        + 26.16 * np.log10(f)
        - 13.82 * np.log10(h_bs)
        - a_hm
        + (44.9 - 6.55 * np.log10(h_bs)) * np.log10(d_km)
    )

    if area == "suburban":
        return L_urban - 2.0 * (np.log10(f / 28.0)) ** 2 - 5.4  # type: ignore[return-value]
    if area == "rural":
        return L_urban - 4.78 * (np.log10(f)) ** 2 + 18.33 * np.log10(f) - 40.94  # type: ignore[return-value]
    return L_urban  # type: ignore[return-value]
