"""Spegnimento e accensione programmati del NAS (Impostazioni -> Generale).

- Impostazioni: /etc/nido/power-schedule.json
  {"off": {"enabled", "days": [0..6], "time": "HH:MM"},
   "on":  {"enabled", "days": [0..6], "time": "HH:MM"},
   "max_wait": minuti, "notify": bool}
- Lo spegnimento parte dal timer nido-poweroff.timer (scritto da qui, Persistent=false: se il NAS era spento
  all'ora giusta non si spegne appena riacceso) che lancia "nidopanel.cli power-scheduled".
- Prima di spegnere aspetta che finiscano backup, aggiornamenti (anche quelli automatici di apt e delle app)
  e le altre operazioni lunghe, fino a "max_wait" minuti; se non finiscono lo spegnimento viene saltato.
- L'accensione usa la sveglia del PC (RTC) con rtcwake: viene impostata a ogni spegnimento, programmato o
  dall'interfaccia. Non tutti i PC si accendono da spenti con la sveglia: c'è una prova nell'interfaccia e
  un avviso se l'impostazione non riesce.
"""
import datetime
import os
import time

from .util import ApiError, ETC, STATE, have, load_json, run_rc, save_json, systemd_running, write_file

CONF = os.path.join(ETC, "power-schedule.json")
LAST = os.path.join(STATE, "power-schedule-last.json")
TIMER = "/etc/systemd/system/nido-poweroff.timer"
WAKEALARM = "/sys/class/rtc/rtc0/wakealarm"
DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
CAL = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
POLL = int(os.environ.get("NIDO_POWER_POLL", "30"))


def load():
    d = load_json(CONF, {}) or {}
    off = d.setdefault("off", {})
    off.setdefault("enabled", False)
    off.setdefault("days", [0, 1, 2, 3, 4, 5, 6])
    off.setdefault("time", "23:30")
    on = d.setdefault("on", {})
    on.setdefault("enabled", False)
    on.setdefault("days", [0, 1, 2, 3, 4, 5, 6])
    on.setdefault("time", "07:30")
    d.setdefault("max_wait", 120)
    d.setdefault("notify", True)
    return d


def _hhmm(v):
    import re
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", v or ""):
        raise ApiError("Orario non valido (es. 23:30)")
    h, m = v.split(":")
    return f"{int(h):02d}:{m}"


def _days(v):
    try:
        days = sorted({int(x) for x in v or []})
    except (TypeError, ValueError):
        raise ApiError("Giorni non validi")
    if any(x < 0 or x > 6 for x in days):
        raise ApiError("Giorni non validi")
    return days


def next_time(rule, after=None):
    """Prossima data e ora (datetime locale) di una regola {days, time}, dopo "after"."""
    after = after or datetime.datetime.now()
    if not rule.get("days"):
        return None
    h, m = int(rule["time"][:2]), int(rule["time"][3:])
    for i in range(0, 8):
        d = (after + datetime.timedelta(days=i)).replace(hour=h, minute=m, second=0, microsecond=0)
        if d.weekday() in rule["days"] and d > after:
            return d
    return None


def _when_text(dt):
    if not dt:
        return ""
    today = datetime.date.today()
    if dt.date() == today:
        day = "oggi"
    elif dt.date() == today + datetime.timedelta(days=1):
        day = "domani"
    else:
        day = f"{DAYS[dt.weekday()]} {dt.day}/{dt.month}"
    return f"{day} alle {dt:%H:%M}"


def get():
    d = load()
    off = next_time(d["off"]) if d["off"]["enabled"] else None
    on_after = off or datetime.datetime.now()
    on = next_time(d["on"], on_after + datetime.timedelta(minutes=5)) if d["on"]["enabled"] else None
    d["next_off"] = _when_text(off)
    d["next_on"] = _when_text(on)
    d["rtc"] = rtc_info()
    d["last"] = load_json(LAST, {})
    return d


