"""Backup con restic: incrementali, cifrati, con versioni precedenti dei file."""
import datetime
import json
import os
import re
import secrets

from .util import (ApiError, ETC, LOGS, STATE, check_name, check_path, have, job_state,
                   load_json, run, run_rc, save_json, start_job, tail, write_file)

CONF = os.path.join(ETC, "backup.json")
KEYS = os.path.join(ETC, "backup-keys")
STATUS = os.path.join(STATE, "backup")
UNIT_DIR = "/etc/systemd/system"
DAYS = {"lun": "Mon", "mar": "Tue", "mer": "Wed", "gio": "Thu", "ven": "Fri", "sab": "Sat", "dom": "Sun"}


def _jobs():
    return load_json(CONF, {"jobs": []}).get("jobs", [])


def _save_jobs(jobs):
    save_json(CONF, {"jobs": jobs}, 0o600)


def _get(job_id):
    for j in _jobs():
        if j["id"] == job_id:
            return j
    raise ApiError("Backup non trovato", 404)


def _status(job_id):
    return load_json(os.path.join(STATUS, f"{job_id}.json"), {})


def _log(job_id):
    return os.path.join(LOGS, f"backup-{job_id}.log")


def list_jobs():
    res = []
    for j in _jobs():
        st = _status(j["id"])
        res.append({**j, "status": st, "running": job_state(f"backup-{j['id']}") in ("active", "activating")})
    return {"jobs": res, "restic": have("restic"), "rclone": have("rclone")}


def rclone_remotes():
    if not have("rclone"):
        return {"available": False, "remotes": []}
    rc, out, _ = run_rc(["rclone", "listremotes"], timeout=20)
    return {"available": True, "remotes": [r.strip() for r in out.splitlines() if r.strip().endswith(":")]}


def summary():
    return [{"name": j["name"], "last_run": _status(j["id"]).get("finished"),
             "ok": _status(j["id"]).get("ok")} for j in _jobs()]


def _repository(job):
    d = job["destination"]
    if d["type"] == "folder":
        return d["path"]
    if d["type"] == "rclone":
        return f"rclone:{d['remote']}"
    raise ApiError("Destinazione non valida")


def _env(job):
    return {"RESTIC_REPOSITORY": _repository(job),
            "RESTIC_PASSWORD_FILE": os.path.join(KEYS, job["id"]),
            "RESTIC_CACHE_DIR": "/var/cache/restic"}


def _write_timer(job):
    name = f"nido-backup-{job['id']}"
    sched = job.get("schedule", {})
    timer_path = os.path.join(UNIT_DIR, name + ".timer")
    service_path = os.path.join(UNIT_DIR, name + ".service")
    if sched.get("type") in ("daily", "weekly"):
        hh, mm = sched.get("time", "03:00").split(":")
        if sched["type"] == "daily":
            cal = f"*-*-* {int(hh):02d}:{int(mm):02d}:00"
        else:
            cal = f"{DAYS.get(sched.get('day', 'dom'), 'Sun')} *-*-* {int(hh):02d}:{int(mm):02d}:00"
        write_file(service_path,
                   f"[Unit]\nDescription=Backup {job['name']}\n\n[Service]\nType=oneshot\n"
                   f"Environment=PYTHONPATH=/usr/lib/nido/panel\n"
                   f"ExecStart=/usr/bin/python3 -m nidopanel.cli backup-run {job['id']}\n"
                   f"StandardOutput=append:{_log(job['id'])}\nStandardError=append:{_log(job['id'])}\n")
        write_file(timer_path,
                   f"[Unit]\nDescription=Pianificazione backup {job['name']}\n\n[Timer]\n"
                   f"OnCalendar={cal}\nPersistent=true\nRandomizedDelaySec=120\n\n"
                   f"[Install]\nWantedBy=timers.target\n")
        run(["systemctl", "daemon-reload"], check=False)
        run(["systemctl", "enable", "--now", name + ".timer"], check=False)
    else:
        _remove_timer(job["id"])


def _remove_timer(job_id):
    name = f"nido-backup-{job_id}"
    run(["systemctl", "disable", "--now", name + ".timer"], check=False)
    for ext in (".timer", ".service"):
        try:
            os.unlink(os.path.join(UNIT_DIR, name + ext))
        except FileNotFoundError:
            pass
    run(["systemctl", "daemon-reload"], check=False)


