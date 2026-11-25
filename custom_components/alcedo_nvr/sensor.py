"""Sensors: last AI description, events today, storage, AI and pCloud status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AlcedoCoordinator
from .entity import AlcedoEntity

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AlcedoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[AlcedoEntity], Any]
    attrs_fn: Callable[[AlcedoEntity], dict[str, Any] | None] = lambda _: None


def _last(entity: AlcedoEntity) -> dict[str, Any]:
    return (entity.coordinator.data or {}).get("last_event", {}).get(entity.camera_id, {})


def _ts(value: float | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value else None


CAMERA_SENSORS = (
    AlcedoSensorDescription(
        key="last_event",
        value_fn=lambda e: (
            (_last(e).get("verdict") or {}).get("description")
            or ", ".join(_last(e).get("labels", []))
            or None
        ),
        attrs_fn=lambda e: (
            {
                "event_id": _last(e).get("id"),
                "confirmed": _last(e).get("confirmed"),
                "labels": _last(e).get("labels"),
                "confidence": (_last(e).get("verdict") or {}).get("confidence"),
                "snapshot_path": _last(e).get("snapshot_path"),
                "clip_path": _last(e).get("clip_path"),
            }
            if _last(e)
            else None
        ),
    ),
    AlcedoSensorDescription(
        key="last_event_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda e: _ts(_last(e).get("start")),
    ),
    AlcedoSensorDescription(
        key="events_today",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda e: e.cam.get("today", {}).get("events"),
    ),
    AlcedoSensorDescription(
        key="alarms_today",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda e: e.cam.get("today", {}).get("confirmed"),
    ),
)


def _info(e: AlcedoEntity) -> dict[str, Any]:
    return (e.coordinator.data or {}).get("info", {})


HUB_SENSORS = (
    AlcedoSensorDescription(
        key="storage_used",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda e: _info(e).get("storage", {}).get("used_percent"),
        attrs_fn=lambda e: _info(e).get("storage"),
    ),
    AlcedoSensorDescription(
        key="ai_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda e: (
            "off"
            if not _info(e).get("llm", {}).get("enabled")
            else "error"
            if _info(e).get("llm", {}).get("last_error")
            else "ok"
        ),
        attrs_fn=lambda e: _info(e).get("llm"),
    ),
    AlcedoSensorDescription(
        key="pcloud_uploads",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda e: e.coordinator.pcloud_uploads,
        attrs_fn=lambda e: {"last_error": e.coordinator.pcloud_last_error},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AlcedoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities = [AlcedoSensor(coordinator, d, None) for d in HUB_SENSORS]
    for cam in coordinator.data["info"]["cameras"]:
        entities += [AlcedoSensor(coordinator, d, cam["id"]) for d in CAMERA_SENSORS]
    async_add_entities(entities)


class AlcedoSensor(AlcedoEntity, SensorEntity):
    entity_description: AlcedoSensorDescription
    _unrecorded_attributes = frozenset({"snapshot_path", "clip_path"})

    def __init__(
        self,
        coordinator: AlcedoCoordinator,
        description: AlcedoSensorDescription,
        camera_id: str | None,
    ) -> None:
        super().__init__(coordinator, description.key, camera_id)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self)
