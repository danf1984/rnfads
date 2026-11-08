"""File manager: navigazione tra dischi e cartelle, operazioni sui file, cestino,
ricerca, anteprime e link di condivisione.

Si lavora solo dentro le cartelle consentite (/DATA, /media, /mnt, /srv): ogni
percorso viene risolto (anche i link simbolici) e controllato.
I file nuovi prendono proprietario e gruppo della cartella in cui finiscono, così
restano accessibili dalle condivisioni Samba.
"""
import datetime
import json
import mimetypes
import os
import re
import secrets
import shutil
import stat
import struct
import threading
import time

from . import jobs
from .util import ALLOWED_ROOTS, ApiError, STATE, load_json, run_rc, save_json

TRASH = ".nido-cestino"
LINKS = os.path.join(STATE, "share-links.json")
PART = ".nidopart"
_links_lock = threading.Lock()

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("text/yaml", ".yaml")
mimetypes.add_type("text/yaml", ".yml")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("application/toml", ".toml")
TEXT_EXT = {".txt", ".md", ".yaml", ".yml", ".json", ".log", ".conf", ".ini", ".cfg", ".py", ".js", ".sh",
            ".csv", ".xml", ".html", ".css", ".env", ".toml", ".service", ".ts", ".c", ".h", ".cpp", ".go", ".rs"}


def safe(path, must_exist=True):
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise ApiError("Percorso non valido")
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + "/") for r in ALLOWED_ROOTS):
        raise ApiError("Cartella non consentita", 403)
    if must_exist and not os.path.lexists(real):
        raise ApiError("File o cartella non trovati", 404)
    return real


