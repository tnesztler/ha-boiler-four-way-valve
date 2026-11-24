"""Load one helper inside the Home Assistant image and require every entity.

Run tests/run_setup_check.sh. This file executes inside that image, which
already has Home Assistant installed. It is not part of the mapping tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import MappingProxyType

from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_SET_COVER_POSITION,
    CoverEntityFeature,
)
from homeassistant.components.frontend import (
    DATA_EXTRA_JS_URL_ES5,
    DATA_EXTRA_MODULE_URL,
    UrlManager,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers import entity_registry as er

DOMAIN = "boiler_four_way_valve"
_MISSING = (STATE_UNAVAILABLE, STATE_UNKNOWN)
_ENTITIES: tuple[tuple[str, str | None], ...] = (
    ("climate", None),
    ("number", "manual_position"),
    ("sensor", "current_command"),
    ("sensor", "calculated_position"),
    ("sensor", "temperature_offset"),
    ("sensor", "outdoor_offset"),
    ("sensor", "maximum_position"),
    ("sensor", "integration_version"),
)
_ERROR_LOGGERS = (
    "custom_components.boiler_four_way_valve",
    "homeassistant.components.sensor",
    "homeassistant.components.climate",
    "homeassistant.components.number",
    "homeassistant.config_entries",
    "homeassistant.helpers.entity_platform",
)


class _Http:
    """Accept the panel files without starting the HTTP server."""

    async def async_register_static_paths(self, configs: object) -> None:
        """Ignore the panel directory."""
        del configs


class _Errors(logging.Handler):
    """Remember setup errors that still leave the config entry loaded."""

    def __init__(self) -> None:
        """Initialize an empty list."""
        super().__init__(logging.ERROR)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store one error from the helper or the entity platforms."""
        if record.name.startswith(_ERROR_LOGGERS):
            self.lines.append(f"{record.name}: {record.getMessage()}")


async def main(component: Path) -> list[str]:
    """Set up the helper and return anything that did not come up."""
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    config = Path(tempfile.mkdtemp(prefix="ha-setup-"))
    custom = config / "custom_components"
    custom.mkdir()
    os.symlink(component, custom / DOMAIN, target_is_directory=True)

    hass = core.HomeAssistant(str(config))
    try:
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await loader.async_get_custom_components(hass)
        if not await bootstrap.async_load_base_functionality(hass):
            return ["Home Assistant registries did not load"]

        hass.http = _Http()  # type: ignore[assignment]
        hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(lambda *_args: None, [])
        hass.data[DATA_EXTRA_JS_URL_ES5] = UrlManager(lambda *_args: None, [])
        hass.config.components.update({"http", "frontend"})

        features = CoverEntityFeature.SET_POSITION
        hass.states.async_set(
            "cover.valve",
            "open",
            {"current_position": 15, "supported_features": features},
        )
        hass.states.async_set("sensor.room", "19.3", {"unit_of_measurement": "°C"})
        hass.states.async_set("sensor.outdoor", "5.0", {"unit_of_measurement": "°C"})

        async def _set_cover(call: core.ServiceCall) -> None:
            entity = call.data[ATTR_ENTITY_ID]
            if isinstance(entity, list):
                entity = entity[0]
            hass.states.async_set(
                entity,
                "open",
                {
                    "current_position": call.data[ATTR_POSITION],
                    "supported_features": features,
                },
            )

        hass.services.async_register(COVER_DOMAIN, SERVICE_SET_COVER_POSITION, _set_cover)
        hass.set_state(core.CoreState.running)

        entry = config_entries.ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Chaudière",
            data={},
            options={
                "cover_entity_id": "cover.valve",
                "temperature_sensor_entity_id": "sensor.room",
                "outdoor_temperature_sensor_entity_id": "sensor.outdoor",
            },
            source="user",
            unique_id=None,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        errors = _Errors()
        logging.getLogger().addHandler(errors)
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

        problems: list[str] = []
        if entry.state is not config_entries.ConfigEntryState.LOADED:
            problems.append(f"config entry state {entry.state}")
        problems.extend(errors.lines)

        registry = er.async_get(hass)
        for domain, suffix in _ENTITIES:
            unique_id = entry.entry_id if suffix is None else f"{entry.entry_id}_{suffix}"
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id is None:
                problems.append(f"missing {domain} {unique_id}")
                continue
            state = hass.states.get(entity_id)
            if state is None or state.state in _MISSING:
                shown = None if state is None else state.state
                problems.append(f"{entity_id} is {shown}")
                continue
            print(f"{entity_id} {state.state}")
            if suffix == "integration_version" and state.state != manifest["version"]:
                problems.append(
                    f"{entity_id} is {state.state}, manifest is {manifest['version']}"
                )
        return problems
    finally:
        await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 2:
        print("usage: setup_check.py COMPONENT_DIR", file=sys.stderr)
        raise SystemExit(2)
    found = asyncio.run(main(Path(sys.argv[1]).resolve()))
    if found:
        print("\n".join(found), file=sys.stderr)
        raise SystemExit(1)
