"""Find cameras that already exist in Home Assistant and offer them to Alcedo.

Sources:

* **Reolink integration** - host, login and channel come from its config
  entry, so Alcedo can use the camera's own AI (person / vehicle / animal).
* **Any camera entity with an RTSP stream** (Generic camera, ONVIF, ...) -
  the stream URL Home Assistant itself uses. INSTAR and ring-mqtt streams are
  recognised by their URL.
* **ring-mqtt** - the ``stream_Source`` attribute of the camera info sensor.

Nothing is sent anywhere until the user confirms a camera. Credentials stay
in memory and are only passed to the Alcedo app (local network).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit, urlunsplit

from homeassistant.components.camera import async_get_stream_source
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    discovery_flow,
    entity_registry as er,
)
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .api import AlcedoError
from .const import AUTO, CONF_DISCOVER_CAMERAS, DOMAIN

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

_LOGGER = logging.getLogger(__name__)
_REOLINK_PATH = re.compile(r"(?i)/(h264|h265)?Preview_(\d{2})_(main|sub|ext)$")
_REOLINK_RTMP = re.compile(r"(?i)channel(\d+)_(main|sub|ext)")
_INSTAR_PATH = re.compile(r"^/(11|12|13)$")
_RING_PATH = re.compile(r"_live$")
SCAN_DELAY = 30
RESCAN = timedelta(hours=6)


@dataclass(slots=True)
class Candidate:
    """A camera in Home Assistant that Alcedo could take over."""

    key: str  # stable: reolink:<entry>:<channel> | entity:<registry id> | ring:<device>
    name: str
    origin: str  # reolink | instar | ring_mqtt | generic | <platform>
    entity_id: str | None
    camera: dict[str, Any] = field(repr=False)  # payload for the app (with credentials)

    @property
    def stream_id(self) -> str:
        return stream_id(self.camera.get("rtsp_main") or _built_main(self.camera))

    @property
    def address(self) -> str:
        """Where the camera is, without credentials (for the confirmation dialog)."""
        url = self.camera.get("rtsp_main")
        if url:
            return _strip_credentials(url)
        return self.camera.get("host", "")

    def payload(
        self, record: str = AUTO, detect: str = AUTO, objects: list[str] | None = None
    ) -> dict[str, Any]:
        cam = {**self.camera, "name": self.name, "ha_entity": self.key}
        if record != AUTO:
            cam["record"] = record
        if detect != AUTO:
            cam["detect"] = detect
        if objects:
            cam["objects"] = ", ".join(objects)
        return cam


# ------------------------------------------------------------------ helpers


def _strip_credentials(url: str) -> str:
    parts = urlsplit(url)
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _built_main(cam: dict[str, Any]) -> str:
    if cam.get("type") == "reolink" and cam.get("host"):
        return f"rtsp://{cam['host']}:554/h264Preview_{int(cam.get('channel', 0)) + 1:02d}_main"
    if cam.get("type") == "instar" and cam.get("host"):
        return f"rtsp://{cam['host']}:554/11"
    return ""


def stream_id(url: str) -> str:
    """Comparable form of a stream URL: host:port + path, main/sub folded together."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port or 554
    except ValueError:
        return ""
    if not host:
        return ""
    path = (
        parts.path.lower().replace("h264preview_", "preview_").replace("h265preview_", "preview_")
    )
    path = re.sub(r"_(main|sub|ext)$", "", path)
    path = re.sub(r"^/1[123]$", "/1x", path)
    return f"{host}:{port}{path}"