def _check_name(name):
    name = (name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\x00" in name or len(name.encode()) > 255:
        raise ApiError("Nome non valido")
    if name == TRASH or name.endswith(PART):
        raise ApiError("Nome riservato")
    return name


def _inherit_owner(path):
    try:
        st = os.stat(os.path.dirname(path))
        os.lchown(path, st.st_uid, st.st_gid)
    except OSError:
        pass


def _unique(path):
    if not os.path.lexists(path):
        return path
    d, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    if base.startswith(".") and not ext:
        stem, ext = base, ""
    k = 2
    while True:
        cand = os.path.join(d, f"{stem} ({k}){ext}")
        if not os.path.lexists(cand):
            return cand
        k += 1


def kind(name, is_dir=False):
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    mime = mimetypes.guess_type(name)[0] or ""
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if ext == ".pdf":
        return "pdf"
    if ext in TEXT_EXT or mime.startswith("text/"):
        return "text"
    if ext in (".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".xz", ".bz2", ".zst"):
        return "archive"
    if ext in (".doc", ".docx", ".odt", ".rtf"):
        return "doc"
    if ext in (".xls", ".xlsx", ".ods"):
        return "sheet"
    if ext in (".ppt", ".pptx", ".odp"):
        return "slides"
    return "file"


# --- luoghi (colonna di sinistra) -----------------------------------------------------------------

def _lsblk_tran():
    rc, out, _ = run_rc(["lsblk", "-J", "-o", "PATH,TRAN,RM,MOUNTPOINTS,LABEL,FSTYPE,TYPE", "-s"], timeout=10)
    res = {}
    try:
        def walk(items, tran=None):
            for d in items or []:
                t = d.get("tran") or tran
                for mp in d.get("mountpoints") or []:
                    if mp:
                        res[mp] = {"tran": t, "rm": d.get("rm"), "label": d.get("label"), "fstype": d.get("fstype")}
                walk(d.get("children"), t)
        walk(json.loads(out or "{}").get("blockdevices"))
    except ValueError:
        pass
    return res


def _df(path):
    try:
        s = os.statvfs(path)
        return {"size": s.f_blocks * s.f_frsize, "free": s.f_bavail * s.f_frsize}
    except OSError:
        return {"size": 0, "free": 0}


def places(user=None):
    fav = []
    home = f"/DATA/Utenti/{user}" if user and os.path.isdir(f"/DATA/Utenti/{user}") else "/DATA"
    fav.append({"name": "Cartella personale", "path": home, "icon": "home"})
    for n, ic in (("Media", "folder"), ("Documenti", "folder"), ("Download", "download"), ("Foto", "folder")):
        p = os.path.join("/DATA", n)
        if os.path.isdir(p):
            fav.append({"name": n, "path": p, "icon": ic})
    # Cartelle aggiunte dall'utente (tasto destro → Aggiungi ai preferiti, o trascinandole)
    for p in favorites(user):
        if os.path.isdir(p) and not any(f["path"] == p for f in fav):
            fav.append({"name": os.path.basename(p) or p, "path": p, "icon": "star", "pinned": True})
    disks = [{"name": "Sistema", "path": "/DATA", "icon": "server", "system": True, **_df("/DATA")}]
    info = _lsblk_tran()
    seen = set()
    for line in open("/proc/self/mounts", encoding="utf-8", errors="replace"):
        f = line.split()
        if len(f) < 3:
            continue
        mp = f[1].replace("\\040", " ")
        if not mp.startswith(("/media/", "/mnt/", "/srv/")) or mp.startswith(("/media/rete/", "/media/cloud/")):
            continue
        if f[2] in ("cifs", "smb3", "nfs", "nfs4", "fuse", "davfs", "fuse.davfs2", "autofs") or mp in seen:
            continue
        seen.add(mp)
        i = info.get(mp, {})
        disks.append({"name": i.get("label") or os.path.basename(mp), "path": mp,
                      "icon": "usb" if i.get("tran") == "usb" or i.get("rm") else "disk",
                      "fstype": i.get("fstype") or f[2], **_df(mp)})
    from . import netmounts
    net = [{"name": m["label"], "path": m["mountpoint"], "icon": "globe", "proto": m["proto"].upper(),
            "mounted": m["mounted"], "id": m["id"]} for m in netmounts.list_mounts()]
    try:   # servizi cloud mostrati come cartella (Impostazioni > Servizi cloud)
        from . import cloud
        net += [{"name": r["name"], "path": r["mountpoint"], "icon": "globe", "proto": r["provider"].split(" (")[0],
                 "mounted": r["mounted"], "id": "cloud:" + r["name"], "cloud": True}
                for r in cloud.list_remotes()["remotes"] if r["mounted"] or r["autoboot"]]
    except Exception:  # noqa: BLE001 — rclone assente o configurazione illeggibile: niente cloud nella barra
        pass
    t = trash_list(summary=True)
    return {"favorites": fav, "disks": disks, "network": net, "trash": t}


# --- elenco e dettagli --------------------------------------------------------------------------------

def _entry(dirpath, de):
    try:
        st = de.stat(follow_symlinks=True)
    except OSError:
        try:
            st = de.stat(follow_symlinks=False)
        except OSError:
            return None
    is_dir = stat.S_ISDIR(st.st_mode)
    e = {"name": de.name, "dir": is_dir, "size": st.st_size if not is_dir else None,
         "mtime": int(st.st_mtime), "kind": kind(de.name, is_dir), "link": de.is_symlink()}
    if is_dir:
        try:
            with os.scandir(os.path.join(dirpath, de.name)) as it:
                n = 0
                for x in it:
                    if not x.name.startswith(".") and not x.name.endswith(PART):
                        n += 1
                        if n >= 9999:
                            break
                e["items"] = n
        except OSError:
            e["items"] = None
    return e


def list_dir(path, hidden=False):
    real = safe(path)
    if not os.path.isdir(real):
        raise ApiError("Non è una cartella")
    out = []
    try:
        with os.scandir(real) as it:
            for de in it:
                if de.name == TRASH or de.name.endswith(PART):
                    continue
                if not hidden and de.name.startswith("."):
                    continue
                e = _entry(real, de)
                if e:
                    out.append(e)
    except PermissionError:
        raise ApiError("Non hai il permesso di leggere questa cartella", 403)
    out.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    parent = os.path.dirname(real)
    if not any(parent == r or parent.startswith(r + "/") for r in ALLOWED_ROOTS):
        parent = None
    return {"path": real, "parent": parent, "entries": out, "space": _df(real),
            "writable": os.access(real, os.W_OK)}


def _image_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(64 * 1024)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) > 24:
        return struct.unpack(">II", head[16:24])
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        if head[12:16] == b"VP8X":
            w = int.from_bytes(head[24:27], "little") + 1
            h = int.from_bytes(head[27:30], "little") + 1
            return w, h
        return None
    if head[:2] == b"\xff\xd8":
        i = 2
        while i < len(head) - 9:
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", head[i + 5:i + 9])
                return w, h
            seg = struct.unpack(">H", head[i + 2:i + 4])[0]
            i += 2 + seg
    return None


def _exif(path):
    """Data di scatto e fotocamera da un JPEG (lettura minima dell'EXIF)."""
    try:
        with open(path, "rb") as f:
            data = f.read(128 * 1024)
    except OSError:
        return {}
    i = data.find(b"Exif\x00\x00")
    if data[:2] != b"\xff\xd8" or i < 0:
        return {}
    t = data[i + 6:]
    if len(t) < 8:
        return {}
    end = "<" if t[:2] == b"II" else ">"
    res = {}

    def ifd(off, depth=0):
        if off + 2 > len(t) or depth > 2:
            return
        n = struct.unpack(end + "H", t[off:off + 2])[0]
        for k in range(min(n, 200)):
            e = off + 2 + 12 * k
            if e + 12 > len(t):
                return
            tag, typ, cnt, val = struct.unpack(end + "HHI4s", t[e:e + 12])
            if typ == 2:
                voff = struct.unpack(end + "I", val)[0] if cnt > 4 else None
                raw = t[voff:voff + cnt] if voff is not None else val[:cnt]
                s = raw.split(b"\x00")[0].decode("utf-8", "replace").strip()
                if tag == 0x0110:
                    res["camera"] = s
                elif tag == 0x010F:
                    res["make"] = s
                elif tag == 0x9003:
                    res["taken"] = s
            elif tag == 0x8769:
                ifd(struct.unpack(end + "I", val)[0], depth + 1)
    try:
        ifd(struct.unpack(end + "I", t[4:8])[0])
    except struct.error:
        pass
    if res.get("make") and res.get("camera") and not res["camera"].startswith(res["make"].split()[0]):
        res["camera"] = f"{res['make']} {res['camera']}"
    res.pop("make", None)
    return res


def details(path):
    real = safe(path)
    st = os.stat(real)
    is_dir = stat.S_ISDIR(st.st_mode)
    try:
        import pwd
        import grp
        owner = pwd.getpwuid(st.st_uid).pw_name
        group = grp.getgrgid(st.st_gid).gr_name
    except (KeyError, ImportError):
        owner, group = str(st.st_uid), str(st.st_gid)
    d = {"path": real, "name": os.path.basename(real), "dir": is_dir, "size": st.st_size,
         "mtime": int(st.st_mtime), "ctime": int(st.st_ctime), "owner": owner, "group": group,
         "mode": stat.filemode(st.st_mode), "kind": kind(real, is_dir),
         "mime": None if is_dir else (mimetypes.guess_type(real)[0] or "application/octet-stream")}
    if d["kind"] == "image":
        sz = _image_size(real)
        if sz:
            d["width"], d["height"] = sz
        d.update(_exif(real))
    if is_dir:
        total, count, t0 = 0, 0, time.time()
        for root, dirs, fs in os.walk(real):
            dirs[:] = [x for x in dirs if x != TRASH]
            for f in fs:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
                count += 1
            if time.time() - t0 > 2:
                d["partial"] = True
                break
        d["size"], d["files"] = total, count
    return d


def read_text(path, limit=256 * 1024):
    real = safe(path)
    if os.path.isdir(real):
        raise ApiError("È una cartella")
    with open(real, "rb") as f:
        data = f.read(limit + 1)
    if b"\x00" in data[:8192]:
        raise ApiError("Il file non è di testo")
    return {"text": data[:limit].decode("utf-8", "replace"), "truncated": len(data) > limit}


# --- operazioni ----------------------------------------------------------------------------------

def mkdir(path, name):
    parent = safe(path)
    target = os.path.join(parent, _check_name(name))
    if os.path.lexists(target):
        raise ApiError("Esiste già un elemento con questo nome")
    os.mkdir(target)
    _inherit_owner(target)
    return {"path": target}


def rename(path, new_name):
    real = safe(path)
    target = os.path.join(os.path.dirname(real), _check_name(new_name))
    if target == real:
        return {"path": real}
    if os.path.lexists(target):
        raise ApiError("Esiste già un elemento con questo nome")
    os.rename(real, target)
    return {"path": target}


def _tree_size(paths):
    total = 0
    for p in paths:
        if os.path.isdir(p) and not os.path.islink(p):
            for root, _, fs in os.walk(p):
                for f in fs:
                    try:
                        total += os.lstat(os.path.join(root, f)).st_size
                    except OSError:
                        pass
        else:
            try:
                total += os.lstat(p).st_size
            except OSError:
                pass
    return total


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def _copystat(src, dst):
    try:
        shutil.copystat(src, dst, follow_symlinks=False)
    except OSError:
        pass  # alcune cartelle di rete non accettano date e permessi


def _copy_file(src, dst, job):
    """Copia un file passando da un nome provvisorio nascosto: se l'operazione viene annullata
    o il disco si riempie, il file di destinazione (anche quello da sovrascrivere) resta com'era."""
    tmp = os.path.join(os.path.dirname(dst), "." + os.path.basename(dst)[:200] + PART)
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                if job.cancel:
                    raise jobs.Cancelled()
                buf = fi.read(8 * 1024 * 1024)
                if not buf:
                    break
                fo.write(buf)
                job.add_bytes(len(buf))
        _copystat(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _inherit_owner(dst)


def _copy_tree(src, dst, job, overwrite=False):
    if job.cancel:
        raise jobs.Cancelled()
    if os.path.islink(src):
        if os.path.lexists(dst) and overwrite:
            _remove(dst)
        os.symlink(os.readlink(src), dst)
        return
    if os.path.isdir(src):
        if not os.path.isdir(dst):
            if os.path.lexists(dst) and overwrite:
                _remove(dst)
            os.mkdir(dst)
            _inherit_owner(dst)
        for n in os.listdir(src):
            if n == TRASH or n.endswith(PART):
                continue
            t = os.path.join(dst, n)
            if os.path.lexists(t) and not overwrite:
                continue
            _copy_tree(os.path.join(src, n), t, job, overwrite)
        _copystat(src, dst)
        job.items_done += 1
    else:
        if os.path.isdir(dst) and not os.path.islink(dst):
            if not overwrite:
                return
            shutil.rmtree(dst)
        _copy_file(src, dst, job)
        job.items_done += 1


def _place(src, dst, move, job, overwrite):
    """Copia o sposta src in dst. Con overwrite le cartelle si uniscono (i file con lo stesso
    nome vengono sostituiti), come in Esplora risorse."""
    if job.cancel:
        raise jobs.Cancelled()
    exists = os.path.lexists(dst)
    if exists and overwrite and os.path.isdir(src) and not os.path.islink(src) \
            and os.path.isdir(dst) and not os.path.islink(dst):
        for n in os.listdir(src):
            if n == TRASH:
                continue
            _place(os.path.join(src, n), os.path.join(dst, n), move, job, True)
        if move:
            try:
                os.rmdir(src)
            except OSError:
                pass
        return
    if move:
        try:
            if exists:
                if not overwrite:
                    return
                if os.path.isdir(dst) and not os.path.islink(dst):
                    shutil.rmtree(dst)
            os.rename(src, dst)        # stesso disco: immediato
            job.items_done += 1
            return
        except OSError as e:
            if e.errno not in (18, 95, 38):   # EXDEV e simili: copia + cancellazione
                raise
    _copy_tree(src, dst, job, overwrite)
    if move:
        _remove(src)


def conflicts(dest, paths=None, names=None):
    """Elementi che esistono già nella cartella di destinazione (prima di incollare,
    spostare o caricare), con dimensioni e date per la finestra dei conflitti."""
    dst = safe(dest)
    if not os.path.isdir(dst):
        raise ApiError("La destinazione non è una cartella")
    res = []
    items = [(safe(p), os.path.basename(safe(p))) for p in paths or []] + [(None, _check_name(n)) for n in names or []]
    for src, name in items:
        t = os.path.join(dst, name)
        if not os.path.lexists(t):
            continue
        same = src is not None and os.path.realpath(t) == src
        try:
            ts = os.stat(t)
        except OSError:
            continue
        e = {"name": name, "same": same, "dst_dir": stat.S_ISDIR(ts.st_mode), "dst_size": ts.st_size,
             "dst_mtime": int(ts.st_mtime)}
        if src:
            try:
                ss = os.stat(src)
                e.update(src_dir=stat.S_ISDIR(ss.st_mode), src_size=ss.st_size, src_mtime=int(ss.st_mtime))
            except OSError:
                pass
        res.append(e)
    return {"conflicts": res}


def transfer(paths, dest, move=False, policy=None):
    """Copia o sposta in una coda di operazioni (una alla volta, in background: prosegue anche
    chiudendo la pagina). policy: {"default": "rename|overwrite|skip", "names": {nome: azione}}."""
    if not paths:
        raise ApiError("Nessun elemento selezionato")
    srcs = [safe(p) for p in paths]
    dst_dir = safe(dest)
    if not os.path.isdir(dst_dir):
        raise ApiError("La destinazione non è una cartella")
    for s in srcs:
        if os.path.isdir(s) and (dst_dir == s or dst_dir.startswith(s + "/")):
            raise ApiError("Non puoi copiare o spostare una cartella dentro se stessa")
        if move and (s in ALLOWED_ROOTS or os.path.ismount(s)):
            raise ApiError("Non si può spostare un disco o una cartella principale")
    policy = policy or {}
    default = policy.get("default") if policy.get("default") in ("rename", "overwrite", "skip") else "rename"
    per_name = {k: v for k, v in (policy.get("names") or {}).items() if v in ("rename", "overwrite", "skip")}
    verb = "Sposto" if move else "Copio"

    def work(job):
        try:
            dev = os.stat(dst_dir).st_dev
            need = [s for s in srcs if not move or os.stat(s).st_dev != dev]
        except OSError:
            need = srcs
        job.set(step="Calcolo la dimensione…")
        job.bytes_total = _tree_size(need)
        job.items_total = len(srcs)
        results, skipped = [], 0
        for k, s in enumerate(srcs):
            if job.cancel:
                raise jobs.Cancelled()
            name = os.path.basename(s)
            target = os.path.join(dst_dir, name)
            overwrite = False
            if os.path.lexists(target):
                if os.path.realpath(target) == s:
                    if move:          # tagliato e incollato nella stessa cartella: niente da fare
                        skipped += 1
                        continue
                    stem, ext = os.path.splitext(name)
                    target = _unique(os.path.join(dst_dir, f"{stem} - copia{ext}"))
                else:
                    action = per_name.get(name, default)
                    if action == "skip":
                        skipped += 1
                        continue
                    if action == "rename":
                        target = _unique(target)
                    else:
                        overwrite = True
            job.set(step=f"{verb} {name}")
            _place(s, target, move, job, overwrite)
            results.append(target)
            if not job.bytes_total:
                job.progress = int(100 * (k + 1) / len(srcs))
        return {"paths": results, "skipped": skipped}

    n = len(srcs)
    title = f"{verb} {n} element{'o' if n == 1 else 'i'} in {os.path.basename(dst_dir) or dst_dir}"
    job = jobs.start("move" if move else "copy", title, work, target=None, exclusive=False, queue="files")
    return {"job": job.id}


# --- cestino ----------------------------------------------------------------------------------------

def _mount_of(path):
    p = path
    while not os.path.ismount(p) and p != "/":
        p = os.path.dirname(p)
    # Il cestino sta nella cartella consentita più vicina sullo stesso disco
    root = next((r for r in ALLOWED_ROOTS if path == r or path.startswith(r + "/")), None)
    if p == "/" or (root and len(root) > len(p)):
        p = root
    return p


def delete(paths, permanent=False):
    if not paths:
        raise ApiError("Nessun elemento selezionato")
    done = []
    for path in paths:
        real = safe(path)
        if real in ALLOWED_ROOTS or os.path.ismount(real):
            raise ApiError("Non si può eliminare un disco o una cartella principale")
        if permanent:
            if os.path.isdir(real) and not os.path.islink(real):
                shutil.rmtree(real)
            else:
                os.unlink(real)
            done.append(real)
            continue
        base = _mount_of(real)
        tdir = os.path.join(base, TRASH)
        os.makedirs(os.path.join(tdir, "files"), exist_ok=True)
        os.makedirs(os.path.join(tdir, "info"), exist_ok=True)
        tid = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)
        tsize = _tree_size([real])
        try:
            os.rename(real, os.path.join(tdir, "files", tid))
        except OSError:
            # Disco diverso (es. sottovolume): niente cestino, sposto dove posso
            shutil.move(real, os.path.join(tdir, "files", tid))
        save_json(os.path.join(tdir, "info", tid + ".json"),
                  {"orig": real, "deleted": int(time.time()), "name": os.path.basename(real), "size": tsize}, 0o644)
        done.append(real)
    return {"deleted": done}


def _trash_dirs():
    res = []
    cands = set(ALLOWED_ROOTS)
    for line in open("/proc/self/mounts", encoding="utf-8", errors="replace"):
        f = line.split()
        if len(f) > 1:
            cands.add(f[1].replace("\\040", " "))
    for c in cands:
        t = os.path.join(c, TRASH)
        if any(c == r or c.startswith(r + "/") for r in ALLOWED_ROOTS) and os.path.isdir(t):
            res.append(t)
    return sorted(set(res))


def trash_list(summary=False):
    items, total = [], 0
    for t in _trash_dirs():
        for f in os.listdir(os.path.join(t, "info")) if os.path.isdir(os.path.join(t, "info")) else []:
            if not f.endswith(".json"):
                continue
            info = load_json(os.path.join(t, "info", f), {})
            p = os.path.join(t, "files", f[:-5])
            if not os.path.lexists(p):
                continue
            # La dimensione è salvata quando l'elemento va nel cestino: rileggerla a ogni
            # richiesta su cartelle grandi rallentava la Home
            size = info.get("size")
            if size is None:
                size = _tree_size([p])
                info["size"] = size
                try:
                    save_json(os.path.join(t, "info", f), info, 0o644)
                except OSError:
                    pass
            total += size
            if not summary:
                items.append({"id": f[:-5], "trash": t, "name": info.get("name"), "orig": info.get("orig"),
                              "deleted": info.get("deleted"), "size": size, "dir": os.path.isdir(p),
                              "kind": kind(info.get("name") or "", os.path.isdir(p))})
    if summary:
        return {"size": total}
    items.sort(key=lambda x: -(x["deleted"] or 0))
    return {"items": items, "size": total}


def _trash_item(trash, tid):
    if trash not in _trash_dirs() or not re.match(r"^[0-9]{14}-[0-9a-f]{6}$", tid or ""):
        raise ApiError("Elemento del cestino non trovato", 404)
    return os.path.join(trash, "files", tid), os.path.join(trash, "info", tid + ".json")


def trash_restore(trash, tid):
    p, ip = _trash_item(trash, tid)
    info = load_json(ip, {})
    orig = info.get("orig") or ""
    try:
        safe(os.path.dirname(orig))
    except ApiError:
        raise ApiError("La cartella di origine non esiste più")
    os.makedirs(os.path.dirname(orig), exist_ok=True)
    target = _unique(orig)
    os.rename(p, target)
    os.unlink(ip)
    return {"path": target}


def trash_empty(trash=None, tid=None):
    if tid:
        p, ip = _trash_item(trash, tid)
        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.unlink(p)
        os.unlink(ip)
        return {"ok": True}
    for t in _trash_dirs():
        shutil.rmtree(t, ignore_errors=True)
    return {"ok": True}


# --- ricerca ---------------------------------------------------------------------------------------

def search(path, query, limit=500):
    real = safe(path)
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise ApiError("Scrivi almeno 2 caratteri")
    res, t0 = [], time.time()
    for root, dirs, fs in os.walk(real):
        dirs[:] = [d for d in dirs if d != TRASH and not d.startswith(".")]
        for n in dirs + fs:
            if q in n.lower() and not n.endswith(PART):
                full = os.path.join(root, n)
                is_dir = os.path.isdir(full)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                res.append({"name": n, "path": full, "dir": is_dir, "size": None if is_dir else st.st_size,
                            "mtime": int(st.st_mtime), "kind": kind(n, is_dir)})
                if len(res) >= limit:
                    return {"results": res, "partial": True}
        if time.time() - t0 > 8:
            return {"results": res, "partial": True}
    return {"results": res, "partial": False}


# --- caricamento a blocchi ------------------------------------------------------------------------------

def _upload_target(dirpath, name, create=False):
    d = safe(dirpath)
    if not os.path.isdir(d):
        raise ApiError("La cartella di destinazione non esiste")
    rel = (name or "").replace("\\", "/").strip("/")
    parts = [_check_name(p) for p in rel.split("/") if p]
    if not parts:
        raise ApiError("Nome file mancante")
    # Caricamento di cartelle: crea le sottocartelle
    for p in parts[:-1]:
        d = os.path.join(d, p)
        if not os.path.isdir(d):
            if not create:
                return d, parts[-1], None
            os.mkdir(d)
            _inherit_owner(d)
    return d, parts[-1], os.path.join(d, parts[-1])


def _part_name(d, leaf, total):
    # La dimensione totale nel nome del file provvisorio: se lo stesso file viene ricaricato
    # (anche dopo aver chiuso la pagina) il caricamento riprende da dove si era fermato.
    return os.path.join(d, f".{leaf[:180]}.{int(total)}{PART}")


def upload_status(dirpath, name, total):
    """Quanti byte di questo file sono già arrivati (per riprendere un caricamento interrotto)."""
    d, leaf, final = _upload_target(dirpath, name)
    try:
        total = int(total)
    except (TypeError, ValueError):
        raise ApiError("Dimensione non valida")
    if final is None:
        return {"received": 0}
    tmp = _part_name(d, leaf, total)
    try:
        return {"received": os.path.getsize(tmp)}
    except OSError:
        return {"received": 0}


def _clean_parts(d, days=3):
    """Toglie i caricamenti lasciati a metà da più di qualche giorno."""
    now = time.time()
    try:
        for de in os.scandir(d):
            if de.name.startswith(".") and de.name.endswith(PART):
                try:
                    if now - de.stat().st_mtime > days * 86400:
                        os.unlink(de.path)
                except OSError:
                    pass
    except OSError:
        pass


def upload_chunk(dirpath, name, offset, total, reader, length, conflict="rename"):
    """Scrive un blocco di un file caricato dal browser. I blocchi arrivano in ordine; se il
    blocco non comincia dove finisce il file provvisorio si risponde 409 con i byte già
    ricevuti (il browser riprende da lì). All'ultimo blocco il file prende il suo nome:
    con conflict="overwrite" sostituisce quello che c'è, altrimenti "(2)"."""
    d, leaf, final = _upload_target(dirpath, name, create=True)
    tmp = _part_name(d, leaf, total)
    if offset == 0:
        _clean_parts(d)
        mode = "wb"
    else:
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if have != offset:
            raise ApiError(f"received={have}", 409)
        mode = "ab"
    s = _df(d)
    if total - offset > s["free"]:
        raise ApiError("Spazio insufficiente sul disco")
    with open(tmp, mode) as f:
        left = length
        while left > 0:
            buf = reader.read(min(1024 * 1024, left))
            if not buf:
                raise ApiError("Connessione interrotta durante il caricamento", 400)
            f.write(buf)
            left -= len(buf)
    size = os.path.getsize(tmp)
    if size >= total:
        if conflict == "overwrite" and os.path.lexists(final) and not os.path.isdir(final):
            target = final
        else:
            target = _unique(final)
        os.replace(tmp, target)
        _inherit_owner(target)
        return {"done": True, "path": target}
    return {"done": False, "received": size}


# --- editor di testo ------------------------------------------------------------------------------------

EDIT_LIMIT = 4 * 1024 * 1024


def read_for_edit(path):
    real = safe(path)
    if os.path.isdir(real):
        raise ApiError("È una cartella")
    st = os.stat(real)
    if st.st_size > EDIT_LIMIT:
        raise ApiError("File troppo grande per l'editor (massimo 4 MB)")
    with open(real, "rb") as f:
        data = f.read()
    if b"\x00" in data[:8192]:
        raise ApiError("Il file non è di testo")
    try:
        text, enc = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, enc = data.decode("latin-1"), "latin-1"
    crlf = b"\r\n" in data[:65536]
    return {"path": real, "name": os.path.basename(real), "text": text.replace("\r\n", "\n") if crlf else text,
            "encoding": enc, "crlf": crlf, "mtime": str(st.st_mtime_ns), "size": st.st_size,
            "writable": os.access(real, os.W_OK)}


def save_text(path, text, mtime=None, encoding="utf-8", crlf=False, force=False):
    """Salva un file di testo dall'editor. Se nel frattempo il file è cambiato (un'app, un altro
    utente) si risponde 409 invece di sovrascrivere, a meno di force."""
    real = safe(path, must_exist=False)
    if not isinstance(text, str) or len(text) > EDIT_LIMIT * 2:
        raise ApiError("Testo non valido o troppo lungo")
    exists = os.path.lexists(real)
    if exists and os.path.isdir(real):
        raise ApiError("È una cartella")
    if exists and mtime is not None and not force and os.stat(real).st_mtime_ns != int(mtime):
        raise ApiError("Il file è stato modificato da un'altra parte dopo che l'hai aperto", 409)
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode(encoding if encoding in ("utf-8", "latin-1") else "utf-8", "replace")
    d = os.path.dirname(real)
    tmp = os.path.join(d, "." + os.path.basename(real)[:200] + PART)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if exists:
        st = os.stat(real)
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
    os.replace(tmp, real)
    if not exists:
        _inherit_owner(real)
    st = os.stat(real)
    return {"path": real, "mtime": str(st.st_mtime_ns), "size": st.st_size}


def new_file(path, name):
    parent = safe(path)
    target = os.path.join(parent, _check_name(name))
    if os.path.lexists(target):
        raise ApiError("Esiste già un elemento con questo nome")
    with open(target, "x", encoding="utf-8"):
        pass
    _inherit_owner(target)
    return {"path": target}


# --- preferiti -----------------------------------------------------------------------------------------

FAVS = os.path.join(STATE, "files-favorites.json")


def favorites(user):
    return [p for p in load_json(FAVS, {}).get(user or "", []) if isinstance(p, str)]


def set_favorite(user, path, on=True):
    real = safe(path)
    if not os.path.isdir(real):
        raise ApiError("Solo le cartelle possono andare nei preferiti")
    data = load_json(FAVS, {})
    lst = [p for p in data.get(user or "", []) if p != real]
    if on:
        lst.append(real)
    data[user or ""] = lst[:40]
    save_json(FAVS, data, 0o644)
    return {"favorites": data[user or ""]}


def move_favorite(user, path, to):
    data = load_json(FAVS, {})
    lst = data.get(user or "", [])
    if path in lst:
        lst.remove(path)
        lst.insert(max(0, min(int(to), len(lst))), path)
        data[user or ""] = lst
        save_json(FAVS, data, 0o644)
    return {"favorites": lst}


# --- dimensione delle cartelle --------------------------------------------------------------------------

def dir_size(paths, limit=25):
    """Dimensione di file e cartelle calcolata su richiesta (al massimo `limit` secondi)."""
    total, files, dirs, t0, partial = 0, 0, 0, time.time(), False
    per = {}
    for path in paths or []:
        real = safe(path)
        sub = 0
        if os.path.isdir(real) and not os.path.islink(real):
            for root, ds, fs in os.walk(real):
                ds[:] = [x for x in ds if x != TRASH]
                dirs += len(ds)
                for f in fs:
                    try:
                        st = os.lstat(os.path.join(root, f))
                        sub += st.st_size
                    except OSError:
                        pass
                    files += 1
                if time.time() - t0 > limit:
                    partial = True
                    break
        else:
            try:
                sub = os.lstat(real).st_size
                files += 1
            except OSError:
                pass
        per[real] = sub
        total += sub
        if partial:
            break
    return {"size": total, "files": files, "dirs": dirs, "partial": partial, "items": per,
            "seconds": round(time.time() - t0, 1)}


# --- permessi --------------------------------------------------------------------------------------------

def _owners():
    import grp
    import pwd
    users = [{"name": u.pw_name, "uid": u.pw_uid} for u in pwd.getpwall()
             if u.pw_uid == 0 or 1000 <= u.pw_uid < 60000]
    groups = [{"name": g.gr_name, "gid": g.gr_gid} for g in grp.getgrall()
              if g.gr_gid in (0, 100) or 1000 <= g.gr_gid < 60000 or g.gr_name in ("users", "sambashare", "docker")]
    return sorted(users, key=lambda x: (x["uid"] == 0, x["name"])), sorted(groups, key=lambda x: (x["gid"] == 0, x["name"]))


def _level(mode, shift):
    r, w = mode >> (shift + 2) & 1, mode >> (shift + 1) & 1
    return "rw" if r and w else "r" if r else "w" if w else "none"


def perms_info(path):
    import grp
    import pwd
    real = safe(path)
    st = os.lstat(real)
    users, groups = _owners()
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)
    m = stat.S_IMODE(st.st_mode)
    return {"path": real, "dir": stat.S_ISDIR(st.st_mode), "owner": owner, "group": group,
            "mode": f"{m:04o}", "text": stat.filemode(st.st_mode),
            "levels": {"owner": _level(m, 6), "group": _level(m, 3), "other": _level(m, 0)},
            "users": users, "groups": groups}


