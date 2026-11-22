"""Device helpers for the Boiler Four-Way Valve integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo


def device_info_for_cover(hass: HomeAssistant, entity_id: str) -> DeviceInfo | None:
    """Attach an entity to the cover's device, when it has one."""
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None or entity.device_id is None:
        return None
    device = dr.async_get(hass).async_get(entity.device_id)
    if device is None or not (device.identifiers or device.connections):
        return None
    info: dict[str, set[tuple[str, str]]] = {}
    if device.identifiers:
        info["identifiers"] = set(device.identifiers)
    if device.connections:
        info["connections"] = set(device.connections)
    return DeviceInfo(**info)
