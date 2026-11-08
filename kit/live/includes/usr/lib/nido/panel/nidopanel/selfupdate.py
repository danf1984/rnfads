"""Aggiornamento del sistema con un pacchetto locale (senza rifare la ISO).

Tutto il codice del NAS (interfaccia, servizi nido-*, script, note legali) sta nel pacchetto Debian
"nido-nas" che build.sh crea insieme alla ISO (rnfads_<versione>_all.deb). Da Impostazioni →
Aggiornamenti di sistema si carica il .deb (e la sua firma .sig):

  1. controllo: nome del pacchetto, versione (più nuova, o più vecchia con conferma), firma Ed25519
     con una delle chiavi pubbliche in /usr/share/nido/update-keys o /etc/nido/update-keys.
     Senza firma valida il pacchetto si installa solo in "modalità sviluppatore" (spenta di base);
  2. installazione (unità nido-job-selfupdate, prosegue anche chiudendo la pagina): snapshot
     "prima", apt-get install ./pacchetto.deb (installa anche i pacchetti nuovi richiesti),
     snapshot "dopo";
  3. controllo: l'interfaccia deve ripartire entro 3 minuti; se non riparte si reinstalla da soli
     il pacchetto di prima (tenuto in /var/lib/nido/updates/installed).

La firma: openssl pkeyutl -sign -rawin con una chiave Ed25519 (vedi kit/strumenti/). La chiave
privata resta a chi fa le build e non va mai nel kit.
"""
import glob
import hashlib
import os
import re
import shutil
import time
import urllib.request

from .util import (ApiError, ETC, LOGS, STATE, job_state, load_json, product, run_rc, save_json, start_job)

PACKAGE = "nido-nas"
DIR = os.path.join(STATE, "updates")
INCOMING = os.path.join(DIR, "in")
INSTALLED = os.path.join(DIR, "installed")
FILE = os.path.join(STATE, "selfupdate.json")
CONF = os.path.join(ETC, "selfupdate.json")
LOG = os.path.join(LOGS, "selfupdate.log")
KEY_DIRS = ["/usr/share/nido/update-keys", os.path.join(ETC, "update-keys")]
MAX_SIZE = 1024 * 1024 * 1024
KEEP = 3


def _say(text):
    print(f"[{time.strftime('%d/%m %H:%M:%S')}] {text}", flush=True)


def installed_version(pkg=PACKAGE):
    rc, out, _ = run_rc(["dpkg-query", "-W", "-f", "${db:Status-Abbrev}|${Version}", pkg], timeout=20)
    st, _, ver = out.strip().partition("|")
    return ver.strip() if rc == 0 and st.startswith("ii") and ver.strip() else None


def _ok_package(name):
    """Pacchetti che si possono installare da qui: quello del sistema e gli aggiuntivi "nido-extra-*"."""
    return name == PACKAGE or bool(re.match(r"^nido-extra-[a-z0-9-]+$", name or ""))


def _cmp(a, b, op):
    rc, _, _ = run_rc(["dpkg", "--compare-versions", a, op, b], timeout=10)
    return rc == 0


def devmode():
    return bool(load_json(CONF, {}).get("devmode"))


def set_devmode(enabled):
    c = load_json(CONF, {})
    c["devmode"] = bool(enabled)
    save_json(CONF, c, 0o600)
    return status()


def _keys():
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    keys = []
    for d in KEY_DIRS:
        for p in sorted(glob.glob(os.path.join(d, "*.pem"))):
            try:
                with open(p, "rb") as f:
                    data = f.read()
                k = load_pem_public_key(data)
                fp = hashlib.sha256(data.strip()).hexdigest()[:16]
                keys.append((os.path.basename(p), fp, k))
            except (OSError, ValueError, TypeError):
                continue
    return keys


def verify(deb, sig):
    """(True, chiave) se la firma Ed25519 del file è valida per una delle chiavi installate."""
    if not sig or not os.path.exists(sig):
        return False, "manca la firma (.sig)"
    keys = _keys()
    if not keys:
        return False, "sul NAS non c'è nessuna chiave pubblica per controllare le firme"
    with open(sig, "rb") as f:
        signature = f.read()
    if len(signature) != 64:
        try:
            import base64
            signature = base64.b64decode(signature.strip())
        except ValueError:
            pass
    with open(deb, "rb") as f:
        data = f.read()
    for name, fp, k in keys:
        try:
            k.verify(signature, data)
            return True, f"{name} ({fp})"
        except Exception:  # noqa: BLE001 — chiave diversa o firma non valida
            continue
    return False, "la firma non corrisponde a nessuna chiave del NAS"