def save(body):
    d = load()
    for k in ("off", "on"):
        b = body.get(k) or {}
        enabled = bool(b.get("enabled"))
        days = _days(b.get("days"))
        if enabled and not days:
            raise ApiError("Scegli almeno un giorno per " + ("lo spegnimento" if k == "off" else "l'accensione"))
        d[k] = {"enabled": enabled, "days": days, "time": _hhmm(b.get("time"))}
    try:
        mw = int(body.get("max_wait", d["max_wait"]))
    except (TypeError, ValueError):
        raise ApiError("Attesa massima non valida")
    if mw < 5 or mw > 720:
        raise ApiError("L'attesa massima va da 5 minuti a 12 ore")
    d["max_wait"] = mw
    d["notify"] = bool(body.get("notify", True))
    save_json(CONF, d, 0o644)
    _write_timer(d)
    if not d["on"]["enabled"]:
        clear_alarm()
    return get()


def _write_timer(d):
    if not systemd_running():
        return
    if d["off"]["enabled"] and d["off"]["days"]:
        days = ",".join(CAL[x] for x in d["off"]["days"])
        write_file(TIMER, "[Unit]\nDescription=Spegnimento programmato del NAS\n\n"
                          f"[Timer]\nOnCalendar={days} *-*-* {d['off']['time']}:00\nPersistent=false\nAccuracySec=30s\n\n"
                          "[Install]\nWantedBy=timers.target\n")
        run_rc(["systemctl", "daemon-reload"], timeout=30)
        run_rc(["systemctl", "enable", "nido-poweroff.timer"], timeout=30)
        run_rc(["systemctl", "restart", "nido-poweroff.timer"], timeout=30)
    else:
        run_rc(["systemctl", "disable", "--now", "nido-poweroff.timer"], timeout=30)


# --- sveglia del PC (RTC) -----------------------------------------------------------------------

def rtc_info():
    ok = os.path.exists(WAKEALARM) and have("rtcwake")
    alarm = ""
    try:
        with open(WAKEALARM) as f:
            v = f.read().strip()
        if v:
            alarm = _when_text(datetime.datetime.fromtimestamp(int(v)))
    except (OSError, ValueError):
        pass
    return {"available": ok, "alarm": alarm}


def set_alarm(dt):
    """Imposta la sveglia del PC. Restituisce (riuscito, messaggio)."""
    if not os.path.exists(WAKEALARM):
        return False, "questo PC non ha una sveglia (RTC) utilizzabile"
    if not have("rtcwake"):
        return False, "manca il comando rtcwake"
    t = int(dt.timestamp())
    run_rc(["rtcwake", "-m", "disable"], timeout=15)
    rc, out, err = run_rc(["rtcwake", "-m", "no", "-t", str(t)], timeout=15)
    try:
        with open(WAKEALARM) as f:
            got = int(f.read().strip() or 0)
    except (OSError, ValueError):
        got = 0
    if rc != 0 or abs(got - t) > 120:
        return False, (err or out).strip() or "la sveglia non è stata accettata"
    return True, ""


def clear_alarm():
    if os.path.exists(WAKEALARM) and have("rtcwake"):
        run_rc(["rtcwake", "-m", "disable"], timeout=15)


def test_rtc():
    """Prova a impostare la sveglia tra un'ora e la toglie subito."""
    ok, msg = set_alarm(datetime.datetime.now() + datetime.timedelta(hours=1))
    clear_alarm()
    if ok:
        return {"ok": True, "message": "La sveglia del PC funziona. Per esserne sicuri fai una prova vera: alcuni PC "
                                       "si accendono solo se nel BIOS/UEFI è attiva l'opzione \"Wake on RTC\" "
                                       "(o \"Power on by RTC\")."}
    return {"ok": False, "message": "La sveglia del PC non funziona: " + msg + ". L'accensione programmata non è possibile "
                                    "su questo PC (prova ad attivare \"Wake on RTC\" nel BIOS/UEFI)."}


def arm_wake():
    """Prima di ogni spegnimento: imposta la prossima accensione se è attiva. (riuscito o None, testo)."""
    d = load()
    if not d["on"]["enabled"]:
        clear_alarm()
        return None, ""
    when = next_time(d["on"], datetime.datetime.now() + datetime.timedelta(minutes=5))
    if not when:
        return None, ""
    ok, msg = set_alarm(when)
    return ok, (_when_text(when) if ok else msg)


# --- operazioni in corso -----------------------------------------------------------------------

def _proc_names():
    res = []
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                res.append(f.read().replace(b"\0", b" ").decode("utf-8", "replace"))
        except OSError:
            pass
    return res