def save(body, job_id=None):
    if not have("restic"):
        raise ApiError("restic non è installato")
    name = check_name(body.get("name"), "Nome del backup")
    sources = []
    for s in body.get("sources") or []:
        real = os.path.realpath(s)
        if real == "/DATA/AppData" or real.startswith("/DATA/AppData/"):
            if not os.path.isdir(real):
                raise ApiError(f"La cartella {s} non esiste")
            sources.append(real)
        else:
            sources.append(check_path(s))
    if not sources:
        raise ApiError("Scegli almeno una cartella da salvare")

    dest = body.get("destination") or {}
    if dest.get("type") == "folder":
        path = os.path.realpath(dest.get("path") or "")
        check_path(os.path.dirname(path))
        if any(path == s or path.startswith(s + "/") for s in sources):
            raise ApiError("La destinazione non può stare dentro una cartella da salvare")
        destination = {"type": "folder", "path": path}
    elif dest.get("type") == "rclone":
        remote = (dest.get("remote") or "").strip()
        if not re.match(r"^[A-Za-z0-9_.-]+:[^\s]*$", remote):
            raise ApiError("Destinazione rclone non valida (es. gdrive:backup-nas)")
        destination = {"type": "rclone", "remote": remote}
    else:
        raise ApiError("Scegli dove salvare il backup")

    sched = body.get("schedule") or {"type": "manual"}
    if sched.get("type") not in ("manual", "daily", "weekly"):
        raise ApiError("Pianificazione non valida")
    if sched["type"] != "manual" and not re.match(r"^\d{1,2}:\d{2}$", sched.get("time", "")):
        raise ApiError("Orario non valido (es. 03:00)")
    if sched["type"] == "weekly" and sched.get("day") not in DAYS:
        raise ApiError("Giorno non valido")

    keep = body.get("keep") or {}
    keep = {k: max(0, min(int(keep.get(k, d)), 999)) for k, d in
            (("daily", 7), ("weekly", 4), ("monthly", 6))}

    jobs = _jobs()
    job = {
        "id": job_id or secrets.token_hex(4), "name": name, "sources": sources,
        "destination": destination, "schedule": sched, "keep": keep,
        "stop_apps": bool(body.get("stop_apps")),
        "notify_ok": bool(body.get("notify_ok")),
    }
    if job_id:
        if not any(j["id"] == job_id for j in jobs):
            raise ApiError("Backup non trovato", 404)
        jobs = [job if j["id"] == job_id else j for j in jobs]
    else:
        jobs.append(job)
        os.makedirs(KEYS, mode=0o700, exist_ok=True)
        key = (body.get("password") or "").strip() or secrets.token_urlsafe(24)
        if len(key) < 8:
            raise ApiError("La chiave deve avere almeno 8 caratteri")
        write_file(os.path.join(KEYS, job["id"]), key + "\n", 0o600)
    _save_jobs(jobs)
    _write_timer(job)
    return job


def delete(job_id):
    jobs = _jobs()
    if not any(j["id"] == job_id for j in jobs):
        raise ApiError("Backup non trovato", 404)
    _remove_timer(job_id)
    _save_jobs([j for j in jobs if j["id"] != job_id])
    # La chiave resta in backup-keys/eliminati: senza di essa i dati salvati non si recuperano
    src = os.path.join(KEYS, job_id)
    if os.path.exists(src):
        os.makedirs(os.path.join(KEYS, "eliminati"), mode=0o700, exist_ok=True)
        os.replace(src, os.path.join(KEYS, "eliminati", job_id))
    return {"ok": True}


def key(job_id):
    _get(job_id)
    with open(os.path.join(KEYS, job_id), encoding="utf-8") as f:
        return {"key": f.read().strip()}


def start(job_id):
    _get(job_id)
    start_job(f"backup-{job_id}", ["backup-run", job_id], log=_log(job_id))
    return {"ok": True}


def log(job_id):
    return {"log": tail(_log(job_id), 150),
            "running": job_state(f"backup-{job_id}") in ("active", "activating")}


def snapshots(job_id):
    job = _get(job_id)
    rc, out, err = run_rc(["restic", "snapshots", "--json"], env=_env(job), timeout=300)
    if rc != 0:
        raise ApiError("Non riesco a leggere il backup: " + (err.strip().splitlines() or ["errore"])[-1])
    res = []
    for s in json.loads(out or "[]"):
        res.append({"id": s.get("short_id") or s["id"][:8], "time": s.get("time"),
                    "paths": s.get("paths", []), "hostname": s.get("hostname")})
    return {"snapshots": sorted(res, key=lambda s: s["time"] or "", reverse=True)}