# --- caricamento ---------------------------------------------------------------------------------

def upload_chunk(name, offset, total, reader, length):
    name = os.path.basename(name or "")
    if not re.match(r"^[A-Za-z0-9._+~-]{1,120}\.(deb|sig)$", name):
        raise ApiError("Scegli il file .deb dell'aggiornamento (e la sua firma .sig)")
    if total > MAX_SIZE:
        raise ApiError("File troppo grande")
    os.makedirs(INCOMING, exist_ok=True)
    if offset == 0 and name.endswith(".deb"):
        # Un pacchetto nuovo prende il posto di quello caricato prima (e della sua firma)
        for old in glob.glob(os.path.join(INCOMING, "*")):
            if not old.endswith(".sig") or os.path.basename(old) != name + ".sig":
                try:
                    os.unlink(old)
                except OSError:
                    pass
    tmp = os.path.join(INCOMING, "." + name + ".part")
    if offset == 0:
        mode = "wb"
    else:
        if not os.path.exists(tmp) or os.path.getsize(tmp) != offset:
            raise ApiError("Caricamento interrotto: riprova", 409)
        mode = "ab"
    with open(tmp, mode) as f:
        left = length
        while left > 0:
            b = reader.read(min(1 << 20, left))
            if not b:
                raise ApiError("Connessione interrotta durante il caricamento", 400)
            f.write(b)
            left -= len(b)
    if os.path.getsize(tmp) >= total:
        os.replace(tmp, os.path.join(INCOMING, name))
        return {"done": True}
    return {"done": False, "received": os.path.getsize(tmp)}


def _incoming():
    debs = sorted(glob.glob(os.path.join(INCOMING, "*.deb")), key=os.path.getmtime)
    if not debs:
        return None, None
    deb = debs[-1]
    sig = deb + ".sig"
    if not os.path.exists(sig):
        sigs = glob.glob(os.path.join(INCOMING, "*.sig"))
        sig = sigs[0] if len(sigs) == 1 else None
    return deb, sig


def _control(deb):
    rc, out, err = run_rc(["dpkg-deb", "-f", deb, "Package", "Version", "Description", "Installed-Size", "Depends"], timeout=60)
    if rc != 0:
        raise ApiError("Il file non è un pacchetto .deb valido")
    fields, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"^([A-Za-z-]+):\s?(.*)$", line)
        if m:
            cur = m.group(1)
            fields[cur] = m.group(2)
        elif cur:
            fields[cur] += "\n" + (line[1:] if line.startswith(" ") else line)
    desc = fields.get("Description", "")
    title, _, rest = desc.partition("\n")
    notes = "\n".join("" if ln.strip() == "." else ln for ln in rest.splitlines()).strip()
    return {"package": fields.get("Package"), "version": fields.get("Version"), "title": title.strip(),
            "notes": notes, "size_kb": fields.get("Installed-Size"), "depends": fields.get("Depends", "")}


def inspect():
    deb, sig = _incoming()
    if not deb:
        raise ApiError("Carica prima il file .deb dell'aggiornamento")
    info = _control(deb)
    if not _ok_package(info["package"]):
        raise ApiError(f"Questo non è un aggiornamento di {product()[0]} (pacchetto {info['package']})")
    ok, who = verify(deb, sig)
    cur = installed_version(info["package"])
    newer = not cur or _cmp(info["version"], cur, "gt")
    same = bool(cur) and _cmp(info["version"], cur, "eq")
    res = {**info, "file": os.path.basename(deb), "size": os.path.getsize(deb), "signed": ok,
           "signature": who, "current": cur, "newer": newer, "same": same, "devmode": devmode(),
           "allowed": ok or devmode()}
    data = load_json(FILE, {})
    data["pending"] = res
    save_json(FILE, data, 0o644)
    return res


def discard():
    shutil.rmtree(INCOMING, ignore_errors=True)
    data = load_json(FILE, {})
    data.pop("pending", None)
    save_json(FILE, data, 0o644)
    return status()


