"""Set up a comma by its local address."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GalaxyAccessError, GalaxyClient, GalaxyError
from .const import DEFAULT_PORT, DEVICE_MODELS, DOMAIN, LOGGER


def _schema(host: str = "", port: int = DEFAULT_PORT) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): cv.string,
            vol.Required(CONF_PORT, default=port): cv.port,
        }
    )


class StarPilotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the comma's address and check that Galaxy answers."""

    VERSION = 1

    async def _probe(self, host: str, port: int) -> tuple[str | None, str, str | None]:
        """Return (error key, device title, stable ID)."""
        client = GalaxyClient(async_get_clientsession(self.hass), host, port)
        try:
            await client.async_authenticate()
            await client.async_get("/api/device/state")
        except GalaxyAccessError:
            return "not_local", "", None
        except GalaxyError:
            return "cannot_connect", "", None
        except Exception:  # noqa: BLE001 - a config flow must show an error, never crash.
            LOGGER.exception("Unexpected error while setting up StarPilot")
            return "unknown", "", None

        title, unique_id = "comma", None
        try:
            # The hotspot name ends with the comma's own ID, which survives an address change.
            ssid = (await client.async_get("/api/galaxy/hotspot"))["config"]["ssid"]
            if isinstance(ssid, str) and ssid:
                unique_id = ssid.lower()
        except (GalaxyError, KeyError, TypeError):
            pass
        try:
            device_type = (await client.async_get("/api/system/monitor")).get("deviceType")
            title = DEVICE_MODELS.get(device_type, title)
        except (GalaxyError, AttributeError):
            pass
        return None, title, unique_id

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step: the address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            error, title, unique_id = await self._probe(host, port)
            if error is None:
                if unique_id is not None:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                else:
                    self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(title=title, data={CONF_HOST: host, CONF_PORT: port})
            errors["base"] = error
            return self.async_show_form(step_id="user", data_schema=_schema(host, port), errors=errors)
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the address of a comma that is already set up."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        host, port = entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            error, _, unique_id = await self._probe(host, port)
            if error is None:
                if unique_id is not None and entry.unique_id is not None and unique_id != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host, CONF_PORT: port})
            errors["base"] = error
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(host, port), errors=errors)
