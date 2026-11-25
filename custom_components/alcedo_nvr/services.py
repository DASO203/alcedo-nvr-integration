"""Actions: trigger an alarm in Alcedo from any Home Assistant sensor (e.g. Ring motion)."""

from __future__ import annotations

import asyncio
import time

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .api import AlcedoError
from .const import DOMAIN

SERVICE_TRIGGER = "trigger"
SERVICE_TIMELAPSE = "create_timelapse"
TIMELAPSE_SCHEMA = vol.Schema(
    {
        vol.Optional("hours", default=24): vol.All(vol.Coerce(float), vol.Range(1, 744)),
        vol.Optional("mode", default="clips"): vol.In(["clips", "snapshots"]),
        vol.Optional("speed", default=4): vol.All(vol.Coerce(int), vol.Range(1, 16)),
        vol.Optional("only_confirmed", default=True): cv.boolean,
        vol.Optional("entity_id"): cv.entity_ids,
    }
)
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

    async def create_timelapse(call: ServiceCall) -> ServiceResponse:
        """Build a timelapse in the app and wait for it (max. 30 minutes)."""
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise ServiceValidationError("Alcedo NVR is not loaded")
        entry = entries[0]
        body = {k: call.data[k] for k in ("hours", "mode", "speed", "only_confirmed")}
        if call.data.get("entity_id"):
            registry = er.async_get(hass)
            body["cameras"] = [
                reg.unique_id.removeprefix(f"{entry.entry_id}_").removesuffix("_camera")
                for eid in call.data["entity_id"]
                if (reg := registry.async_get(eid)) and reg.platform == DOMAIN
            ]
        client = entry.runtime_data.client
        try:
            job = await client.timelapse(body)
            deadline = time.monotonic() + 1800
            while job["state"] in ("queued", "building") and time.monotonic() < deadline:
                await asyncio.sleep(3)
                job = await client.timelapse_status(job["id"])
        except AlcedoError as err:
            raise HomeAssistantError(f"Alcedo NVR not reachable: {err}") from err
        if job["state"] not in ("done", "empty"):
            raise HomeAssistantError(f"Timelapse failed: {job.get('error') or job['state']}")
        return {
            "state": job["state"],
            "events": job.get("total", 0),
            "path": job.get("path") if job["state"] == "done" else None,
            "url": f"/api/alcedo_nvr/{entry.entry_id}/file/timelapse/{job['id']}.mp4"
            if job["state"] == "done"
            else None,
        }

    hass.services.async_register(DOMAIN, SERVICE_TRIGGER, trigger, schema=TRIGGER_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_TIMELAPSE,
        create_timelapse,
        schema=TIMELAPSE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
