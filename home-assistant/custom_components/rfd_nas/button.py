"""Pulsanti: riavvia, spegni, cerca aggiornamenti (sistema e app), riavvia/aggiorna ogni app."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity

from . import NasEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    ents = [Cmd(c, "reboot", "Riavvia", "/system/reboot", ButtonDeviceClass.RESTART),
            Cmd(c, "poweroff", "Spegni", "/system/poweroff", None, "mdi:power"),
            Cmd(c, "check_updates", "Cerca aggiornamenti di sistema", "/updates/check", None, "mdi:package-down"),
            Cmd(c, "check_apps", "Cerca aggiornamenti delle app", "/apps/check", None, "mdi:update")]
    for name in (c.data or {}).get("disk_standby", {}):
        ents.append(Cmd(c, f"sleep_{name}", f"Disco {name} in standby", f"/disks/{name}/sleep", None, "mdi:sleep"))
    for a in (c.data or {}).get("apps", []):
        if a.get("managed"):
            t = a.get("title") or a["name"]
            ents.append(Cmd(c, f"restart_{a['name']}", f"Riavvia {t}", f"/apps/{a['name']}/restart", ButtonDeviceClass.RESTART))
            ents.append(Cmd(c, f"update_{a['name']}", f"Aggiorna {t}", f"/apps/{a['name']}/update", ButtonDeviceClass.UPDATE))
    async_add_entities(ents)


class Cmd(NasEntity, ButtonEntity):
    def __init__(self, c, key, name, path, dclass, icon=None):
        super().__init__(c, key, name)
        self._p = path
        self._attr_device_class = dclass
        if icon:
            self._attr_icon = icon

    async def async_press(self):
        await self.coordinator.command(self._p)
