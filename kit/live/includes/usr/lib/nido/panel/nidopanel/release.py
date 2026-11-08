"""Passaggio alla versione nuova di Ubuntu (Impostazioni → Aggiornamenti di sistema).

Il NAS legge l'elenco ufficiale delle versioni (changelogs.ubuntu.com/meta-release) e propone
sempre la versione successiva, anche se non è LTS, dicendo chiaramente se è LTS (5 anni di
supporto) o no (9 mesi, poi va aggiornata di nuovo). Decide l'operatore.

Passaggio (cli.py release-upgrade, come unità systemd: prosegue anche chiudendo la pagina):
controllo dello spazio → sistema aggiornato → snapshot "prima del passaggio" → do-release-upgrade
non interattivo con il registro in diretta → nome e logo del sistema rimessi (rebrand.sh) →
snapshot "dopo". Al riavvio il servizio nido-release-verify controlla le parti del NAS
(versione, nome, dpkg-divert di 80snapper, Caddy, Docker, servizi nido-*, interfaccia) e il
risultato compare nella pagina. Se qualcosa non va si torna indietro con lo snapshot.
"""
import datetime
import os
import re
import shutil
import time
import urllib.request

from .util import (ApiError, LOGS, STATE, have, job_state, load_json, product, read_file, run_rc, save_json,
                   start_job, user_agent, write_file)

META = "https://changelogs.ubuntu.com/meta-release"
FILE = os.path.join(STATE, "release.json")
PENDING = os.path.join(STATE, "release-verify-pending.json")
LOG = os.path.join(LOGS, "release-upgrade.log")
PROMPT = "/etc/update-manager/release-upgrades"
MIN_FREE = 6 * 1024 ** 3


