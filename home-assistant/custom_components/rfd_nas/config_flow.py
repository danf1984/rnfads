"""Configurazione dall'interfaccia di Home Assistant."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NasApi, NasAuthError, NasError
from .const import CONF_SSL, CONF_VERIFY_SSL, DOMAIN


def _schema(d: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HOST, default=d.get(CONF_HOST, "rnfads.local")): str,
        vol.Required(CONF_API_KEY, default=d.get(CONF_API_KEY, "")): str,
        vol.Optional(CONF_SSL, default=d.get(CONF_SSL, True)): bool,
        vol.Optional(CONF_VERIFY_SSL, default=d.get(CONF_VERIFY_SSL, False)): bool,
    })


class RfdNasConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, data: dict) -> tuple[dict, str | None]:
        api = NasApi(async_get_clientsession(self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, False)), data[CONF_HOST],
                     data[CONF_API_KEY], data.get(CONF_SSL, True), data.get(CONF_VERIFY_SSL, False))
        try:
            return await api.status(), None
        except NasAuthError:
            return {}, "invalid_auth"
        except NasError:
            return {}, "cannot_connect"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            st, err = await self._check(user_input)
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(st.get("hostname") or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=st.get("hostname") or "RNFADS", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            _, err = await self._check(data)
            if not err:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = err
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
                                    errors=errors)
