"""Sposta le app su un altro disco (Docker e AppData), con copia controllata e ritorno indietro.

Dopo l'installazione Docker (/var/lib/docker, sottovolume @docker) e i dati delle app
(/DATA/AppData, sottovolume @appdata) stanno sul disco di sistema. Lo spostamento:

 1. controlli: disco montato "a ogni avvio", file system Linux (ext4, XFS, Btrfs), spazio;
 2. app fermate, poi Docker (e containerd, se Docker tiene lì le immagini);
 3. copia con rsync (-aHAX, proprietari e permessi uguali) e secondo passaggio di controllo:
    se trova ancora differenze lo spostamento si ferma e non cambia niente;
 4. i percorsi NON cambiano: le cartelle copiate vengono montate (bind) su /var/lib/docker e
    /DATA/AppData da /etc/fstab, così compose, condivisioni e backup restano uguali.
    Le righe vecchie restano in fstab come commento (copia in /etc/fstab.nido-prima-dello-spostamento);
 5. Docker e le app ripartono; se qualcosa non riparte si torna da soli alla situazione di prima.

I dati vecchi restano sul disco di sistema finché non si preme "Libera lo spazio".
Se Docker usa il driver "btrfs" e il disco nuovo non è Btrfs, le immagini non si possono copiare
così come sono: vengono esportate (docker save) e ricaricate (docker load) sul disco nuovo.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import time

from .util import (ApiError, ETC, LOGS, STATE, job_state, load_json, product, read_file, run_rc, save_json,
                   start_job, write_file)

FILE = os.path.join(ETC, "apps-location.json")
LOG = os.path.join(LOGS, "apps-move.log")
FSTAB = os.environ.get("NIDO_FSTAB", "/etc/fstab")
FSTAB_BACKUP = "/etc/fstab.nido-prima-dello-spostamento"
MARK = "# nido-app-location"
OLD = "#nido-spostato# "
DOCKER, CONTAINERD, APPDATA = "/var/lib/docker", "/var/lib/containerd", "/DATA/AppData"
DROPIN = {"docker": "/etc/systemd/system/docker.service.d/20-nido-disco-app.conf",
          "containerd": "/etc/systemd/system/containerd.service.d/20-nido-disco-app.conf"}
GOOD_FS = ("ext4", "xfs", "btrfs")
_sizes = {"t": 0, "v": None}


def _say(text):
    print(f"[{datetime.datetime.now():%d/%m %H:%M:%S}] {text}", flush=True)


def _findmnt(path):
    rc, out, _ = run_rc(["findmnt", "-n", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "-T", path], timeout=10)
    f = out.split()
    return {"target": f[0], "source": f[1], "fstype": f[2], "options": f[3]} if len(f) >= 4 else {}


def _docker_info():
    rc, out, _ = run_rc(["docker", "info", "--format", "{{json .}}"], timeout=30)
    try:
        d = json.loads(out)
    except ValueError:
        return {"ok": False, "driver": "", "containerd_store": False, "root": DOCKER}
    status = json.dumps(d.get("DriverStatus") or [])
    return {"ok": True, "driver": d.get("Driver") or "", "root": d.get("DockerRootDir") or DOCKER,
            "containerd_store": "io.containerd.snapshotter" in status}


def _du(path):
    if not os.path.isdir(path):
        return 0
    rc, out, _ = run_rc(["du", "-sxb", path], timeout=180)
    try:
        return int(out.split()[0])
    except (ValueError, IndexError):
        return 0


def sizes(fresh=False):
    if fresh or not _sizes["v"] or time.time() - _sizes["t"] > 600:
        info = _docker_info()
        v = {"docker": _du(DOCKER), "appdata": _du(APPDATA),
             "containerd": _du(CONTAINERD) if info["containerd_store"] else 0, "info": info}
        _sizes.update(t=time.time(), v=v)
    return _sizes["v"]


def _app_dir_name():
    return re.sub(r"[^a-z0-9]+", "-", product()[0].lower()).strip("-") + "-app"


def _candidates(total):
    from .disks import fstab_entries
    auto = set(fstab_entries().values())
    res = []
    for line in read_file("/proc/self/mounts").splitlines():
        f = line.split()
        if len(f) < 3:
            continue
        mp = f[1].replace("\\040", " ")
        if not mp.startswith("/media/") or mp.startswith(("/media/rete/", "/media/cloud/")):
            continue
        try:
            st = os.statvfs(mp)
            free = st.f_bavail * st.f_frsize
            size = st.f_blocks * st.f_frsize
        except OSError:
            continue
        why = None
        if f[2] not in GOOD_FS:
            why = f"file system {f[2]}: servono ext4, XFS o Btrfs (proprietari e permessi Linux)"
        elif mp not in auto:
            why = "non è montato a ogni avvio: attivalo in Dischi"
        elif "ro" in f[3].split(","):
            why = "montato in sola lettura"
        elif free < total * 1.1 + 2 * 1024 ** 3:
            why = "spazio libero insufficiente"
        res.append({"path": mp, "name": os.path.basename(mp), "fstype": f[2], "free": free, "size": size,
                    "ok": why is None, "why": why})
    return res


def status():
    loc = load_json(FILE, {})
    sz = sizes()
    total = sz["docker"] + sz["appdata"] + sz["containerd"]
    running = job_state("apps-move") in ("active", "activating") or job_state("apps-move-back") in ("active", "activating")
    return {"location": loc.get("disk") or "system", "info": loc, "sizes": sz, "total": total,
            "candidates": [] if loc.get("disk") else _candidates(total), "running": running,
            "log_size": os.path.getsize(LOG) if os.path.exists(LOG) else 0,
            "last": load_json(os.path.join(STATE, "apps-move-last.json"), {})}


def start(path, confirm):
    if (confirm or "").strip().upper() != "SPOSTA":
        raise ApiError("Per confermare scrivi SPOSTA")
    if load_json(FILE, {}).get("disk"):
        raise ApiError("Le app sono già su un altro disco: prima riportale sul disco di sistema")
    st = status()
    c = next((x for x in st["candidates"] if x["path"] == path), None)
    if not c:
        raise ApiError("Disco non trovato tra quelli montati in /media")
    if not c["ok"]:
        raise ApiError(f"Questo disco non va bene: {c['why']}")
    if st["running"]:
        raise ApiError("C'è già uno spostamento in corso", 409)
    start_job("apps-move", ["apps-move", path], log=LOG)
    return {"ok": True}


def start_back(confirm):
    if (confirm or "").strip().upper() != "RIPORTA":
        raise ApiError("Per confermare scrivi RIPORTA")
    if not load_json(FILE, {}).get("disk"):
        raise ApiError("Le app sono già sul disco di sistema")
    start_job("apps-move-back", ["apps-move-back"], log=LOG)
    return {"ok": True}


def log_since(offset=0):
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
    running = job_state("apps-move") in ("active", "activating") or job_state("apps-move-back") in ("active", "activating")
    return {"text": text, "offset": size, "running": running}


# --- passi --------------------------------------------------------------------------------------

def _sh(cmd, timeout=600, check=True):
    rc, out, err = run_rc(cmd, timeout=timeout)
    if check and rc != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {(err or out).strip()[-300:]}")
    return rc, out


def _rsync(src, dst, label):
    """Copia con avanzamento nel registro (ogni 5%)."""
    os.makedirs(dst, exist_ok=True)
    cmd = ["rsync", "-aHAX", "--numeric-ids", "--delete", "--info=progress2", "--no-inc-recursive",
           src.rstrip("/") + "/", dst.rstrip("/") + "/"]
    _say(f"Copio {label}: {src} → {dst}")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    buf, last, tail = b"", -5, []
    while True:
        ch = p.stdout.read(4096)
        if not ch:
            break
        buf += ch
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for raw in parts:
            line = raw.decode("utf-8", "replace").strip()
            m = re.search(r"\s(\d+)%\s+(\S+/s)", line)
            if m:
                pct = int(m.group(1))
                if pct >= last + 5:
                    last = pct
                    print(f"    {label}: {pct}% · {m.group(2)}", flush=True)
            elif line:
                tail = (tail + [line])[-5:]
    rc = p.wait()
    if rc not in (0, 24):          # 24 = file spariti durante la copia (non succede con tutto fermo)
        raise RuntimeError(f"copia di {label} non riuscita (rsync {rc}): {' / '.join(tail)}")


def _verify(src, dst, label):
    """Secondo passaggio: rsync in prova non deve trovare più nessuna differenza."""
    rc, out, err = run_rc(["rsync", "-aHAXn", "--numeric-ids", "--delete", "--out-format=%n",
                           src.rstrip("/") + "/", dst.rstrip("/") + "/"], timeout=3600)
    diff = [ln for ln in out.splitlines() if ln.strip() and ln.strip() not in ("./", ".")]
    if rc != 0 or diff:
        raise RuntimeError(f"controllo della copia di {label}: {len(diff)} differenze ({', '.join(diff[:3])})")
    _say(f"Controllo di {label}: copia identica")


def _running_projects():
    rc, out, _ = run_rc(["docker", "ps", "--format", "{{.Names}}\t{{.Label \"com.docker.compose.project\"}}"], timeout=60)
    names, projects = [], set()
    for line in out.splitlines():
        n, _, proj = line.partition("\t")
        names.append(n)
        if proj:
            projects.add(proj)
    return names, projects


def _stop_all(info):
    from . import apps
    _say("Fermo le app")
    for name in apps._app_names():
        run_rc(apps._compose_cmd(name, "stop"), timeout=300)
    run_rc(["docker", "stop", "-t", "30"] + _running_projects()[0], timeout=600)
    _say("Fermo Docker")
    for u in ("docker.socket", "docker.service"):
        run_rc(["systemctl", "stop", u], timeout=180)
    if info["containerd_store"]:
        run_rc(["systemctl", "stop", "containerd.service"], timeout=120)


def _start_all(info, names, projects):
    from . import apps
    _say("Avvio Docker")
    if info.get("containerd_store"):
        run_rc(["systemctl", "start", "containerd.service"], timeout=120)
    _sh(["systemctl", "start", "docker.service"], timeout=300)
    for _ in range(30):
        if run_rc(["docker", "info"], timeout=20)[0] == 0:
            break
        time.sleep(2)
    managed = set(apps._app_names())
    for p in sorted(projects & managed):
        _say(f"Avvio {p}")
        rc, out, err = run_rc(apps._compose_cmd(p, "up", "-d", "--pull", "never"), timeout=600)
        if rc != 0:
            _say(f"  {p}: {(err or out).strip()[-200:]}")
    others = [n for n in names if not any(n.startswith(p + "-") or n.startswith(p + "_") for p in managed)]
    if others:
        run_rc(["docker", "start"] + others, timeout=300)


def _check_running(names, wait=60):
    """Tutti i contenitori che giravano prima devono girare di nuovo."""
    t0 = time.time()
    missing = names
    while time.time() - t0 < wait:
        now, _ = _running_projects()
        missing = [n for n in names if n not in now]
        if not missing:
            return []
        time.sleep(5)
    return missing


def _fstab_lines():
    return read_file(FSTAB).splitlines()


def _write_dropins(units, mounts):
    for u in units:
        os.makedirs(os.path.dirname(DROPIN[u]), exist_ok=True)
        write_file(DROPIN[u], "[Unit]\n# Le app stanno su un altro disco (Impostazioni → Dischi → Spazio delle app)\n"
                              f"RequiresMountsFor={' '.join(mounts)}\n")


def _remove_dropins():
    for p in DROPIN.values():
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def _umount(path):
    rc, _, _ = run_rc(["umount", path], timeout=60)
    if rc != 0:
        run_rc(["umount", "-l", path], timeout=60)


def _switch_to(dest, disk, with_containerd):
    """fstab: le righe vecchie diventano commenti, le cartelle sul disco nuovo vengono montate (bind)."""
    if not os.path.exists(FSTAB_BACKUP):
        shutil.copy2(FSTAB, FSTAB_BACKUP)
    targets = [DOCKER, APPDATA] + ([CONTAINERD] if with_containerd else [])
    out = []
    for line in _fstab_lines():
        f = line.split()
        if not line.lstrip().startswith("#") and len(f) >= 2 and f[1] in targets:
            out.append(OLD + line)
        elif MARK in line:
            continue
        else:
            out.append(line)
    pairs = [("docker", DOCKER), ("AppData", APPDATA)] + ([("containerd", CONTAINERD)] if with_containerd else [])
    for sub, mp in pairs:
        out.append(f"{dest}/{sub}  {mp}  none  bind,x-systemd.requires-mounts-for={disk},nofail  0 0  {MARK}")
    write_file(FSTAB, "\n".join(out) + "\n")
    run_rc(["systemctl", "daemon-reload"], timeout=60)
    for _, mp in pairs:
        if os.path.ismount(mp):
            _umount(mp)
        os.makedirs(mp, exist_ok=True)
        _sh(["mount", mp], timeout=60)
        if _findmnt(mp).get("target") != mp:
            raise RuntimeError(f"{mp} non risulta montato dal disco nuovo")
    _write_dropins(["docker"] + (["containerd"] if with_containerd else []),
                   [DOCKER, APPDATA] + ([CONTAINERD] if with_containerd else []))
    run_rc(["systemctl", "daemon-reload"], timeout=60)


def _switch_back():
    """Rimette fstab com'era prima (righe vecchie di nuovo attive) e rimonta i sottovolumi."""
    out, mps = [], []
    for line in _fstab_lines():
        if MARK in line:
            f = line.split()
            if len(f) >= 2:
                mps.append(f[1])
            continue
        if line.startswith(OLD):
            line = line[len(OLD):]
        out.append(line)
    write_file(FSTAB, "\n".join(out) + "\n")
    run_rc(["systemctl", "daemon-reload"], timeout=60)
    for mp in mps:
        if os.path.ismount(mp):
            _umount(mp)
    for mp in mps:
        if mp != CONTAINERD:        # containerd sta sul sottovolume di sistema: niente da montare
            run_rc(["mount", mp], timeout=60)
    _remove_dropins()
    run_rc(["systemctl", "daemon-reload"], timeout=60)
    return mps


