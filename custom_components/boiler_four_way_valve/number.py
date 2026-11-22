"""Manual valve position for the Boiler Four-Way Valve integration."""

from __future__ import annotations

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_COVER_ENTITY_ID, CONF_MAX_POSITION, DEFAULT_MAX, DOMAIN
from .device import device_info_for_cover
from .mapping import OPEN_POSITION
from .runtime import ValveRuntime

_SLIDER_STEP = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the manual position slider for a config entry."""
    cover_entity_id = config_entry.options.get(CONF_COVER_ENTITY_ID)
    device_info = None
    if isinstance(cover_entity_id, str) and cover_entity_id:
        device_info = device_info_for_cover(hass, cover_entity_id)
    async_add_entities(
        [
            ManualPositionNumber(
                entry_id=config_entry.entry_id,
                maximum=_slider_maximum(
                    config_entry.options.get(CONF_MAX_POSITION, DEFAULT_MAX)
                ),
                device_info=device_info,
            )
        ]
    )


def _slider_maximum(value: object) -> float:
    """Return the slider maximum, matching the safety ceiling when it is set."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return float(OPEN_POSITION)
    try:
        number = float(value)
    except ValueError:
        return float(OPEN_POSITION)
    if not math.isfinite(number) or number >= OPEN_POSITION:
        return float(OPEN_POSITION)
    return max(0.0, number)


class ManualPositionNumber(NumberEntity):
    """Position held while the climate preset is Manual."""

    _attr_has_entity_name = True
    _attr_translation_key = "manual_position"
    _attr_native_min_value = 0
    _attr_native_step = _SLIDER_STEP
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:valve"
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        maximum: float,
        device_info: DeviceInfo | None,
    ) -> None:
        """Initialize the slider."""
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_manual_position"
        self._attr_device_info = device_info
        self._attr_native_max_value = maximum
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        """Show the position stored for this helper."""
        await super().async_added_to_hass()
        runtime = self._runtime()
        runtime.number = self
        self.async_on_remove(self._detach)
        self.publish_position(runtime.manual_position)

    @callback
    def _detach(self) -> None:
        """Drop this entity from the shared runtime on unload."""
        data = self.hass.data.get(DOMAIN, {})
        runtime = data.get(self._entry_id)
        if runtime is not None and runtime.number is self:
            runtime.number = None

    def _runtime(self) -> ValveRuntime:
        """Return the shared state for this helper."""
        return self.hass.data[DOMAIN][self._entry_id]

    @callback
    def publish_position(self, position: float) -> None:
        """Show a position, clamped to the slider range."""
        self._attr_native_value = min(
            self.native_max_value,
            max(self.native_min_value, float(position)),
        )
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Hold this position. Heat mode moves the valve and selects Manual."""
        position = float(value)
        self._attr_native_value = position
        runtime = self._runtime()
        runtime.manual_position = position
        climate = runtime.climate
        if climate is not None:
            await climate.async_set_manual_position(position)
        else:
            self.async_write_ha_state()
