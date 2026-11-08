"""Dischi: elenco, salute (SMART), formattazione, montaggio, spazio Docker.

I dischi montati dall'interfaccia vanno in /media/<nome> (visibili nel file manager e nelle app)
e, se richiesto, restano montati a ogni avvio tramite /etc/fstab (righe con il segno "# nido").
Il disco di sistema e la chiavetta del sistema live non si toccano mai.

Per le prove senza dischi veri: NIDO_TEST_LOOP=1 mostra anche i dispositivi loop
(file immagine collegati con "losetup -P").
"""
import json
import os
import re
import threading
import time

from .util import ApiError, have, read_file, run, run_rc, write_file

FSTAB = os.environ.get("NIDO_FSTAB", "/etc/fstab")
MARK = "# nido"
MEDIA_ROOT = "/media"
TEST_LOOP = os.environ.get("NIDO_TEST_LOOP") == "1"

# Formati che si possono creare dall'interfaccia (max = lunghezza massima del nome)
FORMATS = {
    "ext4":  {"label": "ext4", "max": 16, "gpt": "8300"},
    "btrfs": {"label": "Btrfs", "max": 255, "gpt": "8300"},
    "exfat": {"label": "exFAT", "max": 15, "gpt": "0700"},
    "ntfs":  {"label": "NTFS", "max": 32, "gpt": "0700"},
    "vfat":  {"label": "FAT32", "max": 11, "gpt": "0700"},
    "xfs":   {"label": "XFS", "max": 12, "gpt": "8300"},
}
MKFS = {"ext4": "mkfs.ext4", "btrfs": "mkfs.btrfs", "exfat": "mkfs.exfat", "ntfs": "mkfs.ntfs",
        "vfat": "mkfs.vfat", "xfs": "mkfs.xfs"}
# File system che si possono montare
MOUNTABLE = {"ext2", "ext3", "ext4", "btrfs", "xfs", "exfat", "vfat", "ntfs", "ntfs3", "hfsplus", "f2fs"}
FS_NAMES = {"vfat": "FAT32", "ntfs": "NTFS", "ntfs3": "NTFS", "exfat": "exFAT", "btrfs": "Btrfs", "xfs": "XFS",
            "ext4": "ext4", "ext3": "ext3", "ext2": "ext2", "swap": "swap", "LVM2_member": "LVM",
            "linux_raid_member": "RAID", "crypto_LUKS": "cifrato (LUKS)", "hfsplus": "HFS+", "apfs": "APFS",
            "zfs_member": "ZFS", "f2fs": "F2FS", "iso9660": "CD/DVD"}

_smart_cache = {}
_smart_lock = threading.Lock()
SMART_TTL = 300


# --- informazioni -----------------------------------------------------------------

_blkid_cache = {}


def forget_probe():
    """Dopo una formattazione o un montaggio: rileggi tipo ed etichetta."""
    _blkid_cache.clear()


def _lsblk():
    out = run(["lsblk", "-J", "-b", "-o",
               "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,WWN,TRAN,ROTA,RM,PKNAME,"
               "FSSIZE,FSUSED,FSAVAIL,PARTLABEL,PARTTYPENAME,RO"])
    devs = json.loads(out).get("blockdevices", [])
    # lsblk prende tipo ed etichetta dal database di udev, che può essere in ritardo (disco appena
    # collegato o formattato): per quelli che mancano chiedo direttamente a blkid
    missing = []

    def walk(items):
        for d in items or []:
            if not d.get("fstype") and d.get("type") in ("part", "disk", "loop"):
                missing.append(d)
            walk(d.get("children"))
    walk(devs)
    for d in missing:
        if d["name"].startswith(("zram", "sr", "ram", "fd")) or (d["name"].startswith("loop") and not TEST_LOOP):
            continue
        key = (d["path"], d.get("size"))
        i = _blkid_cache.get(key)
        if i is None:
            # letto una volta sola: blkid legge il disco e lo sveglierebbe dallo standby
            rc, out, _ = run_rc(["blkid", "-p", "-o", "export", d["path"]], timeout=15)
            i = _blkid_cache[key] = {k: re.sub(r"\\(.)", r"\1", v) for k, v in
                                    (line.split("=", 1) for line in out.splitlines() if "=" in line)}
        if i.get("TYPE"):
            d["fstype"] = i["TYPE"]
            d["label"] = d.get("label") or i.get("LABEL")
            d["uuid"] = d.get("uuid") or i.get("UUID")
        if not d.get("partlabel") and i.get("PART_ENTRY_NAME"):
            d["partlabel"] = i["PART_ENTRY_NAME"]
    return devs