def restore(job_id, body):
    _get(job_id)
    snap = body.get("snapshot") or ""
    if not re.match(r"^[0-9a-f]{8,64}$|^latest$", snap):
        raise ApiError("Versione non valida")
    target = body.get("target") or f"/DATA/Ripristini/{datetime.datetime.now():%Y-%m-%d_%H%M}"
    parent = check_path(os.path.dirname(os.path.realpath(target)), must_exist=False)
    os.makedirs(parent, exist_ok=True)
    target = os.path.join(parent, os.path.basename(target.rstrip("/")))
    start_job(f"backup-{job_id}", ["backup-restore", job_id, snap, target], log=_log(job_id))
    return {"ok": True, "target": target}


# --- esecuzione (chiamata da cli.py) ------------------------------------------------------

def run_job(job_id):
    from . import notify
    job = _get(job_id)
    env = _env(job)
    started = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"=== {started} backup \"{job['name']}\"", flush=True)
    stopped = []
    status = {"started": started, "ok": False}
    try:
        if job["destination"]["type"] == "folder":
            os.makedirs(job["destination"]["path"], exist_ok=True)
        rc, _, _ = run_rc(["restic", "cat", "config"], env=env, timeout=120)
        if rc != 0:
            print("Inizializzo l'archivio del backup...", flush=True)
            run(["restic", "init"], env=env, timeout=600)
        if job.get("stop_apps"):
            rc, out, _ = run_rc(["docker", "ps", "-q"], timeout=30)
            stopped = out.split()
            if stopped:
                print(f"Fermo {len(stopped)} app...", flush=True)
                run(["docker", "stop"] + stopped, check=False, timeout=600)
        rc, out, err = run_rc(["restic", "backup", "--json", "--exclude-caches",
                               "--exclude", ".cestino"] + job["sources"],
                              env=env, timeout=24 * 3600)
        summary = {}
        for line in out.splitlines():
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("message_type") == "summary":
                summary = m
        if rc not in (0, 3):  # 3 = alcuni file non leggibili, backup comunque creato
            raise RuntimeError((err.strip().splitlines() or [f"errore {rc}"])[-1])
        status["summary"] = {k: summary.get(k) for k in
                             ("files_new", "files_changed", "files_unmodified",
                              "data_added", "total_files_processed", "total_bytes_processed",
                              "snapshot_id")}
        if rc == 3:
            status["warning"] = "Alcuni file non erano leggibili e sono stati saltati"
        k = job["keep"]
        print("Elimino le versioni vecchie...", flush=True)
        run(["restic", "forget", "--prune", "--keep-daily", str(k["daily"]),
             "--keep-weekly", str(k["weekly"]), "--keep-monthly", str(k["monthly"])],
            env=env, check=False, timeout=6 * 3600)
        status["ok"] = True
        print("Backup completato.", flush=True)
    except Exception as e:  # noqa: BLE001 — qualunque errore va riportato all'utente
        msg = e.message if isinstance(e, ApiError) else str(e)
        status["error"] = msg
        print(f"ERRORE: {msg}", flush=True)
    finally:
        if stopped:
            print("Riavvio le app...", flush=True)
            run(["docker", "start"] + stopped, check=False, timeout=600)
        status["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_json(os.path.join(STATUS, f"{job_id}.json"), status, 0o644)
    if status["ok"]:
        if job.get("notify_ok"):
            notify.event("backup_ok", f"Backup \"{job['name']}\" completato",
                         f"Dati aggiunti: {_fmt((status.get('summary') or {}).get('data_added'))}",
                         level="info", key=f"backup-ok-{job_id}-{status['finished']}")
    else:
        notify.event("backup_fail", f"Backup \"{job['name']}\" non riuscito",
                     status.get("error", ""), level="error",
                     key=f"backup-fail-{job_id}-{status['finished']}")
    return status["ok"]


def run_restore(job_id, snap, target):
    job = _get(job_id)
    print(f"=== ripristino {snap} in {target}", flush=True)
    rc, out, err = run_rc(["restic", "restore", snap, "--target", target],
                          env=_env(job), timeout=24 * 3600)
    print(out[-2000:], err[-2000:], flush=True)
    print("Ripristino completato." if rc == 0 else f"ERRORE nel ripristino ({rc})", flush=True)
    return rc == 0


def _fmt(n):
    from .util import human_bytes
    return human_bytes(n or 0)
