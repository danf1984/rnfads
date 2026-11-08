"""Servizi cloud (Google Drive, OneDrive, Dropbox, Box, Mega, WebDAV/Nextcloud, S3, Backblaze B2, SFTP, FTP).

Tutto con rclone (MIT, già nella ISO), configurato dall'interfaccia invece che con "rclone config":
- i servizi con accesso via browser (OAuth) usano "rclone authorize" sul NAS: l'utente apre la pagina di
  accesso del servizio dal suo browser, alla fine il browser va a http://127.0.0.1:53682/... (che sul suo
  dispositivo non si apre) e lui incolla quell'indirizzo nell'interfaccia; il NAS lo "visita" in locale e
  rclone riceve il codice e restituisce il token;
- gli altri con nome utente/password o chiavi: le password vengono offuscate con "rclone obscure" (via stdin)
  e scritte direttamente nel file di configurazione di rclone, mai sulla riga di comando;
- il file è quello di root (/root/.config/rclone/rclone.conf, permessi 600): lo vedono anche i backup
  (destinazione "Cloud") e il terminale;
- "Mostra nei File": rclone mount in /media/cloud/<nome> con l'unità nido-cloud@<nome> (Ricollega all'avvio
  = unità abilitata). Le app (Docker) vedono la cartella come una cartella normale.
"""
import configparser
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .util import ApiError, ETC, have, run_rc

BASE = "/media/cloud"
ENV_DIR = os.path.join(ETC, "cloud")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
_lock = threading.Lock()

# tipo rclone -> descrizione per l'interfaccia. "oauth": accesso dal browser; "fields": campi del modulo
# (id, etichetta, tipo: text/password/select, obbligatorio, predefinito, scelte)
PROVIDERS = {
    "drive": {"name": "Google Drive", "oauth": True, "color": "#4285f4"},
    "onedrive": {"name": "OneDrive", "oauth": True, "color": "#0078d4"},
    "dropbox": {"name": "Dropbox", "oauth": True, "color": "#0061ff"},
    "box": {"name": "Box", "oauth": True, "color": "#0061d5"},
    "mega": {"name": "MEGA", "color": "#d9272e", "fields": [
        ["user", "Email", "text", True], ["pass", "Password", "password", True]]},
    "webdav": {"name": "WebDAV / Nextcloud", "color": "#0082c9", "fields": [
        ["url", "Indirizzo (es. https://cloud.esempio.it/remote.php/dav/files/mario)", "text", True],
        ["vendor", "Tipo di server", "select", True, "nextcloud",
         [["nextcloud", "Nextcloud"], ["owncloud", "ownCloud"], ["sharepoint", "SharePoint"], ["other", "Altro"]]],
        ["user", "Nome utente", "text", False], ["pass", "Password (o password per le app)", "password", False]]},
    "s3": {"name": "S3 (Amazon, Wasabi, Cloudflare R2, MinIO…)", "color": "#ff9900", "fields": [
        ["provider", "Servizio", "select", True, "AWS",
         [["AWS", "Amazon S3"], ["Wasabi", "Wasabi"], ["Cloudflare", "Cloudflare R2"], ["Minio", "MinIO"],
          ["IDrive", "IDrive e2"], ["Other", "Altro compatibile S3"]]],
        ["access_key_id", "Access key ID", "text", True], ["secret_access_key", "Secret access key", "password", True],
        ["region", "Regione (es. eu-central-1, facoltativa)", "text", False],
        ["endpoint", "Endpoint (per servizi diversi da Amazon)", "text", False]]},
    "b2": {"name": "Backblaze B2", "color": "#e21e29", "fields": [
        ["account", "Application key ID", "text", True], ["key", "Application key", "password", True]]},
    "sftp": {"name": "SFTP (server SSH)", "color": "#64748b", "fields": [
        ["host", "Server", "text", True], ["port", "Porta", "text", False, "22"],
        ["user", "Nome utente", "text", True], ["pass", "Password", "password", True]]},
    "ftp": {"name": "FTP", "color": "#64748b", "fields": [
        ["host", "Server", "text", True], ["port", "Porta", "text", False, "21"],
        ["user", "Nome utente", "text", True], ["pass", "Password", "password", True]]},
}
SECRET_KEYS = {"pass", "secret_access_key", "key", "token", "client_secret"}
OBSCURED = {"pass"}           # rclone vuole queste "offuscate" (rclone obscure)


# --- file di configurazione di rclone ------------------------------------------------------------------

def _conf_path():
    rc, out, _ = run_rc(["rclone", "config", "file"], timeout=20)
    m = re.search(r"(/\S+\.conf)", out or "")
    return m.group(1) if rc == 0 and m else "/root/.config/rclone/rclone.conf"