def _source_disk(mountpoint):
    rc, out, _ = run_rc(["findmnt", "-no", "SOURCE", mountpoint], timeout=10)
    if rc != 0 or not out.strip():
        return None
    src = re.sub(r"\[.*\]$", "", out.strip().splitlines()[0])
    rc, out, _ = run_rc(["lsblk", "-no", "PKNAME", src], timeout=10)
    parent = out.strip().splitlines()[0] if out.strip() else ""
    return parent or os.path.basename(src)


def protected_disks():
    """Disco di sistema e chiavetta live: non si toccano."""
    res = set()
    for mp in ("/", "/run/live/medium"):
        d = _source_disk(mp)
        if d:
            res.add(d)
    return res


def _loop_file(name):
    return read_file(f"/sys/block/{name}/loop/backing_file").strip()


def _smart_life(data):
    """Vita residua stimata (%) per gli SSD, se il disco la dichiara."""
    nvme = data.get("nvme_smart_health_information_log")
    if nvme and nvme.get("percentage_used") is not None:
        return max(0, 100 - int(nvme["percentage_used"]))
    for attr in (data.get("ata_smart_attributes") or {}).get("table", []):
        if attr.get("id") in (231, 233, 177, 202, 169) and attr.get("value") is not None:
            v = int(attr["value"])
            if 0 < v <= 100:
                return v
    return None


def smart(disk_path, full=False, fresh=False):
    """Riassunto SMART (con cache). Non sveglia i dischi in standby (-n standby)."""
    with _smart_lock:
        hit = _smart_cache.get(disk_path)
        if hit and not full and not fresh and time.time() - hit[0] < SMART_TTL:
            return hit[1]
    prev = hit[1] if hit else {}
    info = {"available": False}
    data = {}
    if have("smartctl") and not disk_path.startswith("/dev/loop"):
        args = ["smartctl", "-j", "-a" if full else "-H", "-n", "standby"]
        if not full:
            args += ["-A", "-i", "-l", "selftest"]
        rc, out, _ = run_rc(args + [disk_path], timeout=40)
        try:
            data = json.loads(out or "{}")
        except ValueError:
            data = {}
        msgs = " ".join(m.get("string", "") for m in (data.get("smartctl") or {}).get("messages", []))
        status = data.get("smart_status")
        if status is not None:
            info = {
                "available": True,
                "passed": bool(status.get("passed")),
                "temperature": (data.get("temperature") or {}).get("current"),
                "power_on_hours": (data.get("power_on_time") or {}).get("hours"),
                "power_cycles": data.get("power_cycle_count"),
                "model": data.get("model_name"),
                "rpm": data.get("rotation_rate"),
                "bad_sectors": 0,
                "life": _smart_life(data),
            }
            # Settori riallocati / in attesa / non correggibili: segnale precoce di guasto
            for attr in (data.get("ata_smart_attributes") or {}).get("table", []):
                if attr.get("id") in (5, 197, 198):
                    info["bad_sectors"] += int((attr.get("raw") or {}).get("value", 0) or 0)
            nvme = data.get("nvme_smart_health_information_log")
            if nvme:
                info["bad_sectors"] = int(nvme.get("media_errors") or 0)
                info["percentage_used"] = nvme.get("percentage_used")
            tests = (data.get("ata_smart_self_test_log") or {}).get("standard", {}).get("table") or \
                (data.get("nvme_self_test_log") or {}).get("table") or []
            if tests:
                t = tests[0]
                info["last_test"] = {"type": (t.get("type") or {}).get("string") or (t.get("self_test_code") or {}).get("string"),
                                     "result": (t.get("status") or {}).get("string") or (t.get("self_test_result") or {}).get("string"),
                                     "passed": (t.get("status") or {}).get("passed", True),
                                     "hours": t.get("lifetime_hours") or t.get("power_on_hours")}
            running = (data.get("ata_smart_data") or {}).get("self_test", {}).get("status", {})
            if running.get("remaining_percent") is not None and running.get("value", 0) >> 4 == 15:
                info["test_running"] = 100 - int(running["remaining_percent"])
        elif "STANDBY" in msgs.upper() or data.get("power_mode") == "STANDBY":
            # In riposo: tengo gli ultimi valori letti, senza svegliare il disco
            info = {**prev, "available": bool(prev.get("available")) or True, "standby": True}
        elif prev.get("available"):
            info = prev
    if full:
        info["attributes"] = [
            {"id": a.get("id"), "name": (a.get("name") or "").replace("_", " "), "value": a.get("value"),
             "worst": a.get("worst"), "thresh": a.get("thresh"), "raw": (a.get("raw") or {}).get("string"),
             "failed": a.get("when_failed") or ""}
            for a in (data.get("ata_smart_attributes") or {}).get("table", [])]
        nv = data.get("nvme_smart_health_information_log")
        if nv:
            info["nvme"] = nv
        info["tests"] = [
            {"type": (t.get("type") or {}).get("string") or (t.get("self_test_code") or {}).get("string"),
             "result": (t.get("status") or {}).get("string") or (t.get("self_test_result") or {}).get("string"),
             "passed": (t.get("status") or {}).get("passed", True),
             "hours": t.get("lifetime_hours") or t.get("power_on_hours")}
            for t in ((data.get("ata_smart_self_test_log") or {}).get("standard", {}).get("table") or
                      (data.get("nvme_self_test_log") or {}).get("table") or [])[:10]]
        info["serial"] = data.get("serial_number")
        info["firmware"] = data.get("firmware_version")
        info["interface"] = (data.get("interface_speed") or {}).get("current", {}).get("string")
        return info
    with _smart_lock:
        _smart_cache[disk_path] = (time.time(), info)
    return info


