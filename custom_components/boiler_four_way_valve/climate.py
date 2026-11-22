"""Climate platform for the Boiler Four-Way Valve integration.

The valve is a 4-way boiler mixer driven as a cover. 0% keeps the boiler
and radiator loops separate. 100% joins them into one loop. Indoor temperature
picks a position, outdoor temperature trims it, and a safety ceiling can stop
the command from going any higher. A ceiling of 100% disables that limit.
The Manual preset holds a chosen position instead of following the maps.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import math
import time
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import ATTR_PRESET_MODE, PRESET_NONE
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    CoverEntityFeature,
    DOMAIN as COVER_DOMAIN,
    SERVICE_SET_COVER_POSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    EVENT_HOMEASSISTANT_START,
    STATE_CLOSING,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_CALCULATED_POSITION,
    ATTR_CURRENT_COMMAND,
    ATTR_MANUAL_POSITION,
    CONF_ADDITIONAL_COVER_ENTITY_IDS,
    CONF_COVER_ENTITY_ID,
    CONF_EMERGENCY_POSITION,
    CONF_MAX_POSITION,
    CONF_MAX_TEMP,
    CONF_MIN_CYCLE_DURATION,
    CONF_MIN_TEMP,
    CONF_MIN_TEMP_CHANGE_STEP,
    CONF_OUTDOOR_ADJUSTMENT_MAPPING,
    CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID,
    CONF_POSITION_MAPPING,
    CONF_POSITION_TOLERANCE,
    CONF_PRECISION,
    CONF_PRESETS,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMPERATURE_SENSOR_ENTITY_ID,
    DEFAULT_EMERGENCY,
    DEFAULT_MAX,
    DEFAULT_MIN_TEMP_CHANGE_STEP,
    DEFAULT_POSITION_TOLERANCE,
    DOMAIN,
    PRESET_MANUAL,
    SENSOR_MAXIMUM_POSITION,
    SENSOR_OUTDOOR_OFFSET,
    SENSOR_TEMPERATURE_OFFSET,
    STARTUP_SENSOR_GRACE_SECONDS,
)
from .device import device_info_for_cover
from .mapping import (
    DEFAULT_OUTDOOR_ADJUSTMENT,
    parse_outdoor_adjustment,
    parse_position_mapping,
    valve_positions,
)

_LOGGER = logging.getLogger(__name__)

_MOVING_STATES = {STATE_OPENING, STATE_CLOSING}
_RETRY_WHILE_MOVING = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a cover-driven thermostat from a config entry."""
    registry = er.async_get(hass)
    options = config_entry.options

    try:
        mapping = parse_position_mapping(options.get(CONF_POSITION_MAPPING) or {})
        outdoor_mapping = parse_outdoor_adjustment(
            options.get(CONF_OUTDOOR_ADJUSTMENT_MAPPING) or DEFAULT_OUTDOOR_ADJUSTMENT
        )
    except ValueError:
        _LOGGER.error(
            "Position mapping for %s is empty or outside its allowed range",
            config_entry.title,
        )
        return

    outdoor_sensor = options.get(CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID) or None
    if outdoor_sensor:
        outdoor_sensor = er.async_validate_entity_id(registry, outdoor_sensor)

    cover_entity_id = er.async_validate_entity_id(
        registry, options[CONF_COVER_ENTITY_ID]
    )
    additional: list[str] = []
    seen = {cover_entity_id}
    for entity_id in options.get(CONF_ADDITIONAL_COVER_ENTITY_IDS) or []:
        validated = er.async_validate_entity_id(registry, entity_id)
        if validated not in seen:
            seen.add(validated)
            additional.append(validated)

    async_add_entities(
        [
            BoilerFourWayValveClimate(
                hass=hass,
                name=config_entry.title,
                unique_id=config_entry.entry_id,
                cover_entity_id=cover_entity_id,
                additional_cover_entity_ids=additional,
                mapping=mapping,
                temp_sensor_entity_id=er.async_validate_entity_id(
                    registry, options[CONF_TEMPERATURE_SENSOR_ENTITY_ID]
                ),
                outdoor_sensor_entity_id=outdoor_sensor,
                outdoor_mapping=outdoor_mapping,
                max_position=_whole_number(
                    options.get(CONF_MAX_POSITION, DEFAULT_MAX)
                ),
                min_temp=options.get(CONF_MIN_TEMP),
                max_temp=options.get(CONF_MAX_TEMP),
                precision=options.get(CONF_PRECISION),
                min_cycle_duration=_duration(options.get(CONF_MIN_CYCLE_DURATION)),
                emergency_position=options.get(
                    CONF_EMERGENCY_POSITION, DEFAULT_EMERGENCY
                ),
                target_temp_step=options.get(CONF_TARGET_TEMP_STEP),
                min_temp_change_step=options.get(
                    CONF_MIN_TEMP_CHANGE_STEP, DEFAULT_MIN_TEMP_CHANGE_STEP
                ),
                position_tolerance=options.get(
                    CONF_POSITION_TOLERANCE, DEFAULT_POSITION_TOLERANCE
                ),
                unit=hass.config.units.temperature_unit,
                presets={
                    preset: options[option]
                    for preset, option in CONF_PRESETS.items()
                    if option in options and options[option] is not None
                },
            )
        ]
    )