def status():
    data = load_json(FILE, {})
    running = job_state("selfupdate") in ("active", "activating") or job_state("selfupdate-rollback") in ("active", "activating")
    prev = _previous()
    return {"name": product()[0], "version": product()[1], "package_version": installed_version(),
            "pending": data.get("pending"), "last": data.get("last"), "running": running,
            "devmode": devmode(), "keys": [{"name": n, "fingerprint": fp} for n, fp, _ in _keys()],
            "previous": os.path.basename(prev) if prev else None,
            "log_size": os.path.getsize(LOG) if os.path.exists(LOG) else 0}


def start_install(confirm=None):
    p = load_json(FILE, {}).get("pending")
    if not p:
        raise ApiError("Carica prima il file .deb dell'aggiornamento")
    if not p.get("allowed"):
        raise ApiError("Pacchetto senza firma valida: si installa solo in modalità sviluppatore")
    if not p.get("newer") and (confirm or "").strip().upper() != "INSTALLA":
        raise ApiError("Questa versione non è più nuova di quella installata: per installarla comunque scrivi INSTALLA")
    for j in ("selfupdate", "selfupdate-rollback", "updates-install", "release-upgrade"):
        if job_state(j) in ("active", "activating"):
            raise ApiError("È già in corso un aggiornamento", 409)
    start_job("selfupdate", ["selfupdate-install"], log=LOG)
    return {"ok": True}


def start_rollback():
    if not _previous():
        raise ApiError("Non c'è una versione precedente salvata sul NAS")
    if job_state("selfupdate") in ("active", "activating"):
        raise ApiError("È in corso un aggiornamento", 409)
    start_job("selfupdate-rollback", ["selfupdate-rollback"], log=LOG)
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
    running = job_state("selfupdate") in ("active", "activating") or job_state("selfupdate-rollback") in ("active", "activating")
    return {"text": text, "offset": size, "running": running}


# --- esecuzione (cli.py) ---------------------------------------------------------------------

def _versions_saved():
    files = glob.glob(os.path.join(INSTALLED, "*.deb"))
    out = []
    for f in files:
        rc, v, _ = run_rc(["dpkg-deb", "-f", f, "Version"], timeout=30)
        if rc == 0 and v.strip():
            out.append((v.strip(), f))
    import functools
    out.sort(key=functools.cmp_to_key(lambda a, b: -1 if _cmp(a[0], b[0], "lt") else (1 if _cmp(a[0], b[0], "gt") else 0)))
    return out


def _previous():
    """Il pacchetto salvato con la versione più alta tra quelle più vecchie dell'attuale."""
    cur = installed_version()
    older = [(v, f) for v, f in _versions_saved() if cur and _cmp(v, cur, "lt")]
    return older[-1][1] if older else None


def _ui_ok(timeout=180):
    t0 = time.time()
    time.sleep(8)
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8090/api/auth/state", timeout=8) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(4)
    return False


def _apt_install(deb, env):
    from .updates import _stream
    return _stream(["apt-get", "install", "-y", "--allow-downgrades", "-o", "Dpkg::Options::=--force-confdef",
                    "-o", "Dpkg::Options::=--force-confold", os.path.abspath(deb)], env, 3600)


def _save_installed(deb):
    os.makedirs(INSTALLED, exist_ok=True)
    rc, v, _ = run_rc(["dpkg-deb", "-f", deb, "Version"], timeout=30)
    dst = os.path.join(INSTALLED, f"{PACKAGE}_{v.strip() or int(time.time())}_all.deb")
    if os.path.abspath(deb) != os.path.abspath(dst):
        shutil.copy2(deb, dst)
    saved = _versions_saved()
    for _, f in saved[:-KEEP]:
        try:
            os.unlink(f)
        except OSError:
            pass


def _finish(**kw):
    data = load_json(FILE, {})
    data["last"] = {"t": int(time.time()), **kw}
    save_json(FILE, data, 0o644)