def _with_path(url: str, path: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _credentials(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url)
    return parts.hostname or "", unquote(parts.username or ""), unquote(parts.password or "")


def _device_name(hass: HomeAssistant, entry: er.RegistryEntry) -> str:
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    if device and (device.name_by_user or device.name):
        return device.name_by_user or device.name or ""
    state = hass.states.get(entry.entity_id)
    if state and (name := state.attributes.get("friendly_name")):
        return str(name)
    return entry.name or entry.original_name or entry.entity_id.split(".", 1)[1]


async def _stream_source(hass: HomeAssistant, entity_id: str) -> str | None:
    try:
        async with asyncio.timeout(10):
            return await async_get_stream_source(hass, entity_id)
    except Exception as err:
        _LOGGER.debug("No stream source for %s: %s", entity_id, err)
        return None


def classify_url(url: str) -> dict[str, Any] | None:
    """Camera payload for an RTSP URL (type guessed from the URL), or None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("rtsp", "rtsps") or not parts.hostname:
        return None
    host, user, password = _credentials(url)
    if _INSTAR_PATH.match(parts.path):
        return {
            "type": "instar",
            "host": host,
            "username": user,
            "password": password,
            "use_https": False,
            "rtsp_main": _with_path(url, "/11"),
            "rtsp_sub": _with_path(url, "/12"),
            "detect": "both",  # own motion detection works without alarm-server setup
        }
    if parts.port == 8554 and _RING_PATH.search(parts.path):
        return {"type": "ring", "rtsp_main": url, "record": "on_demand", "detect": "off"}
    cam: dict[str, Any] = {"type": "generic", "rtsp_main": url}
    if m := _REOLINK_PATH.search(parts.path):
        prefix = parts.path[: m.start()]
        codec = m[1] or ""
        cam["rtsp_main"] = _with_path(url, f"{prefix}/{codec}Preview_{m[2]}_main")
        cam["rtsp_sub"] = _with_path(url, f"{prefix}/{codec}Preview_{m[2]}_sub")
    return cam


def _reolink_channel(source: str | None) -> int | None:
    if not source:
        return None
    if m := _REOLINK_PATH.search(urlsplit(source).path):
        return int(m[2]) - 1
    if m := _REOLINK_RTMP.search(source):
        return int(m[1])
    return None


async def _reolink(hass: HomeAssistant, entry: er.RegistryEntry) -> Candidate | None:
    cfg = hass.config_entries.async_get_entry(entry.config_entry_id or "")
    if cfg is None or not cfg.data.get("host") or entry.disabled_by:
        return None
    source = await _stream_source(hass, entry.entity_id)
    channel = _reolink_channel(source)
    if channel is None:
        return None
    data = cfg.data
    cam: dict[str, Any] = {
        "type": "reolink",
        "host": data["host"],
        "port": data.get("port"),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
        "use_https": bool(data.get("use_https", True)),
        "channel": channel,
    }
    if source and urlsplit(source).scheme.lower() in ("rtsp", "rtsps"):
        # keep the exact path the camera uses (h264Preview_ / Preview_ for H.265)
        classified = classify_url(source) or {}
        cam["rtsp_main"] = classified.get("rtsp_main", "")
        cam["rtsp_sub"] = classified.get("rtsp_sub", "")
    return Candidate(
        key=f"reolink:{cfg.entry_id}:{channel}",
        name=_device_name(hass, entry),
        origin="reolink",
        entity_id=entry.entity_id,
        camera=cam,
    )


async def _other(hass: HomeAssistant, entry: er.RegistryEntry) -> Candidate | None:
    if entry.disabled_by:
        return None
    source = await _stream_source(hass, entry.entity_id)
    cam = classify_url(source or "")
    if cam is None:
        return None
    origin = {"instar": "instar", "ring": "ring_mqtt"}.get(cam["type"], entry.platform)
    return Candidate(
        key=f"entity:{entry.id}",
        name=_device_name(hass, entry),
        origin=origin,
        entity_id=entry.entity_id,
        camera=cam,
    )


def _ring_mqtt(hass: HomeAssistant) -> list[Candidate]:
    """ring-mqtt publishes the RTSP URL as attribute of the camera info sensor."""
    registry = er.async_get(hass)
    found = []
    for state in hass.states.async_all("sensor"):
        url = next(
            (
                str(v)
                for k, v in state.attributes.items()
                if re.sub(r"[^a-z]", "", k.lower()) == "streamsource"
            ),
            "",
        )
        cam = classify_url(url)
        if cam is None:
            continue
        cam.update(type="ring", record="on_demand", detect="off")
        entry = registry.async_get(state.entity_id)
        device_id = entry.device_id if entry else None
        name = state.attributes.get("friendly_name", state.entity_id)
        if entry is not None and device_id:
            name = _device_name(hass, entry)
        found.append(
            Candidate(
                key=f"ring:{device_id or state.entity_id}",
                name=str(name).removesuffix(" Info").strip(),
                origin="ring_mqtt",
                entity_id=state.entity_id,
                camera=cam,
            )
        )
    return found


async def async_find_cameras(hass: HomeAssistant) -> list[Candidate]:
    """All cameras in Home Assistant that Alcedo could record (deduplicated)."""
    registry = er.async_get(hass)
    jobs = []
    for entry in list(registry.entities.values()):
        if entry.domain != "camera" or entry.platform == DOMAIN:
            continue
        jobs.append(_reolink(hass, entry) if entry.platform == "reolink" else _other(hass, entry))
    found: dict[str, Candidate] = {}
    streams: set[str] = set()
    results = [c for c in await asyncio.gather(*jobs) if c is not None] + _ring_mqtt(hass)
    # the Reolink integration wins over a second entity (e.g. Generic) on the same stream
    results.sort(key=lambda c: c.origin != "reolink")
    for cand in results:
        if cand.key in found:
            continue
        sid = cand.stream_id
        if sid and sid in streams:  # e.g. a Generic camera on the same Reolink stream
            continue
        streams.add(sid)
        found[cand.key] = cand
    # prefer the Reolink integration entry over a second entity for the same stream
    return sorted(found.values(), key=lambda c: (c.origin != "reolink", c.name.lower()))


def not_in_alcedo(cands: list[Candidate], app_cameras: list[dict[str, Any]]) -> list[Candidate]:
    """Drop candidates Alcedo already records (taken over before or same stream)."""
    keys = {c.get("ha_entity") for c in app_cameras if c.get("ha_entity")}
    streams = {stream_id(f"rtsp://{c['stream_id']}") for c in app_cameras if c.get("stream_id")}
    hosts = {
        (c.get("host") or "").lower() for c in app_cameras if c.get("type") in ("reolink", "instar")
    }
    left = []
    for cand in cands:
        if cand.key in keys or (cand.stream_id and cand.stream_id in streams):
            continue
        host = str(cand.camera.get("host", "")).lower()
        if host and host in hosts and not cand.camera.get("channel"):
            continue
        left.append(cand)
    return left


async def async_find_new_cameras(hass: HomeAssistant, entry: AlcedoConfigEntry) -> list[Candidate]:
    app_cameras = await entry.runtime_data.client.cameras()
    return not_in_alcedo(await async_find_cameras(hass), app_cameras)


# ------------------------------------------------------------------ scanner


class CameraScanner:
    """Offers new Home Assistant cameras as "discovered" (Settings → Devices)."""

    def __init__(self, hass: HomeAssistant, entry: AlcedoConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._cancel_later: Callable[[], None] | None = None

    @callback
    def async_start(self) -> None:
        if not self.entry.options.get(CONF_DISCOVER_CAMERAS, True):
            return

        @callback
        def _started(_hass: HomeAssistant) -> None:
            self.schedule(SCAN_DELAY)

        self.entry.async_on_unload(async_at_started(self.hass, _started))
        self.entry.async_on_unload(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_updated)
        )
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, lambda _now: self.schedule(1), RESCAN)
        )
        self.entry.async_on_unload(self._cancel)

    @callback
    def _cancel(self) -> None:
        if self._cancel_later:
            self._cancel_later()
            self._cancel_later = None

    @callback
    def _registry_updated(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        if event.data["action"] == "create" and event.data["entity_id"].startswith(
            ("camera.", "sensor.")
        ):
            self.schedule(SCAN_DELAY)  # give the new integration time to load

    @callback
    def schedule(self, delay: float) -> None:
        self._cancel()

        async def _run(_now: Any) -> None:
            self._cancel_later = None
            await self.async_scan()

        self._cancel_later = async_call_later(self.hass, delay, _run)

    async def async_scan(self) -> int:
        """Start a discovery flow for every camera Alcedo does not know yet."""
        try:
            new = await async_find_new_cameras(self.hass, self.entry)
        except AlcedoError as err:
            _LOGGER.debug("Camera scan skipped, app not reachable: %s", err)
            return 0
        for cand in new:
            discovery_flow.async_create_flow(
                self.hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={"key": cand.key, "name": cand.name, "origin": cand.origin},
            )
        if new:
            _LOGGER.debug("Offered %d camera(s) to Alcedo: %s", len(new), [c.name for c in new])
        return len(new)
