"""Integrazione Home Assistant per RNFADS."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

from .api import NasApi, NasAuthError, NasError
from .const import CONF_SSL, CONF_VERIFY_SSL, DEFAULT_SCAN, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.BUTTON, Platform.UPDATE]


class NasCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=DEFAULT_SCAN))
        d = entry.data
        self.api = NasApi(async_get_clientsession(hass, verify_ssl=d.get(CONF_VERIFY_SSL, False)),
                          d[CONF_HOST], d[CONF_API_KEY], d.get(CONF_SSL, True), d.get(CONF_VERIFY_SSL, False))
        self.entry = entry

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.status()
        except NasAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        except NasError as e:
            raise UpdateFailed(str(e)) from e

    async def command(self, path: str) -> None:
        await self.api.post(path)
        await self.async_request_refresh()


class NasEntity(CoordinatorEntity[NasCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NasCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name
        d = coordinator.data or {}
        host = coordinator.entry.data[CONF_HOST]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)}, name=d.get("hostname") or "RNFADS",
            manufacturer="RNFADS", model=d.get("name") or "RNFADS", sw_version=d.get("version"),
            configuration_url=f"{'https' if coordinator.entry.data.get(CONF_SSL, True) else 'http'}://{host}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = NasCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
