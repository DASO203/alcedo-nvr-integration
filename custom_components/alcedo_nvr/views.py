"""HTTP views used by the dashboard card and the media browser.

All views require a logged-in Home Assistant user (or a signed, time-limited
URL for <video>/<img> sources). Only a fixed set of app paths can be proxied.
"""

from __future__ import annotations

from http import HTTPStatus
import re
import time
from typing import Any

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AlcedoError
from .archive import merge_timeline
from .const import DOMAIN

CARD_URL = "/alcedo_nvr_static/alcedo-timeline-card.js"
CARD_VERSION = "0.3.0"  # bump to bust browser caches
_ID = r"[A-Za-z0-9_.-]{1,128}"
_FILE_PATHS = (
    (re.compile(rf"^events/({_ID})/(clip\.mp4|snapshot\.jpg)$"), "video"),
    (re.compile(rf"^cameras/({_ID})/snapshot\.jpg$"), "image"),
    (re.compile(rf"^cameras/({_ID})/recording/(\d{{9,11}})/(\d{{2,3}})\.mp4$"), "recording"),
    (re.compile(r"^timelapse/([0-9a-f]{12})\.mp4$"), "timelapse"),
)


def _entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry | None:
    """Return the entry ("_" = the first loaded Alcedo entry)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry_id in ("_", entry.entry_id):
            return entry
    return None


async def _proxy(request: web.Request, upstream: Any, content_type: str) -> web.StreamResponse:
    try:
        response = web.StreamResponse(
            headers={"Content-Type": content_type, "Cache-Control": "private, max-age=300"}
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


async def _from_pcloud(
    hass: HomeAssistant, request: web.Request, entry: ConfigEntry, event_id: str, kind: str
) -> web.StreamResponse:
    """Stream an archived clip / snapshot back from pCloud (local copy already deleted).

    The pCloud link is fetched server side and never shown to the browser.
    """
    archive = entry.runtime_data.coordinator.archive
    url = await archive.async_link(event_id, kind)
    if url is None:
        return web.Response(status=HTTPStatus.NOT_FOUND)
    try:
        upstream = await async_get_clientsession(hass).get(
            url, timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=120)
        )
    except (TimeoutError, aiohttp.ClientError):
        return web.Response(status=HTTPStatus.BAD_GATEWAY)
    if upstream.status != 200:
        upstream.release()
        return web.Response(status=HTTPStatus.NOT_FOUND)
    return await _proxy(request, upstream, "video/mp4" if kind == "clip" else "image/jpeg")


class AlcedoEventMediaView(HomeAssistantView):
    """/api/alcedo_nvr/<entry>/<event_id>/<clip|snapshot> (media browser, notifications)."""

    url = "/api/alcedo_nvr/{entry_id}/{event_id}/{kind}"
    name = "api:alcedo_nvr:event_media"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(
        self, request: web.Request, entry_id: str, event_id: str, kind: str
    ) -> web.StreamResponse:
        entry = _entry(self.hass, entry_id)
        if entry is None or kind not in ("clip", "snapshot") or not re.fullmatch(_ID, event_id):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        try:
            upstream = await entry.runtime_data.client.open_file(event_id, kind)
        except AlcedoError:
            return await _from_pcloud(self.hass, request, entry, event_id, kind)
        return await _proxy(request, upstream, "video/mp4" if kind == "clip" else "image/jpeg")


class AlcedoFileView(HomeAssistantView):
    """/api/alcedo_nvr/<entry>/file/<whitelisted path> (dashboard card)."""

    url = "/api/alcedo_nvr/{entry_id}/file/{path:.+}"
    name = "api:alcedo_nvr:file"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str, path: str) -> web.StreamResponse:
        entry = _entry(self.hass, entry_id)
        if entry is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        client = entry.runtime_data.client
        for pattern, kind in _FILE_PATHS:
            if not (m := pattern.match(path)):
                continue
            try:
                if kind == "recording":
                    upstream = await client.open_path(
                        f"cameras/{m[1]}/recording.mp4", {"start": m[2], "duration": m[3]}
                    )
                elif kind == "timelapse":
                    upstream = await client.open_path(f"timelapse/{m[1]}/video.mp4")
                else:
                    upstream = await client.open_path(path)
            except AlcedoError:
                if kind == "video":  # events/<id>/clip.mp4 | snapshot.jpg
                    media = "clip" if m[2] == "clip.mp4" else "snapshot"
                    return await _from_pcloud(self.hass, request, entry, m[1], media)
                return web.Response(status=HTTPStatus.NOT_FOUND)
            ctype = "image/jpeg" if path.endswith(".jpg") else "video/mp4"
            return await _proxy(request, upstream, ctype)
        return web.Response(status=HTTPStatus.NOT_FOUND)


class AlcedoTimelineView(HomeAssistantView):
    """GET /api/alcedo_nvr/<entry>/timeline?hours=24 | start=&end=."""

    url = "/api/alcedo_nvr/{entry_id}/timeline"
    name = "api:alcedo_nvr:timeline"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        entry = _entry(self.hass, entry_id)
        if entry is None:
            return self.json_message("Alcedo NVR not loaded", HTTPStatus.NOT_FOUND)
        q = request.query
        try:
            if "start" in q:
                start, end = float(q["start"]), float(q.get("end", time.time()))
            else:
                end = time.time()
                start = end - max(1.0, min(744.0, float(q.get("hours", 24)))) * 3600
            data = await entry.runtime_data.client.timeline(start, end)
            archive = entry.runtime_data.coordinator.archive
            if archive.enabled:
                await archive.async_refresh()
                merge_timeline(data, archive.between(start, end))
        except ValueError:
            return self.json_message("invalid range", HTTPStatus.BAD_REQUEST)
        except AlcedoError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        data["entry_id"] = entry.entry_id
        return self.json(data)


class AlcedoTimelapseView(HomeAssistantView):
    """POST /api/alcedo_nvr/<entry>/timelapse  ·  GET .../timelapse/<job>."""

    url = "/api/alcedo_nvr/{entry_id}/timelapse"
    extra_urls = ["/api/alcedo_nvr/{entry_id}/timelapse/{job}"]  # noqa: RUF012 - HA API
    name = "api:alcedo_nvr:timelapse"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        entry = _entry(self.hass, entry_id)
        if entry is None:
            return self.json_message("Alcedo NVR not loaded", HTTPStatus.NOT_FOUND)
        try:
            body = await request.json()
            allowed = {"hours", "start", "end", "cameras", "only_confirmed", "mode", "speed"}
            job = await entry.runtime_data.client.timelapse(
                {k: v for k, v in body.items() if k in allowed}
            )
        except ValueError:
            return self.json_message("invalid JSON", HTTPStatus.BAD_REQUEST)
        except AlcedoError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        return self.json(_public_job(job))

    async def get(self, request: web.Request, entry_id: str, job: str = "") -> web.Response:
        entry = _entry(self.hass, entry_id)
        if entry is None or not re.fullmatch(r"[0-9a-f]{12}", job):
            return self.json_message("not found", HTTPStatus.NOT_FOUND)
        try:
            return self.json(_public_job(await entry.runtime_data.client.timelapse_status(job)))
        except AlcedoError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        k: job.get(k)
        for k in ("id", "state", "progress", "total", "error", "start", "end", "mode", "speed")
    }


async def async_register(hass: HomeAssistant) -> None:
    """Register views and the dashboard card once."""
    if hass.data.get(f"{DOMAIN}_http"):
        return
    hass.data[f"{DOMAIN}_http"] = True
    for view in (AlcedoEventMediaView, AlcedoFileView, AlcedoTimelineView, AlcedoTimelapseView):
        hass.http.register_view(view(hass))
    from pathlib import Path

    from homeassistant.components.frontend import add_extra_js_url

    card = Path(__file__).parent / "frontend" / "alcedo-timeline-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
