"""Server SSH: acceso/spento, porta, accesso con password, solo dalla rete di casa, chiavi autorizzate.

Le impostazioni vanno in /etc/ssh/sshd_config.d/10-nido.conf (il file principale di Ubuntu non si tocca).
In Ubuntu SSH parte con l'attivazione da socket (ssh.socket): il generatore di systemd legge la porta
da sshd_config, quindi dopo un cambio di porta basta daemon-reload e il riavvio del socket.
"""
import os
import pwd
import re
import tempfile

from .util import ApiError, read_file, run, run_rc, write_file

CONF = "/etc/ssh/sshd_config.d/10-nido.conf"
LAN = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,100.64.0.0/10,::1,fe80::/10,fc00::/7"
KEY_RE = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|"
                    r"sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/=]{40,}(\s+.*)?$")


def _settings():
    text = read_file(CONF)
    port = re.search(r"^Port\s+(\d+)", text, re.M)
    pw = re.search(r"^PasswordAuthentication\s+(\w+)", text, re.M)
    return {"port": int(port.group(1)) if port else 22,
            "password": not pw or pw.group(1).lower() == "yes",
            "lan_only": "DenyUsers *" in text}


def _active():
    for unit in ("ssh.socket", "ssh.service"):
        rc, out, _ = run_rc(["systemctl", "is-active", unit], timeout=10)
        if out.strip() == "active":
            return True
    return False


def _enabled():
    for unit in ("ssh.socket", "ssh.service"):
        rc, out, _ = run_rc(["systemctl", "is-enabled", unit], timeout=10)
        if out.strip() == "enabled":
            return True
    return False


def _admins():
    from .users import list_users
    return [u for u in list_users() if u["admin"]]


def _keys_file(user):
    try:
        p = pwd.getpwnam(user)
    except KeyError:
        raise ApiError("Utente non trovato", 404)
    return p, os.path.join(p.pw_dir, ".ssh", "authorized_keys")


def _fingerprint(line):
    with tempfile.NamedTemporaryFile("w", suffix=".pub", delete=False) as f:
        f.write(line + "\n")
        tmp = f.name
    try:
        rc, out, _ = run_rc(["ssh-keygen", "-lf", tmp], timeout=10)
    finally:
        os.unlink(tmp)
    if rc != 0:
        return None
    parts = out.split()
    return {"bits": parts[0], "fingerprint": parts[1], "type": parts[-1].strip("()")} if len(parts) >= 2 else None


def _list_keys(user):
    p, path = _keys_file(user)
    res = []
    for line in read_file(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fp = _fingerprint(line)
        if fp:
            comment = line.split(None, 2)[2] if len(line.split(None, 2)) > 2 else ""
            res.append({**fp, "comment": comment})
    return res


def status():
    s = _settings()
    users = []
    for u in _admins():
        try:
            users.append({"name": u["name"], "keys": _list_keys(u["name"])})
        except ApiError:
            pass
    return {**s, "active": _active(), "enabled": _enabled(), "users": users,
            "hostname": os.uname().nodename}


def _write_conf(s):
    lines = ["# Gestito dall'interfaccia del NAS (Terminale > Accesso SSH): non modificare a mano.",
             f"Port {int(s['port'])}",
             f"PasswordAuthentication {'yes' if s['password'] else 'no'}",
             "PermitRootLogin no"]
    if s["lan_only"]:
        lines += ["", "# Solo dalla rete di casa: da qualunque altro indirizzo nessun utente può entrare",
                  "Match Address *," + ",".join("!" + x for x in LAN.split(",")), "    DenyUsers *"]
    old = read_file(CONF, None)
    write_file(CONF, "\n".join(lines) + "\n")
    rc, _, err = run_rc(["sshd", "-t"], timeout=20)
    if rc != 0:
        if old is None:
            os.unlink(CONF)
        else:
            write_file(CONF, old)
        raise ApiError("Configurazione SSH non valida: " + (err.strip().splitlines() or ["errore"])[-1])


def _restart():
    run(["systemctl", "daemon-reload"], check=False, timeout=60)
    if _active():
        run(["systemctl", "restart", "ssh.socket"], check=False, timeout=60)
        run(["systemctl", "restart", "ssh.service"], check=False, timeout=60)


def save(body):
    cur = _settings()
    s = dict(cur)
    if "port" in body:
        try:
            port = int(body["port"])
        except (TypeError, ValueError):
            raise ApiError("Porta non valida")
        if port != 22 and not 1024 <= port <= 65535:
            raise ApiError("Usa la porta 22 oppure una porta tra 1024 e 65535")
        if port in (80, 443, 445, 139, 2049, 8090):
            raise ApiError("Questa porta è già usata da un altro servizio del NAS")
        s["port"] = port
    for k in ("password", "lan_only"):
        if k in body:
            s[k] = bool(body[k])
    if not s["password"] and not any(u["keys"] for u in status()["users"]):
        raise ApiError("Aggiungi prima almeno una chiave: senza password e senza chiavi non potresti più entrare")
    _write_conf(s)
    _restart()
    if "enabled" in body:
        if body["enabled"]:
            run(["systemctl", "enable", "--now", "ssh.socket"], check=False, timeout=60)
        else:
            run(["systemctl", "disable", "--now", "ssh.socket", "ssh.service"], check=False, timeout=60)
    return status()


def add_key(user, key, name=""):
    if user not in {u["name"] for u in _admins()}:
        raise ApiError("Le chiavi SSH si aggiungono solo agli amministratori (gli altri utenti non hanno il terminale)")
    key = " ".join((key or "").strip().split())
    if not KEY_RE.match(key):
        raise ApiError("Chiave non valida: incolla il contenuto del file .pub (es. ssh-ed25519 AAAA… nome)")
    parts = key.split(None, 2)
    name = re.sub(r"[^\w .@()-]", "", name or "").strip()[:60]
    if name:
        key = f"{parts[0]} {parts[1]} {name}"
    fp = _fingerprint(key)
    if not fp:
        raise ApiError("Chiave non valida")
    if any(k["fingerprint"] == fp["fingerprint"] for k in _list_keys(user)):
        raise ApiError("Questa chiave c'è già")
    p, path = _keys_file(user)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    text = read_file(path)
    write_file(path, (text.rstrip("\n") + "\n" if text.strip() else "") + key + "\n", 0o600)
    for d in (os.path.dirname(path), path):
        os.chown(d, p.pw_uid, p.pw_gid)
    os.chmod(os.path.dirname(path), 0o700)
    return {"ok": True, **fp}


def remove_key(user, fingerprint):
    p, path = _keys_file(user)
    keep, found = [], False
    for line in read_file(path).splitlines():
        fp = _fingerprint(line.strip()) if line.strip() and not line.startswith("#") else None
        if fp and fp["fingerprint"] == fingerprint:
            found = True
            continue
        keep.append(line)
    if not found:
        raise ApiError("Chiave non trovata", 404)
    write_file(path, "\n".join(keep) + ("\n" if keep else ""), 0o600)
    os.chown(path, p.pw_uid, p.pw_gid)
    return {"ok": True}
