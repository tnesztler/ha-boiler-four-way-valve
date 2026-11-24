"""Config flow for the Boiler Four-Way Valve integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.climate.const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME, DEGREE, PERCENTAGE
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

from .const import (
    CONF_ADDITIONAL_COVER_ENTITY_IDS,
    CONF_COVER_ENTITY_ID,
    CONF_EMERGENCY_POSITION,
    CONF_MAX_POSITION,
    CONF_MAX_POSITION_INCREASE,
    CONF_MAX_TEMP,
    CONF_MIN_CYCLE_DURATION,
    CONF_MIN_TEMP,
    CONF_MIN_TEMP_CHANGE_STEP,
    CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID,
    CONF_POSITION_TOLERANCE,
    CONF_PRECISION,
    CONF_PRESETS,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMPERATURE_DEADBAND,
    CONF_TEMPERATURE_SENSOR_ENTITY_ID,
    DEFAULT_DEADBAND,
    DEFAULT_EMERGENCY,
    DEFAULT_INCREASE,
    DEFAULT_MAX,
    DEFAULT_MIN_TEMP_CHANGE_STEP,
    DEFAULT_POSITION_TOLERANCE,
    DOMAIN,
)

_TEMPERATURE_DOMAINS = [SENSOR_DOMAIN, NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN]

COVER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TEMPERATURE_SENSOR_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_TEMPERATURE_DOMAINS)
        ),
        vol.Optional(CONF_PRECISION, default=0.1): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=5,
                step=0.01,
                unit_of_measurement=DEGREE,
            )
        ),
        vol.Required(CONF_COVER_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=COVER_DOMAIN)
        ),
        vol.Optional(CONF_ADDITIONAL_COVER_ENTITY_IDS): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=COVER_DOMAIN, multiple=True)
        ),
        vol.Optional(
            CONF_MIN_CYCLE_DURATION, default={"minutes": 2}
        ): selector.DurationSelector(
            selector.DurationSelectorConfig(allow_negative=False)
        ),
        vol.Optional(
            CONF_TEMPERATURE_DEADBAND, default=DEFAULT_DEADBAND
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=2,
                step=0.1,
                unit_of_measurement=DEGREE,
            )
        ),
        vol.Optional(
            CONF_MAX_POSITION_INCREASE, default=DEFAULT_INCREASE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=1,
                max=100,
                step=1,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Optional(CONF_MAX_POSITION, default=DEFAULT_MAX): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=100,
                step=1,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Optional(
            CONF_EMERGENCY_POSITION, default=DEFAULT_EMERGENCY
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=100,
                step=1,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Optional(
            CONF_MIN_TEMP_CHANGE_STEP, default=DEFAULT_MIN_TEMP_CHANGE_STEP
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=5,
                step=0.01,
                unit_of_measurement=DEGREE,
            )
        ),
        vol.Optional(
            CONF_POSITION_TOLERANCE, default=DEFAULT_POSITION_TOLERANCE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                min=0,
                max=10,
                step=1,
                unit_of_measurement=PERCENTAGE,
            )
        ),
    }
)

OUTDOOR_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=_TEMPERATURE_DOMAINS)
        ),
    }
)

THERMOSTAT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=DEGREE,
                step=0.1,
            )
        ),
        vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=DEGREE,
                step=0.1,
            )
        ),
        vol.Optional(CONF_TARGET_TEMP_STEP, default=0.5): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=DEGREE,
                step=0.01,
            )
        ),
    }
)

PRESETS_SCHEMA = vol.Schema(
    {
        vol.Optional(option): selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=DEGREE,
                step=0.1,
            )
        )
        for option in CONF_PRESETS.values()
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
    }
).extend(COVER_SCHEMA.schema)


async def async_validate_cover(
    _handler: Any, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Drop the main cover from the additional-cover list."""
    main = user_input.get(CONF_COVER_ENTITY_ID)
    additional = user_input.get(CONF_ADDITIONAL_COVER_ENTITY_IDS) or []
    if isinstance(additional, str):
        additional = [additional]
    if main:
        user_input[CONF_ADDITIONAL_COVER_ENTITY_IDS] = [
            entity_id for entity_id in additional if entity_id != main
        ]
    outdoor = _handler.options.get(CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID)
    indoor = user_input.get(CONF_TEMPERATURE_SENSOR_ENTITY_ID)
    if outdoor and indoor and outdoor == indoor:
        raise SchemaFlowError("same_temperature_sensor")
    return user_input


async def async_validate_outdoor(
    _handler: Any, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Require an outdoor sensor distinct from the indoor one."""
    outdoor = user_input.get(CONF_OUTDOOR_TEMPERATURE_SENSOR_ENTITY_ID)
    indoor = _handler.options.get(CONF_TEMPERATURE_SENSOR_ENTITY_ID)
    if outdoor and indoor and outdoor == indoor:
        raise SchemaFlowError("same_temperature_sensor")
    return user_input


async def async_validate_thermostat(
    _handler: Any, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Require the minimum temperature to be below the maximum."""
    if float(user_input[CONF_MIN_TEMP]) >= float(user_input[CONF_MAX_TEMP]):
        raise SchemaFlowError("invalid_temperature_range")
    return user_input


CONFIG_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "user": SchemaFlowFormStep(
        CONFIG_SCHEMA,
        validate_user_input=async_validate_cover,
        next_step="outdoor",
    ),
    "outdoor": SchemaFlowFormStep(
        OUTDOOR_SCHEMA,
        validate_user_input=async_validate_outdoor,
        next_step="thermostat",
    ),
    "thermostat": SchemaFlowFormStep(
        THERMOSTAT_SCHEMA,
        validate_user_input=async_validate_thermostat,
        next_step="presets",
    ),
    "presets": SchemaFlowFormStep(PRESETS_SCHEMA),
}

OPTIONS_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "init": SchemaFlowMenuStep(
        options=["cover", "outdoor", "thermostat", "presets"]
    ),
    "cover": SchemaFlowFormStep(
        COVER_SCHEMA, validate_user_input=async_validate_cover
    ),
    "outdoor": SchemaFlowFormStep(
        OUTDOOR_SCHEMA, validate_user_input=async_validate_outdoor
    ),
    "thermostat": SchemaFlowFormStep(
        THERMOSTAT_SCHEMA, validate_user_input=async_validate_thermostat
    ),
    "presets": SchemaFlowFormStep(PRESETS_SCHEMA),
}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config or options flow for Boiler Four-Way Valve."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return the config entry title."""
        return cast(str, options[CONF_NAME]) if CONF_NAME in options else ""
