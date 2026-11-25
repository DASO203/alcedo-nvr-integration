"""Config flow.

Setup (usually automatic, the app announces itself):
  1. connect to the app
  2. take over cameras that already exist in Home Assistant (optional)
  3. pCloud upload (only if pCloud Sync is installed)

Later, new Home Assistant cameras appear as "discovered" (one confirmation
each) and everything can be changed under Configure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import AlcedoAuthError, AlcedoClient, AlcedoError
from .const import (
    AUTO,
    CONF_API_KEY,
    CONF_DISCOVER_CAMERAS,
    CONF_PCLOUD_ARCHIVE,
    CONF_PCLOUD_MODE,
    CONF_PCLOUD_SNAPSHOT,
    CONF_PCLOUD_SUBFOLDER,
    DEFAULT_PCLOUD_SUBFOLDER,
    DEFAULT_PORT,
    DETECT_MODES,
    DOMAIN,
    OBJECTS,
    PCLOUD_ALL,
    PCLOUD_CONFIRMED,
    PCLOUD_DOMAIN,
    PCLOUD_OFF,
    RECORD_MODES,
)
from .discovery import Candidate, async_find_cameras, not_in_alcedo

if TYPE_CHECKING:
    from . import AlcedoConfigEntry

UNIQUE_ID = "alcedo_nvr_app"
PCLOUD_URL = "https://github.com/DASO203/pcloud-sync-unofficial"
CONF_CAMERAS = "cameras"
CONF_RECORD = "record"
CONF_DETECT = "detect"
CONF_OBJECTS = "objects"

_ORIGIN = {
    "de": {
        "reolink": "Reolink-Integration",
        "instar": "INSTAR (RTSP)",
        "ring_mqtt": "Ring über ring-mqtt",
        "generic": "Generische Kamera (RTSP)",
    },
    "en": {
        "reolink": "Reolink integration",
        "instar": "INSTAR (RTSP)",
        "ring_mqtt": "Ring via ring-mqtt",
        "generic": "Generic camera (RTSP)",
    },
}


def _origin(hass: HomeAssistant, origin: str) -> str:
    lang = "de" if (hass.config.language or "").startswith("de") else "en"
    return _ORIGIN[lang].get(origin, origin)


def _label(hass: HomeAssistant, cand: Candidate) -> str:
    return f"{cand.name} · {_origin(hass, cand.origin)} · {cand.address}"


def _select(key: str, options: tuple[str, ...], multiple: bool = False) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=list(options),
            translation_key=key,
            multiple=multiple,
            mode=SelectSelectorMode.LIST
            if multiple or len(options) <= 5
            else SelectSelectorMode.DROPDOWN,
        )
    )


def _hub(hass: HomeAssistant) -> AlcedoConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    return None


def _pcloud_installed(hass: HomeAssistant) -> bool:
    return hass.services.has_service(PCLOUD_DOMAIN, "upload_file")


def _camera_settings_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(CONF_RECORD, default=defaults.get(CONF_RECORD, AUTO)): _select(
            CONF_RECORD, RECORD_MODES
        ),
        vol.Required(CONF_DETECT, default=defaults.get(CONF_DETECT, AUTO)): _select(
            CONF_DETECT, DETECT_MODES
        ),
        vol.Required(
            CONF_OBJECTS, default=defaults.get(CONF_OBJECTS, ["person", "vehicle"])
        ): _select(CONF_OBJECTS, OBJECTS, multiple=True),
    }


def _pcloud_schema(o: dict[str, Any], full: bool) -> vol.Schema:
    schema: dict[Any, Any] = {
        vol.Required(CONF_PCLOUD_MODE, default=o.get(CONF_PCLOUD_MODE, PCLOUD_CONFIRMED)): _select(
            CONF_PCLOUD_MODE, (PCLOUD_OFF, PCLOUD_CONFIRMED, PCLOUD_ALL)
        ),
        vol.Required(
            CONF_PCLOUD_ARCHIVE, default=o.get(CONF_PCLOUD_ARCHIVE, True)
        ): BooleanSelector(),
    }
    if full:
        schema[vol.Required(CONF_PCLOUD_SNAPSHOT, default=o.get(CONF_PCLOUD_SNAPSHOT, True))] = (
            BooleanSelector()
        )
        schema[
            vol.Required(
                CONF_PCLOUD_SUBFOLDER,
                default=o.get(CONF_PCLOUD_SUBFOLDER, DEFAULT_PCLOUD_SUBFOLDER),
            )
        ] = TextSelector()
    return vol.Schema(schema)


async def _add(client: AlcedoClient, cands: list[Candidate], user_input: dict[str, Any]) -> None:
    await client.add_cameras(
        [
            c.payload(
                user_input.get(CONF_RECORD, AUTO),
                user_input.get(CONF_DETECT, AUTO),
                user_input.get(CONF_OBJECTS),
            )
            for c in cands
        ]
    )


class AlcedoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._candidates: dict[str, Candidate] = {}
        self._camera_key = ""
        self._camera_name = ""

    def _client(self) -> AlcedoClient:
        return AlcedoClient(
            async_get_clientsession(self.hass),
            self._data[CONF_HOST],
            self._data[CONF_PORT],
            self._data[CONF_API_KEY],
        )

    async def _test(self) -> str | None:
        try:
            await self._client().info()
        except AlcedoAuthError:
            return "invalid_auth"
        except AlcedoError:
            return "cannot_connect"
        return None

    # ----------------------------------------------------------- 1 connect

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual setup (host / port / API key from the app's web UI)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {**user_input, CONF_PORT: int(user_input[CONF_PORT])}
            if not (error := await self._test()):
                await self.async_set_unique_id(UNIQUE_ID)
                self._abort_if_unique_id_configured(updates=self._data)
                return await self.async_step_cameras()
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): TextSelector(),
                        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
                            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
                        ),
                        vol.Required(CONF_API_KEY): TextSelector(),
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The app announced itself via the Supervisor."""
        cfg = discovery_info.config
        self._data = {
            CONF_HOST: cfg["host"],
            CONF_PORT: int(cfg.get("port", DEFAULT_PORT)),
            CONF_API_KEY: cfg["api_key"],
        }
        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured(updates=self._data)
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await self._test()):
                return await self.async_step_cameras()
            errors["base"] = error
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    # ----------------------------------------------------------- 2 cameras

    async def async_step_cameras(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the cameras that already exist in Home Assistant."""
        client = self._client()
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [self._candidates[k] for k in user_input.get(CONF_CAMERAS, [])]
            if chosen:
                try:
                    await _add(client, chosen, user_input)
                except AlcedoError:
                    errors["base"] = "add_failed"
            if not errors:
                return await self.async_step_pcloud()
        else:
            try:
                found = not_in_alcedo(await async_find_cameras(self.hass), await client.cameras())
            except AlcedoError:
                found = []
            self._candidates = {c.key: c for c in found}
            if not found:
                return await self.async_step_pcloud()
        return self.async_show_form(
            step_id="cameras",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CAMERAS, default=list(self._candidates)): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=k, label=_label(self.hass, c))
                                for k, c in self._candidates.items()
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    **_camera_settings_schema({}),
                }
            ),
            description_placeholders={"count": str(len(self._candidates))},
            errors=errors,
        )

    # ----------------------------------------------------------- 3 pCloud

    async def async_step_pcloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None or not _pcloud_installed(self.hass):
            self._options = {
                CONF_PCLOUD_MODE: PCLOUD_OFF,
                CONF_PCLOUD_SUBFOLDER: DEFAULT_PCLOUD_SUBFOLDER,
                CONF_PCLOUD_SNAPSHOT: True,
                CONF_PCLOUD_ARCHIVE: True,
                CONF_DISCOVER_CAMERAS: True,
                **(user_input or {}),
            }
            return self.async_create_entry(
                title="Alcedo NVR", data=self._data, options=self._options
            )
        return self.async_show_form(
            step_id="pcloud",
            data_schema=_pcloud_schema({}, full=False),
            description_placeholders={"folder": DEFAULT_PCLOUD_SUBFOLDER},
        )

    # ----------------------------------------------------------- discovered camera

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """A camera in Home Assistant that Alcedo does not record yet."""
        self._camera_key = discovery_info["key"]
        self._camera_name = discovery_info.get("name", self._camera_key)
        await self.async_set_unique_id(f"camera:{self._camera_key}")
        self._abort_if_unique_id_configured()
        if _hub(self.hass) is None:
            return self.async_abort(reason="not_loaded")
        self.context["title_placeholders"] = {"name": self._camera_name}
        return await self.async_step_camera_confirm()

    async def async_step_camera_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        hub = _hub(self.hass)
        if hub is None:
            return self.async_abort(reason="not_loaded")
        cand = next(
            (c for c in await async_find_cameras(self.hass) if c.key == self._camera_key), None
        )
        if cand is None:
            return self.async_abort(reason="camera_gone")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _add(hub.runtime_data.client, [cand], user_input)
            except AlcedoError:
                errors["base"] = "add_failed"
            else:
                return self.async_abort(
                    reason="camera_added", description_placeholders={"name": cand.name}
                )
        return self.async_show_form(
            step_id="camera_confirm",
            data_schema=vol.Schema(_camera_settings_schema({})),
            description_placeholders={
                "name": cand.name,
                "origin": _origin(self.hass, cand.origin),
                "address": cand.address,
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AlcedoOptionsFlow()


class AlcedoOptionsFlow(OptionsFlow):
    """Configure: cameras, pCloud, automatic camera search."""

    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}

    @property
    def _client(self) -> AlcedoClient:
        return self.config_entry.runtime_data.client

    def _save(self, changes: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **(changes or {})})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="not_loaded")
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_cameras", "remove_cameras", "pcloud", "discovery"],
        )

    async def async_step_add_cameras(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [self._candidates[k] for k in user_input.get(CONF_CAMERAS, [])]
            if not chosen:
                return self._save()
            try:
                await _add(self._client, chosen, user_input)
            except AlcedoError:
                errors["base"] = "add_failed"
            else:
                return self._save()
        else:
            try:
                found = not_in_alcedo(
                    await async_find_cameras(self.hass), await self._client.cameras()
                )
            except AlcedoError:
                return self.async_abort(reason="cannot_connect")
            self._candidates = {c.key: c for c in found}
            if not found:
                return self.async_abort(reason="no_new_cameras")
        return self.async_show_form(
            step_id="add_cameras",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CAMERAS, default=list(self._candidates)): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=k, label=_label(self.hass, c))
                                for k, c in self._candidates.items()
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    **_camera_settings_schema({}),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_cameras(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        try:
            cams = [c for c in await self._client.cameras() if c.get("source") == "ha"]
        except AlcedoError:
            return self.async_abort(reason="cannot_connect")
        if not cams:
            return self.async_abort(reason="no_managed_cameras")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                for cam_id in user_input.get(CONF_CAMERAS, []):
                    await self._client.remove_camera(cam_id)
            except AlcedoError:
                errors["base"] = "cannot_connect"
            else:
                return self._save()
        return self.async_show_form(
            step_id="remove_cameras",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CAMERAS, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=c["id"], label=c["name"]) for c in cams
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_pcloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        o = {CONF_PCLOUD_MODE: PCLOUD_OFF, **self.config_entry.options}
        return self.async_show_form(
            step_id="pcloud",
            data_schema=_pcloud_schema(o, full=True),
            description_placeholders={
                "pcloud_status": "✅" if _pcloud_installed(self.hass) else "❌",
                "pcloud_url": PCLOUD_URL,
            },
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="discovery",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DISCOVER_CAMERAS,
                        default=self.config_entry.options.get(CONF_DISCOVER_CAMERAS, True),
                    ): BooleanSelector()
                }
            ),
        )
