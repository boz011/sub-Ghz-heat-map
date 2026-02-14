"""Base protocol definition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Protocol:
    """Base class for an LPWAN protocol configuration.

    Subclasses populate sensible defaults; users can override any field.
    """

    name: str = "generic"
    frequency_mhz: float = 868.0
    bandwidth_khz: float = 125.0
    max_tx_power_dbm: float = 14.0
    sensitivity_dbm: float = -130.0

    def link_budget_db(self) -> float:
        """Maximum allowable path loss (tx power − sensitivity)."""
        return self.max_tx_power_dbm - self.sensitivity_dbm