def _vt(v):
    m = re.match(r"^(\d+)\.(\d+)", v or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def current():
    path = "/usr/lib/os-release.base" if os.path.exists("/usr/lib/os-release.base") else "/etc/os-release"
    d = {}
    for line in read_file(path).splitlines():
        k, _, v = line.partition("=")
        d[k.strip()] = v.strip().strip('"')
    ver = d.get("VERSION_ID", "")
    return {"version": ver, "codename": d.get("VERSION_CODENAME", ""), "lts": "LTS" in (d.get("VERSION", "") + d.get("PRETTY_NAME", "")),
            "pretty": d.get("PRETTY_NAME") or f"Ubuntu {ver}"}


def _parse_meta(text):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        e = {}
        for line in block.splitlines():
            k, _, v = line.partition(":")
            e[k.strip()] = v.strip()
        if e.get("Dist") and e.get("Version"):
            out.append(e)
    return out


def check():
    """Cerca la versione successiva di Ubuntu (anche non LTS)."""
    cur = current()
    try:
        req = urllib.request.Request(META, headers={"User-Agent": user_agent("release")})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read(2 * 1024 * 1024).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        data = load_json(FILE, {})
        data["error"] = f"Elenco delle versioni non raggiungibile: {getattr(e, 'reason', e)}"
        data["checked"] = int(time.time())
        save_json(FILE, data, 0o644)
        raise ApiError(data["error"], 502)
    now = datetime.datetime.now(datetime.timezone.utc)
    newer = []
    for e in _parse_meta(text):
        if e.get("Supported") != "1" or _vt(e["Version"]) <= _vt(cur["version"]):
            continue
        try:
            date = datetime.datetime.strptime(e.get("Date", ""), "%a, %d %B %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc)
            if date > now:
                continue
        except ValueError:
            date = None
        lts = "LTS" in e["Version"]
        newer.append({"codename": e["Dist"], "name": e.get("Name", ""), "version": e["Version"].replace(" LTS", ""),
                      "lts": lts, "support": "5 anni (LTS)" if lts else "9 mesi (non LTS)",
                      "date": date.date().isoformat() if date else None,
                      "notes": e.get("ReleaseNotes", "")})
    newer.sort(key=lambda x: _vt(x["version"]))
    data = load_json(FILE, {})
    data.update(checked=int(time.time()), error=None, current=cur,
                next=newer[0] if newer else None, later=newer[1:4])
    save_json(FILE, data, 0o644)
    return status()


def status():
    from .updates import snapshots_available
    data = load_json(FILE, {})
    try:
        st = os.statvfs("/")
        free = st.f_bavail * st.f_frsize
    except OSError:
        free = 0
    running = job_state("release-upgrade") in ("active", "activating")
    return {"current": current(), "checked": data.get("checked"), "error": data.get("error"),
            "next": data.get("next"), "later": data.get("later") or [], "running": running,
            "upgrade": data.get("upgrade"), "verify": data.get("verify"),
            "pending_verify": os.path.exists(PENDING), "snapshots": snapshots_available(),
            "free": free, "min_free": MIN_FREE, "log_size": os.path.getsize(LOG) if os.path.exists(LOG) else 0}


def start(codename, confirm):
    data = load_json(FILE, {})
    nxt = data.get("next")
    if not nxt or nxt.get("codename") != codename:
        raise ApiError("Versione non proposta: premi prima \"Controlla\"")
    if (confirm or "").strip().lower() != nxt["version"].lower():
        raise ApiError(f"Per confermare scrivi la versione: {nxt['version']}")
    if job_state("updates-install") in ("active", "activating") or job_state("release-upgrade") in ("active", "activating"):
        raise ApiError("È già in corso un aggiornamento", 409)
    data["upgrade"] = {"state": "running", "target": nxt, "started": int(time.time())}
    save_json(FILE, data, 0o644)
    start_job("release-upgrade", ["release-upgrade"], log=LOG)
    return status()


def log_since(offset=0):
    size = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    if offset > size or offset < 0:
        offset = 0
    if offset == 0 and size > 300_000:
        offset = size - 300_000
    text = ""
    if size > offset:
        with open(LOG, "rb") as f:
            f.seek(offset)
            text = f.read(size - offset).decode("utf-8", "replace")
    return {"text": text, "offset": size, "running": job_state("release-upgrade") in ("active", "activating")}


def rollback():
    """Torna allo snapshot "prima del passaggio" (serve un riavvio)."""
    from .updates import restore_snapshot
    data = load_json(FILE, {})
    pre = (data.get("upgrade") or {}).get("pre")
    if not pre:
        raise ApiError("Non c'è uno snapshot del passaggio a cui tornare")
    res = restore_snapshot(pre)
    data["upgrade"]["state"] = "rolled-back"
    data["upgrade"]["rolled_back"] = int(time.time())
    save_json(FILE, data, 0o644)
    try:
        os.unlink(PENDING)
    except OSError:
        pass
    return res


# --- esecuzione (cli.py) ---------------------------------------------------------------------

def _say(text):
    print(f"[{datetime.datetime.now():%d/%m %H:%M:%S}] {text}", flush=True)


def _finish(ok, **kw):
    data = load_json(FILE, {})
    up = data.get("upgrade") or {}
    up.update(kw, state="upgraded" if ok else "failed", ended=int(time.time()))
    data["upgrade"] = up
    save_json(FILE, data, 0o644)


def run_upgrade():
    from . import notify
    from .updates import APT_ENV, _snapshot, _stream
    data = load_json(FILE, {})
    target = (data.get("upgrade") or {}).get("target") or {}
    cur = current()
    tv = target.get("version", "?")
    _say(f"=== Passaggio da Ubuntu {cur['version']} a Ubuntu {tv}{' LTS' if target.get('lts') else ''}")
    env = dict(APT_ENV, LC_ALL="C.UTF-8", NIDO_NO_APT_SNAPSHOT="1")
    st = os.statvfs("/")
    free = st.f_bavail * st.f_frsize
    if free < MIN_FREE:
        _say(f"ERRORE: servono almeno {MIN_FREE // 1024 ** 3} GB liberi sul disco di sistema (ce ne sono {free / 1024 ** 3:.1f})")
        _finish(False, error="spazio insufficiente")
        return False
    if not have("do-release-upgrade"):
        _say("Installo lo strumento di Ubuntu per il passaggio di versione")
        _stream(["apt-get", "-y", "install", "ubuntu-release-upgrader-core"], env, 1800)
    if not have("do-release-upgrade"):
        _say("ERRORE: do-release-upgrade non disponibile")
        _finish(False, error="do-release-upgrade mancante")
        return False
    _say("Porto il sistema attuale all'ultima versione (richiesto prima del passaggio)")
    _stream(["apt-get", "update"], env, 900)
    rc = _stream(["apt-get", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold",
                  "full-upgrade"], env, 4 * 3600)
    if rc != 0:
        _say(f"ERRORE: aggiornamento del sistema attuale non riuscito (codice {rc}): passaggio annullato")
        _finish(False, error=f"apt full-upgrade {rc}")
        return False
    pre = _snapshot(f"prima del passaggio a Ubuntu {tv}")
    _say(f"Snapshot \"prima del passaggio\" creato (#{pre})" if pre else
         "ATTENZIONE: snapshot non disponibili (disco di sistema non Btrfs): non si potrà tornare indietro da qui")
    _finish_partial(pre=pre)
    # Il NAS propone anche le versioni non LTS: lo strumento di Ubuntu va impostato di conseguenza
    old_prompt = read_file(PROMPT)
    write_file(PROMPT, re.sub(r"(?m)^Prompt=.*$", "Prompt=" + ("lts" if target.get("lts") and cur["lts"] else "normal"),
                              old_prompt) if "Prompt=" in old_prompt else "[DEFAULT]\nPrompt=normal\n")
    _say("Avvio do-release-upgrade (può richiedere da 30 minuti a qualche ora: il registro si aggiorna qui)")
    rc = _stream(["do-release-upgrade", "-f", "DistUpgradeViewNonInteractive"], dict(env, RELEASE_UPGRADER_NO_SCREEN="1"), 8 * 3600)
    write_file(PROMPT, re.sub(r"(?m)^Prompt=.*$", "Prompt=normal", old_prompt) if old_prompt else "[DEFAULT]\nPrompt=normal\n")
    new = current()
    ok = rc == 0 and _vt(new["version"]) >= _vt(tv)
    _say("Rimetto nome e logo del sistema")
    run_rc(["/usr/lib/nido/rebrand.sh"], timeout=600)
    for unit in ("nido-ui.service", "nido-standby.service", "nido-mdns.service", "nido-netmounts.service",
                 "nido-uptime.service", "nido-release-verify.service", "caddy.service", "docker.service"):
        run_rc(["systemctl", "enable", unit], timeout=30)
    post = _snapshot(f"dopo il passaggio a Ubuntu {new['version']}")
    if ok:
        save_json(PENDING, {"target": tv, "codename": target.get("codename"), "t": int(time.time())}, 0o644)
        _say(f"Passaggio completato: ora il sistema è Ubuntu {new['version']}. Serve un riavvio: dopo il riavvio "
             "il NAS controlla da solo che tutto funzioni (risultato in questa pagina).")
        _finish(True, pre=pre, post=post, version=new["version"], reboot=True)
        notify.event("updates", "Passaggio di versione completato",
                     f"Ubuntu {new['version']}: riavvia il NAS per finire.", level="info", key=f"rel-{tv}")
    else:
        _say(f"ERRORE: passaggio non riuscito (codice {rc}, versione attuale {new['version']}). "
             + (f"Si può tornare allo snapshot #{pre} con \"Torna alla versione di prima\"." if pre else ""))
        _finish(False, pre=pre, post=post, error=f"do-release-upgrade {rc}", version=new["version"])
        notify.event("updates", "Passaggio di versione non riuscito",
                     "Controlla il registro in Impostazioni > Aggiornamenti di sistema.", level="error", key=f"rel-fail-{tv}")
    return ok


def _finish_partial(**kw):
    data = load_json(FILE, {})
    data.setdefault("upgrade", {}).update(kw)
    save_json(FILE, data, 0o644)


def run_verify():
    """Dopo il riavvio: controlla che le parti del NAS funzionino con la versione nuova."""
    from . import notify
    pend = load_json(PENDING, {})
    name = product()[0]
    checks = []

    def add(label, ok, detail=""):
        checks.append({"name": label, "ok": bool(ok), "detail": detail})
        print(f"  {'OK ' if ok else 'NO '} {label}{': ' + detail if detail else ''}", flush=True)

    _say("=== Controlli dopo il passaggio di versione")
    cur = current()
    add("Versione di Ubuntu", not pend.get("target") or _vt(cur["version"]) >= _vt(pend["target"]), cur["pretty"])
    osr = read_file("/etc/os-release")
    add(f"Nome del sistema ({name})", f'NAME="{name}"' in osr, (re.search(r'PRETTY_NAME="([^"]*)"', osr) or [None, ""])[1])
    rc, out, _ = run_rc(["dpkg-divert", "--list", "/etc/apt/apt.conf.d/80snapper"], timeout=20)
    add("Snapshot di apt senza doppioni (dpkg-divert di 80snapper)",
        "nido" in out or not os.path.exists("/usr/share/nido/80snapper.ubuntu") and not os.path.exists("/etc/apt/apt.conf.d/80snapper"),
        out.strip()[:120])
    for unit, label in (("nido-ui.service", "Interfaccia web"), ("caddy.service", "HTTPS (Caddy)"),
                        ("docker.service", "Docker (app)"), ("nido-standby.service", "Standby dei dischi"),
                        ("nido-mdns.service", "Nomi .local"), ("smbd.service", "Condivisioni Samba"),
                        ("ssh.service", "SSH")):
        rc, out, _ = run_rc(["systemctl", "is-active", unit], timeout=15)
        add(label, out.strip() == "active", out.strip())
    try:
        with urllib.request.urlopen("http://127.0.0.1:8090/api/auth/state", timeout=10) as r:
            add("L'interfaccia risponde", r.status == 200)
    except Exception as e:  # noqa: BLE001
        add("L'interfaccia risponde", False, str(e)[:120])
    rc, out, _ = run_rc(["systemctl", "--failed", "--no-legend", "--plain"], timeout=15)
    failed = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    add("Nessun servizio fallito", not failed, ", ".join(failed[:6]))
    rc, out, _ = run_rc(["docker", "ps", "-a", "--format", "{{.Names}} {{.State}}"], timeout=30)
    add("App (contenitori) leggibili", rc == 0, f"{len(out.splitlines())} contenitori")
    ok = all(c["ok"] for c in checks)
    data = load_json(FILE, {})
    data["verify"] = {"ok": ok, "at": int(time.time()), "checks": checks, "version": cur["version"]}
    save_json(FILE, data, 0o644)
    try:
        os.unlink(PENDING)
    except OSError:
        pass
    _say("Tutto a posto." if ok else "Alcuni controlli non sono passati: vedi Impostazioni > Aggiornamenti di sistema.")
    notify.event("updates", "Controlli dopo il passaggio di versione: " + ("tutto a posto" if ok else "ci sono problemi"),
                 f"Ubuntu {cur['version']}" + ("" if ok else " — puoi tornare alla versione di prima dalla pagina"),
                 level="info" if ok else "error", key=f"rel-verify-{cur['version']}")
    shutil.rmtree("/var/lib/nido/release-tmp", ignore_errors=True)
    return ok