def health_label(s):
    if not s.get("available"):
        return "sconosciuto"
    if s.get("standby") and "passed" not in s:
        return "in riposo"
    if s.get("passed") is False:
        return "guasto"
    if s.get("bad_sectors") or (s.get("life") is not None and s["life"] < 10):
        return "attenzione"
    return "buono"


def _mounts(dev):
    return [m for m in (dev.get("mountpoints") or []) if m]


def _part(p, whole=False):
    return {
        "name": p["name"], "path": p["path"], "size": p.get("size"),
        "fstype": p.get("fstype"), "fsname": FS_NAMES.get(p.get("fstype") or "", p.get("fstype") or ""),
        "label": p.get("label") or p.get("partlabel"), "uuid": p.get("uuid"), "mounts": _mounts(p),
        "fssize": p.get("fssize"), "fsused": p.get("fsused"), "fsavail": p.get("fsavail"),
        "parttype": p.get("parttypename"), "whole": whole,
        "mountable": (p.get("fstype") or "") in MOUNTABLE,
    }


def disk_id(d):
    """Identificativo stabile del disco (non cambia se cambia la lettera sdX)."""
    if d.get("type") == "loop" or d["name"].startswith("loop"):
        return "loop-" + re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(_loop_file(d["name"]) or d["name"]))
    base = d.get("wwn") or d.get("serial")
    if base:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{(d.get('model') or '').strip()}-{base}").strip("_-")
    return "dev-" + d["name"]


def _display_name(d, parts, role):
    if role == "sistema":
        return "Sistema"
    labels = [p["label"] for p in parts if p.get("label") and p.get("fstype") in MOUNTABLE]
    if labels:
        return labels[0]
    model = (d.get("model") or "").strip()
    if d.get("type") == "loop":
        return "Disco di prova " + d["name"]
    return model or d["name"]


def list_disks(with_smart=True):
    prot = protected_disks()
    res = []
    for d in _lsblk():
        loop = d.get("type") == "loop" or d["name"].startswith("loop")
        if loop:
            if not TEST_LOOP or not d.get("size") or not _loop_file(d["name"]):
                continue
        elif d.get("type") != "disk" or d["name"].startswith(("zram", "sr", "fd", "ram", "nbd")):
            continue
        elif TEST_LOOP and d["name"] not in prot:
            continue        # prove: solo i dischi finti e il disco di sistema, mai i dischi veri della macchina
        parts = [_part(p) for p in d.get("children") or [] if p.get("type") in ("part", None)]
        if not parts and d.get("fstype"):
            parts.append(_part(d, whole=True))       # disco formattato senza tabella delle partizioni
        s = smart(d["path"]) if with_smart else {"available": False}
        role = "sistema" if d["name"] in prot else ("usb" if d.get("tran") == "usb" else "dati")
        model = (d.get("model") or "").strip() or (("File " + os.path.basename(_loop_file(d["name"]))) if loop else None)
        res.append({
            "id": disk_id(d), "name": d["name"], "path": d["path"], "size": d.get("size"),
            "display": _display_name(d, parts, role),
            "model": model, "serial": d.get("serial"),
            "tran": d.get("tran") or ("loop" if loop else None), "ssd": d.get("rota") in (False, "0", 0),
            "removable": d.get("rm") in (True, "1", 1), "readonly": d.get("ro") in (True, "1", 1),
            "role": role, "protected": d["name"] in prot,
            "smart": s, "health": health_label(s), "partitions": parts,
            "empty": not parts,
        })
    return res


