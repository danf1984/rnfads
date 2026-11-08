"""Condivisioni di rete: Samba (Windows/Mac) e NFS. Il DLNA non è più di sistema: si usa un'app Docker (es. minidlna)."""
import os
import re

from .util import (ApiError, ETC, check_name, check_path, have, load_json, read_file,
                   run, run_rc, save_json, write_file)

CONF = os.path.join(ETC, "shares.json")
SMB_CONF = "/etc/samba/smb.conf"
SMB_NIDO = "/etc/samba/nido-shares.conf"
NFS_EXPORTS = "/etc/exports.d/nido.exports"
HOMES_ROOT = "/DATA/Utenti"

DEFAULT = {"shares": [], "homes": True}
RESERVED = {"global", "homes", "printers", "print$", "ipc$"}


def load():
    data = load_json(CONF, None) or {}
    for k, v in DEFAULT.items():
        data.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return data


def get():
    data = load()
    from .users import list_users
    return {
        **data,
        "users": [u["name"] for u in list_users()],
        "hostname": os.uname().nodename,
        "services": {
            "samba": _active("smbd"),
            "nfs": _active("nfs-server") if have("exportfs") else None,
        },
    }


def _active(unit):
    rc, out, _ = run_rc(["systemctl", "is-active", unit], timeout=10)
    return out.strip() == "active"


def _has_recycle():
    import glob
    return bool(glob.glob("/usr/lib/*/samba/vfs/recycle.so") + glob.glob("/usr/lib/samba/vfs/recycle.so"))


# --- Samba ------------------------------------------------------------------------------

def _smb_quote(names):
    return " ".join(f'"{n}"' if " " in n else n for n in names)


def _render_samba(data):
    out = ["# Generato dall'interfaccia del NAS: non modificare a mano.", ""]
    if data.get("homes"):
        out += [
            "[homes]",
            "   comment = Cartella personale",
            f"   path = {HOMES_ROOT}/%S",
            "   browseable = no",
            "   read only = no",
            "   valid users = %S",
            "   create mask = 0600",
            "   directory mask = 0700",
            "",
        ]
    for s in data["shares"]:
        access = s.get("access", {})
        rw = sorted(u for u, a in access.items() if a == "rw")
        ro = sorted(u for u, a in access.items() if a == "ro")
        out += [f"[{s['name']}]",
                f"   path = {s['path']}",
                f"   comment = {s.get('comment') or s['name']}",
                "   browseable = yes",
                "   read only = yes",
                "   force group = users",
                "   create mask = 0664",
                "   directory mask = 2775"]
        if rw:
            out.append(f"   write list = {_smb_quote(rw)}")
        everyone = s.get("all_users")
        if everyone == "rw":
            out.append("   write list = @users" + (" " + _smb_quote(rw) if rw else ""))
        if s.get("guest"):
            out.append("   guest ok = yes")
        elif everyone:
            out.append("   valid users = @users" + (" " + _smb_quote(rw + ro) if rw + ro else ""))
        else:
            users = rw + ro
            out.append(f"   valid users = {_smb_quote(users) if users else 'nobody'}")
        if s.get("recycle") and _has_recycle():
            out += ["   vfs objects = recycle",
                    "   recycle:repository = .cestino/%U",
                    "   recycle:keeptree = yes",
                    "   recycle:versions = yes"]
        out.append("")
    return "\n".join(out)


def _ensure_include():
    text = read_file(SMB_CONF)
    line = f"include = {SMB_NIDO}"
    if line not in text:
        write_file(SMB_CONF, text.rstrip("\n") + f"\n\n# Condivisioni dell'interfaccia del NAS\n{line}\n")


def _apply_samba(data):
    old = read_file(SMB_NIDO, None)
    write_file(SMB_NIDO, _render_samba(data))
    _ensure_include()
    rc, _, err = run_rc(["testparm", "-s", SMB_CONF], timeout=30)
    if rc != 0:
        if old is None:
            os.unlink(SMB_NIDO)
        else:
            write_file(SMB_NIDO, old)
        raise ApiError("Configurazione Samba non valida: " + err.strip().splitlines()[-1] if err.strip() else "Configurazione Samba non valida")
    rc, _, _ = run_rc(["smbcontrol", "smbd", "reload-config"], timeout=20)
    if rc != 0:
        run(["systemctl", "restart", "smbd"], check=False, timeout=60)


