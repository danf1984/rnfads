"""Aggiornamento del sistema RNFADS (canale online firmato): entità "update" di Home Assistant."""
from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature

from . import NasEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    if "system_update" in (c.data or {}):
        async_add_entities([SystemUpdate(c)])


class SystemUpdate(NasEntity, UpdateEntity):
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, c):
        super().__init__(c, "system_update", "Sistema")
        self._attr_title = (c.data or {}).get("name") or "RNFADS"

    @property
    def _u(self):
        return (self.coordinator.data or {}).get("system_update") or {}

    @property
    def installed_version(self):
        return self._u.get("installed") or (self.coordinator.data or {}).get("version")

    @property
    def latest_version(self):
        u = self._u
        return u.get("latest") if u.get("available") else self.installed_version

    @property
    def release_summary(self):
        return (self._u.get("notes") or None) if self._u.get("available") else None

    async def async_release_notes(self):
        return self._u.get("notes") or None

    async def async_install(self, version, backup, **kwargs):
        await self.coordinator.command("/v1/system/update")
