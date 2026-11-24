"""Constants for the Boiler Four-Way Valve integration."""

from __future__ import annotations

from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
)

from .mapping import DEFAULT_EMERGENCY_POSITION, DEFAULT_MAX_POSITION

DOMAIN = "boiler_four_way_valve"

PRESET_MANUAL = "manual"
ATTR_MANUAL_POSITION = "manual_position"
ATTR_CALCULATED_POSITION = "calculated_position"
ATTR_CURRENT_COMMAND = "current_command"
SENSOR_TEMPERATURE_OFFSET = "temperature_offset"
SENSOR_OUTDOOR_OFFSET = "outdoor_offset"
SENSOR_MAXIMUM_POSITION = "maximum_position"
SENSOR_INTEGRATION_VERSION = "integration_version"

CONF_TEMPERATURE_SENSOR_ENTITY_ID = "temperature_sensor_entity_id"
CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID = "outdoor_temperature_sensor_entity_id"
CONF_OUTDOOR_ADJUSTMENT_MAPPING = "outdoor_adjustment_mapping"
CONF_MAX_POSITION = "max_position"
CONF_PRECISION = "precision"
CONF_COVER_ENTITY_ID = "cover_entity_id"
CONF_ADDITIONAL_COVER_ENTITY_IDS = "additional_cover_entity_ids"
CONF_MIN_CYCLE_DURATION = "min_cycle_duration"
CONF_EMERGENCY_POSITION = "emergency_position"
CONF_MIN_TEMP_CHANGE_STEP = "min_temp_change_step"
CONF_POSITION_TOLERANCE = "position_tolerance"
CONF_POSITION_MAPPING = "position_mapping"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP_STEP = "target_temp_step"

DEFAULT_POSITION_TOLERANCE = 1
DEFAULT_MIN_TEMP_CHANGE_STEP = 0
STARTUP_SENSOR_GRACE_SECONDS = 30

CONF_PRESETS = {
    preset: f"{preset}_temp"
    for preset in (
        PRESET_AWAY,
        PRESET_COMFORT,
        PRESET_ECO,
        PRESET_HOME,
    )
}

DEFAULT_EMERGENCY = DEFAULT_EMERGENCY_POSITION
DEFAULT_MAX = DEFAULT_MAX_POSITION