# --- NFS -------------------------------------------------------------------------------

def _apply_nfs(data):
    if not have("exportfs"):
        return
    lines = ["# Generato dall'interfaccia del NAS"]
    for s in data["shares"]:
        if s.get("nfs"):
            hosts = s.get("nfs_hosts") or "*"
            mode = "rw" if s.get("nfs_rw", True) else "ro"
            for h in hosts.split():
                lines.append(f'"{s["path"]}" {h}({mode},sync,no_subtree_check,all_squash,anonuid=65534,anongid=100)')
    any_nfs = len(lines) > 1
    os.makedirs(os.path.dirname(NFS_EXPORTS), exist_ok=True)
    write_file(NFS_EXPORTS, "\n".join(lines) + "\n")
    if any_nfs:
        run(["systemctl", "enable", "--now", "nfs-server"], check=False, timeout=60)
        run(["exportfs", "-ra"], check=False, timeout=30)
    else:
        run(["exportfs", "-ra"], check=False, timeout=30)
        run(["systemctl", "disable", "--now", "nfs-server"], check=False, timeout=60)


def _fix_permissions(path):
    """Rende la cartella scrivibile dal gruppo "users" (solo la cartella stessa)."""
    try:
        st = os.stat(path)
        if st.st_uid == 0 and st.st_gid == 0:
            os.chown(path, 0, 100)
            os.chmod(path, (st.st_mode & 0o7777) | 0o2070)
    except OSError:
        pass


def apply_all(data=None):
    data = data or load()
    _apply_samba(data)
    _apply_nfs(data)


def save_share(body, original=None):
    data = load()
    name = check_name(body.get("name"), "Nome della condivisione")
    if name.lower() in RESERVED:
        raise ApiError("Questo nome è riservato")
    raw = (body.get("path") or "").strip().rstrip("/")
    # Una cartella nuova sul disco di sistema (/DATA, dove è installato il NAS) viene creata qui
    if raw.startswith("/DATA/") and not os.path.exists(raw) and ".." not in raw.split("/"):
        check_path(os.path.dirname(raw))
        try:
            os.makedirs(raw, mode=0o2775)
            os.chown(raw, 0, 100)
            os.chmod(raw, 0o2775)      # scrivibile per il gruppo "users" (makedirs risente della umask)
        except OSError as e:
            raise ApiError(f"Non riesco a creare la cartella {raw}: {e.strerror}") from None
    path = check_path(raw)
    from .users import list_users
    known = {u["name"] for u in list_users()}
    access = {}
    for u, a in (body.get("access") or {}).items():
        if u in known and a in ("rw", "ro"):
            access[u] = a
    share = {
        "name": name, "path": path, "comment": (body.get("comment") or "")[:80],
        "access": access, "guest": bool(body.get("guest")),
        "all_users": body.get("all_users") if body.get("all_users") in ("rw", "ro") else "",
        "recycle": bool(body.get("recycle")),
        "nfs": bool(body.get("nfs")), "nfs_rw": bool(body.get("nfs_rw", True)),
        "nfs_hosts": re.sub(r"[^0-9A-Za-z./*: -]", "", body.get("nfs_hosts") or "*").strip() or "*",
    }
    others = [s for s in data["shares"] if s["name"].lower() != (original or name).lower()]
    if any(s["name"].lower() == name.lower() for s in others):
        raise ApiError("Esiste già una condivisione con questo nome")
    data["shares"] = sorted(others + [share], key=lambda s: s["name"].lower())
    _fix_permissions(path)
    apply_all(data)
    save_json(CONF, data, 0o644)
    return share


def delete_share(name):
    data = load()
    before = len(data["shares"])
    data["shares"] = [s for s in data["shares"] if s["name"] != name]
    if len(data["shares"]) == before:
        raise ApiError("Condivisione non trovata", 404)
    apply_all(data)
    save_json(CONF, data, 0o644)
    return {"ok": True}


def save_settings(body):
    data = load()
    if "homes" in body:
        data["homes"] = bool(body["homes"])
    data.pop("dlna", None)
    apply_all(data)
    save_json(CONF, data, 0o644)
    return get()