def _done(ok, **kw):
    save_json(os.path.join(STATE, "apps-move-last.json"),
              {"ok": ok, "t": int(time.time()), **kw}, 0o644)


def run_move(disk):
    from . import notify
    _say(f"=== Sposto le app su {disk}")
    info = _docker_info()
    if not info["ok"]:
        _say("ERRORE: Docker non risponde: lo spostamento non parte")
        _done(False, error="Docker non risponde")
        return False
    sz = sizes(fresh=True)
    m = _findmnt(disk)
    if m.get("target") != disk or m.get("fstype") not in GOOD_FS:
        _say(f"ERRORE: {disk} non è montato o non ha un file system adatto")
        _done(False, error="disco non adatto")
        return False
    dest = os.path.join(disk, _app_dir_name())
    if os.path.isdir(dest) and any(os.scandir(dest)):
        old = f"{dest}.vecchia-{datetime.datetime.now():%Y%m%d-%H%M%S}"
        os.rename(dest, old)
        _say(f"C'era già una cartella {dest} (spostamento precedente): rinominata in {old}")
    os.makedirs(dest, exist_ok=True)
    reload_images = info["driver"] == "btrfs" and m["fstype"] != "btrfs"
    _say(f"Docker: driver {info['driver'] or '?'}{', immagini in containerd' if info['containerd_store'] else ''}; "
         f"da copiare {(sz['docker'] + sz['appdata'] + sz['containerd']) / 1024 ** 3:.1f} GB")
    names, projects = _running_projects()
    _say(f"App accese adesso: {', '.join(sorted(projects)) or 'nessuna'}")
    images = []
    if reload_images:
        _say("Il disco nuovo non è Btrfs e Docker usa il driver btrfs: esporto le immagini per ricaricarle dopo")
        rc, out, _ = run_rc(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=60)
        images = [x for x in out.split() if "<none>" not in x]
        if images:
            rc, out, err = run_rc(["docker", "save", "-o", os.path.join(dest, "immagini.tar")] + images, timeout=6 * 3600)
            if rc != 0:
                _say(f"ERRORE: esportazione delle immagini non riuscita: {err.strip()[-300:]}")
                _done(False, error="docker save")
                return False
    switched = False
    try:
        _stop_all(info)
        _rsync(APPDATA, os.path.join(dest, "AppData"), "dati delle app (AppData)")
        if reload_images:
            _rsync(os.path.join(DOCKER, "volumes"), os.path.join(dest, "docker", "volumes"), "volumi di Docker")
        else:
            _rsync(DOCKER, os.path.join(dest, "docker"), "Docker")
        if info["containerd_store"] and os.path.isdir(CONTAINERD):
            _rsync(CONTAINERD, os.path.join(dest, "containerd"), "immagini (containerd)")
        _say("Controllo le copie (secondo passaggio)")
        _verify(APPDATA, os.path.join(dest, "AppData"), "AppData")
        if reload_images:
            _verify(os.path.join(DOCKER, "volumes"), os.path.join(dest, "docker", "volumes"), "volumi di Docker")
        else:
            _verify(DOCKER, os.path.join(dest, "docker"), "Docker")
        if info["containerd_store"] and os.path.isdir(CONTAINERD):
            _verify(CONTAINERD, os.path.join(dest, "containerd"), "containerd")
        _say("Monto le cartelle del disco nuovo al posto di quelle vecchie (i percorsi non cambiano)")
        switched = True
        _switch_to(dest, disk, info["containerd_store"] and os.path.isdir(CONTAINERD))
        if reload_images:
            if info.get("containerd_store"):
                run_rc(["systemctl", "start", "containerd.service"], timeout=120)
            _sh(["systemctl", "start", "docker.service"], timeout=300)
            if images:
                _say(f"Ricarico {len(images)} immagini")
                _sh(["docker", "load", "-i", os.path.join(dest, "immagini.tar")], timeout=6 * 3600)
                os.unlink(os.path.join(dest, "immagini.tar"))
            for p in projects:
                run_rc(["docker", "compose", "-p", p, "down"], timeout=300)
        _start_all(info, names, projects)
        missing = _check_running(names)
        if missing and not reload_images:
            raise RuntimeError(f"non ripartono: {', '.join(missing[:6])}")
        if missing:
            _say(f"Attenzione: non ripartiti {', '.join(missing)} (contenitori avviati fuori dal NAS vanno ricreati a mano)")
    except Exception as e:  # noqa: BLE001
        _say(f"ERRORE: {e}")
        _say("Torno alla situazione di prima")
        try:
            _stop_all(info)
        except Exception:  # noqa: BLE001
            pass
        if switched:
            _switch_back()
        _start_all(info, names, projects)
        _say("Le app sono di nuovo sul disco di sistema. Le copie sul disco nuovo restano in " + dest)
        _done(False, error=str(e)[:300], disk=disk)
        notify.event("apps", "Spostamento delle app non riuscito", str(e)[:200], level="error",
                     key=f"appmove-{int(time.time()) // 3600}")
        return False
    save_json(FILE, {"disk": disk, "dest": dest, "moved": int(time.time()), "old_kept": True,
                     "containerd": bool(info["containerd_store"] and os.path.isdir(dest + "/containerd")),
                     "reloaded_images": reload_images, "sizes": {k: v for k, v in sz.items() if k != "info"}}, 0o644)
    _sizes["v"] = None
    _done(True, disk=disk)
    _say(f"Fatto: Docker e AppData ora stanno su {disk}. I dati vecchi restano sul disco di sistema finché non premi "
         "\"Libera lo spazio sul disco di sistema\".")
    notify.event("apps", "App spostate su un altro disco", f"Docker e AppData ora stanno su {disk}.", level="info",
                 key=f"appmove-ok-{int(time.time()) // 3600}")
    return True