def _read():
    p = _conf_path()
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    if text.lstrip().startswith("# Encrypted rclone configuration"):
        raise ApiError("Il file di configurazione di rclone è protetto da password: gestiscilo dal terminale")
    cp.read_string(text)
    return p, cp


def _write(p, cp):
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    buf = io.StringIO()
    cp.write(buf)
    tmp = p + ".nido-tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    os.replace(tmp, p)


def _obscure(value):
    rc, out, err = run_rc(["rclone", "obscure", "-"], input=value, timeout=20)
    if rc != 0 or not out.strip():
        raise ApiError("rclone: non riesco a preparare la password")
    return out.strip()


# --- elenco --------------------------------------------------------------------------------------------

def _mountpoint(name):
    return os.path.join(BASE, name)


def _mounted():
    res = set()
    try:
        with open("/proc/self/mounts", encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.split()
                if len(p) > 2 and p[1].startswith(BASE + "/"):
                    res.add(p[1])
    except OSError:
        pass
    return res


def _unit(name):
    return f"nido-cloud@{name}.service"


def _unit_state(name):
    rc, out, _ = run_rc(["systemctl", "is-enabled", _unit(name)], timeout=10)
    return out.strip() == "enabled"


def list_remotes():
    if not have("rclone"):
        return {"available": False, "providers": PROVIDERS, "remotes": []}
    try:
        _, cp = _read()
    except ApiError as e:
        return {"available": True, "providers": PROVIDERS, "remotes": [], "error": e.message}
    mounted = _mounted()
    res = []
    for name in cp.sections():
        t = cp.get(name, "type", fallback="?")
        mp = _mountpoint(name)
        res.append({"name": name, "type": t, "provider": PROVIDERS.get(t, {}).get("name", t),
                    "color": PROVIDERS.get(t, {}).get("color", "#64748b"),
                    "mountpoint": mp, "mounted": mp in mounted, "autoboot": _unit_state(name),
                    "managed": t in PROVIDERS})
    return {"available": True, "providers": PROVIDERS, "remotes": res}


def _check_name(name, cp=None, new=True):
    if not NAME_RE.match(name or ""):
        raise ApiError("Nome non valido: lettere, numeri, - e _ (al massimo 31 caratteri)")
    if cp is not None:
        if new and cp.has_section(name):
            raise ApiError(f"Esiste già un servizio chiamato {name}")
        if not new and not cp.has_section(name):
            raise ApiError("Servizio non trovato", 404)


# --- servizi con nome utente / chiavi -------------------------------------------------------------------

def create(body):
    t = body.get("type")
    prov = PROVIDERS.get(t)
    if not prov or prov.get("oauth"):
        raise ApiError("Servizio non valido")
    name = (body.get("name") or "").strip()
    vals = body.get("fields") or {}
    sec = {"type": t}
    for f in prov["fields"]:
        k, label, kind, req = f[0], f[1], f[2], f[3]
        v = str(vals.get(k) or (f[4] if len(f) > 4 else "") or "").strip()
        if req and not v:
            raise ApiError(f"Manca: {label.split(' (')[0]}")
        if kind == "select" and v and v not in [c[0] for c in f[5]]:
            raise ApiError("Scelta non valida")
        if v:
            sec[k] = _obscure(v) if k in OBSCURED else v
    if t == "s3":
        sec["env_auth"] = "false"
        if sec.get("provider") == "Cloudflare" and not sec.get("endpoint"):
            raise ApiError("Per Cloudflare R2 serve l'endpoint (https://<account>.r2.cloudflarestorage.com)")
    if t == "sftp":
        sec.setdefault("shell_type", "unix")
    with _lock:
        p, cp = _read()
        _check_name(name, cp)
        cp[name] = sec
        _write(p, cp)
    res = test(name)
    if not res["ok"]:
        remove(name)
        raise ApiError("Collegamento non riuscito: " + res["error"])
    return {"name": name, **res}


# --- servizi con accesso dal browser (OAuth con "rclone authorize") -------------------------------------

_auth = {"proc": None, "type": None, "lines": [], "started": 0}


def _auth_stop():
    p = _auth.get("proc")
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    _auth.update(proc=None, type=None, lines=[], started=0)


def _reader(p, lines):
    for line in p.stdout:
        lines.append(line.rstrip("\n"))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def oauth_start(body):
    t = body.get("type")
    if not PROVIDERS.get(t, {}).get("oauth"):
        raise ApiError("Servizio non valido")
    if not have("rclone"):
        raise ApiError("rclone non è installato")
    with _lock:
        _auth_stop()
        # un accesso lasciato a metà (anche da un altro processo) tiene occupata la porta 53682
        run_rc(["pkill", "-f", "^rclone authorize "], timeout=10)
        time.sleep(0.3)
        p = subprocess.Popen(["rclone", "authorize", t, "--auth-no-open-browser"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=dict(os.environ, LC_ALL="C.UTF-8"))
        lines = []
        threading.Thread(target=_reader, args=(p, lines), daemon=True).start()
        _auth.update(proc=p, type=t, lines=lines, started=time.time())
    local = None
    for _ in range(100):
        m = next((re.search(r"(http://127\.0\.0\.1:53682/auth\?state=\S+)", ln) for ln in lines
                  if "127.0.0.1:53682/auth" in ln), None)
        if m:
            local = m.group(1)
            break
        if p.poll() is not None:
            break
        time.sleep(0.2)
    if not local:
        _auth_stop()
        raise ApiError("rclone non ha avviato l'accesso: " + (" ".join(lines[-3:]) or "nessuna risposta"))
    # La pagina locale di rclone rimanda (redirect) alla pagina di accesso vera del servizio
    try:
        urllib.request.build_opener(_NoRedirect).open(local, timeout=10)
        url = None
    except urllib.error.HTTPError as e:
        url = e.headers.get("Location")
    except OSError as e:
        _auth_stop()
        raise ApiError(f"rclone non risponde: {e}") from None
    if not url or not url.startswith("https://"):
        _auth_stop()
        raise ApiError("Non trovo la pagina di accesso del servizio")
    return {"url": url, "type": t}


def oauth_finish(body):
    name = (body.get("name") or "").strip()
    pasted = (body.get("url") or "").strip()
    t = _auth.get("type")
    p = _auth.get("proc")
    if not p or p.poll() is not None or not t:
        raise ApiError("L'accesso è scaduto: premi di nuovo \"Apri la pagina di accesso\"")
    if time.time() - _auth["started"] > 900:
        _auth_stop()
        raise ApiError("L'accesso è scaduto (15 minuti): ricomincia")
    with _lock:
        _, cp = _read()
        _check_name(name, cp)
    u = urllib.parse.urlparse(pasted)
    q = urllib.parse.parse_qs(u.query)
    if u.hostname not in ("127.0.0.1", "localhost") or u.port != 53682:
        raise ApiError("Incolla l'indirizzo completo che il browser mostra alla fine (inizia con http://127.0.0.1:53682 o http://localhost:53682)")
    if "error" in q:
        raise ApiError("Il servizio ha rifiutato l'accesso: " + q["error"][0])
    if "code" not in q:
        raise ApiError("Nell'indirizzo non c'è il codice di accesso: copia tutto l'indirizzo dalla barra del browser")
    local = "http://127.0.0.1:53682" + (u.path or "/") + "?" + u.query
    try:
        urllib.request.urlopen(local, timeout=30).read()
    except urllib.error.HTTPError as e:
        if e.code >= 400:
            raise ApiError(f"rclone ha rifiutato il codice ({e.code}): ricomincia") from None
    except OSError as e:
        raise ApiError(f"rclone non risponde: {e}") from None
    token = None
    for _ in range(150):
        text = "\n".join(_auth["lines"])
        m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
        if m:
            token = m.group(1)
            break
        if p.poll() is not None and "<---" not in text:
            break
        time.sleep(0.2)
    if not token:
        text = "\n".join(_auth["lines"])
        m = re.search(r"Fatal error: (.*)", text)
        err = (m.group(1) if m else _clean_err(text))[:240]
        _auth_stop()
        raise ApiError("Token non ricevuto: " + (err or "nessuna risposta da rclone"))
    _auth_stop()
    sec = {"type": t, "token": token}
    if t == "drive":
        sec["scope"] = "drive"
    if t == "onedrive":
        sec.update(_onedrive_drive(token))
    with _lock:
        p2, cp = _read()
        _check_name(name, cp)
        cp[name] = sec
        _write(p2, cp)
    res = test(name)
    return {"name": name, **res}


def _onedrive_drive(token):
    """OneDrive: rclone vuole anche l'id e il tipo del disco (personale, business) — li chiedo a Microsoft Graph."""
    try:
        at = json.loads(token)["access_token"]
        req = urllib.request.Request("https://graph.microsoft.com/v1.0/me/drive",
                                     headers={"Authorization": "Bearer " + at})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        return {"drive_id": d["id"], "drive_type": d.get("driveType") or "personal"}
    except Exception as e:  # noqa: BLE001
        raise ApiError(f"OneDrive: non riesco a leggere il disco ({str(e)[:80]})") from None


# --- prova, spazio, cartella nei File ---------------------------------------------------------------------

FRIENDLY = [
    (r"401|403|unauthori[sz]ed|forbidden|access ?denied|login failed|invalid.?credentials|authenticat|"
     r"InvalidAccessKeyId|SignatureDoesNotMatch|bad_auth|wrong password|EACCESS|530 ",
     "nome utente, password o chiavi non corretti"),
    (r"no such host|name resolution|lookup .* on ", "server non trovato: controlla l'indirizzo"),
    (r"connection refused|connect: ", "server non raggiungibile: controlla indirizzo e porta"),
    (r"timeout|deadline exceeded", "il server non risponde (tempo scaduto)"),
    (r"certificate|x509|tls", "problema con il certificato HTTPS del server"),
    (r"NoSuchBucket|bucket.*not (found|exist)", "bucket non trovato"),
]


def _clean_err(text):
    lines = [re.sub(r"^\S+ \S+ (ERROR|NOTICE)\s*:?\s*(: )?", "", ln) for ln in (text or "").splitlines()
             if ln.strip() and "DEBUG" not in ln]
    last = (lines[-1] if lines else "errore sconosciuto")
    last = re.sub(r"^Failed to [a-z ]+?(with \d+ errors: last error was)?:\s*", "", last)
    for rx, msg in FRIENDLY:
        if re.search(rx, last, re.I):
            return msg
    return last[:300]


def test(name):
    with _lock:
        _, cp = _read()
    _check_name(name, cp, new=False)
    rc, out, err = run_rc(["rclone", "lsf", "--max-depth", "1", "--dirs-only", f"{name}:"], timeout=90)
    if rc != 0:
        return {"ok": False, "error": _clean_err(err or out)}
    res = {"ok": True, "folders": len([x for x in out.splitlines() if x.strip()])}
    rc, out, _ = run_rc(["rclone", "about", "--json", f"{name}:"], timeout=60)
    if rc == 0:
        try:
            a = json.loads(out)
            res["space"] = {k: a.get(k) for k in ("total", "used", "free") if a.get(k) is not None}
        except ValueError:
            pass
    return res


def _env_file(name):
    from .apps import nas_user
    u = nas_user()
    os.makedirs(ENV_DIR, exist_ok=True)
    with open(os.path.join(ENV_DIR, f"{name}.env"), "w", encoding="utf-8") as f:
        f.write(f"NIDO_UID={u['uid']}\nNIDO_GID={u['gid']}\nRCLONE_CONFIG={_conf_path()}\n")


def mount(name, body):
    with _lock:
        _, cp = _read()
    _check_name(name, cp, new=False)
    on = bool(body.get("enabled", True))
    unit = _unit(name)
    if on:
        _env_file(name)
        os.makedirs(_mountpoint(name), exist_ok=True)
        run_rc(["systemctl", "daemon-reload"], timeout=30)
        rc, _, err = run_rc(["systemctl", "restart", unit], timeout=90)
        if rc != 0:
            _, log, _ = run_rc(["journalctl", "-u", unit, "-n", "5", "--no-pager", "-o", "cat"], timeout=15)
            raise ApiError("La cartella non si collega: " + _clean_err(log or err))
        auto = body.get("autoboot", True)
        run_rc(["systemctl", "enable" if auto else "disable", unit], timeout=30)
    else:
        run_rc(["systemctl", "disable", "--now", unit], timeout=60)
        run_rc(["fusermount3", "-uz", _mountpoint(name)], timeout=20)
        try:
            os.rmdir(_mountpoint(name))
        except OSError:
            pass
    return list_remotes()


def autoboot(name, enabled):
    run_rc(["systemctl", "enable" if enabled else "disable", _unit(name)], timeout=30)
    return list_remotes()


def remove(name):
    if not NAME_RE.match(name or ""):
        raise ApiError("Nome non valido")
    run_rc(["systemctl", "disable", "--now", _unit(name)], timeout=60)
    run_rc(["fusermount3", "-uz", _mountpoint(name)], timeout=20)
    try:
        os.rmdir(_mountpoint(name))
    except OSError:
        pass
    try:
        os.unlink(os.path.join(ENV_DIR, f"{name}.env"))
    except OSError:
        pass
    with _lock:
        p, cp = _read()
        if cp.has_section(name):
            cp.remove_section(name)
            _write(p, cp)
    shutil.rmtree(os.path.join("/var/cache/rclone/vfs", name), ignore_errors=True)
    return list_remotes()