def summary():
    """Una riga per disco: per la panoramica e Home Assistant."""
    res = []
    for d in list_disks():
        size = used = 0
        for p in d["partitions"]:
            if p.get("fssize"):
                size += int(p["fssize"])
                used += int(p.get("fsused") or 0)
        res.append({
            "name": d["name"], "model": d["model"], "role": d["role"],
            "size": d["size"], "health": d["health"],
            "temperature": d["smart"].get("temperature"),
            "used_percent": round(100 * used / size, 1) if size else None,
        })
    return res


def filesystems_usage():
    """Utilizzo dei file system montati (per gli avvisi di spazio)."""
    res = []
    rc, out, _ = run_rc(["df", "-P", "-B1", "-x", "tmpfs", "-x", "devtmpfs", "-x", "overlay",
                         "-x", "squashfs", "-x", "efivarfs"], timeout=20)
    seen = set()
    for line in out.splitlines()[1:]:
        f = line.split()
        if len(f) < 6:
            continue
        dev, size, used, mp = f[0], int(f[1]), int(f[2]), f[5]
        if mp.startswith(("/boot", "/run", "/snap", "/var/lib/docker/")) or size == 0:
            continue
        key = dev.split("[")[0]
        if key in seen:
            continue
        seen.add(key)
        res.append({"device": dev, "mount": mp, "size": size, "used": used,
                    "percent": round(100 * used / size, 1)})
    return res


# --- fstab ---------------------------------------------------------------------------

def _fstab_remove(uuid=None, mountpoint=None):
    lines = read_file(FSTAB).splitlines()
    keep = []
    for line in lines:
        f = line.split()
        if line.rstrip().endswith(MARK) and len(f) >= 2 and (
                (uuid and f[0] == f"UUID={uuid}") or (mountpoint and f[1] == mountpoint.replace(" ", "\\040"))):
            continue
        keep.append(line)
    write_file(FSTAB, "\n".join(keep) + "\n")


def _fstab_add(uuid, mountpoint, fstype, opts):
    _fstab_remove(uuid=uuid, mountpoint=mountpoint)
    text = read_file(FSTAB).rstrip("\n")
    passno = "2" if fstype.startswith("ext") or fstype == "xfs" else "0"
    text += f"\nUUID={uuid}  {mountpoint.replace(' ', chr(92) + '040')}  {fstype}  {opts}  0 {passno}  {MARK}\n"
    write_file(FSTAB, text)


def fstab_entries():
    """Dischi montati a ogni avvio dall'interfaccia: {uuid: mountpoint}."""
    res = {}
    for line in read_file(FSTAB).splitlines():
        f = line.split()
        if line.rstrip().endswith(MARK) and len(f) >= 2 and f[0].startswith("UUID="):
            res[f[0][5:]] = f[1].replace("\\040", " ")
    return res


def mount_boot_disks(wait=60):
    """All'avvio (servizio nido-netmounts, prima di Docker): monta i dischi "a ogni avvio" che systemd non è
    riuscito a montare (dischi lenti a partire, box USB). Aggiorna anche le righe vecchie con l'attesa di 10 s."""
    txt = read_file(FSTAB)
    if "x-systemd.device-timeout=10s" in txt and MARK in txt:
        new = "\n".join(l.replace("x-systemd.device-timeout=10s", "x-systemd.device-timeout=90s") if l.rstrip().endswith(MARK) else l
                        for l in txt.splitlines()) + "\n"
        write_file(FSTAB, new)
        run_rc(["systemctl", "daemon-reload"], timeout=60)
    entries = fstab_entries()
    if not entries:
        return []
    run_rc(["udevadm", "settle", f"--timeout={wait}"], timeout=wait + 10)
    done = []
    deadline = time.time() + wait
    pending = dict(entries)
    while pending:
        for uuid, mp in list(pending.items()):
            if os.path.ismount(mp):
                pending.pop(uuid)
                continue
            if os.path.exists(f"/dev/disk/by-uuid/{uuid}"):
                rc, _, err = run_rc(["mount", mp], timeout=120)
                print(f"{mp}: " + ("montato" if rc == 0 else "non montato: " + err.strip()), flush=True)
                if rc == 0:
                    done.append(mp)
                pending.pop(uuid)
        if not pending or time.time() > deadline:
            break
        time.sleep(3)
    for mp in pending.values():
        print(f"{mp}: disco non collegato", flush=True)
    return done


