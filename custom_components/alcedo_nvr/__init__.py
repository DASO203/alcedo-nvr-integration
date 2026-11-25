"""Alcedo NVR integration - connects the Alcedo NVR app to Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AlcedoClient, AlcedoError
from .const import CONF_API_KEY, DOMAIN
from .coordinator import AlcedoCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class AlcedoData:
    client: AlcedoClient
    coordinator: AlcedoCoordinator


type AlcedoConfigEntry = ConfigEntry[AlcedoData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions."""
    async_setup_services(hass)
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
    entry.runtime_data = AlcedoData(client, coordinator)

    entry.async_create_background_task(
        hass,
        client.listen(coordinator.handle_message, coordinator.set_connected),
        f"{DOMAIN} websocket",
    )
    if not hass.data.get(f"{DOMAIN}_view"):
        hass.http.register_view(AlcedoMediaView(hass))
        hass.data[f"{DOMAIN}_view"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: AlcedoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AlcedoConfigEntry) -> bool:
    """Unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class AlcedoMediaView(HomeAssistantView):
    """Proxy for snapshots / clips (HA login or signed URL required)."""

    url = "/api/alcedo_nvr/{entry_id}/{event_id}/{kind}"
    name = "api:alcedo_nvr:media"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(
        self, request: web.Request, entry_id: str, event_id: str, kind: str
    ) -> web.StreamResponse:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or kind not in ("clip", "snapshot"):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        try:
            upstream = await entry.runtime_data.client.open_file(event_id, kind)
        except AlcedoError:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        try:
            response = web.StreamResponse(
                headers={"Content-Type": "video/mp4" if kind == "clip" else "image/jpeg"}
            )
            if upstream.content_length:
                response.content_length = upstream.content_length
            await response.prepare(request)
            async for chunk in upstream.content.iter_chunked(256 * 1024):
                await response.write(chunk)
            await response.write_eof()
            return response
        finally:
            upstream.release()
