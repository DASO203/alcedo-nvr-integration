"""pCloud archive: events that were uploaded with pCloud Sync.

Alcedo deletes local recordings after the retention time. Events that were
uploaded to pCloud stay visible in the timeline anyway, and their clips and
snapshots are streamed back from pCloud on demand.

* Every upload is remembered here (event metadata + remote path).
* The pCloud folder is listed (at most every 15 minutes, only when the
  timeline asks for a period) so uploads from before this index existed, or
  from another Home Assistant, show up too. Their camera and start time come
  from the file name ``<camera>-<YYYYMMDDTHHMMSS>-<id>.mp4``.
* Files are read through pCloud Sync's ``list_folder`` / ``get_file_link``
  actions, which only allow access below its target folder.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_PCLOUD_ARCHIVE,
    CONF_PCLOUD_SUBFOLDER,
    DEFAULT_PCLOUD_SUBFOLDER,
    DOMAIN,
    PCLOUD_LINK,
    PCLOUD_LIST,
)

_LOGGER = logging.getLogger(__name__)
_NAME = re.compile(
    r"^(?P<id>(?P<camera>[a-z0-9_]+)-(?P<ts>\d{8}T\d{6})-[0-9a-f]{4})\.(?P<ext>mp4|jpg)$"
)
LIST_INTERVAL = 900
KEEP_DAYS = 400
MAX_EVENTS = 50000


def parse_remote_name(name: str) -> tuple[str, str, float, str] | None:
    """(event_id, camera, start, "clip"|"snapshot") from an uploaded file name."""
    m = _NAME.match(name)
    if not m:
        return None
    start = datetime.strptime(m["ts"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC).timestamp()
    return m["id"], m["camera"], start, "clip" if m["ext"] == "mp4" else "snapshot"


class PcloudArchive:
    """Index of uploaded events (stored in .storage, no media)."""

    def __init__(self, hass: HomeAssistant, entry_id: str, options: dict[str, Any]) -> None:
        self.hass = hass
        self._options = options
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry_id}.archive")
        self.events: dict[str, dict[str, Any]] = {}
        self._listed = 0.0
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._options.get(CONF_PCLOUD_ARCHIVE, True)) and self.available

    @property
    def available(self) -> bool:
        return self.hass.services.has_service("pcloud_sync", PCLOUD_LINK)

    @property
    def folder(self) -> str:
        return self._options.get(CONF_PCLOUD_SUBFOLDER, DEFAULT_PCLOUD_SUBFOLDER)

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.events = data.get("events", {})

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"events": self.events}, 10)

    def _prune(self) -> None:
        cutoff = time.time() - KEEP_DAYS * 86400
        for event_id in [k for k, v in self.events.items() if v.get("start", 0) < cutoff]:
            del self.events[event_id]
        if len(self.events) > MAX_EVENTS:
            for event_id in sorted(self.events, key=lambda k: self.events[k]["start"])[
                : len(self.events) - MAX_EVENTS
            ]:
                del self.events[event_id]

    # ------------------------------------------------------------ write

    def record(self, event: dict[str, Any], kind: str, remote_path: str) -> None:
        """Remember an upload (kind = clip | snapshot)."""
        verdict = event.get("verdict") or {}
        item = self.events.setdefault(
            event["id"], {"camera": event["camera"], "start": event.get("start") or 0}
        )
        item.update(
            end=event.get("end") or event.get("start"),
            confirmed=event.get("confirmed"),
            labels=list(event.get("labels") or []),
            description=verdict.get("description"),
        )
        item[kind] = remote_path
        self._prune()
        self._save()

    # ------------------------------------------------------------ read

    async def async_refresh(self, force: bool = False) -> None:
        """Merge the file list of the pCloud folder into the index (rate limited)."""
        if not self.available or not (force or self.enabled):
            return
        if not force and time.time() - self._listed < LIST_INTERVAL:
            return
        self._listed = time.time()
        try:
            result = await self.hass.services.async_call(
                "pcloud_sync",
                PCLOUD_LIST,
                {"path": self.folder, "recursive": True},
                blocking=True,
                return_response=True,
            )
        except Exception as err:
            self.last_error = str(err)
            _LOGGER.debug("pCloud listing failed: %s", err)
            return
        self.last_error = None
        files = (result or {}).get("files", [])
        seen: set[str] = set()
        for item in files:
            if item.get("is_folder") or not (parsed := parse_remote_name(item.get("name", ""))):
                continue
            event_id, camera, start, kind = parsed
            seen.add(event_id)
            entry = self.events.setdefault(event_id, {"camera": camera, "start": start})
            entry[kind] = item["path"]
        if (result or {}).get("exists") and not (result or {}).get("truncated"):
            # files deleted in pCloud are no longer offered
            for event_id in [k for k in self.events if k not in seen]:
                del self.events[event_id]
        self._prune()
        self._save()

    def between(self, start: float, end: float) -> list[dict[str, Any]]:
        return [
            {"id": event_id, **item}
            for event_id, item in self.events.items()
            if start <= item.get("start", 0) <= end
        ]

    def get(self, event_id: str) -> dict[str, Any] | None:
        return self.events.get(event_id)

    async def async_link(self, event_id: str, kind: str) -> str | None:
        """Temporary download URL of an archived clip / snapshot."""
        item = self.events.get(event_id)
        if not item or not item.get(kind) or not self.available:
            return None
        try:
            result = await self.hass.services.async_call(
                "pcloud_sync",
                PCLOUD_LINK,
                {"path": item[kind]},
                blocking=True,
                return_response=True,
            )
        except Exception as err:
            self.last_error = str(err)
            _LOGGER.debug("pCloud link for %s failed: %s", event_id, err)
            return None
        url = (result or {}).get("url")
        return url if isinstance(url, str) and url.startswith("https://") else None


def merge_timeline(data: dict[str, Any], archived: list[dict[str, Any]]) -> None:
    """Add archived events that the app no longer has to the timeline rows."""
    rows = {cam["id"]: cam for cam in data.get("cameras", [])}
    for row in rows.values():
        local = {e["id"] for e in row.get("events", [])}
        row.setdefault("events", [])
        for item in archived:
            if item["camera"] != row["id"] or item["id"] in local:
                continue
            row["events"].append(
                {
                    "id": item["id"],
                    "start": item["start"],
                    "end": item.get("end") or item["start"],
                    "confirmed": item.get("confirmed", True),
                    "labels": item.get("labels", []),
                    "description": item.get("description"),
                    "has_clip": bool(item.get("clip")),
                    "has_snapshot": bool(item.get("snapshot")),
                    "archived": True,
                }
            )
        row["events"].sort(key=lambda e: e["start"])
