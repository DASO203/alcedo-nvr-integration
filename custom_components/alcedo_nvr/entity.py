"""Base entity: one device per camera plus one hub device."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlcedoCoordinator


class AlcedoEntity(CoordinatorEntity[AlcedoCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AlcedoCoordinator, key: str, camera_id: str | None) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self.camera_id = camera_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{camera_id or 'hub'}_{key}"
        if camera_id:
            cam = coordinator.camera(camera_id) or {}
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{camera_id}")},
                name=cam.get("name", camera_id),
                manufacturer={"reolink": "Reolink", "instar": "INSTAR"}.get(
                    cam.get("type", ""), "RTSP"
                ),
                model="Camera via Alcedo NVR",
                via_device=(DOMAIN, entry_id),
            )
        else:
            info = (coordinator.data or {}).get("info", {})
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name="Alcedo NVR",
                manufacturer="Alcedo NVR",
                sw_version=info.get("version"),
            )

    @property
    def cam(self) -> dict[str, Any]:
        return self.coordinator.camera(self.camera_id or "") or {}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.camera_id is None or bool(self.cam)
