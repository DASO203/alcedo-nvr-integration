"""Diagnostics with secrets redacted."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

TO_REDACT = {CONF_API_KEY, "host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AlcedoConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "push_connected": coordinator.connected,
        "pcloud": {
            "uploads": coordinator.pcloud_uploads,
            "last_error": coordinator.pcloud_last_error,
        },
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
