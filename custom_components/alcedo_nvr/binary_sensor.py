"""Binary sensors: alarm (LLM confirmed), recording, connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AlcedoCoordinator
from .entity import AlcedoEntity

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: AlcedoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [ConnectionSensor(coordinator)]
    for cam in coordinator.data["info"]["cameras"]:
        entities += [
            AlarmSensor(coordinator, cam["id"]),
            ActivitySensor(coordinator, cam["id"]),
            RecordingSensor(coordinator, cam["id"]),
        ]
    async_add_entities(entities)


class AlarmSensor(AlcedoEntity, BinarySensorEntity):
    """On while an event is active and the AI did not reject it."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: AlcedoCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, "alarm", camera_id)

    @property
    def is_on(self) -> bool:
        event = self.cam.get("active_event")
        return bool(event) and event.get("confirmed") is True

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        event = self.cam.get("active_event")
        if not event:
            return None
        verdict = event.get("verdict") or {}
        return {
            "event_id": event["id"],
            "labels": event.get("labels"),
            "description": verdict.get("description"),
            "confidence": verdict.get("confidence"),
        }


class ActivitySensor(AlcedoEntity, BinarySensorEntity):
    """On while any (not yet reviewed or rejected) event is active."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: AlcedoCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, "activity", camera_id)

    @property
    def is_on(self) -> bool:
        return bool(self.cam.get("active_event"))


class RecordingSensor(AlcedoEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AlcedoCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, "recording", camera_id)

    @property
    def is_on(self) -> bool:
        return bool(self.cam.get("recording"))


class ConnectionSensor(AlcedoEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AlcedoCoordinator) -> None:
        super().__init__(coordinator, "push_connection", None)

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected
