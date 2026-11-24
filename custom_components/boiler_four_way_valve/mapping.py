"""Valve position mapping for a cover-driven four-way boiler valve.

0 is closed and 100 is open.

A key is the opening at that exact temperature difference, or at that outdoor
temperature. Between two keys the value moves in a straight line. Outside the
keys, the nearest end of the line is kept.

The command then saves oil. Inside a deadband below the target the valve stays
where it is. At or above the target it follows the curve closed in one move.
Further below the target it may open by only a few points per cycle, and it
may close by as many points as the curve asks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CLOSED_POSITION = 0
OPEN_POSITION = 100

# Opening at each target − current difference. Shallow through the deadband,
# then a recovery slope. Between these keys the opening is a straight line.
DEFAULT_POSITION_MAPPING: dict[str, int] = {
    "-0.2": 0,
    "0.0": 8,
    "0.3": 12,
    "0.7": 28,
    "1.2": 50,
    "1.7": 75,
    "2.0": 100,
}

DEFAULT_EMERGENCY_POSITION = 14

# Room may sit this far below the target without the valve opening further.
DEFAULT_TEMPERATURE_DEADBAND = 0.3

# Largest opening added in one automatic cycle while the room is below the band.
DEFAULT_MAX_POSITION_INCREASE = 5

# Added to the indoor position. Negative values close the valve.
# Between keys the adjustment moves in a straight line.
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


def interpolate(mapping: Mapping[float, float], point: float) -> float:
    """Return the straight-line value of ``mapping`` at ``point``."""
    if not mapping:
        raise InvalidPositionMapping("Mapping is empty")

    keys = sorted(mapping)
    if point <= keys[0]:
        return float(mapping[keys[0]])
    if point >= keys[-1]:
        return float(mapping[keys[-1]])

    for index in range(1, len(keys)):
        right = keys[index]
        if point <= right:
            left = keys[index - 1]
            span = right - left
            if span == 0:
                return float(mapping[right])
            weight = (point - left) / span
            left_value = float(mapping[left])
            right_value = float(mapping[right])
            return left_value + weight * (right_value - left_value)
    return float(mapping[keys[-1]])


def position_for_difference(
    mapping: Mapping[float, float], difference: float
) -> float:
    """Return the opening on the indoor curve for target − current."""
    return interpolate(mapping, difference)


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
    """Return the outdoor adjustment on the straight line between keys."""
    return interpolate(mapping, outdoor)


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


def economy_command(
    desired: int,
    *,
    difference: float,
    previous: int | None,
    deadband: float,
    max_increase: float,
    holding: int,
) -> int:
    """Return the opening to send before the safety ceiling.

    At or above the target, move straight to ``desired``. Inside the deadband
    below the target, keep ``previous``, or ``holding`` when the valve has no
    position yet. Further below, step up by at most ``max_increase`` points
    and step down to ``desired`` in one move.
    """
    if difference <= 0:
        return desired
    if deadband > 0 and difference <= deadband:
        if previous is None:
            return holding
        return previous

    start = holding if previous is None else previous
    if desired > start:
        allowance = max(0.0, float(max_increase))
        return to_cover_percent(min(float(desired), float(start) + allowance))
    return desired


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
    previous: int | None = None,
    deadband: float = DEFAULT_TEMPERATURE_DEADBAND,
    max_increase: float = DEFAULT_MAX_POSITION_INCREASE,
) -> tuple[int, int, float | None, float | None]:
    """Return ``(command, calculated, difference, adjustment)``.

    ``calculated`` is the curve after the outdoor trim, clamped to 0–100.
    It keeps climbing past the safety ceiling so the unmet opening stays
    visible. ``command`` is what the valve is sent: the curve, then the
    deadband and the slow open, then the ceiling. Manual holds its position
    under the ceiling. Off commands the lowest mapped position.
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
        max_position=None,
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
    elif difference is None:
        command = limit_position(calculated, max_position)
    else:
        at_target, _ignored = apply_outdoor_and_limit(
            to_cover_percent(position_for_difference(mapping, 0.0)),
            outdoor=outdoor,
            outdoor_mapping=outdoor_mapping,
            max_position=None,
        )
        shaped = economy_command(
            calculated,
            difference=difference,
            previous=previous,
            deadband=deadband,
            max_increase=max_increase,
            holding=at_target,
        )
        command = limit_position(shaped, max_position)
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
