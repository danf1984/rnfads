"""Sensori: CPU, RAM, temperatura, acceso da, aggiornamenti, dischi, backup, app."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import EntityCategory

from . import NasEntity

BASE = [
    ("cpu_percent", "CPU", PERCENTAGE, None, "mdi:cpu-64-bit"),
    ("memory_percent", "Memoria", PERCENTAGE, None, "mdi:memory"),
    ("temperature_c", "Temperatura", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, None),
    ("load_1m", "Carico (1 min)", None, None, "mdi:gauge"),
    ("updates", "Aggiornamenti di sistema", None, None, "mdi:package-up"),
    ("security_updates", "Aggiornamenti di sicurezza", None, None, "mdi:shield-alert"),
]


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    d = c.data or {}
    ents: list[SensorEntity] = [Base(c, *b) for b in BASE]
    ents.append(Uptime(c))
    if "power_on_hours" in d:
        ents.append(PowerOnHours(c))
        ents.append(Counter(c, "boots", "Avvii", "mdi:restart"))
        ents.append(Counter(c, "unclean_shutdowns", "Spegnimenti improvvisi", "mdi:power-plug-off"))
        ents.append(LastShutdown(c))
    ents.append(AppsRunning(c))
    for disk in d.get("disks", []):
        ents.append(DiskUsed(c, disk["name"], disk.get("model")))
        ents.append(DiskTemp(c, disk["name"], disk.get("model")))
        ents.append(DiskHealth(c, disk["name"], disk.get("model")))
    for b in d.get("backups", []):
        ents.append(BackupLast(c, b["name"]))
    ents.append(NextPower(c, "next_off", "Prossimo spegnimento programmato", "mdi:power-sleep"))
    ents.append(NextPower(c, "next_on", "Prossima accensione programmata", "mdi:power"))
    async_add_entities(ents)


class Base(NasEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, key, name, unit, dclass, icon):
        super().__init__(c, key, name)
        self._k = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dclass
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._k)


class Uptime(NasEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, c):
        super().__init__(c, "boot", "Acceso dal")

    @property
    def native_value(self):
        up = (self.coordinator.data or {}).get("uptime_s")
        if up is None:
            return None
        t = datetime.now(timezone.utc) - timedelta(seconds=up)
        return t.replace(second=0, microsecond=0)   # niente cambi di stato a ogni aggiornamento


class AppsRunning(NasEntity, SensorEntity):
    _attr_icon = "mdi:docker"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c):
        super().__init__(c, "apps_running", "App accese")

    @property
    def native_value(self):
        return sum(1 for a in (self.coordinator.data or {}).get("apps", []) if a.get("state") == "attiva")

    @property
    def extra_state_attributes(self):
        return {a["name"]: a.get("state") for a in (self.coordinator.data or {}).get("apps", [])}


def _disk(c, name):
    return next((d for d in (c.data or {}).get("disks", []) if d["name"] == name), {})


class _Disk(NasEntity, SensorEntity):
    def __init__(self, c, name, model, key, label):
        super().__init__(c, f"disk_{name}_{key}", f"Disco {model or name} {label}")
        self._n = name


class DiskUsed(_Disk):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:harddisk"

    def __init__(self, c, name, model):
        super().__init__(c, name, model, "used", "spazio usato")

    @property
    def native_value(self):
        return _disk(self.coordinator, self._n).get("used_percent")

    @property
    def extra_state_attributes(self):
        return {"standby": (self.coordinator.data or {}).get("disk_standby", {}).get(self._n)}


class DiskTemp(_Disk):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, name, model):
        super().__init__(c, name, model, "temp", "temperatura")

    @property
    def native_value(self):
        return _disk(self.coordinator, self._n).get("temperature_c")


class DiskHealth(_Disk):
    _attr_icon = "mdi:heart-pulse"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, c, name, model):
        super().__init__(c, name, model, "health", "salute")

    @property
    def native_value(self):
        return _disk(self.coordinator, self._n).get("health")


class BackupLast(NasEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:backup-restore"

    def __init__(self, c, name):
        super().__init__(c, f"backup_{name}", f"Backup {name}")
        self._n = name

    def _b(self):
        return next((b for b in (self.coordinator.data or {}).get("backups", []) if b["name"] == self._n), {})

    @property
    def native_value(self):
        t = self._b().get("last_run")
        if not t:
            return None
        if isinstance(t, (int, float)):
            return datetime.fromtimestamp(t, timezone.utc)
        try:
            v = datetime.fromisoformat(str(t))
            return v if v.tzinfo else v.astimezone()
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        return {"riuscito": self._b().get("ok")}


class NextPower(NasEntity, SensorEntity):
    def __init__(self, c, key, name, icon):
        super().__init__(c, key, name)
        self._k = key
        self._attr_icon = icon

    @property
    def native_value(self):
        return ((self.coordinator.data or {}).get("power_schedule") or {}).get(self._k) or "non programmato"


class PowerOnHours(NasEntity, SensorEntity):
    """Ore totali di accensione dall'installazione (contate dal NAS, restano dopo i riavvii)."""
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-outline"
    _attr_suggested_display_precision = 1

    def __init__(self, c):
        super().__init__(c, "power_on_hours", "Ore totali di accensione")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("power_on_hours")


class Counter(NasEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, c, key, name, icon):
        super().__init__(c, key, name)
        self._k = key
        self._attr_icon = icon

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._k)


class LastShutdown(NasEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power"

    def __init__(self, c):
        super().__init__(c, "last_shutdown", "Ultimo spegnimento")

    @property
    def native_value(self):
        t = (self.coordinator.data or {}).get("last_shutdown")
        return datetime.fromtimestamp(t, timezone.utc) if t else None

    @property
    def extra_state_attributes(self):
        clean = (self.coordinator.data or {}).get("last_shutdown_clean")
        return {"regolare": clean, "tipo": None if clean is None else ("regolare" if clean else "improvviso (mancanza di corrente?)")}
