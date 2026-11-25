"""Camera entities (snapshot via the app, live stream directly from the camera)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AlcedoError
from .coordinator import AlcedoCoordinator
from .entity import AlcedoEntity

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: AlcedoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        AlcedoCamera(coordinator, cam["id"]) for cam in coordinator.data["info"]["cameras"]
    )


class AlcedoCamera(AlcedoEntity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_name = None  # use the device name

    def __init__(self, coordinator: AlcedoCoordinator, camera_id: str) -> None:
        AlcedoEntity.__init__(self, coordinator, "camera", camera_id)
        Camera.__init__(self)
        self._stream_url: str | None = None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.coordinator.client.camera_snapshot(self.camera_id or "")
        except AlcedoError:
            return None

    async def stream_source(self) -> str | None:
        if self._stream_url is None:
            try:
                urls = await self.coordinator.client.camera_stream(self.camera_id or "")
            except AlcedoError:
                return None
            self._stream_url = urls.get("main")
        return self._stream_url

    @property
    def is_recording(self) -> bool:
        return bool(self.cam.get("recording"))

    @property
    def motion_detection_enabled(self) -> bool:
        return bool(self.cam.get("detection", True))
