"""Utenti del NAS: account Linux + Samba con la stessa password e cartella personale."""
import grp
import os
import pwd
import shutil

from .util import USER_RE, ApiError, run, run_rc

HOMES_ROOT = "/DATA/Utenti"


def _samba_users():
    rc, out, _ = run_rc(["pdbedit", "-L"], timeout=20)
    return {line.split(":")[0] for line in out.splitlines() if ":" in line}


def _group_members(name):
    try:
        return set(grp.getgrnam(name).gr_mem)
    except KeyError:
        return set()


def list_users():
    smb = _samba_users()
    admins = _group_members("sudo")
    res = []
    for p in pwd.getpwall():
        # Solo gli utenti del NAS (non gli account di servizio dei programmi)
        if 1000 <= p.pw_uid < 60000 and p.pw_dir.startswith(("/home/", HOMES_ROOT + "/")):
            res.append({
                "name": p.pw_name,
                "fullname": p.pw_gecos.split(",")[0],
                "admin": p.pw_name in admins,
                "samba": p.pw_name in smb,
                "home": p.pw_dir,
            })
    return sorted(res, key=lambda u: u["name"])


def _set_password(name, password):
    if not password or len(password) < 6:
        raise ApiError("La password deve avere almeno 6 caratteri")
    if "\n" in password or ":" in password:
        raise ApiError("La password non può contenere \":\" o a capo")
    run(["chpasswd"], input=f"{name}:{password}\n")
    run(["smbpasswd", "-a", "-s", name], input=f"{password}\n{password}\n")
    run(["smbpasswd", "-e", name], check=False)


def create(body):
    name = (body.get("name") or "").strip().lower()
    if not USER_RE.match(name):
        raise ApiError("Nome utente non valido: lettere minuscole, numeri, _ e - (inizia con una lettera)")
    try:
        pwd.getpwnam(name)
        raise ApiError("Esiste già un utente (o un account di sistema) con questo nome")
    except KeyError:
        pass
    fullname = "".join(c for c in (body.get("fullname") or "") if c not in ":,\n")[:60]
    admin = bool(body.get("admin"))
    home = os.path.join(HOMES_ROOT, name)
    groups = "users,sudo" if admin else "users"
    run(["useradd", "-M", "-d", home, "-s", "/bin/bash" if admin else "/usr/sbin/nologin",
         "-c", fullname, "-G", groups, name])
    try:
        _set_password(name, body.get("password"))
    except ApiError:
        run(["userdel", name], check=False)
        raise
    os.makedirs(home, exist_ok=True)
    p = pwd.getpwnam(name)
    os.chown(home, p.pw_uid, 100)
    os.chmod(home, 0o700)
    return {"ok": True}


def update(name, body):
    try:
        p = pwd.getpwnam(name)
    except KeyError:
        raise ApiError("Utente non trovato", 404)
    if p.pw_uid < 1000:
        raise ApiError("Account di sistema")
    if body.get("password"):
        _set_password(name, body["password"])
    if "fullname" in body:
        fullname = "".join(c for c in body["fullname"] if c not in ":,\n")[:60]
        run(["usermod", "-c", fullname, name])
    if "admin" in body:
        admins = _group_members("sudo")
        if body["admin"]:
            run(["usermod", "-aG", "sudo", name])
            run(["usermod", "-s", "/bin/bash", name])
        elif name in admins:
            if len(admins & {u["name"] for u in list_users()}) <= 1:
                raise ApiError("Deve restare almeno un amministratore")
            run(["gpasswd", "-d", name, "sudo"])
            run(["usermod", "-s", "/usr/sbin/nologin", name])
    return {"ok": True}


def delete(name, remove_files=False):
    users = {u["name"]: u for u in list_users()}
    if name not in users:
        raise ApiError("Utente non trovato", 404)
    admins = [u for u in users.values() if u["admin"]]
    if users[name]["admin"] and len(admins) <= 1:
        raise ApiError("Non puoi eliminare l'unico amministratore")
    run(["smbpasswd", "-x", name], check=False)
    run(["userdel", name])
    home = os.path.realpath(users[name]["home"])
    if remove_files and home.startswith(HOMES_ROOT + "/") and os.path.isdir(home):
        shutil.rmtree(home, ignore_errors=True)
    # Toglie l'utente dai permessi delle condivisioni
    from . import shares
    data = shares.load()
    changed = False
    for s in data["shares"]:
        if name in s.get("access", {}):
            del s["access"][name]
            changed = True
    if changed:
        shares.apply_all(data)
        from .util import save_json
        save_json(shares.CONF, data, 0o644)
    return {"ok": True}