def run_move_back():
    from . import notify
    loc = load_json(FILE, {})
    dest = loc.get("dest")
    if not dest:
        _say("Le app sono già sul disco di sistema")
        return True
    _say(f"=== Riporto le app sul disco di sistema (da {dest})")
    info = _docker_info()
    info["containerd_store"] = info["containerd_store"] or loc.get("containerd")
    names, projects = _running_projects()
    try:
        _stop_all(info)
        _switch_back()
        _rsync(os.path.join(dest, "AppData"), APPDATA, "dati delle app (AppData)")
        _rsync(os.path.join(dest, "docker"), DOCKER, "Docker")
        if loc.get("containerd") and os.path.isdir(os.path.join(dest, "containerd")):
            _rsync(os.path.join(dest, "containerd"), CONTAINERD, "immagini (containerd)")
        _verify(os.path.join(dest, "AppData"), APPDATA, "AppData")
        _verify(os.path.join(dest, "docker"), DOCKER, "Docker")
        _start_all(info, names, projects)
        missing = _check_running(names)
        if missing:
            raise RuntimeError(f"non ripartono: {', '.join(missing[:6])}")
    except Exception as e:  # noqa: BLE001
        _say(f"ERRORE: {e}")
        _say("Rimonto le cartelle del disco esterno (situazione di prima)")
        try:
            _stop_all(info)
        except Exception:  # noqa: BLE001
            pass
        _switch_to(dest, loc["disk"], bool(loc.get("containerd")))
        _start_all(info, names, projects)
        _done(False, error=str(e)[:300], back=True)
        return False
    os.unlink(FILE)
    _sizes["v"] = None
    _done(True, back=True)
    _say(f"Fatto: le app sono di nuovo sul disco di sistema. La copia su {dest} si può cancellare dal file manager.")
    notify.event("apps", "App riportate sul disco di sistema", "", level="info", key=f"appback-{int(time.time()) // 3600}")
    return True


