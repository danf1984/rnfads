"""Panoramica del sistema, stato per Home Assistant, navigazione cartelle."""
import glob
import os
import socket
import time

from .util import ALLOWED_ROOTS, ApiError, load_json, read_file, run, STATE


def _cpu_times():
    parts = read_file("/proc/stat").splitlines()[0].split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return idle, sum(vals)


def cpu_percent(interval=0.4):
    i1, t1 = _cpu_times()
    time.sleep(interval)
    i2, t2 = _cpu_times()
    dt = t2 - t1
    return round(100.0 * (1 - (i2 - i1) / dt), 1) if dt > 0 else 0.0


def memory():
    info = {}
    for line in read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        info[k] = int(v.split()[0]) * 1024 if v.split() else 0
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    return {"total": total, "used": total - avail,
            "percent": round(100 * (total - avail) / total, 1) if total else 0}


def temperature():
    """Temperatura più alta tra CPU e sensori di sistema, in °C (o None)."""
    best = None
    for path in glob.glob("/sys/class/hwmon/hwmon*/temp*_input") + \
            glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            v = int(read_file(path).strip()) / 1000
        except ValueError:
            continue
        if 0 < v < 130 and (best is None or v > best):
            best = v
    return round(best, 1) if best is not None else None


def uptime():
    try:
        return int(float(read_file("/proc/uptime").split()[0]))
    except (IndexError, ValueError):
        return 0


def os_info():
    info = {}
    for line in read_file("/etc/os-release").splitlines():
        k, _, v = line.partition("=")
        info[k] = v.strip().strip('"')
    conf = {}
    for line in read_file("/etc/nido/nido.conf").splitlines():
        k, _, v = line.partition("=")
        if k and not k.startswith("#"):
            conf[k.strip()] = v.strip().strip('"')
    return {
        "name": conf.get("NIDO_NAME", info.get("NAME", "NAS")),
        "version": conf.get("NIDO_VERSION", ""),
        "pretty": info.get("PRETTY_NAME", ""),
        "kernel": os.uname().release,
        "hostname": socket.gethostname(),
    }


def reboot_required():
    if os.path.exists("/run/reboot-required") or os.path.exists("/var/run/reboot-required"):
        return True
    # Kernel installato più recente di quello in uso
    running = os.uname().release
    mods = sorted(os.listdir("/lib/modules")) if os.path.isdir("/lib/modules") else []
    if mods:
        from .updates import _version_key
        newest = max(mods, key=_version_key)
        if newest != running and _version_key(newest) > _version_key(running):
            return True
    return False


def ip_addresses():
    from .util import run_rc
    rc, out, _ = run_rc(["ip", "-j", "-4", "addr", "show", "scope", "global"], timeout=10)
    import json
    try:
        data = json.loads(out or "[]")
    except ValueError:
        return []
    res = []
    for iface in data:
        name = iface.get("ifname", "")
        if name.startswith(("docker", "br-", "veth")):
            continue
        for a in iface.get("addr_info", []):
            res.append({"iface": name, "ip": a.get("local")})
    return res


def overview():
    from . import disks, updates, backup
    st = disks.summary()
    upd = updates.cached()
    return {
        "os": os_info(),
        "uptime": uptime(),
        "load": os.getloadavg(),
        "cpu_percent": cpu_percent(),
        "cpus": os.cpu_count(),
        "memory": memory(),
        "temperature": temperature(),
        "ips": ip_addresses(),
        "disks": st,
        "updates": {"count": len(upd.get("packages", [])),
                    "security": sum(1 for p in upd.get("packages", []) if p.get("security")),
                    "checked_at": upd.get("checked_at")},
        "reboot_required": reboot_required(),
        "backups": backup.summary(),
    }


def _uptime_ha():
    try:
        from .uptime import summary
        u = summary()
    except Exception:  # noqa: BLE001
        return {}
    ls = u.get("last_shutdown") or {}
    return {"power_on_hours": u["total_hours"], "boots": u["boots"], "unclean_shutdowns": u["unclean"],
            "boot_time": u["boot_time"], "last_shutdown": ls.get("time"), "last_shutdown_clean": ls.get("clean")}


def ha_status():
    """Stato compatto per Home Assistant (sensori REST)."""
    ov = overview()
    return {
        "hostname": ov["os"]["hostname"],
        "name": ov["os"]["name"],
        "version": ov["os"]["version"],
        "uptime_s": ov["uptime"],
        "cpu_percent": ov["cpu_percent"],
        "load_1m": round(ov["load"][0], 2),
        "memory_percent": ov["memory"]["percent"],
        "temperature_c": ov["temperature"],
        "updates": ov["updates"]["count"],
        "security_updates": ov["updates"]["security"],
        "reboot_required": ov["reboot_required"],
        **_uptime_ha(),
        "disks": [
            {"name": d["name"], "model": d.get("model"), "health": d.get("health"),
             "temperature_c": d.get("temperature"), "used_percent": d.get("used_percent")}
            for d in ov["disks"]
        ],
        "backups": [
            {"name": b["name"], "last_run": b.get("last_run"), "ok": b.get("ok")}
            for b in ov["backups"]
        ],
    }


def power(action):
    if action not in ("reboot", "poweroff"):
        raise ApiError("Azione non valida")
    wake = None
    if action == "poweroff":
        from . import powersched
        ok, txt = powersched.arm_wake()
        wake = {"ok": ok, "text": txt}
    # Ritardo breve così la risposta HTTP arriva al browser
    run(["systemd-run", "--on-active=2", "--quiet", "systemctl", action], timeout=15)
    return {"ok": True, "wake": wake}


def list_dirs(path):
    """Elenco delle sottocartelle, per il selettore di cartelle dell'interfaccia."""
    if not path or path == "/":
        return {"path": "/", "parent": None,
                "dirs": [r for r in ALLOWED_ROOTS if os.path.isdir(r)]}
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + "/") for r in ALLOWED_ROOTS):
        raise ApiError("Cartella non consentita")
    if not os.path.isdir(real):
        raise ApiError("La cartella non esiste", 404)
    try:
        names = sorted(n for n in os.listdir(real)
                       if not n.startswith(".") and os.path.isdir(os.path.join(real, n)))
    except PermissionError:
        names = []
    parent = os.path.dirname(real) if real not in ALLOWED_ROOTS else "/"
    return {"path": real, "parent": parent, "dirs": [os.path.join(real, n) for n in names]}


def make_dir(path):
    parent = os.path.dirname(os.path.realpath(path.rstrip("/")))
    if not any(parent == r or parent.startswith(r + "/") for r in ALLOWED_ROOTS):
        raise ApiError("Cartella non consentita")
    name = os.path.basename(path.rstrip("/"))
    if not name or name.startswith(".") or "/" in name:
        raise ApiError("Nome cartella non valido")
    os.makedirs(os.path.join(parent, name), exist_ok=True)
    return {"path": os.path.join(parent, name)}


def last_state(name):
    return load_json(os.path.join(STATE, name), {})
