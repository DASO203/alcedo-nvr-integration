"""Coordinator: polls the app, receives push events and hands clips to pCloud Sync."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlcedoAuthError, AlcedoClient, AlcedoError
from .const import (
    CONF_PCLOUD_MODE,
    CONF_PCLOUD_SNAPSHOT,
    CONF_PCLOUD_SUBFOLDER,
    DEFAULT_PCLOUD_SUBFOLDER,
    DOMAIN,
    EVENT_ALCEDO,
    PCLOUD_ALL,
    PCLOUD_DOMAIN,
    PCLOUD_OFF,
    PCLOUD_SERVICE,
    POLL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


class AlcedoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data: {"info": <app info>, "last_event": {camera_id: event}}."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: AlcedoClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=POLL_MINUTES),
        )
        self.client = client
        self.connected = False
        self.pcloud_uploads = 0
        self.pcloud_last_error: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            info = await self.client.info()
            events = await self.client.events(limit=100)
        except AlcedoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AlcedoError as err:
            raise UpdateFailed(str(err)) from err
        last: dict[str, dict[str, Any]] = {}
        for event in events:  # newest first
            last.setdefault(event["camera"], event)
        return {"info": info, "last_event": last}

    def camera(self, camera_id: str) -> dict[str, Any] | None:
        for cam in (self.data or {}).get("info", {}).get("cameras", []):
            if cam["id"] == camera_id:
                return cam
        return None

    # ------------------------------------------------------------- push

    def set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            _LOGGER.debug("Alcedo push channel %s", "connected" if connected else "lost")
            if self.data:
                self.async_update_listeners()

    async def handle_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "hello":
            await self.async_request_refresh()
            return
        if self.data is None:
            return
        data = {**self.data, "last_event": dict(self.data["last_event"])}
        if kind in ("event_start", "event_update", "event_verdict", "event_end"):
            event = message["event"]
            cam = self.camera(event["camera"])
            if cam is not None:
                cam["active_event"] = None if kind == "event_end" else event
            data["last_event"][event["camera"]] = event
            self.hass.bus.async_fire(
                EVENT_ALCEDO, {"type": kind.removeprefix("event_"), **_event_data(event)}
            )
            if kind == "event_end":
                self.hass.async_create_task(self._to_pcloud(event))
                self.hass.async_create_task(self.async_request_refresh())
        elif kind == "camera_update":
            cam = self.camera(message["camera"])
            if cam is not None:
                for key in ("recording", "detection"):
                    if key in message:
                        cam[key] = message[key]
        self.async_set_updated_data(data)

    async def _to_pcloud(self, event: dict[str, Any]) -> None:
        """Hand finished events to the pCloud Sync integration (if configured)."""
        options = self.config_entry.options
        mode = options.get(CONF_PCLOUD_MODE, PCLOUD_OFF)
        if mode == PCLOUD_OFF or not (event.get("confirmed") or mode == PCLOUD_ALL):
            return
        if not self.hass.services.has_service(PCLOUD_DOMAIN, PCLOUD_SERVICE):
            self.pcloud_last_error = "pCloud Sync is not installed or not loaded"
            _LOGGER.warning("Event %s: %s", event["id"], self.pcloud_last_error)
            return
        paths = [event.get("clip_path")]
        if options.get(CONF_PCLOUD_SNAPSHOT, True) or not event.get("clip_path"):
            paths.append(event.get("snapshot_path"))
        subfolder = (
            f"{options.get(CONF_PCLOUD_SUBFOLDER, DEFAULT_PCLOUD_SUBFOLDER)}/{event['camera']}"
        )
        for path in filter(None, paths):
            try:
                await self.hass.services.async_call(
                    PCLOUD_DOMAIN,
                    PCLOUD_SERVICE,
                    {"path": path, "subfolder": subfolder, "delete_after_upload": False},
                    blocking=True,
                )
                self.pcloud_uploads += 1
                self.pcloud_last_error = None
            except Exception as err:
                self.pcloud_last_error = str(err)
                _LOGGER.warning("pCloud upload of %s failed: %s", path, err)
        self.async_update_listeners()


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    verdict = event.get("verdict") or {}
    return {
        "event_id": event["id"],
        "camera": event["camera"],
        "labels": event.get("labels", []),
        "confirmed": event.get("confirmed"),
        "description": verdict.get("description"),
        "confidence": verdict.get("confidence"),
        "snapshot_path": event.get("snapshot_path"),
        "clip_path": event.get("clip_path"),
        "start": event.get("start"),
        "end": event.get("end"),
    }
