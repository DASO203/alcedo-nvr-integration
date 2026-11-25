"""Media browser: Alcedo NVR -> camera -> events (clips / snapshots)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.media_player import MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import AlcedoError
from .const import DOMAIN


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return AlcedoMediaSource(hass)


class AlcedoMediaSource(MediaSource):
    name = "Alcedo NVR"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _entries(self):
        return [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        parts = (item.identifier or "").split("/")
        if len(parts) != 4:
            raise Unresolvable("Unknown item")
        entry_id, _camera, event_id, kind = parts
        mime = "video/mp4" if kind == "clip" else "image/jpeg"
        return PlayMedia(f"/api/alcedo_nvr/{entry_id}/{event_id}/{kind}", mime)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        parts = [p for p in (item.identifier or "").split("/") if p]
        entries = self._entries()
        if not parts:
            if len(entries) == 1:
                return await self._cameras(entries[0].entry_id)
            raise Unresolvable("No Alcedo NVR configured")
        if len(parts) == 1:
            return await self._cameras(parts[0])
        return await self._events(parts[0], parts[1])

    def _root(self, identifier: str, title: str, children: list[BrowseMediaSource]):
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.DIRECTORY,
        )

    async def _cameras(self, entry_id: str) -> BrowseMediaSource:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            raise Unresolvable("Entry not loaded")
        cams = entry.runtime_data.coordinator.data["info"]["cameras"]
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/{c['id']}",
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title=c["name"],
                can_play=False,
                can_expand=True,
            )
            for c in cams
        ]
        return self._root(entry_id, "Alcedo NVR", children)

    async def _events(self, entry_id: str, camera: str) -> BrowseMediaSource:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            raise Unresolvable("Entry not loaded")
        try:
            events = await entry.runtime_data.client.events(limit=200, camera=camera)
        except AlcedoError as err:
            raise Unresolvable(str(err)) from err
        children = []
        for ev in events:
            kind = (
                "clip" if ev.get("clip_path") else "snapshot" if ev.get("snapshot_path") else None
            )
            if kind is None:
                continue
            when = datetime.fromtimestamp(ev["start"]).strftime("%d.%m.%Y %H:%M:%S")
            verdict = (ev.get("verdict") or {}).get("description") or ", ".join(ev["labels"])
            flag = "🔴" if ev.get("confirmed") else "⚪"
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry_id}/{camera}/{ev['id']}/{kind}",
                    media_class=MediaClass.VIDEO if kind == "clip" else MediaClass.IMAGE,
                    media_content_type="video/mp4" if kind == "clip" else "image/jpeg",
                    title=f"{flag} {when} – {verdict}"[:120],
                    can_play=True,
                    can_expand=False,
                    thumbnail=(
                        f"/api/alcedo_nvr/{entry_id}/{ev['id']}/snapshot"
                        if ev.get("snapshot_path")
                        else None
                    ),
                )
            )
        return self._root(f"{entry_id}/{camera}", camera, children)