def busy():
    """Elenco (in italiano) delle operazioni che impediscono lo spegnimento."""
    out = []
    if systemd_running():
        rc, txt, _ = run_rc(["systemctl", "list-units", "--type=service", "--state=active,activating",
                             "--no-legend", "--plain", "nido-job-*", "nido-apps-update.service",
                             "apt-daily-upgrade.service", "apt-daily.service", "unattended-upgrades.service"], timeout=20)
        for line in txt.splitlines():
            u = line.split()[0] if line.split() else ""
            if u.startswith("nido-job-backup") or u.startswith("nido-job-restore"):
                out.append("backup in corso")
            elif u.startswith("nido-job-updates") or u in ("apt-daily-upgrade.service", "apt-daily.service"):
                out.append("aggiornamento di sistema in corso")
            elif u == "nido-apps-update.service" or u.startswith("nido-job-app"):
                out.append("aggiornamento delle app in corso")
            elif u == "unattended-upgrades.service":
                continue    # resta sempre attivo: conta solo se sta davvero installando (sotto)
            elif u.startswith("nido-job-"):
                out.append("operazione in corso (" + u[9:].replace(".service", "") + ")")
    else:
        jd = os.path.join(STATE, "jobs")
        for f in os.listdir(jd) if os.path.isdir(jd) else []:
            if f.endswith(".pid"):
                try:
                    with open(os.path.join(jd, f)) as fh:
                        os.kill(int(fh.read().strip()), 0)
                    out.append("operazione in corso (" + f[9:-4] + ")")
                except (OSError, ValueError):
                    pass
    for c in _proc_names():
        exe = os.path.basename(c.split(" ")[0]) if c else ""
        if exe in ("dpkg", "apt-get", "apt") or "unattended-upgrade " in c and "--download-only" not in c and \
                "unattended-upgrade-shutdown" not in c:
            out.append("aggiornamento di sistema in corso")
        elif exe in ("restic", "rclone"):
            out.append("backup in corso")
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


# --- spegnimento ---------------------------------------------------------------------------------

def _host():
    import socket
    return socket.gethostname()


def _notify(d, title, message, level="info"):
    if not d.get("notify", True):
        return
    try:
        from . import notify
        if notify.load()["events"].get("power", True):
            notify.send(title, message, level, "power")
    except Exception:  # noqa: BLE001 — la notifica non deve bloccare lo spegnimento
        pass


def _last(**kw):
    kw["t"] = int(time.time())
    save_json(LAST, kw, 0o644)


def run_scheduled(dry_run=False):
    """Eseguito dal timer: aspetta le operazioni in corso, avvisa e spegne."""
    d = load()
    if not d["off"]["enabled"]:
        return 0
    name = _host()
    start = time.time()
    b = busy()
    if b:
        _notify(d, f"{name}: spegnimento programmato in attesa",
                "Aspetto che finisca: " + ", ".join(b) + f". Al massimo {d['max_wait']} minuti, poi lo spegnimento viene saltato.")
        while b and time.time() - start < d["max_wait"] * 60:
            time.sleep(POLL)
            b = busy()
        if b:
            _notify(d, f"{name}: spegnimento programmato saltato",
                    "Dopo " + str(d["max_wait"]) + " minuti è ancora in corso: " + ", ".join(b) + ". Il NAS resta acceso.", "warning")
            _last(result="skipped", reason=", ".join(b))
            return 1
    ok, wake = arm_wake()
    if ok is None:
        msg = "Si riaccende con il pulsante di accensione."
    elif ok:
        msg = f"Si riaccende da solo {wake}."
    else:
        msg = f"ATTENZIONE: l'accensione programmata non è stata impostata ({wake}). Per riaccenderlo usa il pulsante."
    waited = int((time.time() - start) / 60)
    _notify(d, f"{name}: spegnimento programmato",
            ("Il NAS si spegne adesso" + (f" (dopo {waited} minuti di attesa)" if waited else "") + ". ") + msg,
            "warning" if ok is False else "info")
    _last(result="poweroff", wake=wake if ok else "", wake_ok=ok, waited=waited)
    if dry_run:
        return 0
    run_rc(["sync"], timeout=120)
    run_rc(["systemctl", "poweroff"], timeout=30)
    return 0
