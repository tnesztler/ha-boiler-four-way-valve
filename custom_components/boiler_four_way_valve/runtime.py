"""Shared state for one boiler four-way valve helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValveRuntime:
    """Manual position shared by the climate entity and the number entity."""

    manual_position: float = 0.0
    climate: Any = None
    number: Any = None
