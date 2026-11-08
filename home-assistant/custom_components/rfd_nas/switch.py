"""Un interruttore per ogni app: acceso = app avviata (il tocco agisce subito, senza conferma)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from . import NasEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    known: set[str] = set()

    def add_new():
        new = [a for a in (c.data or {}).get("apps", []) if a["name"] not in known]
        known.update(a["name"] for a in new)
        if new:
            async_add_entities([AppSwitch(c, a["name"], a.get("title") or a["name"]) for a in new])

    add_new()
    entry.async_on_unload(c.async_add_listener(add_new))   # app installate dopo


class AppSwitch(NasEntity, SwitchEntity):
    _attr_icon = "mdi:application-cog"

    def __init__(self, c, name, title):
        super().__init__(c, f"app_{name}", f"App {title}")
        self._n = name

    def _a(self):
        return next((a for a in (self.coordinator.data or {}).get("apps", []) if a["name"] == self._n), None)

    @property
    def available(self):
        return super().available and self._a() is not None

    @property
    def is_on(self):
        a = self._a()
        return bool(a and a.get("state") in ("attiva", "parziale", "riavvio"))

    @property
    def extra_state_attributes(self):
        a = self._a() or {}
        return {"stato": a.get("state"), "versione": a.get("version"), "aggiornamento": a.get("update"), "porta": a.get("port")}

    async def async_turn_on(self, **kwargs):
        await self.coordinator.command(f"/apps/{self._n}/start")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.command(f"/apps/{self._n}/stop")
