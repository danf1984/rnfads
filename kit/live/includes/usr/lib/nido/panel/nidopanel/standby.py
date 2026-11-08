"""Standby dei dischi: spegne i dischi rotanti che non lavorano da un po'.

Al posto del timer interno del disco (hdparm -S) c'è un piccolo servizio (nido-standby) che legge
/proc/diskstats: se un disco non fa letture né scritture per il tempo scelto lo mette in standby
con "hdparm -y". Così si possono avere anche l'eccezione oraria per i backup, il conteggio delle
accensioni e lo stesso comportamento con i dischi USB (dove -S spesso non funziona).

- Impostazioni: /etc/nido/standby.json  {"disks": {<id>: {minutes, backup_window, apm, schedule}}, "window": {...},
  "schedule": {"enabled", "idle", "rules": [{"mode": "standby"|"on", "days": [0..6], "from", "to"}]}}
- Programma settimanale: nelle fasce "standby" i dischi si spengono dopo pochi minuti senza attività (anche se il
  loro tempo è "Mai"), nelle fasce "on" restano sempre accesi; fuori dalle fasce vale il tempo del disco.
  Se due fasce si sovrappongono vince "sempre accesi".
- Stato del servizio: /run/nido/standby.json (letto dall'interfaccia)
- Il disco di sistema non si spegne mai.
"""
import datetime
import os
import re
import time

from .util import ApiError, ETC, have, load_json, run_rc, save_json

CONF = os.path.join(ETC, "standby.json")
STATE = os.environ.get("NIDO_STANDBY_STATE", "/run/nido/standby.json")
SIM = "/run/nido/standby-sim.json"      # solo prove con i dischi loop (NIDO_TEST_LOOP=1)
MANUAL = "/run/nido/standby-manual.json"  # "spegni adesso" dall'interfaccia: {id: ora}
CHOICES = [0, 5, 10, 20, 30, 60, 120, 240]
APM = {"": None, "performance": 254, "balanced": 128, "saving": 64}
INTERVAL = int(os.environ.get("NIDO_STANDBY_INTERVAL", "20"))


def load():
    data = load_json(CONF, {}) or {}
    data.setdefault("disks", {})
    w = data.setdefault("window", {})
    w.setdefault("from", "02:00")
    w.setdefault("to", "04:00")
    sc = data.setdefault("schedule", {})
    sc.setdefault("enabled", False)
    sc.setdefault("idle", 5)
    sc.setdefault("rules", [])
    return data


def state():
    return load_json(STATE, {"disks": {}, "t": 0})


def _hhmm(v):
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", v or ""):
        raise ApiError("Orario non valido (es. 02:00)")
    h, m = v.split(":")
    return f"{int(h):02d}:{m}"


def set_disk(body):
    from . import disks
    did = body.get("id") or ""
    d = next((x for x in disks.list_disks(with_smart=False) if x["id"] == did), None)
    if not d:
        raise ApiError("Disco non trovato", 404)
    if d["protected"]:
        raise ApiError("Il disco di sistema resta sempre acceso")
    try:
        minutes = int(body.get("minutes") or 0)
    except (TypeError, ValueError):
        raise ApiError("Tempo non valido")
    if minutes < 0 or minutes > 24 * 60 or (0 < minutes < 2):
        raise ApiError("Scegli un tempo tra 2 minuti e 24 ore (oppure Mai)")
    apm = body.get("apm") or ""
    if apm not in APM:
        raise ApiError("Valore APM non valido")
    data = load()
    data["disks"][did] = {"minutes": minutes, "backup_window": bool(body.get("backup_window", True)),
                          "apm": apm, "name": d["display"], "schedule": bool(body.get("schedule", True))}
    if body.get("window"):
        data["window"] = {"from": _hhmm(body["window"].get("from")), "to": _hhmm(body["window"].get("to"))}
    save_json(CONF, data, 0o644)
    if apm and APM[apm] and not d["path"].startswith("/dev/loop"):
        run_rc(["hdparm", "-B", str(APM[apm]), d["path"]], timeout=20)
    return {"ok": True, "config": data["disks"][did]}


DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def set_schedule(body):
    """Programma settimanale (uguale per tutti i dischi che lo seguono)."""
    rules = []
    for r in (body.get("rules") or [])[:20]:
        mode = r.get("mode")
        if mode not in ("standby", "on"):
            raise ApiError("Tipo di fascia non valido")
        try:
            days = sorted({int(x) for x in r.get("days") or []})
        except (TypeError, ValueError):
            raise ApiError("Giorni non validi")
        if not days or any(x < 0 or x > 6 for x in days):
            raise ApiError("Scegli almeno un giorno per ogni fascia")
        rules.append({"mode": mode, "days": days, "from": _hhmm(r.get("from")), "to": _hhmm(r.get("to"))})
    try:
        idle = int(body.get("idle") or 5)
    except (TypeError, ValueError):
        raise ApiError("Minuti non validi")
    if idle < 1 or idle > 120:
        raise ApiError("Nelle fasce di standby scegli tra 1 e 120 minuti senza attività")
    enabled = bool(body.get("enabled"))
    if enabled and not rules:
        raise ApiError("Aggiungi almeno una fascia oraria")
    data = load()
    data["schedule"] = {"enabled": enabled, "idle": idle, "rules": rules}
    save_json(CONF, data, 0o644)
    return data["schedule"]


