"""NB-IoT protocol parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .base import Protocol

# Centre frequency (MHz) per 3GPP band
BAND_FREQ: Dict[str, float] = {
    "B1": 2140.0,
    "B3": 1805.0,
    "B5": 869.0,
    "B8": 925.0,
    "B20": 791.0,
    "B28": 758.0,
}


@dataclass
class NBIoT(Protocol):
    """NB-IoT protocol configuration.

    Parameters
    ----------
    band : str
        3GPP band name, e.g. ``"B20"``.
    tone_mode : str
        ``"single-3.75"`` | ``"single-15"`` | ``"multi-3"`` | ``"multi-6"`` | ``"multi-12"``.
    """

    name: str = "NB-IoT"
    band: str = "B20"
    tone_mode: str = "single-15"
    max_tx_power_dbm: float = 23.0
    sensitivity_dbm: float = -141.0

    def __post_init__(self) -> None:
        self.frequency_mhz = BAND_FREQ.get(self.band, 791.0)
        bw_map = {
            "single-3.75": 3.75,
            "single-15": 15.0,
            "multi-3": 45.0,
            "multi-6": 90.0,
            "multi-12": 180.0,
        }
        self.bandwidth_khz = bw_map.get(self.tone_mode, 15.0)
