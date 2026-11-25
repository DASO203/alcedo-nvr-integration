"""Alcedo NVR integration - connects the Alcedo NVR app to Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AlcedoClient
from .const import CONF_API_KEY, DOMAIN
from .coordinator import AlcedoCoordinator
from .discovery import CameraScanner
from .services import async_setup_services
from .views import async_register as async_register_views

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class AlcedoData:
    client: AlcedoClient
    coordinator: AlcedoCoordinator
    scanner: CameraScanner


type AlcedoConfigEntry = ConfigEntry[AlcedoData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions."""
    async_setup_services(hass)
    await async_register_views(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AlcedoConfigEntry) -> bool:
    """Set up from a config entry."""
    client = AlcedoClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_KEY],
    )
    coordinator = AlcedoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.archive.async_load()
    scanner = CameraScanner(hass, entry)
    entry.runtime_data = AlcedoData(client, coordinator, scanner)
    _remove_stale_devices(hass, entry, coordinator)

    entry.async_create_background_task(
        hass,
        client.listen(coordinator.handle_message, coordinator.set_connected),
        f"{DOMAIN} websocket",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    scanner.async_start()
    return True


def _remove_stale_devices(
    hass: HomeAssistant, entry: AlcedoConfigEntry, coordinator: AlcedoCoordinator
) -> None:
    """Remove devices of cameras that no longer exist in the app."""
    registry = dr.async_get(hass)
    valid = {(DOMAIN, entry.entry_id)} | {
        (DOMAIN, f"{entry.entry_id}_{cam['id']}") for cam in coordinator.data["info"]["cameras"]
    }
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & valid:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def _options_updated(hass: HomeAssistant, entry: AlcedoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AlcedoConfigEntry) -> bool:
    """Unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