def run_install():
    from . import notify
    from .updates import APT_ENV, _snapshot
    deb, sig = _incoming()
    if not deb:
        _say("ERRORE: nessun pacchetto caricato")
        return False
    info = _control(deb)
    ok, who = verify(deb, sig)
    pkg = info["package"]
    extra = pkg != PACKAGE
    cur = installed_version(pkg)
    _say(f"=== {'Pacchetto aggiuntivo ' + pkg if extra else 'Aggiornamento di ' + product()[0]}: {cur or 'nessuna versione'} → {info['version']}")
    if not _ok_package(pkg):
        _say("ERRORE: pacchetto sbagliato")
        _finish(ok=False, error="pacchetto sbagliato", to=info["version"])
        return False
    if ok:
        _say(f"Firma valida ({who})")
    elif devmode():
        _say(f"ATTENZIONE: {who}. Installo comunque perché la modalità sviluppatore è attiva.")
    else:
        _say(f"ERRORE: {who}. Aggiornamento rifiutato.")
        _finish(ok=False, error=who, to=info["version"])
        return False
    env = dict(APT_ENV, LC_ALL="C.UTF-8", NIDO_NO_APT_SNAPSHOT="1")
    pre = _snapshot(f"prima dell'aggiornamento di {product()[0]} {info['version']}")
    _say(f"Snapshot \"prima\" creato (#{pre})" if pre else "Snapshot non disponibili: continuo senza")
    _say("Installo il pacchetto (e gli eventuali pacchetti nuovi che richiede)")
    rc = _apt_install(deb, env)
    if rc != 0:
        _say(f"ERRORE: installazione non riuscita (codice {rc}). Il sistema non è cambiato o è rimasto a metà: "
             "controllo e, se serve, rimetto la versione di prima.")
    new = installed_version(pkg)
    if rc == 0 and new == info["version"]:
        _say("Controllo che l'interfaccia riparta…")
        if _ui_ok():
            if not extra:
                _save_installed(deb)
            post = _snapshot(f"dopo l'aggiornamento di {product()[0]} {info['version']}")
            _say(f"Fatto: {product()[0]} {info['version']} installato" + (f" (snapshot #{post})" if post else ""))
            _finish(ok=True, **{"from": cur, "to": new, "pre": pre})
            shutil.rmtree(INCOMING, ignore_errors=True)
            data = load_json(FILE, {})
            data.pop("pending", None)
            save_json(FILE, data, 0o644)
            notify.event("updates", f"{product()[0]} aggiornato", f"Versione {new}", level="info", key=f"self-{new}")
            return True
        _say("ERRORE: l'interfaccia non riparte con la versione nuova")
    prev = _previous() if new and cur and new != cur and not extra else None
    if not extra and (prev or (cur and rc != 0)):
        prev = prev or _previous()
    if extra and rc == 0:   # aggiuntivo installato ma l'interfaccia non riparte: lo tolgo
        _say(f"Tolgo il pacchetto aggiuntivo {pkg}")
        run_rc(["apt-get", "-y", "remove", pkg], timeout=600)
    if prev:
        _say(f"Rimetto la versione di prima ({os.path.basename(prev)})")
        rc2 = _apt_install(prev, env)
        back_ok = rc2 == 0 and _ui_ok()
        _say("Versione di prima rimessa: tutto come prima." if back_ok else
             f"ATTENZIONE: anche il ritorno non è riuscito. Si può tornare allo snapshot #{pre} da Snapshot del sistema.")
    else:
        back_ok = False
        if pre:
            _say(f"Nessun pacchetto precedente salvato: per tornare indietro usa lo snapshot #{pre} (Snapshot del sistema).")
    _finish(ok=False, error="installazione non riuscita" if rc != 0 else "l'interfaccia non ripartiva",
            to=info["version"], **{"from": cur, "pre": pre, "rolled_back": back_ok})
    notify.event("updates", f"Aggiornamento di {product()[0]} non riuscito",
                 "Tornato alla versione di prima." if back_ok else "Controlla Impostazioni > Aggiornamenti di sistema.",
                 level="error", key=f"self-fail-{info['version']}")
    return False


def run_rollback():
    from .updates import APT_ENV
    prev = _previous()
    cur = installed_version()
    if not prev:
        _say("ERRORE: nessuna versione precedente salvata")
        return False
    _say(f"=== Torno alla versione precedente: {cur} → {os.path.basename(prev)}")
    rc = _apt_install(prev, dict(APT_ENV, LC_ALL="C.UTF-8", NIDO_NO_APT_SNAPSHOT="1"))
    ok = rc == 0 and _ui_ok()
    _finish(ok=ok, rollback=True, **{"from": cur, "to": installed_version()})
    _say("Fatto." if ok else f"ERRORE (codice {rc})")
    return ok
