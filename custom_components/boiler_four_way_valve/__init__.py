"""The Boiler Four-Way Valve integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .runtime import ValveRuntime

_LOGGER = logging.getLogger(__name__)
PLATFORMS: tuple[Platform, ...] = (Platform.CLIMATE, Platform.NUMBER)
_FRONTEND_PATH = f"/{DOMAIN}/frontend"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load the valve panel that sits above the built-in thermostat."""
    del config
    try:
        await _async_register_frontend(hass)
    except Exception:
        _LOGGER.exception("Unable to register the valve panel")
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the panel script and load it with the frontend."""
    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    _FRONTEND_PATH,
                    str(Path(__file__).parent / "frontend"),
                    False,
                )
            ]
        )
    except RuntimeError:
        return
    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"
    add_extra_js_url(hass, f"{_FRONTEND_PATH}/panel.js?v={version}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Boiler Four-Way Valve from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ValveRuntime()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
