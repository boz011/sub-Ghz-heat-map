"""Wi-Fi HaLow (IEEE 802.11ah) protocol parameters."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Protocol


@dataclass
class WiFiHaLow(Protocol):
    """802.11ah (Wi-Fi HaLow) configuration.

    Parameters
    ----------
    channel_width_mhz : float
        1, 2, 4, 8, or 16 MHz.
    mcs : int
        MCS index 0–10.
    """

    name: str = "WiFi-HaLow"
    frequency_mhz: float = 900.0
    channel_width_mhz: float = 1.0
    mcs: int = 0
    max_tx_power_dbm: float = 30.0
    sensitivity_dbm: float = -130.0

    def __post_init__(self) -> None:
        self.bandwidth_khz = self.channel_width_mhz * 1000.0
        # Rough sensitivity curve: higher MCS → worse sensitivity
        base = -130.0
        self.sensitivity_dbm = base + self.mcs * 3.0  # e.g. MCS10 ≈ -100 dBm