def _mins(v):
    return int(v[:2]) * 60 + int(v[3:])


def schedule_mode(sched, now=None):
    """Fascia attiva adesso: (None | "standby" | "on", minuto della settimana in cui finisce)."""
    if not sched or not sched.get("enabled"):
        return None, None
    now = now or datetime.datetime.now()
    cur = now.weekday() * 1440 + now.hour * 60 + now.minute
    found = {}
    for r in sched.get("rules", []):
        f, t = _mins(r["from"]), _mins(r["to"])
        length = (t - f) % 1440 or 1440           # stessa ora = tutto il giorno; t < f = passa la mezzanotte
        for d in r["days"]:
            start = d * 1440 + f
            for c in (cur, cur + 7 * 1440):
                if start <= c < start + length:
                    end = (start + length) % (7 * 1440)
                    if r["mode"] not in found or r["mode"] == "on":
                        found[r["mode"]] = end
    if "on" in found:
        return "on", found["on"]
    if "standby" in found:
        return "standby", found["standby"]
    return None, None


def _until_text(end):
    if end is None:
        return ""
    d, m = divmod(end, 1440)
    today = datetime.datetime.now().weekday()
    day = "" if d == today else (" di domani" if d == (today + 1) % 7 else f" di {DAYS[d]}")
    return f"fino alle {m // 60:02d}:{m % 60:02d}{day}"


def schedule_now():
    sc = load()["schedule"]
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    mode, end = schedule_mode(sc, now)
    if mode is None:
        return {"mode": None, "until": ""}
    # fasce attaccate (es. tutti i giorni 00:00-00:00): cerca il vero momento in cui cambia
    t = now
    for _ in range(7 * 24 * 4):
        t += datetime.timedelta(minutes=15)
        m, e = schedule_mode(sc, t)
        if m != mode:
            break
        if e is not None:
            end = e
    else:
        return {"mode": mode, "until": "sempre"}
    return {"mode": mode, "until": _until_text(end)}


def set_window(body):
    data = load()
    data["window"] = {"from": _hhmm(body.get("from")), "to": _hhmm(body.get("to"))}
    save_json(CONF, data, 0o644)
    return data["window"]


# --- stato e comandi del disco ---------------------------------------------------------------

def _sim():
    return load_json(SIM, {})


def power_state(dev):
    """"active", "standby" o "unknown". hdparm -C non sveglia il disco."""
    if dev.startswith("/dev/loop"):
        return _sim().get(dev, "active")
    if not have("hdparm"):
        return "unknown"
    rc, out, _ = run_rc(["hdparm", "-C", dev], timeout=15)
    m = re.search(r"drive state is:\s*(.+)", out)
    s = (m.group(1).strip() if m else "").lower()
    if "standby" in s or "sleeping" in s:
        return "standby"
    if "active" in s or "idle" in s:
        return "active"
    return "unknown"


def spin_down(dev):
    if dev.startswith("/dev/loop"):
        sim = _sim()
        sim[dev] = "standby"
        save_json(SIM, sim, 0o644)
        return True, ""
    rc, out, err = run_rc(["hdparm", "-y", dev], timeout=30)
    return rc == 0, (err or out).strip()


def sleep_now(disk_path):
    from . import disks
    d = next((x for x in disks.list_disks(with_smart=False) if x["path"] == disk_path), None)
    if not d:
        raise ApiError("Disco non trovato", 404)
    if d["protected"]:
        raise ApiError("Il disco di sistema resta sempre acceso")
    run_rc(["sync"], timeout=60)
    ok, err = spin_down(d["path"])
    if not ok:
        raise ApiError("Il disco non accetta il comando di standby" + (f": {err}" if err else ""))
    man = load_json(MANUAL, {})
    man[d["id"]] = int(time.time())
    os.makedirs(os.path.dirname(MANUAL), exist_ok=True)
    save_json(MANUAL, man, 0o644)
    return {"ok": True}


def _write_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    save_json(STATE, st, 0o644)


def _in_window(w, now=None):
    now = now or datetime.datetime.now()
    cur = now.hour * 60 + now.minute
    f = int(w["from"][:2]) * 60 + int(w["from"][3:])
    t = int(w["to"][:2]) * 60 + int(w["to"][3:])
    return f <= cur < t if f <= t else (cur >= f or cur < t)