def _ntfs_driver():
    if "ntfs3" in read_file("/proc/filesystems"):
        return "ntfs3"
    rc, _, _ = run_rc(["modprobe", "ntfs3"], timeout=15)
    return "ntfs3" if rc == 0 and "ntfs3" in read_file("/proc/filesystems") else "ntfs-3g"


def _mount_options(fstype, readonly=False, driver=None):
    base = "defaults,nofail,x-systemd.device-timeout=90s"
    t = fstype
    if fstype == "btrfs":
        base += ",noatime,compress=zstd:1"
    elif fstype in ("vfat", "exfat"):
        base += ",uid=0,gid=100,umask=0002"
    elif fstype in ("ntfs", "ntfs3"):
        t = driver or _ntfs_driver()
        base += ",uid=0,gid=100,umask=0002" + (",windows_names" if t == "ntfs-3g" else "")
    elif fstype == "xfs":
        base += ",noatime"
    if readonly:
        base += ",ro"
    return t, base


def clean_name(name):
    safe = re.sub(r"[^A-Za-z0-9 ._-]+", "", name or "").strip(" .-")
    return re.sub(r"\s+", " ", safe)[:40] or "Disco"


def _unique_mountpoint(name):
    safe = clean_name(name)
    mp = os.path.join(MEDIA_ROOT, safe)
    n = 2
    while os.path.exists(mp) and (os.path.ismount(mp) or os.listdir(mp)):
        mp = os.path.join(MEDIA_ROOT, f"{safe}-{n}")
        n += 1
    return mp


def find(path):
    forget_probe()
    for d in list_disks(with_smart=False):
        for p in d["partitions"]:
            if p["path"] == path:
                return d, p
        if d["path"] == path:
            return d, None
    raise ApiError("Dispositivo non trovato", 404)


def _blkid(path, tag):
    rc, out, _ = run_rc(["blkid", "-s", tag, "-o", "value", path], timeout=15)
    return out.strip()


def _settle():
    run_rc(["udevadm", "settle", "--timeout=10"], timeout=20)
    forget_probe()


# --- azioni ----------------------------------------------------------------------------

def _try_mount(mtype, opts, path, mp):
    now = ",".join(o for o in opts.split(",") if o != "nofail" and not o.startswith("x-systemd"))
    return run_rc(["mount", "-t", mtype, "-o", now, path, mp], timeout=90)


