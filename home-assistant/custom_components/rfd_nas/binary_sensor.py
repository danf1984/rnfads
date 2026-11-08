"""Sensori sì/no: riavvio necessario, aggiornamenti, dischi in standby, app accese."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from . import NasEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    d = c.data or {}
    ents = [Simple(c, "reboot_required", "Riavvio necessario", BinarySensorDeviceClass.PROBLEM,
                   lambda x: bool(x.get("reboot_required"))),
            Simple(c, "updates_available", "Aggiornamenti disponibili", BinarySensorDeviceClass.UPDATE,
                   lambda x: (x.get("updates") or 0) > 0)]
    for name in d.get("disk_standby", {}):
        ents.append(Simple(c, f"standby_{name}", f"Disco {name} acceso", BinarySensorDeviceClass.RUNNING,
                           lambda x, n=name: x.get("disk_standby", {}).get(n) != "standby", "mdi:harddisk"))
    for disk in d.get("disks", []):
        n = disk["name"]
        ents.append(Simple(c, f"problem_{n}", f"Disco {disk.get('model') or n} problema", BinarySensorDeviceClass.PROBLEM,
                           lambda x, n=n: next((k.get("health") for k in x.get("disks", []) if k["name"] == n), None)
                           in ("attenzione", "guasto")))
    async_add_entities(ents)


class Simple(NasEntity, BinarySensorEntity):
    def __init__(self, c, key, name, dclass, fn, icon=None):
        super().__init__(c, key, name)
        self._attr_device_class = dclass
        self._fn = fn
        if icon:
            self._attr_icon = icon

    @property
    def is_on(self):
        return self._fn(self.coordinator.data or {})
