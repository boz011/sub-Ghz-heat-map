"""Device classes: Transmitter, Gateway, NoiseSource."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lpwan_sim.protocols.base import Protocol


@dataclass
class Transmitter:
    """IoT end-device that transmits at a given power using a protocol."""

    x: float
    y: float
    protocol: Protocol
    tx_power_dbm: float = 14.0
    label: str = ""
    antenna_gain_dbi: float = 0.0

    @property
    def eirp_dbm(self) -> float:
        return self.tx_power_dbm + self.antenna_gain_dbi


@dataclass
class Gateway:
    """Receiver/gateway with sensitivity and antenna gain."""

    x: float
    y: float
    protocol: Protocol
    sensitivity_dbm: float = -137.0
    antenna_gain_dbi: float = 3.0
    label: str = ""


@dataclass
class NoiseSource:
    """Generates interference at specific frequency/bandwidth."""

    x: float
    y: float
    power_dbm: float = 0.0
    frequency_mhz: float = 868.0
    bandwidth_khz: float = 125.0
    label: str = ""
