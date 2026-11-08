"""Aggiornamenti di sistema (apt) e snapshot del sistema (snapper).

- "Cerca aggiornamenti": apt-get update + elenco dei pacchetti, diviso in sicurezza, del NAS ("own") e sistema.
- "Aggiorna ora": snapshot prima, apt full-upgrade, snapshot dopo; il registro si segue in diretta.
- Impostazioni automatiche: ricerca (APT::Periodic), sicurezza da sole (unattended-upgrades),
  riavvio automatico di notte quando serve.
"""
import datetime
import json
import os
import re
import subprocess

from .util import (ApiError, LOGS, STATE, have, job_state, load_json, product, read_file, run,
                   run_rc, save_json, start_job, write_file)

CACHE = os.path.join(STATE, "updates.json")
LOG = os.path.join(LOGS, "updates.log")
AUTO = "/etc/apt/apt.conf.d/20auto-upgrades"
UNATTENDED = "/etc/apt/apt.conf.d/52nido-unattended"
APT_ENV = {"DEBIAN_FRONTEND": "noninteractive", "APT_LISTCHANGES_FRONTEND": "none"}
# Pacchetti nostri (quando ci sarà un archivio apt del progetto): il nome inizia con quello del
# sistema (NIDO_NAME in minuscolo) o con "nido", oppure l'origine lo contiene


def _own(name, origin):
    brand = re.sub(r"[^a-z0-9]", "", product()[0].lower()) or "nido"
    return bool(re.match(rf"^({brand}|nido)[a-z0-9.+-]*$", name)) or brand in origin


def _version_key(v):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.-]", v)]


def cached():
    return load_json(CACHE, {"packages": [], "checked_at": None})


def _list_upgradable():
    rc, out, _ = run_rc(["apt", "list", "--upgradable"], timeout=120)
    pkgs = []
    for line in out.splitlines():
        m = re.match(r"^([^/\s]+)/(\S+)\s+(\S+)\s+\S+\s+\[(?:upgradable from|aggiornabile da): ([^\]]+)\]", line)
        if m:
            name, origin = m.group(1), m.group(2)
            group = "own" if _own(name, origin) else (
                "security" if "security" in origin else "system")
            pkgs.append({"name": name, "origin": origin, "to": m.group(3), "from": m.group(4),
                         "security": group == "security", "group": group})
    order = {"security": 0, "own": 1, "system": 2}
    return sorted(pkgs, key=lambda p: (order[p["group"]], p["name"]))


