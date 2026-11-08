"""Procedura guidata al primo avvio (dopo il primo accesso di un amministratore).

Passi: benvenuto → nome del NAS e fuso orario → dischi dei dati → cartella condivisa →
sicurezza (aggiornamenti automatici, certificato di casa) → fatto. Si può saltare in ogni
momento e riaprire da Impostazioni → Generale. Lo stato sta in /etc/nido/wizard.json.
"""
import os
import re
import socket
import time

from .util import ApiError, ETC, load_json, read_file, run_rc, save_json, write_file

FILE = os.path.join(ETC, "wizard.json")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def _timezones():
    rc, out, _ = run_rc(["timedatectl", "list-timezones"], timeout=15)
    zones = [z for z in out.split() if "/" in z]
    if not zones:
        base = "/usr/share/zoneinfo"
        for region in ("Europe", "America", "Asia", "Africa", "Australia", "Atlantic", "Pacific"):
            try:
                zones += [f"{region}/{z}" for z in sorted(os.listdir(os.path.join(base, region)))
                          if not z.startswith(".")]
            except OSError:
                pass
    return zones or ["Europe/Rome"]


def status():
    from . import apps, shares, updates
    w = load_json(FILE, {})
    data_disks = []
    try:
        from . import disks
        for d in disks.list_disks(with_smart=False):
            if d.get("protected"):
                continue
            parts = d.get("partitions") or []
            data_disks.append({"name": d.get("display") or d.get("name"), "path": d.get("path"), "size": d.get("size"),
                               "mounted": any(p.get("mounts") for p in parts), "empty": d.get("empty"),
                               "formatted": any(p.get("fstype") for p in parts)})
    except Exception:  # noqa: BLE001 — i dischi non devono bloccare la procedura
        pass
    try:
        sh = shares.get().get("shares", [])
    except Exception:  # noqa: BLE001
        sh = []
    try:
        sec = updates.settings().get("security")
    except Exception:  # noqa: BLE001
        sec = None
    return {"done": bool(w.get("done")), "skipped": bool(w.get("skipped")), "step": w.get("step", 0),
            "hostname": socket.gethostname().split(".")[0], "timezone": apps.timezone(), "timezones": _timezones(),
            "disks": data_disks, "shares": [s.get("name") for s in sh], "security_updates": sec}


def _set_hostname(name):
    name = (name or "").strip().lower()
    if not HOST_RE.match(name):
        raise ApiError("Nome non valido: lettere minuscole, numeri e trattini (es. rnfads)")
    old = socket.gethostname().split(".")[0]
    if name == old:
        return
    rc, out, err = run_rc(["hostnamectl", "set-hostname", name], timeout=30)
    if rc != 0:
        write_file("/etc/hostname", name + "\n")
        run_rc(["hostname", name], timeout=10)
    hosts = read_file("/etc/hosts")
    if re.search(r"(?m)^127\.0\.1\.1\s", hosts):
        hosts = re.sub(r"(?m)^127\.0\.1\.1\s.*$", f"127.0.1.1\t{name}.local {name}", hosts)
    else:
        hosts += f"\n127.0.1.1\t{name}.local {name}\n"
    write_file("/etc/hosts", hosts)
    run_rc(["systemctl", "restart", "avahi-daemon"], timeout=60)
    # Certificato di casa e Caddy con il nome nuovo
    try:
        from . import https
        https.ensure_home_cert(force=True)
        https.apply()
    except Exception as e:  # noqa: BLE001
        print(f"wizard: https: {e}", flush=True)


def _set_timezone(tz):
    if tz not in _timezones():
        raise ApiError("Fuso orario non valido")
    rc, out, err = run_rc(["timedatectl", "set-timezone", tz], timeout=30)
    if rc != 0:
        try:
            os.unlink("/etc/localtime")
        except FileNotFoundError:
            pass
        os.symlink(f"/usr/share/zoneinfo/{tz}", "/etc/localtime")
        write_file("/etc/timezone", tz + "\n")


def save(body):
    w = load_json(FILE, {})
    if "hostname" in body:
        _set_hostname(body["hostname"])
    if "timezone" in body:
        _set_timezone(body["timezone"])
    if body.get("share"):
        from . import shares
        os.makedirs("/DATA/Condivisa", exist_ok=True)
        try:
            shares.save_share({"name": "Condivisa", "path": "/DATA/Condivisa", "all_users": "rw", "recycle": True,
                               "comment": "Cartella condivisa creata dalla procedura guidata"})
        except ApiError as e:
            if "esiste già" not in e.message.lower():
                raise
    if "security_updates" in body:
        from . import updates
        updates.save_settings({"security": bool(body["security_updates"])})
    if "step" in body:
        w["step"] = int(body["step"])
    if body.get("done"):
        w["done"] = True
        w["finished"] = int(time.time())
    if body.get("skip"):
        w["done"] = True
        w["skipped"] = True
    if body.get("reopen"):
        w["done"] = False
        w["skipped"] = False
        w["step"] = 0
    save_json(FILE, w, 0o644)
    return status()