def _mode_for(levels, is_dir, old):
    bits = {"none": 0, "r": 4, "w": 2, "rw": 6}
    m = 0
    for who, shift in (("owner", 6), ("group", 3), ("other", 0)):
        lv = bits.get(levels.get(who, "none"), 0)
        if lv & 4 and (is_dir or old >> shift & 1):
            lv |= 1          # cartelle leggibili = attraversabili; i programmi restano eseguibili
        m |= lv << shift
    return m | (old & 0o7000 if is_dir else 0)


def set_perms(paths, owner=None, group=None, levels=None, recursive=False):
    import grp
    import pwd
    if not paths:
        raise ApiError("Nessun elemento selezionato")
    reals = [safe(p) for p in paths]
    uid = gid = -1
    if owner:
        try:
            uid = pwd.getpwnam(owner).pw_uid
        except KeyError:
            raise ApiError(f"Utente sconosciuto: {owner}")
    if group:
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError:
            raise ApiError(f"Gruppo sconosciuto: {group}")
    if levels is not None and not isinstance(levels, dict):
        raise ApiError("Permessi non validi")

    def apply(p, job=None):
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            return
        if uid != -1 or gid != -1:
            os.chown(p, uid, gid)
        if levels:
            os.chmod(p, _mode_for(levels, stat.S_ISDIR(st.st_mode), stat.S_IMODE(st.st_mode)))
        if job:
            job.items_done += 1

    if not recursive:
        for p in reals:
            apply(p)
        return {"ok": True, "info": perms_info(reals[0])}

    def work(job):
        job.items_total = 0
        for p in reals:
            apply(p, job)
            if os.path.isdir(p) and not os.path.islink(p):
                for root, ds, fs in os.walk(p):
                    ds[:] = [x for x in ds if x != TRASH]
                    for n in ds + fs:
                        if job.cancel:
                            raise jobs.Cancelled()
                        apply(os.path.join(root, n), job)
                    job.step = f"{job.items_done} elementi aggiornati"
        return {"items": job.items_done}

    job = jobs.start("perms", f"Permessi di {len(reals)} element{'o' if len(reals) == 1 else 'i'}", work,
                     exclusive=False, queue="files")
    return {"job": job.id}


