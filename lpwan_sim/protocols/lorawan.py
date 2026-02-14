"""LoRaWAN protocol parameters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .base import Protocol

# Sensitivity per spreading factor (dBm) for 125 kHz BW
SF_SENSITIVITY: Dict[int, float] = {
    7: -124.0,
    8: -127.0,
    9: -130.0,
    10: -133.0,
    11: -135.0,
    12: -137.0,
}


@dataclass
class LoRaWAN(Protocol):
    """LoRaWAN protocol configuration.

    Parameters
    ----------
    region : str
        ``"EU868"`` or ``"US915"``.
    spreading_factor : int
        SF7–SF12 (default SF7).
    """

    name: str = "LoRaWAN"
    region: str = "EU868"
    spreading_factor: int = 7
    bandwidth_khz: float = 125.0

    def __post_init__(self) -> None:
        if self.region == "EU868":
            self.frequency_mhz = 868.0
            self.max_tx_power_dbm = 14.0
        elif self.region == "US915":
            self.frequency_mhz = 915.0
            self.max_tx_power_dbm = 30.0

        self.sensitivity_dbm = SF_SENSITIVITY.get(self.spreading_factor, -130.0)
