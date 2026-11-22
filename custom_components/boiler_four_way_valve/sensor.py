"""Sensors that record the valve command and the temperature offsets."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_CALCULATED_POSITION,
    ATTR_CURRENT_COMMAND,
    CONF_COVER_ENTITY_ID,
    DOMAIN,
    SENSOR_MAXIMUM_POSITION,
    SENSOR_OUTDOOR_OFFSET,
    SENSOR_TEMPERATURE_OFFSET,
)
from .device import device_info_for_cover
from .runtime import ValveRuntime


@dataclass(frozen=True)
class _SensorKind:
    """One recorded value."""

    key: str
    unit: str | None
    device_class: SensorDeviceClass | None
    precision: int
    icon: str


_KINDS: tuple[_SensorKind, ...] = (
    _SensorKind(ATTR_CURRENT_COMMAND, PERCENTAGE, None, 0, "mdi:valve"),
    _SensorKind(
        ATTR_CALCULATED_POSITION,
        PERCENTAGE,
        None,
        0,
        "mdi:function-variant",
    ),
    _SensorKind(
        SENSOR_TEMPERATURE_OFFSET,
        None,
        SensorDeviceClass.TEMPERATURE,
        1,
        "mdi:thermometer",
    ),
    _SensorKind(
        SENSOR_OUTDOOR_OFFSET,
        PERCENTAGE,
        None,
        1,
        "mdi:sun-thermometer-outline",
    ),
    _SensorKind(
        SENSOR_MAXIMUM_POSITION,
        PERCENTAGE,
        None,
        0,
        "mdi:arrow-collapse-up",
    ),
)


class TrackedSensors:
    """Sensors updated together from the climate entity."""

    def __init__(self) -> None:
        """Initialize an empty group."""
        self._sensors: dict[str, TrackedValveSensor] = {}

    @callback
    def attach(self, key: str, sensor: TrackedValveSensor) -> None:
        """Register a sensor that is ready to publish."""
        self._sensors[key] = sensor

    @callback
    def detach(self, key: str, sensor: TrackedValveSensor) -> None:
        """Drop a sensor that is being removed."""
        if self._sensors.get(key) is sensor:
            del self._sensors[key]

    @callback
    def publish(self, values: dict[str, float | None]) -> None:
        """Store each recorded value."""
        for key, sensor in self._sensors.items():
            sensor.set_native_value(values.get(key))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the recorded valve sensors for a config entry."""
    cover_entity_id = config_entry.options.get(CONF_COVER_ENTITY_ID)
    device_info = None
    if isinstance(cover_entity_id, str) and cover_entity_id:
        device_info = device_info_for_cover(hass, cover_entity_id)
    temperature_unit = hass.config.units.temperature_unit
    runtime: ValveRuntime = hass.data[DOMAIN][config_entry.entry_id]
    runtime.tracked = TrackedSensors()
    async_add_entities(
        [
            TrackedValveSensor(
                entry_id=config_entry.entry_id,
                kind=kind,
                unit=temperature_unit if kind.unit is None else kind.unit,
                device_info=device_info,
            )
            for kind in _KINDS
        ]
    )


class TrackedValveSensor(SensorEntity):
    """One valve value recorded for history and statistics."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry_id: str,
        kind: _SensorKind,
        unit: str,
        device_info: DeviceInfo | None,
    ) -> None:
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._key = kind.key
        self._attr_unique_id = f"{entry_id}_{kind.key}"
        self._attr_translation_key = kind.key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = kind.device_class
        self._attr_suggested_display_precision = kind.precision
        self._attr_icon = kind.icon
        self._attr_device_info = device_info
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Show the latest value once the climate entity has one."""
        await super().async_added_to_hass()
        runtime = self._runtime()
        if runtime.tracked is not None:
            runtime.tracked.attach(self._key, self)
        self.async_on_remove(self._detach)
        climate = runtime.climate
        if climate is not None:
            self.set_native_value(climate.tracked_snapshot().get(self._key))

    @callback
    def _detach(self) -> None:
        """Drop this sensor from the shared group on unload."""
        data = self.hass.data.get(DOMAIN, {})
        runtime = data.get(self._entry_id)
        if runtime is not None and runtime.tracked is not None:
            runtime.tracked.detach(self._key, self)

    def _runtime(self) -> ValveRuntime:
        """Return the shared state for this helper."""
        return self.hass.data[DOMAIN][self._entry_id]

    @callback
    def set_native_value(self, value: float | None) -> None:
        """Record a new value. Missing values stay unknown."""
        new = None if value is None else float(value)
        if self._attr_native_value == new:
            return
        self._attr_native_value = new
        if self.hass is not None:
            self.async_write_ha_state()
