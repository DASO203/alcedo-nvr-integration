"""Config flow: automatic discovery of the Alcedo NVR app or manual setup."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import AlcedoAuthError, AlcedoClient, AlcedoError
from .const import (
    CONF_API_KEY,
    CONF_PCLOUD_MODE,
    CONF_PCLOUD_SNAPSHOT,
    CONF_PCLOUD_SUBFOLDER,
    DEFAULT_PCLOUD_SUBFOLDER,
    DEFAULT_PORT,
    DOMAIN,
    PCLOUD_ALL,
    PCLOUD_CONFIRMED,
    PCLOUD_DOMAIN,
    PCLOUD_OFF,
)

UNIQUE_ID = "alcedo_nvr_app"


class AlcedoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def _test(self, data: dict[str, Any]) -> str | None:
        client = AlcedoClient(
            async_get_clientsession(self.hass),
            data[CONF_HOST],
            data[CONF_PORT],
            data[CONF_API_KEY],
        )
        try:
            await client.info()
        except AlcedoAuthError:
            return "invalid_auth"
        except AlcedoError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual setup (host / port / API key from the app's web UI)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_PORT: int(user_input[CONF_PORT])}
            if not (error := await self._test(data)):
                await self.async_set_unique_id(UNIQUE_ID)
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title="Alcedo NVR", data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): TextSelector(),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                    vol.Required(CONF_API_KEY): TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The app announced itself via the Supervisor."""
        cfg = discovery_info.config
        self._discovered = {
            CONF_HOST: cfg["host"],
            CONF_PORT: int(cfg.get("port", DEFAULT_PORT)),
            CONF_API_KEY: cfg["api_key"],
        }
        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured(updates=self._discovered)
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await self._test(self._discovered)):
                return self.async_create_entry(title="Alcedo NVR", data=self._discovered)
            errors["base"] = error
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AlcedoOptionsFlow()


class AlcedoOptionsFlow(OptionsFlow):
    """pCloud hand-over options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        installed = self.hass.services.has_service(PCLOUD_DOMAIN, "upload_file")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PCLOUD_MODE, default=o.get(CONF_PCLOUD_MODE, PCLOUD_OFF)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[PCLOUD_OFF, PCLOUD_CONFIRMED, PCLOUD_ALL],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_PCLOUD_MODE,
                        )
                    ),
                    vol.Required(
                        CONF_PCLOUD_SUBFOLDER,
                        default=o.get(CONF_PCLOUD_SUBFOLDER, DEFAULT_PCLOUD_SUBFOLDER),
                    ): TextSelector(),
                    vol.Required(
                        CONF_PCLOUD_SNAPSHOT, default=o.get(CONF_PCLOUD_SNAPSHOT, True)
                    ): BooleanSelector(),
                }
            ),
            description_placeholders={
                "pcloud_status": "✅" if installed else "❌",
                "pcloud_url": "https://github.com/DASO203/pcloud-sync-unofficial",
            },
        )
