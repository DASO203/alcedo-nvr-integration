"""Switch per camera: pause / resume alarm detection (recording continues)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AlcedoError
from .coordinator import AlcedoCoordinator
from .entity import AlcedoEntity

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: AlcedoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DetectionSwitch(coordinator, cam["id"]) for cam in coordinator.data["info"]["cameras"]
    )


class DetectionSwitch(AlcedoEntity, SwitchEntity):
    def __init__(self, coordinator: AlcedoCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, "detection", camera_id)

    @property
    def is_on(self) -> bool:
        return bool(self.cam.get("detection", True))

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_detection(self.camera_id or "", enabled)
        except AlcedoError as err:
            raise HomeAssistantError(f"Alcedo NVR not reachable: {err}") from err
        self.cam["detection"] = enabled
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