def mount(path, name=None, readonly=False, auto=True, share=False, fresh=False):
    """Monta una partizione già formattata in /media/<nome>. Non cancella niente."""
    disk, part = find(path)
    if disk["protected"]:
        raise ApiError("Questo è il disco di sistema")
    if part is None:
        raise ApiError("Scegli una partizione da montare")
    if part["mounts"]:
        raise ApiError(f"Già montato in {part['mounts'][0]}")
    fstype = part.get("fstype") or _blkid(path, "TYPE")
    if fstype not in MOUNTABLE:
        raise ApiError(f"File system non supportato: {FS_NAMES.get(fstype, fstype or 'sconosciuto')}")
    uuid = part.get("uuid") or _blkid(path, "UUID")
    name = clean_name(name or part.get("label") or f"{disk['display']}-{part['name']}")
    mp = _unique_mountpoint(name)
    os.makedirs(mp, exist_ok=True)
    notes = []
    mtype, opts = _mount_options(fstype, readonly)
    rc, _, err = _try_mount(mtype, opts, path, mp)
    if rc != 0 and fstype in ("ntfs", "ntfs3"):
        # NTFS chiuso male da Windows (spegnimento brusco o "avvio rapido"): ntfsfix sistema il
        # registro del file system senza toccare i file, poi riprovo (anche con l'altro driver)
        if have("ntfsfix") and not readonly:
            frc, fout, ferr = run_rc(["ntfsfix", "-d", path], timeout=300)
            if frc == 0:
                notes.append("Il disco era stato chiuso male da Windows: sistemato con ntfsfix prima di montarlo.")
        rc, _, err = _try_mount(mtype, opts, path, mp)
        if rc != 0 and mtype == "ntfs3" and have("ntfs-3g"):
            mtype, opts = _mount_options(fstype, readonly, driver="ntfs-3g")
            rc, _, err2 = _try_mount(mtype, opts, path, mp)
            err = err2 or err
        if rc != 0 and "hibernat" in (err or "").lower():
            _rmdir(mp)
            raise ApiError("Windows ha lasciato il disco in ibernazione (\"avvio rapido\"). Spegni del tutto il PC "
                           "Windows prima di staccare il disco, oppure montalo in sola lettura.")
    if rc != 0:
        _rmdir(mp)
        raise ApiError("Montaggio non riuscito: " + _mount_error(err, fstype))
    if uuid and auto:
        _fstab_add(uuid, mp, mtype, opts)
    if fresh and fstype in ("ext4", "btrfs", "xfs"):
        os.chown(mp, 0, 100)
        os.chmod(mp, 0o2775)
    res = {"mountpoint": mp, "notes": notes, "readonly": readonly}
    if share:
        from . import shares
        try:
            shares.save_share({"name": os.path.basename(mp), "path": mp, "comment": f"Disco {name}",
                               "access": {}, "guest": False, "all_users": "rw"})
            res["share"] = os.path.basename(mp)
        except ApiError as e:
            res["notes"].append("Condivisione non creata: " + e.message)
    return res


def _mount_error(err, fstype):
    lines = [l.strip() for l in (err or "").splitlines() if l.strip() and "dmesg" not in l]
    text = " ".join(lines)
    if "unknown filesystem type" in text or "wrong fs type" in text and not lines[1:]:
        return f"il sistema non riesce a leggere questo formato ({FS_NAMES.get(fstype, fstype)})"
    return lines[-1] if lines else "errore sconosciuto"


def _rmdir(mp):
    if mp.startswith(MEDIA_ROOT + "/"):
        try:
            os.rmdir(mp)
        except OSError:
            pass


def unmount(path, keep_fstab=False):
    disk, part = find(path)
    if disk["protected"]:
        raise ApiError("Questo è il disco di sistema")
    targets = [part] if part else [p for p in disk["partitions"] if p["mounts"]]
    if not targets or not any(p["mounts"] for p in targets):
        raise ApiError("Non è montato")
    for p in targets:
        for mp in p["mounts"]:
            rc, _, err = run_rc(["umount", mp], timeout=90)
            if rc != 0:
                raise ApiError("Non riesco a smontarlo: forse un'app o una condivisione lo sta usando. " + err.strip())
            if not keep_fstab:
                _fstab_remove(uuid=p.get("uuid"), mountpoint=mp)
            _rmdir(mp)
    return {"ok": True}


def _clean_label(label, fs):
    label = re.sub(r"[^A-Za-z0-9 _-]", "", label or "").strip() or "Dati"
    label = label[:FORMATS[fs]["max"]]
    return label.upper() if fs == "vfat" else label


def _wait_for(path, seconds=15):
    for _ in range(seconds * 4):
        if os.path.exists(path):
            return True
        time.sleep(0.25)
    return False


def _part_path(dev, n=1):
    return dev + (f"p{n}" if dev[-1].isdigit() else str(n))


def check_format(path, fs, label, confirm):
    """Controlli prima della formattazione (anche lato server: la conferma scritta è obbligatoria)."""
    if fs not in FORMATS:
        raise ApiError("Formato non valido")
    if not have(MKFS[fs]):
        raise ApiError(f"Manca il programma per creare {FORMATS[fs]['label']} ({MKFS[fs]})")
    disk, part = find(path)
    if disk["protected"]:
        raise ApiError("Il disco di sistema non si può formattare da qui")
    expected = disk["display"] if part is None else (part.get("label") or part["name"])
    if (confirm or "").strip() != expected:
        raise ApiError(f"Per confermare scrivi esattamente: {expected}")
    return disk, part, _clean_label(label, fs)