def _whole_number(value: object) -> float:
    """Return a config number, as an int when it has no fractional part."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return float(DEFAULT_MAX)
    try:
        number = float(value)
    except ValueError:
        return float(DEFAULT_MAX)
    if not math.isfinite(number):
        return float(DEFAULT_MAX)
    return int(number) if number.is_integer() else number


def _duration(value: object) -> timedelta | None:
    """Return a positive duration stored by the duration selector."""
    if not isinstance(value, dict) or not value:
        return None
    try:
        duration = timedelta(
            **{str(key): float(amount) for key, amount in value.items()}
        )
    except (TypeError, ValueError):
        _LOGGER.error("Invalid minimum cycle duration: %s", value)
        return None
    if duration.total_seconds() <= 0:
        return None
    return duration


class BoilerFourWayValveClimate(ClimateEntity, RestoreEntity):
    """Climate entity that drives a four-way boiler valve through a cover position."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        unique_id: str,
        cover_entity_id: str,
        additional_cover_entity_ids: list[str],
        mapping: dict[float, float],
        temp_sensor_entity_id: str,
        outdoor_sensor_entity_id: str | None,
        outdoor_mapping: dict[float, float],
        max_position: float,
        min_temp: float | None,
        max_temp: float | None,
        precision: float | None,
        min_cycle_duration: timedelta | None,
        emergency_position: float | None,
        target_temp_step: float | None,
        min_temp_change_step: float,
        position_tolerance: float,
        unit: UnitOfTemperature,
        presets: dict[str, float],
    ) -> None:
        """Initialize the climate entity."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_temperature_unit = unit
        self._attr_device_info = device_info_for_cover(hass, cover_entity_id)
        self._attr_translation_key = "boiler_four_way_valve"

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_preset_modes = [PRESET_NONE, PRESET_MANUAL, *presets]
        self._attr_preset_mode = PRESET_NONE

        if min_temp is not None:
            self._attr_min_temp = min_temp
        if max_temp is not None:
            self._attr_max_temp = max_temp
        if precision is not None:
            self._attr_precision = precision
        self._attr_target_temperature_step = (
            target_temp_step if target_temp_step is not None else precision
        )

        self._cover_entity_id = cover_entity_id
        self._additional_cover_entity_ids = additional_cover_entity_ids
        self._cover_entity_ids = [cover_entity_id, *additional_cover_entity_ids]
        self._temp_sensor_entity_id = temp_sensor_entity_id
        self._outdoor_sensor_entity_id = outdoor_sensor_entity_id
        self._outdoor_mapping = outdoor_mapping
        self._max_position = max_position
        self._mapping = mapping
        self._min_position = min(mapping.values())
        self._min_cycle_duration = min_cycle_duration
        self._emergency_position = emergency_position
        self._min_temp_change_step = min_temp_change_step
        self._position_tolerance = position_tolerance
        self._presets = presets
        self._presets_inv = {
            temperature: preset for preset, temperature in presets.items()
        }

        self._target_temp: float | None = None
        self._saved_target_temp: float | None = None
        self._current_temp: float | None = None
        self._outdoor_temp: float | None = None
        self._last_outdoor_adjustment: float | None = None
        self._last_outdoor_at_update: float | None = None
        self._hvac_mode: HVACMode | None = None
        self._commanded_position: int | None = None
        self._calculated_position: int | None = None
        self._next_command: int | None = None
        self._manual_position = 0.0
        self._last_difference: float | None = None
        self._last_update_temp: float | None = None
        self._last_command_at: float | None = None
        self._pending_update: asyncio.Task[None] | None = None
        self._logged_cover_unavailable = False
        self._logged_outdoor_unavailable = False

    async def async_added_to_hass(self) -> None:
        """Restore state, then subscribe to the sensor and the covers."""
        await super().async_added_to_hass()

        temperature_sensors = [self._temp_sensor_entity_id]
        if self._outdoor_sensor_entity_id:
            temperature_sensors.append(self._outdoor_sensor_entity_id)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                temperature_sensors,
                self._async_sensor_changed,
            )
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._cover_entity_ids, self._async_cover_changed
            )
        )

        await self._async_restore()
        self._publish_manual_position()
        self._read_current_temperature()
        self._read_outdoor_temperature()

        if self.hass.state is CoreState.running:
            self.hass.async_create_task(self._async_startup(), eager_start=True)
        else:
            self.async_on_remove(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_START, self._async_startup_event
                )
            )
        self.async_write_ha_state()
        self._publish_tracked()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel a cover move that is waiting out the cycle time."""
        self._cancel_pending()
        await super().async_will_remove_from_hass()

    @callback
    def _async_startup_event(self, _event: Event) -> None:
        """Start control after Home Assistant has finished starting."""
        self.hass.async_create_task(self._async_startup(), eager_start=True)

    async def _async_startup(self) -> None:
        """Move the cover to the restored setpoint once temperatures exist."""
        self._read_current_temperature()
        self._read_outdoor_temperature()
        if self._hvac_mode == HVACMode.OFF or self._manual_active:
            await self._async_control_heating(force=True)
        elif self._current_temp is None:
            _LOGGER.debug(
                "Temperature sensor %s is not ready; waiting %s s before moving %s",
                self._temp_sensor_entity_id,
                STARTUP_SENSOR_GRACE_SECONDS,
                self._cover_entity_id,
            )
            self._schedule_deferred(STARTUP_SENSOR_GRACE_SECONDS)
        else:
            await self._async_control_heating(force=True)
        self.async_write_ha_state()

    async def _async_restore(self) -> None:
        """Restore the target, mode, and preset from the previous run."""
        last_state = await self.async_get_last_state()
        if last_state is not None:
            raw_temperature = last_state.attributes.get(ATTR_TEMPERATURE)
            if raw_temperature is not None:
                self._target_temp = float(raw_temperature)
                self._saved_target_temp = self._target_temp

            if last_state.state not in (None, STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
                try:
                    self._hvac_mode = HVACMode(last_state.state)
                except ValueError:
                    self._hvac_mode = HVACMode.OFF

            preset = last_state.attributes.get(ATTR_PRESET_MODE)
            if preset in (self.preset_modes or []):
                self._attr_preset_mode = preset
                if preset != PRESET_NONE and preset in self._presets:
                    self._target_temp = self._presets[preset]

            raw_position = last_state.attributes.get(ATTR_MANUAL_POSITION)
            if (
                not isinstance(raw_position, bool)
                and isinstance(raw_position, (int, float))
                and math.isfinite(float(raw_position))
            ):
                self._manual_position = float(raw_position)

        if self._target_temp is None:
            self._target_temp = self.min_temp
            self._saved_target_temp = self._target_temp
        if self._hvac_mode not in self.hvac_modes:
            self._hvac_mode = HVACMode.OFF

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Recalculate when the indoor or outdoor temperature changes."""
        new_state = event.data["new_state"]
        if event.data["entity_id"] == self._outdoor_sensor_entity_id:
            self._apply_outdoor_state(new_state)
        elif new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "Indoor temperature sensor %s is %s; using the emergency position",
                self._temp_sensor_entity_id,
                new_state.state if new_state else "removed",
            )
            self._current_temp = None
        else:
            self._read_temperature_state(new_state)

        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_cover_changed(self, event: Event[EventStateChangedData]) -> None:
        """Publish the heating action when a cover reports a new position."""
        if event.data["new_state"] is None:
            return
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True when the main cover entity is loaded."""
        state = self.hass.states.get(self._cover_entity_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        return self._hvac_mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode and move the cover immediately."""
        if hvac_mode not in self.hvac_modes:
            raise ValueError(
                f"Unsupported HVAC mode {hvac_mode}. Expected one of {self.hvac_modes}"
            )
        self._hvac_mode = hvac_mode
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    @property
    def hvac_action(self) -> HVACAction:
        """Return heating while any cover is open past the closed position."""
        if self._is_heating():
            return HVACAction.HEATING
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def native_current_temperature(self) -> float | None:
        """Return the room temperature."""
        return self._current_temp

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._target_temp

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature and move the cover immediately."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            return
        target = float(temperature)
        if not self.min_temp <= target <= self.max_temp:
            raise ValueError(
                f"Temperature {target} is outside {self.min_temp}–{self.max_temp}"
            )

        preset = self._presets_inv.get(target, PRESET_NONE)
        if self._attr_preset_mode == PRESET_NONE and preset == PRESET_NONE:
            self._saved_target_temp = target
        self._attr_preset_mode = preset
        self._target_temp = target
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Apply a preset temperature, or restore the previous target."""
        if preset_mode not in (self.preset_modes or []):
            raise ValueError(
                f"Unsupported preset {preset_mode}. Expected one of {self.preset_modes}"
            )
        if preset_mode == self._attr_preset_mode:
            return

        if preset_mode == PRESET_MANUAL:
            if self._attr_preset_mode == PRESET_NONE:
                self._saved_target_temp = self._target_temp
            self._attr_preset_mode = PRESET_MANUAL
        elif preset_mode == PRESET_NONE:
            self._attr_preset_mode = PRESET_NONE
            self._target_temp = self._saved_target_temp
        else:
            if self._attr_preset_mode == PRESET_NONE:
                self._saved_target_temp = self._target_temp
            self._attr_preset_mode = preset_mode
            self._target_temp = self._presets[preset_mode]

        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, int | float]:
        """Return the command, the map opening, and the temperature difference."""
        attributes: dict[str, int | float] = {}
        command = self._commanded_position
        if command is None:
            command = self._next_command
        if command is not None:
            attributes[ATTR_CURRENT_COMMAND] = command
            attributes["valve_position"] = command
        if self._calculated_position is not None:
            attributes[ATTR_CALCULATED_POSITION] = self._calculated_position
        reported = self._reported_position(self._cover_entity_id)
        if reported is not None:
            attributes["cover_position"] = reported
        if self._last_difference is not None:
            attributes["temperature_difference"] = self._last_difference
        if self._outdoor_temp is not None:
            attributes["outdoor_temperature"] = self._outdoor_temp
        if self._last_outdoor_adjustment is not None:
            attributes["outdoor_adjustment"] = self._last_outdoor_adjustment
        attributes[ATTR_MANUAL_POSITION] = self._manual_position
        attributes["max_position"] = self._max_position
        return attributes

    async def async_set_manual_position(self, position: float) -> None:
        """Hold this position and stop following the temperature maps.

        ``off`` still keeps the valve closed. The position is applied when the
        mode is switched back to heat.
        """
        self._manual_position = float(position)
        if self._attr_preset_mode == PRESET_NONE:
            self._saved_target_temp = self._target_temp
        self._attr_preset_mode = PRESET_MANUAL
        if self._hvac_mode != HVACMode.OFF:
            await self._async_control_heating(force=True)
        self.async_write_ha_state()

    @property
    def _manual_active(self) -> bool:
        """Return True while the Manual preset is selected."""
        return self._attr_preset_mode == PRESET_MANUAL

    def _publish_manual_position(self) -> None:
        """Share the restored override with the position slider."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self._attr_unique_id)
        if runtime is None:
            return
        runtime.climate = self
        runtime.manual_position = self._manual_position
        self.async_on_remove(self._detach_runtime)
        if runtime.number is not None:
            runtime.number.publish_position(self._manual_position)

    @callback
    def _detach_runtime(self) -> None:
        """Drop this entity from the shared runtime on unload."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self._attr_unique_id)
        if runtime is not None and runtime.climate is self:
            runtime.climate = None

    async def _async_control_heating(self, force: bool = False) -> None:
        """Command every cover from the current temperature difference."""
        if not self.available:
            if not self._logged_cover_unavailable:
                _LOGGER.warning(
                    "Cover %s is unavailable; the valve position was not changed",
                    self._cover_entity_id,
                )
                self._logged_cover_unavailable = True
            return
        self._logged_cover_unavailable = False
        if force:
            self._cancel_pending()

        self._store_calculated_position()

        sensor_failed = self._current_temp is None
        if not force and (self._hvac_mode == HVACMode.OFF or self._manual_active):
            return

        if not force and self._covers_moving():
            self._schedule_deferred(_RETRY_WHILE_MOVING)
            return

        if not force and not sensor_failed:
            remaining = self._cycle_remaining()
            if remaining > 0:
                _LOGGER.debug(
                    "Cover move deferred for %.1f s (minimum cycle)", remaining
                )
                self._schedule_deferred(remaining)
                return
            if not self._temperature_changed_enough():
                return

        position = self._next_command or 0
        self._commanded_position = position
        self._publish_tracked()

        if self._covers_within_tolerance(position):
            self._cancel_pending()
            self._remember_temperatures()
            return

        self._last_command_at = time.monotonic()
        await self._async_set_cover_positions(position)
        self._remember_temperatures()

    async def _async_set_cover_positions(self, position: int) -> None:
        """Set each cover that is not already at this position."""
        targets = [
            entity_id
            for entity_id in self._cover_entity_ids
            if not self._within_tolerance(entity_id, position)
        ]
        if not targets:
            return

        _LOGGER.debug("Setting valve position to %s%%", position)
        await asyncio.gather(
            *(self._async_set_one_cover(entity_id, position) for entity_id in targets)
        )

    async def _async_set_one_cover(self, entity_id: str, position: int) -> None:
        """Send one cover to an integer position from 0 (closed) to 100 (open)."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            _LOGGER.warning(
                "Cover %s is unavailable; position %s was not sent",
                entity_id,
                position,
            )
            return
        if not _supports_set_position(state):
            _LOGGER.error(
                "Cover %s does not support setting a position. "
                "Use a Shelly 2PM Gen4 cover that exposes position",
                entity_id,
            )
            return

        try:
            await self.hass.services.async_call(
                COVER_DOMAIN,
                SERVICE_SET_COVER_POSITION,
                {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: position},
                blocking=True,
            )
        except Exception:
            _LOGGER.exception("Failed to set %s to %s%%", entity_id, position)

    def _covers_within_tolerance(self, position: int) -> bool:
        """Return True when every cover is already close enough to position."""
        return all(
            self._within_tolerance(entity_id, position)
            for entity_id in self._cover_entity_ids
        )

    def _within_tolerance(self, entity_id: str, position: int) -> bool:
        """Return True when this cover does not need another move."""
        reported = self._reported_position(entity_id)
        if reported is None:
            return False
        return abs(reported - position) <= self._position_tolerance

    def _covers_moving(self) -> bool:
        """Return True when any cover is opening or closing."""
        return any(
            (state := self.hass.states.get(entity_id)) is not None
            and state.state in _MOVING_STATES
            for entity_id in self._cover_entity_ids
        )

    def _cycle_remaining(self) -> float:
        """Return the seconds left in the minimum cycle, or 0."""
        if self._min_cycle_duration is None or self._last_command_at is None:
            return 0.0
        elapsed = time.monotonic() - self._last_command_at
        return max(0.0, self._min_cycle_duration.total_seconds() - elapsed)

    def _temperature_changed_enough(self) -> bool:
        """Return True when indoor or outdoor temperature has moved enough."""
        if self._outdoor_temp != self._last_outdoor_at_update:
            return True
        if self._min_temp_change_step <= 0:
            return True
        if self._current_temp is None or self._last_update_temp is None:
            return True
        delta = abs(self._current_temp - self._last_update_temp)
        return delta >= self._min_temp_change_step

    def _store_calculated_position(self) -> None:
        """Store the map opening and the position that would be commanded."""
        command, calculated, difference, adjustment = valve_positions(
            self._mapping,
            current=self._current_temp,
            target=self._target_temp,
            emergency=self._emergency_position,
            hvac_off=self._hvac_mode == HVACMode.OFF,
            manual=self._manual_active,
            manual_position=self._manual_position,
            outdoor=self._outdoor_temp,
            outdoor_mapping=self._outdoor_mapping,
            max_position=self._max_position,
        )
        self._next_command = command
        self._calculated_position = calculated
        self._last_difference = difference
        self._last_outdoor_adjustment = adjustment
        self._publish_tracked()

    def tracked_snapshot(self) -> dict[str, float | None]:
        """Return the values recorded by the history sensors."""
        command = self._commanded_position
        if command is None:
            command = self._next_command
        calculated = self._calculated_position
        return {
            ATTR_CURRENT_COMMAND: None if command is None else float(command),
            ATTR_CALCULATED_POSITION: (
                None if calculated is None else float(calculated)
            ),
            SENSOR_TEMPERATURE_OFFSET: self._last_difference,
            SENSOR_OUTDOOR_OFFSET: self._last_outdoor_adjustment,
            SENSOR_MAXIMUM_POSITION: float(self._max_position),
        }

    def _publish_tracked(self) -> None:
        """Push the recorded values to their sensors."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self._attr_unique_id)
        tracked = None if runtime is None else runtime.tracked
        if tracked is not None:
            tracked.publish(self.tracked_snapshot())

    def _remember_temperatures(self) -> None:
        """Store the temperatures that produced the latest command."""
        self._last_update_temp = self._current_temp
        self._last_outdoor_at_update = self._outdoor_temp

    def _is_heating(self) -> bool:
        """Return True when a cover is open above the closed position."""
        for entity_id in self._cover_entity_ids:
            reported = self._reported_position(entity_id)
            if reported is not None and reported > self._min_position:
                return True
        return False

    def _reported_position(self, entity_id: str) -> float | None:
        """Return the cover's current position, if it is a number."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        raw = state.attributes.get(ATTR_CURRENT_POSITION)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        if not math.isfinite(raw):
            return None
        return float(raw)

    def _read_current_temperature(self) -> None:
        """Read the indoor temperature sensor's current state."""
        state = self.hass.states.get(self._temp_sensor_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._current_temp = None
            return
        self._read_temperature_state(state)

    def _read_outdoor_temperature(self) -> None:
        """Read the outdoor sensor, if one is configured."""
        if not self._outdoor_sensor_entity_id:
            self._outdoor_temp = None
            return
        self._apply_outdoor_state(self.hass.states.get(self._outdoor_sensor_entity_id))

    def _apply_outdoor_state(self, state: State | None) -> None:
        """Store the outdoor temperature, or forget it when the sensor is down."""
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            if not self._logged_outdoor_unavailable:
                _LOGGER.warning(
                    "Outdoor temperature sensor %s is %s; "
                    "the valve follows the indoor map only",
                    self._outdoor_sensor_entity_id,
                    state.state if state else "missing",
                )
                self._logged_outdoor_unavailable = True
            self._outdoor_temp = None
            return

        try:
            temperature = float(state.state)
        except (TypeError, ValueError):
            temperature = math.nan
        if not math.isfinite(temperature):
            if not self._logged_outdoor_unavailable:
                _LOGGER.warning(
                    "Outdoor temperature sensor %s has a non-numeric state: %s",
                    self._outdoor_sensor_entity_id,
                    state.state,
                )
                self._logged_outdoor_unavailable = True
            self._outdoor_temp = None
            return

        self._logged_outdoor_unavailable = False
        self._outdoor_temp = temperature

    def _read_temperature_state(self, state: State) -> None:
        """Store a numeric sensor state."""
        try:
            temperature = float(state.state)
        except (TypeError, ValueError):
            temperature = math.nan
        if not math.isfinite(temperature):
            _LOGGER.warning(
                "Temperature sensor %s has a non-numeric state: %s",
                self._temp_sensor_entity_id,
                state.state,
            )
            self._current_temp = None
            return
        self._current_temp = temperature

    def _schedule_deferred(self, delay: float) -> None:
        """Run one later control pass. A pass that is already waiting is kept."""
        if self._pending_update and not self._pending_update.done():
            return
        self._pending_update = self.hass.async_create_task(
            self._execute_deferred(delay), eager_start=True
        )

    def _cancel_pending(self) -> None:
        """Cancel a deferred cover move that is not the task running now."""
        task = self._pending_update
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def _execute_deferred(self, delay: float) -> None:
        """Wait, then apply the position that is current at that time."""
        try:
            await asyncio.sleep(delay)
            await self._async_control_heating()
            self.async_write_ha_state()
        except asyncio.CancelledError:
            raise
        finally:
            if self._pending_update is asyncio.current_task():
                self._pending_update = None


def _supports_set_position(state: State) -> bool:
    """Return True when position can be set, or features are not known yet."""
    features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
    if not features:
        return True
    if isinstance(features, (list, set, tuple, frozenset)):
        return (
            SERVICE_SET_COVER_POSITION in features
            or CoverEntityFeature.SET_POSITION in features
        )
    try:
        return bool(int(features) & CoverEntityFeature.SET_POSITION)
    except (TypeError, ValueError):
        return True