def refresh_cache(checked=False):
    data = cached()
    data["packages"] = _list_upgradable()
    if checked:
        data["checked_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_json(CACHE, data, 0o644)
    return data


def settings():
    auto = read_file(AUTO)
    un = read_file(UNATTENDED)
    m = re.search(r'Update-Package-Lists\s+"(\d+)"', auto)
    days = int(m.group(1)) if m else 1
    return {
        "check": "off" if days == 0 else ("weekly" if days >= 7 else "daily"),
        "security": bool(re.search(r'Unattended-Upgrade\s+"1"', auto)),
        "reboot": bool(re.search(r'Automatic-Reboot\s+"true"', un)),
        "reboot_time": (re.search(r'Automatic-Reboot-Time\s+"(\d\d:\d\d)"', un) or [None, "04:00"])[1],
    }


def save_settings(body):
    cur = settings()
    check = body.get("check", cur["check"])
    if check not in ("off", "daily", "weekly"):
        raise ApiError("Frequenza non valida")
    sec = bool(body.get("security", cur["security"]))
    reboot = bool(body.get("reboot", cur["reboot"]))
    rt = body.get("reboot_time") or cur["reboot_time"]
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", rt):
        raise ApiError("Orario non valido (es. 04:00)")
    days = {"off": 0, "daily": 1, "weekly": 7}[check]
    write_file(AUTO,
               "// Gestito dall'interfaccia del NAS (Impostazioni > Aggiornamenti di sistema)\n"
               f'APT::Periodic::Update-Package-Lists "{days}";\n'
               f'APT::Periodic::Unattended-Upgrade "{1 if sec else 0}";\n'
               'APT::Periodic::AutocleanInterval "7";\n')
    write_file(UNATTENDED,
               "// Gestito dall'interfaccia del NAS\n"
               f'Unattended-Upgrade::Automatic-Reboot "{"true" if reboot else "false"}";\n'
               f'Unattended-Upgrade::Automatic-Reboot-Time "{rt}";\n'
               'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";\n')
    return settings()


def set_auto(enabled):          # compatibilità
    return save_settings({"security": bool(enabled)})


def status():
    from .system import reboot_required
    data = cached()
    groups = {"security": 0, "own": 0, "system": 0}
    for p in data.get("packages", []):
        groups[p.get("group") or ("security" if p.get("security") else "system")] += 1
    last = load_json(os.path.join(STATE, "updates-last.json"), {})
    return {
        **data,
        "groups": groups,
        "checking": job_state("updates-check") in ("active", "activating"),
        "installing": job_state("updates-install") in ("active", "activating"),
        "settings": settings(),
        "reboot_required": reboot_required(),
        "snapshots": snapshots_available(),
        "last": last,
        "log_size": os.path.getsize(LOG) if os.path.exists(LOG) else 0,
    }


def log_since(offset=0):
    """Registro in diretta: il testo aggiunto dopo "offset" (in byte)."""
    size = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    if offset > size or offset < 0:
        offset = 0
    if offset == 0 and size > 200_000:
        offset = size - 200_000
    text = ""
    if size > offset:
        with open(LOG, "rb") as f:
            f.seek(offset)
            text = f.read(size - offset).decode("utf-8", "replace")
    running = job_state("updates-install") in ("active", "activating") or \
        job_state("updates-check") in ("active", "activating")
    return {"text": text, "offset": size, "running": running}


def check():
    if job_state("updates-install") in ("active", "activating"):
        raise ApiError("È in corso un aggiornamento", 409)
    start_job("updates-check", ["updates-check"], log=LOG)
    return {"ok": True}


def install():
    if job_state("updates-check") in ("active", "activating"):
        raise ApiError("Attendi la fine del controllo aggiornamenti", 409)
    start_job("updates-install", ["updates-install"], log=LOG)
    return {"ok": True}


# --- esecuzione (cli.py) ---------------------------------------------------------------------

def _say(text):
    print(f"[{datetime.datetime.now():%d/%m %H:%M:%S}] {text}", flush=True)


def _stream(cmd, env, timeout):
    """Esegue un comando mostrando l'output riga per riga nel registro."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         env=dict(os.environ, **env), bufsize=1)
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line:
                print("    " + line, flush=True)
        return p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return 124


def run_check():
    _say("Cerco aggiornamenti")
    rc = _stream(["apt-get", "update"], dict(APT_ENV, LC_ALL="C.UTF-8"), 900)
    data = refresh_cache(checked=True)
    n = len(data["packages"])
    sec = sum(1 for p in data["packages"] if p["group"] == "security")
    if rc == 0:
        _say(f"Aggiornamenti disponibili: {n}" + (f" (di cui {sec} di sicurezza)" if sec else ""))
    else:
        _say(f"ERRORE: non riesco a leggere gli archivi dei pacchetti (codice {rc}). Controlla la connessione.")
    return rc == 0


def _snapshot(desc):
    if not snapshots_available():
        return None
    rc, out, err = run_rc(["snapper", "--no-dbus", "-c", "root", "create", "--print-number",
                           "--cleanup-algorithm", "number", "--description", desc,
                           "--userdata", "important=yes"], timeout=300)
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else None


def run_install():
    from . import notify
    from .system import reboot_required
    started = datetime.datetime.now()
    _say("=== Aggiornamento del sistema")
    env = dict(APT_ENV, LC_ALL="C.UTF-8", NIDO_NO_APT_SNAPSHOT="1")
    pre = _snapshot("prima dell'aggiornamento")
    if pre:
        _say(f"Snapshot \"prima dell'aggiornamento\" creato (#{pre})")
    else:
        _say("Snapshot non disponibili (il disco di sistema non è Btrfs con snapper): continuo senza")
    _say("Aggiorno l'elenco dei pacchetti")
    _stream(["apt-get", "update"], env, 900)
    pk = _list_upgradable()
    _say(f"Pacchetti da aggiornare: {len(pk)}")
    rc = 0
    if pk:
        _say("Scarico e installo")
        rc = _stream(["apt-get", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o",
                      "Dpkg::Options::=--force-confold", "full-upgrade"], env, 4 * 3600)
        if rc == 0:
            _stream(["apt-get", "-y", "autoremove", "--purge"], env, 1800)
    post = _snapshot("dopo l'aggiornamento")
    if post:
        _say(f"Snapshot \"dopo l'aggiornamento\" creato (#{post})")
    refresh_cache(checked=True)
    ok = rc == 0
    reboot = reboot_required()
    secs = int((datetime.datetime.now() - started).total_seconds())
    save_json(os.path.join(STATE, "updates-last.json"),
              {"ok": ok, "when": started.isoformat(timespec="seconds"), "seconds": secs, "packages": len(pk),
               "pre": pre, "post": post, "reboot": reboot}, 0o644)
    if ok:
        _say("Fatto. " + ("Serve un riavvio per completare (nuovo kernel o librerie di sistema)." if reboot
                          else "Nessun riavvio necessario."))
        notify.event("updates", "Aggiornamento completato",
                     "Serve un riavvio per completare." if reboot else "Il sistema è aggiornato.", level="info",
                     key=f"upd-done-{datetime.date.today()}")
    else:
        _say(f"ERRORE durante l'aggiornamento (codice {rc}). Il sistema si può riportare allo snapshot #{pre}."
             if pre else f"ERRORE durante l'aggiornamento (codice {rc}).")
        notify.event("updates", "Aggiornamento non riuscito",
                     "Controlla il registro in Impostazioni > Aggiornamenti di sistema.",
                     level="error", key=f"upd-fail-{datetime.datetime.now():%Y%m%d%H}")
    return ok


# --- snapshot ------------------------------------------------------------------------------------

def snapshots_available():
    return have("snapper") and os.path.exists("/etc/snapper/configs/root")


def _snapper(*args, timeout=300):
    return run(["snapper", "--no-dbus", "-c", "root"] + list(args), timeout=timeout)


def snapshots():
    if not snapshots_available():
        return {"available": False, "snapshots": []}
    out = run(["snapper", "--no-dbus", "--jsonout", "-c", "root", "list"], timeout=60)
    data = json.loads(out or "{}").get("root", [])
    res = []
    for s in data:
        if s.get("number") == 0:
            continue
        res.append({"number": s["number"], "type": s.get("type"), "pre": s.get("pre-number"),
                    "date": s.get("date"), "description": s.get("description"),
                    "important": "important" in (s.get("userdata") or {}),
                    "cleanup": s.get("cleanup")})
    return {"available": True, "snapshots": list(reversed(res))}


def create_snapshot(description):
    if not snapshots_available():
        raise ApiError("Gli snapshot funzionano solo con il disco di sistema in Btrfs")
    desc = re.sub(r"[^\w .,:()'-]", "", description or "")[:60] or "Manuale"
    out = _snapper("create", "--print-number", "--description", desc, "--userdata", "important=yes")
    return {"number": int(out.strip() or 0)}


def delete_snapshot(number):
    _snapper("delete", str(int(number)))
    return {"ok": True}


def restore_snapshot(number):
    n = int(number)
    # Snapshot di sicurezza dello stato attuale, per poter tornare indietro
    _snapper("create", "--description", f"Prima del ripristino a {n}", "--userdata", "important=yes")
    _snapper("undochange", f"{n}..0", timeout=1800)
    return {"ok": True, "reboot": True}