# --- archivi (zip, 7z, tar.gz) ----------------------------------------------------------------------------

ARCH_EXT = (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst", ".tgz", ".txz", ".tbz2", ".tar", ".zip", ".7z", ".rar")


def _seven():
    from shutil import which
    return which("7z") or which("7zz") or which("7za")


def _arch_stem(name):
    low = name.lower()
    for e in ARCH_EXT:
        if low.endswith(e):
            return name[:-len(e)] or "archivio"
    return os.path.splitext(name)[0] or "archivio"


def _run_7z(args, job, cwd=None):
    import subprocess
    exe = _seven()
    if not exe:
        raise ApiError("Manca il programma 7-Zip (pacchetto 7zip)")
    p = subprocess.Popen([exe] + args + ["-bsp1", "-bso0", "-bse1", "-y"], cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail_lines = []
    buf = ""
    while True:
        ch = p.stdout.read(1)
        if not ch:
            break
        if ch in "\r\n\b":
            m = re.search(r"(\d+)%", buf)
            if m:
                job.progress = min(99, int(m.group(1)))
            elif buf.strip():
                tail_lines = (tail_lines + [buf.strip()])[-5:]
            buf = ""
            if job.cancel:
                p.kill()
                p.wait()
                raise jobs.Cancelled()
        else:
            buf += ch
    rc = p.wait()
    if rc not in (0, 1):
        msg = next((x for x in reversed(tail_lines) if "ERROR" in x.upper() or "Wrong" in x), tail_lines[-1] if tail_lines else "")
        if "Wrong password" in msg or "password" in msg.lower():
            raise ApiError("L'archivio è protetto da password: non supportato")
        raise ApiError(f"7-Zip: {msg or 'errore ' + str(rc)}")


def compress(paths, fmt="zip", name=None):
    """Crea un archivio con gli elementi scelti, nella loro cartella."""
    if not paths:
        raise ApiError("Nessun elemento selezionato")
    if fmt not in ("zip", "7z", "tar.gz"):
        raise ApiError("Formato non supportato")
    reals = [safe(p) for p in paths]
    parent = os.path.dirname(reals[0])
    if any(os.path.dirname(r) != parent for r in reals):
        raise ApiError("Gli elementi devono stare nella stessa cartella")
    base = _check_name(name) if name else (os.path.basename(reals[0]) if len(reals) == 1 else "Archivio")
    if not base.lower().endswith("." + fmt):
        base += "." + fmt
    out = _unique(os.path.join(parent, base))

    def work(job):
        job.bytes_total = _tree_size(reals)
        tmp = os.path.join(parent, "." + os.path.basename(out) + PART)
        try:
            if fmt == "zip":
                import zipfile
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6) as z:
                    for r in reals:
                        for full in _walk_all(r):
                            if job.cancel:
                                raise jobs.Cancelled()
                            arc = os.path.relpath(full, parent)
                            job.step = arc
                            if os.path.isdir(full) and not os.path.islink(full):
                                z.write(full, arc + "/")
                                continue
                            with open(full, "rb") as fi, z.open(_zinfo(full, arc), "w", force_zip64=True) as fo:
                                while True:
                                    if job.cancel:
                                        raise jobs.Cancelled()
                                    b = fi.read(4 * 1024 * 1024)
                                    if not b:
                                        break
                                    fo.write(b)
                                    job.add_bytes(len(b))
            elif fmt == "tar.gz":
                import tarfile

                class Counted:
                    def __init__(self, f):
                        self.f = f

                    def read(self, n=-1):
                        if job.cancel:
                            raise jobs.Cancelled()
                        b = self.f.read(n)
                        job.add_bytes(len(b))
                        return b
                with tarfile.open(tmp, "w:gz", compresslevel=6) as t:
                    for r in reals:
                        for full in _walk_all(r):
                            arc = os.path.relpath(full, parent)
                            job.step = arc
                            ti = t.gettarinfo(full, arc)
                            if ti.isreg():
                                with open(full, "rb") as fi:
                                    t.addfile(ti, Counted(fi))
                            else:
                                t.addfile(ti)
            else:
                job.step = "Comprimo con 7-Zip…"
                _run_7z(["a", "-t7z", "-mx=5", tmp, "--"] + [os.path.basename(r) for r in reals], job, cwd=parent)
            os.replace(tmp, out)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        _inherit_owner(out)
        return {"path": out}

    job = jobs.start("compress", f"Comprimo in {os.path.basename(out)}", work, exclusive=False, queue="files")
    return {"job": job.id, "path": out}


def _zinfo(full, arc):
    import zipfile
    zi = zipfile.ZipInfo.from_file(full, arc)
    zi.compress_type = zipfile.ZIP_DEFLATED
    return zi


def _walk_all(root):
    yield root
    if os.path.isdir(root) and not os.path.islink(root):
        for r, ds, fs in os.walk(root):
            ds[:] = sorted(x for x in ds if x != TRASH)
            for n in ds + sorted(fs):
                if not n.endswith(PART):
                    yield os.path.join(r, n)


def is_archive(name):
    return name.lower().endswith(ARCH_EXT)


def extract(path):
    """Estrae un archivio nella sua cartella. Se dentro c'è una sola cartella si estrae così
    com'è, altrimenti in una cartella nuova con il nome dell'archivio. Si lavora in una
    cartella provvisoria nascosta: niente file a metà se si annulla."""
    real = safe(path)
    if os.path.isdir(real) or not is_archive(real):
        raise ApiError("Non è un archivio supportato (zip, 7z, rar, tar, tar.gz, tar.xz)")
    parent = os.path.dirname(real)
    stem = _arch_stem(os.path.basename(real))
    low = real.lower()

    def work(job):
        tmp = os.path.join(parent, "." + stem[:150] + ".estrai" + PART)
        shutil.rmtree(tmp, ignore_errors=True)
        os.mkdir(tmp)
        root_tmp = os.path.realpath(tmp)
        try:
            if low.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(real) as z:
                    infos = z.infolist()
                    job.bytes_total = sum(i.file_size for i in infos)
                    for i in infos:
                        if job.cancel:
                            raise jobs.Cancelled()
                        if i.flag_bits & 0x1:
                            raise ApiError("L'archivio è protetto da password: non supportato")
                        name = i.filename.replace("\\", "/")
                        dest = os.path.realpath(os.path.join(tmp, name))
                        if not (dest == root_tmp or dest.startswith(root_tmp + "/")):
                            continue          # percorso che esce dalla cartella: ignorato
                        job.step = name
                        if name.endswith("/"):
                            os.makedirs(dest, exist_ok=True)
                            continue
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with z.open(i) as fi, open(dest, "wb") as fo:
                            while True:
                                if job.cancel:
                                    raise jobs.Cancelled()
                                b = fi.read(4 * 1024 * 1024)
                                if not b:
                                    break
                                fo.write(b)
                                job.add_bytes(len(b))
                        t = time.mktime(i.date_time + (0, 0, -1)) if i.date_time[0] > 1980 else None
                        if t:
                            os.utime(dest, (t, t))
            elif re.search(r"\.(tar(\.(gz|xz|bz2))?|tgz|txz|tbz2)$", low):
                import tarfile
                with tarfile.open(real) as t:
                    members = t.getmembers()
                    job.bytes_total = sum(m.size for m in members if m.isreg())
                    for m in members:
                        if job.cancel:
                            raise jobs.Cancelled()
                        job.step = m.name
                        try:
                            t.extract(m, tmp, filter="data")
                        except (tarfile.FilterError, OSError) as e:
                            job.log(f"saltato {m.name}: {e}")
                            continue
                        if m.isreg():
                            job.add_bytes(m.size)
            else:
                job.step = "Estraggo con 7-Zip…"
                _run_7z(["x", real, "-o" + tmp], job)
            top = [n for n in os.listdir(tmp) if n not in ("__MACOSX",)]
            if len(top) == 1 and os.path.isdir(os.path.join(tmp, top[0])):
                final = _unique(os.path.join(parent, top[0]))
                os.rename(os.path.join(tmp, top[0]), final)
                shutil.rmtree(tmp, ignore_errors=True)
            else:
                final = _unique(os.path.join(parent, stem))
                os.rename(tmp, final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        # Proprietario come la cartella che lo contiene (accessibile dalle condivisioni)
        try:
            st = os.stat(parent)
            for r, ds, fs in os.walk(final):
                for n in ds + fs:
                    try:
                        os.lchown(os.path.join(r, n), st.st_uid, st.st_gid)
                    except OSError:
                        pass
            os.lchown(final, st.st_uid, st.st_gid)
        except OSError:
            pass
        return {"path": final}

    job = jobs.start("extract", f"Estraggo {os.path.basename(real)}", work, exclusive=False, queue="files")
    return {"job": job.id}


# --- miniature -------------------------------------------------------------------------------------------

THUMBS = os.path.join(STATE, "thumbs")
_thumb_sem = threading.Semaphore(2)
VIDEO_THUMB = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".mpg", ".mpeg", ".ts"}


def thumbnail(path, size=256):
    """Miniatura JPEG generata dal NAS (cache in /var/lib/nido/thumbs): le foto non arrivano
    più intere al browser. Video con ffmpegthumbnailer, se c'è. Restituisce il percorso o None."""
    import hashlib
    real = safe(path)
    size = 512 if int(size or 256) > 256 else 256
    st = os.stat(real)
    key = hashlib.sha1(f"{real}\0{st.st_mtime_ns}\0{st.st_size}\0{size}".encode()).hexdigest()
    out = os.path.join(THUMBS, key[:2], key + ".jpg")
    if os.path.exists(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ext = os.path.splitext(real)[1].lower()
    tmp = out + f".{os.getpid()}.{threading.get_ident()}.tmp"
    with _thumb_sem:
        if os.path.exists(out):
            return out
        if ext in VIDEO_THUMB:
            from shutil import which
            if not which("ffmpegthumbnailer"):
                return None
            rc, _, _ = run_rc(["ffmpegthumbnailer", "-i", real, "-o", tmp, "-s", str(size), "-t", "15%", "-q", "7",
                               "-c", "jpeg"], timeout=40)
            if rc != 0 or not os.path.exists(tmp):
                return None
        else:
            try:
                from PIL import Image, ImageOps
            except ImportError:
                return None
            try:
                Image.MAX_IMAGE_PIXELS = 300_000_000
                with Image.open(real) as im:
                    im.draft("RGB", (size * 2, size * 2))
                    im = ImageOps.exif_transpose(im)
                    im.thumbnail((size, size))
                    if im.mode not in ("RGB", "L"):
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        im2 = im.convert("RGBA")
                        bg.paste(im2, mask=im2.split()[-1])
                        im = bg
                    im.save(tmp, "JPEG", quality=82, optimize=True)
            except Exception:  # noqa: BLE001 — foto rovinata o formato sconosciuto
                return None
        os.replace(tmp, out)
    return out


def clean_thumbs(max_mb=2048):
    """Tiene la cache delle miniature sotto una certa dimensione (le più vecchie se ne vanno)."""
    files = []
    for r, _, fs in os.walk(THUMBS):
        for f in fs:
            p = os.path.join(r, f)
            try:
                st = os.stat(p)
                files.append((st.st_atime, st.st_size, p))
            except OSError:
                pass
    total = sum(x[1] for x in files)
    for _, sz, p in sorted(files):
        if total <= max_mb * 1024 * 1024:
            break
        try:
            os.unlink(p)
            total -= sz
        except OSError:
            pass


# --- link di condivisione ---------------------------------------------------------------------------

def _links():
    data = load_json(LINKS, {})
    now = time.time()
    return {k: v for k, v in data.items() if not v.get("expires") or v["expires"] > now}


def share_create(path, days, user):
    real = safe(path)
    try:
        days = int(days or 7)
    except (TypeError, ValueError):
        days = 7
    with _links_lock:
        links = _links()
        for k, v in links.items():
            if v["path"] == real and (not days or v.get("expires")):
                return {"token": k, **v}
        token = secrets.token_urlsafe(18)
        links[token] = {"path": real, "name": os.path.basename(real), "dir": os.path.isdir(real),
                        "created": int(time.time()), "expires": int(time.time() + days * 86400) if days > 0 else None,
                        "user": user, "downloads": 0}
        save_json(LINKS, links, 0o600)
    return {"token": token, **links[token]}


def share_list():
    return {"links": [{"token": k, **v} for k, v in sorted(_links().items(), key=lambda x: -x[1]["created"])]}


def share_delete(token):
    with _links_lock:
        links = _links()
        if links.pop(token, None) is None:
            raise ApiError("Link non trovato", 404)
        save_json(LINKS, links, 0o600)
    return {"ok": True}


def share_resolve(token):
    if not re.match(r"^[A-Za-z0-9_-]{10,40}$", token or ""):
        return None
    with _links_lock:
        links = _links()
        v = links.get(token)
        if not v or not os.path.lexists(v["path"]):
            return None
        v["downloads"] = v.get("downloads", 0) + 1
        save_json(LINKS, links, 0o600)
    return v