def format_device(path, fs, label, confirm, auto=True, job=None):
    disk, part, label = check_format(path, fs, label, confirm)
    say = (lambda p, s: job.set(p, s)) if job else (lambda p, s: None)

    # Smonta tutto quello che c'è sul disco (o sulla partizione)
    say(5, "Smonto il disco")
    targets = disk["partitions"] if part is None else [part]
    for p in targets:
        for mp in p["mounts"]:
            rc, _, err = run_rc(["umount", mp], timeout=90)
            if rc != 0:
                raise ApiError(f"Non riesco a smontare {mp}: chiudi le app che lo usano. {err.strip()}")
            _fstab_remove(mountpoint=mp)
            _rmdir(mp)
        if p.get("uuid"):
            _fstab_remove(uuid=p["uuid"])

    if part is None:
        # Disco intero: nuova tabella GPT con una sola partizione
        dev = disk["path"]
        say(15, "Creo una nuova tabella delle partizioni (GPT)")
        for p in disk["partitions"]:
            if not p.get("whole"):
                run(["wipefs", "-af", p["path"]], check=False)
        run(["wipefs", "-af", dev])
        run(["sgdisk", "--zap-all", dev], check=False)
        run(["sgdisk", "-n1:0:0", f"-t1:{FORMATS[fs]['gpt']}", f"-c1:{label}", dev])
        run(["partprobe", dev], check=False)
        _settle()
        target = _part_path(dev)
        if not _wait_for(target):
            run(["blockdev", "--rereadpt", dev], check=False)
            if not _wait_for(target, 10):
                raise ApiError("La nuova partizione non è comparsa: riprova")
    else:
        target = part["path"]
        run(["wipefs", "-af", target])

    say(35, f"Creo il file system {FORMATS[fs]['label']}")
    cmd = {
        "ext4": ["mkfs.ext4", "-F", "-L", label, "-m", "1", target],
        "btrfs": ["mkfs.btrfs", "-f", "-L", label, target],
        "exfat": ["mkfs.exfat", "-L", label, target],
        "ntfs": ["mkfs.ntfs", "-Q", "-F", "-L", label, target],
        "vfat": ["mkfs.vfat", "-F", "32", "-n", label, target],
        "xfs": ["mkfs.xfs", "-f", "-L", label, target],
    }[fs]
    run(cmd, timeout=3600)
    _settle()
    time.sleep(1)
    with _smart_lock:
        _smart_cache.pop(disk["path"], None)
    say(85, "Monto il disco")
    try:
        res = mount(target, name=label, auto=auto, fresh=True)
    except ApiError as e:
        raise ApiError(f"Disco formattato in {FORMATS[fs]['label']}, ma non montato: {e.message}")
    say(100, f"Fatto: {res['mountpoint']}")
    return {"device": target, "label": label, **res}


def smart_test(disk_path, kind="short"):
    if kind not in ("short", "long"):
        raise ApiError("Tipo di test non valido")
    for d in list_disks(with_smart=False):
        if d["path"] == disk_path:
            rc, out, err = run_rc(["smartctl", "-t", kind, disk_path], timeout=30)
            if rc & 0b11:
                raise ApiError("Il disco non accetta il test SMART")
            with _smart_lock:
                _smart_cache.pop(disk_path, None)
            m = re.search(r"Please wait (\d+) minutes", out)
            mins = int(m.group(1)) if m else (2 if kind == "short" else 120)
            return {"ok": True, "minutes": mins,
                    "message": f"Test {'breve' if kind == 'short' else 'completo'} avviato: dura circa {mins} minuti"}
    raise ApiError("Disco non trovato", 404)


# --- Docker -----------------------------------------------------------------------------

def docker_info():
    if not have("docker"):
        return {"available": False}
    rc, out, _ = run_rc(["docker", "system", "df", "--format", "{{json .}}"], timeout=60)
    rows = []
    for line in out.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    rc2, out2, _ = run_rc(["df", "-P", "-B1", "/var/lib/docker"], timeout=10)
    fs = {}
    lines = out2.splitlines()
    if len(lines) > 1:
        f = lines[1].split()
        fs = {"size": int(f[1]), "used": int(f[2]), "avail": int(f[3])}
    return {"available": rc == 0, "types": rows, "filesystem": fs}


def docker_prune():
    before = docker_info().get("filesystem", {}).get("used", 0)
    run(["docker", "image", "prune", "-a", "-f"], timeout=900)
    run(["docker", "builder", "prune", "-a", "-f"], check=False, timeout=900)
    after = docker_info().get("filesystem", {}).get("used", 0)
    return {"freed": max(0, before - after)}
