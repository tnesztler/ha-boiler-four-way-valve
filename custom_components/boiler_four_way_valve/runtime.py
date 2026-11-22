"""Shared state for one boiler four-way valve helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValveRuntime:
    """State shared by the climate entity and its helper entities."""

    manual_position: float = 0.0
    climate: Any = None
    number: Any = None
    tracked: Any = None