def free_old():
    """Cancella i dati vecchi rimasti sul disco di sistema dopo uno spostamento riuscito."""
    from . import jobs
    loc = load_json(FILE, {})
    if not loc.get("disk") or not loc.get("old_kept"):
        raise ApiError("Non ci sono dati vecchi da cancellare")

    def work(job):
        tmp = "/run/nido-vecchi"
        freed = []
        for line in _fstab_lines():
            if not line.startswith(OLD):
                continue
            f = line[len(OLD):].split()
            if len(f) < 4 or f[1] not in (DOCKER, APPDATA):
                continue
            mp = os.path.join(tmp, os.path.basename(f[1]))
            os.makedirs(mp, exist_ok=True)
            _sh(["mount", "-t", f[2], "-o", f[3], f[0], mp], timeout=60)
            try:
                job.set(step=f"Cancello i dati vecchi di {f[1]}")
                run_rc(["find", mp, "-mindepth", "1", "-delete"], timeout=6 * 3600)
                freed.append(f[1])
            finally:
                _umount(mp)
        if loc.get("containerd"):
            mp = os.path.join(tmp, "root")
            os.makedirs(mp, exist_ok=True)
            _sh(["mount", "--bind", "/", mp], timeout=60)      # mostra la cartella nascosta sotto il bind
            try:
                job.set(step="Cancello le immagini vecchie (containerd)")
                run_rc(["find", mp + CONTAINERD, "-mindepth", "1", "-delete"], timeout=6 * 3600)
                freed.append(CONTAINERD)
            finally:
                _umount(mp)
        loc["old_kept"] = False
        save_json(FILE, loc, 0o644)
        return {"freed": freed}

    job = jobs.start("appmove-free", "Libero lo spazio sul disco di sistema", work, target="__appmove__")
    return {"job": job.id}
