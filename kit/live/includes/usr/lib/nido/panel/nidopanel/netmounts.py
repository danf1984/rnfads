"""Cartelle di rete: collega cartelle condivise di altri PC e NAS (SMB, NFS, WebDAV).

- Scoperta automatica dei computer in rete (mDNS/Bonjour con avahi e NetBIOS con nmblookup).
- Le password sono salvate cifrate (secretbox) in /etc/nido/netmounts.json. Al momento del
  montaggio vengono scritte per un istante in un file temporaneo in /run (solo root) e poi
  cancellate: non finiscono mai nella riga di comando, nei log o in /etc/fstab.
- Le cartelle con "Ricollega all'avvio" vengono montate dal servizio nido-netmounts prima di
  Docker, così sono visibili anche alle app.
"""
import os
import re
import secrets
import socket
import tempfile
import threading

from . import secretbox
from .util import ApiError, ETC, load_json, run_rc, save_json

CONF = os.path.join(ETC, "netmounts.json")
BASE = "/media/rete"
RUN = "/run/nido"
_lock = threading.Lock()
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,252})$|^\[?[0-9a-fA-F:]+\]?$")


def _conf():
    return load_json(CONF, {"mounts": []})


def _save(c):
    save_json(CONF, c, 0o600)


def _mounted():
    res = {}
    try:
        with open("/proc/self/mounts", encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.split()
                if len(p) > 2:
                    res[p[1].replace("\\040", " ")] = p[2]
    except OSError:
        pass
    return res


def _public(m, mounted=None):
    mounted = mounted if mounted is not None else _mounted()
    return {"id": m["id"], "proto": m["proto"], "host": m["host"], "share": m["share"], "user": m.get("user") or "",
            "guest": bool(m.get("guest")), "label": m["label"], "mountpoint": m["mountpoint"],
            "autoboot": bool(m.get("autoboot", True)), "readonly": bool(m.get("readonly")),
            "apps": bool(m.get("apps", True)), "has_password": bool(m.get("password")),
            "mounted": m["mountpoint"] in mounted, "error": m.get("error")}


def list_mounts():
    mounted = _mounted()
    return [_public(m, mounted) for m in _conf()["mounts"]]


# --- scoperta -----------------------------------------------------------------------------------

def discover():
    """Computer e NAS trovati nella rete locale (pochi secondi)."""
    found = {}

    def add(ip, name, kind, proto):
        if not ip or ip.startswith(("127.", "169.254.")) or ":" in ip and ip.startswith("fe80"):
            return
        e = found.setdefault(ip, {"ip": ip, "name": name or ip, "kinds": [], "protos": []})
        if name and (e["name"] == ip or len(name) < len(e["name"])):
            e["name"] = name
        if kind and kind not in e["kinds"]:
            e["kinds"].append(kind)
        if proto and proto not in e["protos"]:
            e["protos"].append(proto)

    for svc, proto in (("_smb._tcp", "smb"), ("_nfs._tcp", "nfs"), ("_webdav._tcp", "webdav"),
                       ("_device-info._tcp", None)):
        rc, out, _ = run_rc(["avahi-browse", "-tprk", svc], timeout=8)
        for line in out.splitlines():
            f = line.split(";")
            if len(f) >= 9 and f[0] == "=" and f[2] == "IPv4":
                # Nome del servizio (quello che si vede in rete), altrimenti il nome host
                name = f[3].replace("\\032", " ") or f[6].removesuffix(".local")
                txt = f[9] if len(f) > 9 else ""
                model = re.search(r'"model=([^"]+)"', txt)
                add(f[7], name, model.group(1) if model else None, proto)
    rc, out, _ = run_rc(["nmblookup", "-S", "*"], timeout=8)
    ip = None
    for line in out.splitlines():
        m = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+\*<00>", line)
        if m:
            ip = m.group(1)
            continue
        m = re.match(r"^\s+(\S+)\s+<20>", line)
        if m and ip:
            add(ip, m.group(1), "Windows / Samba", "smb")
    # Il NAS stesso non serve
    mine = set()
    try:
        mine = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    rc, out, _ = run_rc(["hostname", "-I"], timeout=5)
    mine |= set(out.split())
    return {"hosts": sorted((h for h in found.values() if h["ip"] not in mine), key=lambda h: h["name"].lower())}


def _check_host(host):
    host = (host or "").strip().strip("\\/")
    if not HOST_RE.match(host):
        raise ApiError("Nome o indirizzo del computer non valido")
    return host


def _credfile(lines):
    os.makedirs(RUN, mode=0o700, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=RUN, prefix="cred-")
    with os.fdopen(fd, "w") as f:
        f.write("".join(x + "\n" for x in lines))
    os.chmod(path, 0o600)
    return path


def smb_shares(host, user="", password="", domain=""):
    host = _check_host(host)
    cmd = ["smbclient", "-L", f"//{host}", "-g", "-t", "8"]
    cred = None
    if user:
        cred = _credfile([f"username={user}", f"password={password}"] + ([f"domain={domain}"] if domain else []))
        cmd += ["-A", cred]
    else:
        cmd += ["-N"]
    try:
        rc, out, err = run_rc(cmd, timeout=20)
    finally:
        if cred:
            os.unlink(cred)
    shares = []
    for line in out.splitlines():
        f = line.split("|")
        if len(f) >= 2 and f[0] == "Disk" and not f[1].endswith("$"):
            shares.append({"name": f[1], "comment": f[2] if len(f) > 2 else ""})
    if not shares and rc != 0:
        msg = (err or out).strip().splitlines()
        text = msg[-1] if msg else "errore"
        if "LOGON_FAILURE" in text or "ACCESS_DENIED" in text:
            raise ApiError("Utente o password non accettati dal computer remoto", 401)
        if any(x in text for x in ("IO_TIMEOUT", "HOST_UNREACHABLE", "CONNECTION_REFUSED", "NETWORK_UNREACHABLE", "Connection refused", "timed out")):
            raise ApiError("Il computer non risponde: è acceso e collegato alla rete?", 502)
        if "NOT_FOUND" in text or "BAD_NETWORK_NAME" in text or "not known" in text:
            raise ApiError("Computer non trovato: controlla il nome o usa l'indirizzo IP", 502)
        raise ApiError(f"Impossibile leggere le cartelle condivise: {text}", 502)
    return {"shares": shares}


def nfs_exports(host):
    host = _check_host(host)
    rc, out, err = run_rc(["showmount", "-e", "--no-headers", host], timeout=15)
    if rc != 0:
        raise ApiError("Il server NFS non risponde", 502)
    return {"shares": [{"name": line.split()[0], "comment": " ".join(line.split()[1:])} for line in out.splitlines() if line.strip()]}


# --- montaggio -------------------------------------------------------------------------------------

def _mountpoint(host, share):
    leaf = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{host.split('.')[0]}-{share.strip('/').replace('/', '-')}").strip("-")
    return os.path.join(BASE, leaf[:60] or "cartella")


def _uidgid():
    from .apps import nas_user
    u = nas_user()
    return u["uid"], u["gid"]


def _do_mount(m):
    mp = m["mountpoint"]
    os.makedirs(mp, exist_ok=True)
    if mp in _mounted():
        return
    uid, gid = _uidgid()
    ro = "ro" if m.get("readonly") else "rw"
    cleanup = []
    try:
        if m["proto"] == "smb":
            opts = [ro, f"uid={uid}", f"gid={gid}", "file_mode=0664", "dir_mode=0775", "iocharset=utf8",
                    "nofail", "noserverino"]
            if m.get("guest") or not m.get("user"):
                opts.append("guest")
            else:
                cred = _credfile([f"username={m['user']}", f"password={secretbox.decrypt(m.get('password'))}"] +
                                 ([f"domain={m['domain']}"] if m.get("domain") else []))
                cleanup.append(cred)
                opts.append(f"credentials={cred}")
            src = f"//{m['host']}/{m['share'].strip('/')}"
            rc, out, err = run_rc(["mount", "-t", "cifs", src, mp, "-o", ",".join(opts)], timeout=40)
        elif m["proto"] == "nfs":
            src = f"{m['host']}:{m['share'] if m['share'].startswith('/') else '/' + m['share']}"
            rc, out, err = run_rc(["mount", "-t", "nfs", src, mp, "-o", f"{ro},soft,timeo=150,retrans=3,nofail"], timeout=40)
        elif m["proto"] == "webdav":
            url = m["share"]
            sec = _credfile([f'"{url}" "{m.get("user") or ""}" "{secretbox.decrypt(m.get("password")) if m.get("password") else ""}"'])
            conf = _credfile([f"secrets {sec}", "use_locks 0", "ask_auth 0"])
            cleanup += [sec, conf]
            rc, out, err = run_rc(["mount", "-t", "davfs", url, mp, "-o", f"{ro},uid={uid},gid={gid},conf={conf}"],
                                  timeout=60)
        else:
            raise ApiError("Protocollo non supportato")
    finally:
        for c in cleanup:
            try:
                os.unlink(c)
            except OSError:
                pass
    if rc != 0:
        text = (err or out).strip().splitlines()
        text = text[-1] if text else f"errore {rc}"
        full = (err or "") + (out or "")
        if "No such device" in full or "unknown filesystem type" in full or "error(19)" in full or "mount.cifs(8)" in full and "error(" not in full:
            text = f"questo sistema non ha il supporto per {m['proto'].upper()} (modulo del kernel mancante)"
        elif "Permission denied" in text or "error(13)" in text:
            text = "accesso negato: controlla utente e password"
        elif "No such file" in text or "error(2)" in text:
            text = "cartella condivisa non trovata"
        elif "Host is down" in text or "error(112)" in text or "timed out" in text:
            text = "il computer non risponde (spento o fuori rete?)"
        try:
            os.rmdir(mp)
        except OSError:
            pass
        raise ApiError(f"Collegamento non riuscito: {text}", 502)


def _validate(body):
    proto = (body.get("proto") or "smb").lower()
    if proto not in ("smb", "nfs", "webdav"):
        raise ApiError("Protocollo non supportato")
    host, share = body.get("host") or "", (body.get("share") or "").strip()
    # Accetta anche \\PC\Cartella, smb://pc/cartella, pc:/export
    addr = (body.get("address") or "").strip()
    if addr:
        m = re.match(r"^(?:\\\\|//|smb://)([^\\/]+)[\\/](.+)$", addr, re.I)
        n = re.match(r"^(?:nfs://)?([^:/]+):?(/.*)$", addr, re.I)
        if proto in ("smb",) and m:
            host, share = m.group(1), m.group(2).replace("\\", "/")
        elif proto == "nfs" and n:
            host, share = n.group(1), n.group(2)
        elif proto == "webdav" and re.match(r"^https?://", addr):
            host, share = re.match(r"^https?://([^/:]+)", addr).group(1), addr
        else:
            raise ApiError("Indirizzo non riconosciuto: es. \\\\PC\\Cartella oppure smb://pc/cartella")
    host = _check_host(host)
    if not share or "\x00" in share or len(share) > 300:
        raise ApiError("Manca il nome della cartella condivisa")
    if proto == "webdav" and not re.match(r"^https?://", share):
        share = "https://" + host + "/" + share.lstrip("/")
    return proto, host, share


def test(body):
    proto, host, share = _validate(body)
    m = _from_body(body, proto, host, share, {"id": "prova"})
    m["mountpoint"] = os.path.join(RUN, "prova-" + secrets.token_hex(3))
    _do_mount(m)
    try:
        n = len(os.listdir(m["mountpoint"]))
    finally:
        run_rc(["umount", m["mountpoint"]], timeout=30)
        try:
            os.rmdir(m["mountpoint"])
        except OSError:
            pass
    return {"ok": True, "items": n}


def _from_body(body, proto, host, share, base):
    m = dict(base)
    m.update(proto=proto, host=host, share=share,
             user=(body.get("user") or "").strip()[:100], domain=(body.get("domain") or "").strip()[:100],
             guest=bool(body.get("guest")), autoboot=body.get("autoboot", True) is not False,
             readonly=bool(body.get("readonly")), apps=body.get("apps", True) is not False)
    # NFS non usa password; per gli ospiti non si salva niente
    if body.get("password") and proto != "nfs" and not m["guest"]:
        m["password"] = secretbox.encrypt(body["password"])
    elif m["guest"] or proto == "nfs":
        m.pop("password", None)
    if proto == "smb":
        m["label"] = f"{host}\\{share.strip('/')}"
    elif proto == "nfs":
        m["label"] = f"{host}:{share}"
    else:
        path = [x for x in share.split("//", 1)[-1].split("/")[1:] if x]
        m["label"] = f"{host} (WebDAV{': ' + path[-1] if path else ''})"
    m["label"] = (body.get("label") or "").strip()[:60] or m["label"]
    return m


def connect(body):
    proto, host, share = _validate(body)
    with _lock:
        c = _conf()
        if proto == "webdav":
            path = [x for x in share.split("//", 1)[-1].split("/")[1:] if x]
            mp = _mountpoint(host, path[-1] if path else "webdav")
        else:
            mp = _mountpoint(host, share)
        if any(x["mountpoint"] == mp for x in c["mounts"]):
            raise ApiError("Questa cartella di rete è già collegata")
        m = _from_body(body, proto, host, share, {"id": secrets.token_hex(4), "mountpoint": mp})
        _do_mount(m)
        c["mounts"].append(m)
        _save(c)
    return _public(m)


def mount(mid):
    with _lock:
        c = _conf()
        m = next((x for x in c["mounts"] if x["id"] == mid), None)
        if not m:
            raise ApiError("Cartella di rete non trovata", 404)
        try:
            _do_mount(m)
            m.pop("error", None)
        except ApiError as e:
            m["error"] = e.message
            _save(c)
            raise
        _save(c)
    return _public(m)


def unmount(mid):
    c = _conf()
    m = next((x for x in c["mounts"] if x["id"] == mid), None)
    if not m:
        raise ApiError("Cartella di rete non trovata", 404)
    if m["mountpoint"] in _mounted():
        rc, out, err = run_rc(["umount", m["mountpoint"]], timeout=30)
        if rc != 0:
            rc, out, err = run_rc(["umount", "-l", m["mountpoint"]], timeout=30)
            if rc != 0:
                raise ApiError("Impossibile scollegare: la cartella è in uso", 409)
    try:
        os.rmdir(m["mountpoint"])
    except OSError:
        pass
    return _public(m)


def update(mid, body):
    with _lock:
        c = _conf()
        m = next((x for x in c["mounts"] if x["id"] == mid), None)
        if not m:
            raise ApiError("Cartella di rete non trovata", 404)
        for k in ("autoboot", "readonly", "apps"):
            if k in body:
                m[k] = bool(body[k])
        if body.get("label"):
            m["label"] = str(body["label"]).strip()[:60]
        if "user" in body:
            m["user"] = str(body["user"]).strip()[:100]
        if body.get("password"):
            m["password"] = secretbox.encrypt(body["password"])
        _save(c)
    return _public(m)


def remove(mid):
    unmount(mid)
    with _lock:
        c = _conf()
        c["mounts"] = [x for x in c["mounts"] if x["id"] != mid]
        _save(c)
    return {"ok": True}


def mount_all():
    """All'avvio: collega tutte le cartelle con "Ricollega all'avvio" (chiamata da cli.py)."""
    c = _conf()
    for m in c["mounts"]:
        if not m.get("autoboot", True):
            continue
        try:
            _do_mount(m)
            m.pop("error", None)
            print(f"{m['label']}: collegata", flush=True)
        except ApiError as e:
            m["error"] = e.message
            print(f"{m['label']}: {e.message}", flush=True)
    _save(c)