def _diskstats():
    res = {}
    try:
        with open("/proc/diskstats", encoding="ascii") as f:
            for line in f:
                p = line.split()
                if len(p) >= 10:
                    # letture completate, settori letti, scritture completate, settori scritti
                    res[p[2]] = (int(p[3]), int(p[5]), int(p[7]), int(p[9]))
    except OSError:
        pass
    return res


def info_for(d):
    """Riassunto per l'interfaccia di un disco (impostazioni + stato attuale)."""
    conf = load()
    c = conf["disks"].get(d["id"], {"minutes": 0, "backup_window": True, "apm": ""})
    s = dict(state().get("disks", {}).get(d["id"], {}))
    t = load_json(MANUAL, {}).get(d["id"], 0)
    if t > (s.get("manual_t") or 0) and t > (s.get("since") or 0):
        s.update({"state": "standby", "since": t})
    today = datetime.date.today().isoformat()
    return {"minutes": c.get("minutes", 0), "backup_window": c.get("backup_window", True), "apm": c.get("apm", ""),
            "schedule": c.get("schedule", True),
            "state": s.get("state") or ("active" if d["protected"] else "unknown"),
            "since": s.get("since"), "last_io": s.get("last_io"),
            "spinups_today": s.get("spinups", 0) if s.get("day") == today else 0,
            "error": s.get("error")}


# --- servizio ------------------------------------------------------------------------------------

def run_daemon(once=False):
    from . import disks
    st = state()
    st.setdefault("disks", {})
    known = {}
    conf_mtime = None
    applied_apm = {}
    last_list = 0
    while True:
        now = time.time()
        if now - last_list > 60 or not known:
            try:
                known = {d["id"]: d for d in disks.list_disks(with_smart=False)}
            except Exception:  # noqa: BLE001 — lsblk temporaneamente non disponibile
                pass
            last_list = now
        try:
            m = os.path.getmtime(CONF)
        except OSError:
            m = None
        if m != conf_mtime:
            conf_mtime = m
            applied_apm = {}
        conf = load()
        stats = _diskstats()
        window = _in_window(conf["window"])
        smode, _ = schedule_mode(conf["schedule"])
        today = datetime.date.today().isoformat()
        manual = load_json(MANUAL, {})
        for did, d in known.items():
            if d["protected"]:
                continue
            c = conf["disks"].get(did, {})
            dev, name = d["path"], d["name"]
            s = st["disks"].setdefault(did, {})
            if s.get("day") != today:
                s["day"], s["spinups"] = today, 0
            mt = manual.get(did, 0)
            if mt > (s.get("manual_t") or 0):
                s["manual_t"] = mt
                s["state"], s["since"] = "standby", mt
                if stats.get(name):
                    s["io"] = list(stats[name])
            # APM: una volta all'avvio, quando cambia l'impostazione o quando il disco ricompare
            apm = APM.get(c.get("apm") or "")
            if apm and applied_apm.get(did) != (dev, apm) and not dev.startswith("/dev/loop"):
                run_rc(["hdparm", "-B", str(apm), dev], timeout=20)
                applied_apm[did] = (dev, apm)
            cur = stats.get(name)
            if cur is None:
                continue
            if s.get("io") != list(cur):
                if s.get("io") is not None and s.get("state") == "standby":
                    s["spinups"] = s.get("spinups", 0) + 1
                    s["state"], s["since"] = "active", int(now)
                    if dev.startswith("/dev/loop"):
                        sim = _sim()
                        sim[dev] = "active"
                        save_json(SIM, sim, 0o644)
                s["io"] = list(cur)
                s["last_io"] = int(now)
                if s.get("state") != "standby":
                    s["state"] = "active"
            minutes = int(c.get("minutes") or 0)
            follows = c.get("schedule", True)
            if follows and smode == "on":
                continue                                  # fascia "sempre accesi"
            if follows and smode == "standby":
                sm = int(conf["schedule"].get("idle") or 5)
                minutes = min(minutes, sm) if minutes > 0 else sm
            if minutes <= 0 or s.get("state") == "standby":
                continue
            if c.get("backup_window", True) and window:
                continue
            if now - s.get("last_io", now) >= minutes * 60:
                ps = power_state(dev)
                if ps == "standby":
                    s["state"], s["since"] = "standby", int(now)
                    continue
                ok, err = spin_down(dev)
                if ok:
                    s["state"], s["since"] = "standby", int(now)
                    s.pop("error", None)
                    # il comando stesso non deve contare come attività
                    s["io"] = list(_diskstats().get(name, cur))
                else:
                    s["error"] = err or "comando di standby non accettato"
                    s["last_io"] = int(now)     # riprova al prossimo intervallo pieno
        st["t"] = int(now)
        _write_state(st)
        if once:
            return st
        time.sleep(INTERVAL)
