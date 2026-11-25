"""Constants for the Alcedo NVR integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "alcedo_nvr"
DEFAULT_PORT: Final = 8765

CONF_API_KEY: Final = "api_key"
CONF_PCLOUD_MODE: Final = "pcloud_mode"
CONF_PCLOUD_SUBFOLDER: Final = "pcloud_subfolder"
CONF_PCLOUD_SNAPSHOT: Final = "pcloud_snapshot"

PCLOUD_OFF: Final = "off"
PCLOUD_CONFIRMED: Final = "confirmed"
PCLOUD_ALL: Final = "all"
DEFAULT_PCLOUD_SUBFOLDER: Final = "alcedo"

PCLOUD_DOMAIN: Final = "pcloud_sync"
PCLOUD_SERVICE: Final = "upload_file"

EVENT_ALCEDO: Final = f"{DOMAIN}_event"
POLL_MINUTES: Final = 5
