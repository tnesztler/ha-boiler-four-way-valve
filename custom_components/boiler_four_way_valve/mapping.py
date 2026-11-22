"""Valve position mapping for a cover-driven four-way boiler valve.

0 is closed and 100 is open.

A stored position applies when the temperature difference (target − current,
rounded to 0.1 °C) is greater than that key, up to and including the next key.
At or below the lowest key, the lowest position in the map is used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CLOSED_POSITION = 0
OPEN_POSITION = 100

DEFAULT_POSITION_MAPPING: dict[str, int] = {
    "-0.2": 0,
    "-0.1": 8,
    "0.0": 14,
    "0.1": 19,
    "0.2": 28,
    "0.4": 44,
    "0.7": 50,
    "1.0": 56,
    "1.3": 67,
    "1.7": 83,
    "2.0": 100,
}

DEFAULT_EMERGENCY_POSITION = 14

# Added to the indoor position. Negative values close the valve.
# A key applies from that outdoor temperature up to the next warmer key.
DEFAULT_OUTDOOR_ADJUSTMENT: dict[str, int] = {
    "-10": 35,
    "-5": 20,
    "0": 10,
    "5": 0,
    "10": -15,
    "15": -40,
}

# 100 means the safety ceiling is off. The cover can be commanded to fully open.
DEFAULT_MAX_POSITION = 100


class InvalidPositionMapping(ValueError):
    """Position mapping is missing or outside the 0–100 cover range."""


def parse_position_mapping(raw: Mapping[Any, Any]) -> dict[float, float]:
    """Return the indoor map, or raise InvalidPositionMapping."""
    return _parse_mapping(
        raw,
        minimum=CLOSED_POSITION,
        maximum=OPEN_POSITION,
        value_label="cover position",
    )


def parse_outdoor_adjustment(raw: Mapping[Any, Any]) -> dict[float, float]:
    """Return the outdoor adjustment map, or raise InvalidPositionMapping."""
    return _parse_mapping(
        raw,
        minimum=-OPEN_POSITION,
        maximum=OPEN_POSITION,
        value_label="outdoor adjustment",
    )


def position_for_difference(
    mapping: Mapping[float, float], difference: float
) -> float:
    """Return the mapped position for a target − current difference."""
    if not mapping:
        raise InvalidPositionMapping("Position mapping is empty")

    keys = sorted(mapping)
    if difference <= keys[0]:
        return min(mapping.values())
    if difference >= keys[-1]:
        return float(mapping[keys[-1]])

    for index, key in enumerate(keys):
        if difference <= key:
            return float(mapping[keys[index - 1]])
    return max(mapping.values())


def cover_position(
    mapping: Mapping[float, float],
    *,
    current: float | None,
    target: float | None,
    emergency: float | None,
    hvac_off: bool,
) -> tuple[int, float | None]:
    """Return ``(position, rounded difference)``.

    ``hvac_off`` selects the lowest mapped position.
    A missing or non-finite temperature selects the emergency position.
    The difference is ``None`` in both of those cases.
    """
    if not mapping:
        raise InvalidPositionMapping("Position mapping is empty")

    if hvac_off:
        return to_cover_percent(min(mapping.values())), None

    if (
        current is None
        or target is None
        or not math.isfinite(current)
        or not math.isfinite(target)
    ):
        fallback = emergency if emergency is not None else min(mapping.values())
        return to_cover_percent(fallback), None

    difference = round(float(target) - float(current), 1)
    return to_cover_percent(position_for_difference(mapping, difference)), difference


def adjustment_for_outdoor(
    mapping: Mapping[float, float], outdoor: float
) -> float:
    """Return the adjustment for an outdoor temperature.

    The value of a key applies from that temperature up to, but not including,
    the next warmer key. Colder than every key uses the coldest key.
    """
    if not mapping:
        raise InvalidPositionMapping("Outdoor adjustment mapping is empty")

    keys = sorted(mapping)
    if outdoor < keys[0]:
        return float(mapping[keys[0]])

    selected = keys[0]
    for key in keys:
        if outdoor >= key:
            selected = key
        else:
            break
    return float(mapping[selected])


def limit_position(position: float, max_position: float | None) -> int:
    """Clamp to 0–100, and never above ``max_position`` when that is below 100.

    A maximum of 100, or ``None``, disables the safety ceiling.
    """
    if not math.isfinite(position):
        raise InvalidPositionMapping("Cover position is not a finite number")

    ceiling = float(OPEN_POSITION)
    if (
        max_position is not None
        and math.isfinite(max_position)
        and max_position < OPEN_POSITION
    ):
        ceiling = max(float(CLOSED_POSITION), float(max_position))

    clamped = min(ceiling, max(float(CLOSED_POSITION), float(position)))
    return to_cover_percent(clamped)


def apply_outdoor_and_limit(
    position: float,
    *,
    outdoor: float | None,
    outdoor_mapping: Mapping[float, float] | None,
    max_position: float | None,
) -> tuple[int, float | None]:
    """Add the outdoor adjustment, then apply the safety ceiling.

    Returns ``(commanded position, adjustment)``. The adjustment is ``None``
    when outdoor temperature is not used. ``off`` must not call this: a stopped
    thermostat stays on the closed position from the indoor map.
    """
    raw = float(position)
    adjustment: float | None = None
    if (
        outdoor is not None
        and math.isfinite(outdoor)
        and outdoor_mapping
    ):
        adjustment = adjustment_for_outdoor(outdoor_mapping, outdoor)
        raw += adjustment
    return limit_position(raw, max_position), adjustment


def valve_positions(
    mapping: Mapping[float, float],
    *,
    current: float | None,
    target: float | None,
    emergency: float | None,
    hvac_off: bool,
    manual: bool,
    manual_position: float,
    outdoor: float | None,
    outdoor_mapping: Mapping[float, float] | None,
    max_position: float | None,
) -> tuple[int, int, float | None, float | None]:
    """Return ``(command, calculated, difference, adjustment)``.

    ``calculated`` is the heat-map opening after the outdoor trim and the
    ceiling. ``command`` matches it, unless Manual is holding a position or
    the mode is off. Off commands the lowest mapped position. Manual and off
    still stay under the ceiling.
    """
    indoor, difference = cover_position(
        mapping,
        current=current,
        target=target,
        emergency=emergency,
        hvac_off=False,
    )
    calculated, adjustment = apply_outdoor_and_limit(
        indoor,
        outdoor=outdoor,
        outdoor_mapping=outdoor_mapping,
        max_position=max_position,
    )
    if manual and not hvac_off:
        command = limit_position(manual_position, max_position)
    elif hvac_off:
        closed, _difference = cover_position(
            mapping,
            current=current,
            target=target,
            emergency=emergency,
            hvac_off=True,
        )
        command = limit_position(closed, max_position)
    else:
        command = calculated
    return command, calculated, difference, adjustment


def to_cover_percent(position: float) -> int:
    """Clamp to 0–100 and round half up to a whole percent."""
    if not math.isfinite(position):
        raise InvalidPositionMapping("Cover position is not a finite number")
    clamped = min(float(OPEN_POSITION), max(float(CLOSED_POSITION), float(position)))
    return int(Decimal(str(clamped)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_mapping(
    raw: Mapping[Any, Any],
    *,
    minimum: float,
    maximum: float,
    value_label: str,
) -> dict[float, float]:
    if not isinstance(raw, Mapping) or len(raw) == 0:
        raise InvalidPositionMapping("Mapping is empty")

    parsed: dict[float, float] = {}
    for key, value in raw.items():
        temperature = _number(key, "temperature")
        mapped = _number(value, value_label)
        if not minimum <= mapped <= maximum:
            raise InvalidPositionMapping(
                f"{value_label} {mapped} is outside {minimum}–{maximum}"
            )
        if temperature in parsed:
            raise InvalidPositionMapping(f"Duplicate temperature {temperature}")
        parsed[temperature] = mapped
    return parsed


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidPositionMapping(f"{label} must be a number")
    try:
        number = float(value)
    except ValueError as err:
        raise InvalidPositionMapping(f"{label} must be a number") from err
    if not math.isfinite(number):
        raise InvalidPositionMapping(f"{label} must be a finite number")
    return number
