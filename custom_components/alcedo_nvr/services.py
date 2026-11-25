"""Actions: trigger an alarm in Alcedo from any Home Assistant sensor (e.g. Ring motion)."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .api import AlcedoError
from .const import DOMAIN

SERVICE_TRIGGER = "trigger"
TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Optional("label", default="motion"): vol.All(cv.string, vol.Length(max=32)),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def trigger(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        for entity_id in call.data["entity_id"]:
            reg = registry.async_get(entity_id)
            if reg is None or reg.platform != DOMAIN or not reg.unique_id.endswith("_camera"):
                raise ServiceValidationError(f"{entity_id} is not an Alcedo NVR camera")
            entry = hass.config_entries.async_get_entry(reg.config_entry_id or "")
            if entry is None or entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError("Alcedo NVR is not loaded")
            camera_id = reg.unique_id.removeprefix(f"{entry.entry_id}_").removesuffix("_camera")
            try:
                await entry.runtime_data.client.trigger(camera_id, call.data["label"])
            except AlcedoError as err:
                raise HomeAssistantError(f"Alcedo NVR not reachable: {err}") from err

    hass.services.async_register(DOMAIN, SERVICE_TRIGGER, trigger, schema=TRIGGER_SCHEMA)
