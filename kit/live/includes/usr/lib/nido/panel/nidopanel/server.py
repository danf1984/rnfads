"""Server web dell'interfaccia del NAS (sostituisce CasaOS).

- Interfaccia nuova su "/" (file in ../ui), API JSON su /api/.
- Accesso con account propri e sessione in un cookie (vedi auth.py). Le richieste che
  modificano qualcosa devono avere l'intestazione X-Nido: 1 (protezione CSRF, insieme
  al cookie SameSite=Strict).
- Tutte le funzioni del vecchio Centro di controllo sono passate nell'interfaccia (fase 1B).
- Link di condivisione pubblici su /s/<token>.
- Home Assistant: /api/v1/status con la chiave API (X-API-Key).

Indirizzo di ascolto: variabile NIDO_LISTEN (predefinito 0.0.0.0:80). Con Caddy davanti
(HTTPS, fase 1B) si usa 127.0.0.1:8090.
"""
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import signal
import threading
import time
import traceback
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import (online, cloud, network, screen, apps, auth, backup, catalog, disks, files, jobs, metrics, netmounts, notify, registry, remote,
               https, powersched, server_fallback, shares, sshd, standby, system, terminal, updates, users,
               release, appmove, selfupdate, wizard)
from .util import ApiError, ETC, product, read_file, run_rc, write_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.environ.get("NIDO_UI_DIR", os.path.join(ROOT, "ui"))
API_KEY_FILE = os.path.join(ETC, "api.key")
MAX_JSON = 4 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024

CSP = ("default-src 'self'; img-src 'self' data: blob: https: http:; media-src 'self' blob:; "
       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self' data:; "
       "frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")


def conf():
    c = {}
    for line in read_file(os.path.join(ETC, "nido.conf")).splitlines():
        k, _, v = line.partition("=")
        if k and not k.startswith("#"):
            c[k.strip()] = v.strip().strip('"')
    return c


def api_key(create=True):
    key = read_file(API_KEY_FILE).strip()
    if not key and create:
        key = secrets.token_urlsafe(32)
        write_file(API_KEY_FILE, key + "\n", 0o600)
    return key


# --- rotte ---------------------------------------------------------------------------------------------

ROUTES = []          # (metodo, regex, funzione, admin)


def route(method, pattern, admin=True):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, admin))
        return fn
    return deco


# --- informazioni generali --------------------------------------------------------------------------------

def _about():
    c = conf()
    donate = []
    for key, label in (("NIDO_DONATE_PAYPAL", "PayPal"), ("NIDO_DONATE_KOFI", "Ko-fi"),
                       ("NIDO_DONATE_GITHUB", "GitHub Sponsors"), ("NIDO_DONATE_LIBERAPAY", "Liberapay"),
                       ("NIDO_DONATE_OTHER", "Altro")):
        if c.get(key, "").startswith("https://"):
            donate.append({"label": label, "url": c[key]})
    return {"name": c.get("NIDO_NAME", "NAS"), "version": c.get("NIDO_VERSION", ""),
            "wordmark": c.get("NIDO_WORDMARK", ""), "hostname": socket.gethostname(),
            "base": _base_os(), "donate": donate,
            "project_url": c.get("NIDO_PROJECT_URL", ""), "app_domain": _safe_app_domain(),
            "lang": _ui_lang(), "stores_extra": catalog._extra is not None}


def _local_addresses():
    """Indirizzi IPv4 del NAS nella rete (per la pagina di accesso sullo schermo del NAS)."""
    rc, out, _ = run_rc(["ip", "-4", "-o", "addr", "show", "scope", "global"], timeout=10)
    res = []
    for line in out.splitlines():
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", line)
        if m and not re.search(r"\b(docker\d*|br-\w+|veth\w*|tailscale\d*|zt\w+)\b", line):
            res.append(m.group(1))
    return res


LANG_FILE = "/etc/nido/ui-language.json"
LANGS = ("it", "en", "es", "de")


def _ui_lang():
    try:
        with open(LANG_FILE, encoding="utf-8") as f:
            v = json.load(f).get("lang")
        return v if v in LANGS else "it"
    except (OSError, ValueError, AttributeError):
        return "it"


def _safe_app_domain():
    try:
        return https.app_domain()
    except Exception:  # noqa: BLE001
        return None


def _base_os():
    """Sistema di base: os-release originale di Ubuntu (salvato dall'hook) o quello attuale."""
    for path in ("/usr/lib/os-release.base", "/etc/os-release"):
        info = dict(line.split("=", 1) for line in read_file(path).splitlines() if "=" in line)
        name = info.get("PRETTY_NAME", "").strip('"')
        if name:
            return "basato su " + name
    return "basato su Ubuntu"


@route("GET", "/https")
def _https(req):
    return https.status()


@route("POST", "/https")
def _https_save(req):
    return https.save(req.json())


@route("POST", "/https/upload")
def _https_upload(req):
    b = req.json()
    return https.upload(b.get("cert"), b.get("key"))


@route("POST", "/https/renew")
def _https_renew(req):
    return https.renew_home()


@route("GET", "/about", admin=False)
def _r_about(req):
    return _about()


@route("GET", "/about/notices", admin=False)
def _r_notices(req):
    text = read_file("/usr/share/doc/nido/THIRD_PARTY_NOTICES.txt") or read_file(os.path.join(UI, "licenze.txt"))
    return {"text": text, "license": read_file(os.path.join(UI, "LICENSE.txt"))[:200000]}


_home_cache = {}


def _home_disks():
    """Spazio dei dischi per la Home: sistema + dischi montati in /media e /mnt."""
    rc, out, _ = run_rc(["lsblk", "-J", "-b", "-o", "NAME,PATH,TYPE,ROTA,TRAN,MODEL,MOUNTPOINTS,FSTYPE,LABEL,PKNAME"], timeout=10)
    info = {}
    try:
        def walk(items, parent=None):
            for d in items or []:
                p = parent or d
                for mp in d.get("mountpoints") or []:
                    if mp:
                        info[mp] = {"rota": p.get("rota"), "tran": p.get("tran"), "model": (p.get("model") or "").strip(),
                                    "fstype": d.get("fstype"), "label": d.get("label")}
                walk(d.get("children"), p)
        walk(json.loads(out or "{}").get("blockdevices"))
    except ValueError:
        pass
    pl = files.places()
    res = []
    for d in pl["disks"]:
        mp = "/" if d.get("system") else d["path"]
        i = info.get(mp) or info.get(d["path"]) or {}
        kind = "USB" if i.get("tran") == "usb" else ("HDD" if i.get("rota") in (True, "1", 1) else "SSD")
        if d.get("system"):
            s = files._df("/DATA")
        else:
            s = {"size": d.get("size", 0), "free": d.get("free", 0)}
        res.append({"name": d["name"], "path": d["path"], "kind": kind, "fstype": i.get("fstype") or d.get("fstype") or "",
                    "size": s["size"], "used": max(0, s["size"] - s["free"]), "free": s["free"], "system": bool(d.get("system"))})
    return res


def _home_apps():
    try:
        al = apps.list_apps()
        return {"apps": [{k: a.get(k) for k in ("name", "title", "icon", "state", "web", "managed", "update")}
                         for a in al["apps"]], "docker": al["docker"]}
    except ApiError:
        return {"apps": [], "docker": False}


_home_lock = threading.Lock()


def _home_part(key, fn, ttl=15, wait=2.5):
    """Valore in cache per la Home, aggiornato in un thread a parte.
    La Home non aspetta mai Docker o i dischi più di `wait` secondi: con Docker che si sta
    avviando (o una macchina lenta) `docker ps` può impiegare decine di secondi e la pagina
    restava sulla rotellina. Se il valore non è pronto si restituisce None e la pagina
    lo chiede di nuovo poco dopo."""
    with _home_lock:
        ent = _home_cache.setdefault(key, {"t": 0, "v": None, "th": None})
        fresh = time.time() - ent["t"] < ttl
        if not fresh and not (ent["th"] and ent["th"].is_alive()):
            def work():
                try:
                    v = fn()
                except Exception as e:  # noqa: BLE001
                    print(f"home: {key}: {e}", flush=True)
                    v = ent["v"]
                with _home_lock:
                    ent["v"], ent["t"] = v, time.time()
            ent["th"] = threading.Thread(target=work, daemon=True, name="home-" + key)
            ent["th"].start()
        th = ent["th"]
    if ent["v"] is None and th is not None:
        th.join(wait)
    return ent["v"]


@route("GET", "/home", admin=False)
def _r_home(req):
    ap = _home_part("apps", _home_apps)
    dk = _home_part("disks", _home_disks)
    app_list = ap["apps"] if ap else None
    upd = updates.cached() if hasattr(updates, "cached") else {}
    try:
        from . import uptime as uptime_mod
        up = uptime_mod.summary()
    except Exception:  # noqa: BLE001
        up = None
    return {
        "user": req.user, "about": _about(), "uptime": system.uptime(), "uptime_stats": up,
        "cpu": metrics.cpu_info(),
        "live": metrics.live(), "history": metrics.history(120), "link": metrics.link_speed(),
        "disks": dk, "apps": app_list, "docker": ap["docker"] if ap else None,
        "updates": {"system": len(upd.get("packages", [])), "apps": sum(1 for a in (app_list or []) if a.get("update"))},
        "reboot": system.reboot_required(),
    }


@route("GET", "/home/live", admin=False)
def _r_live(req):
    return metrics.live()


# --- store ---------------------------------------------------------------------------------------------

@route("GET", "/store/apps", admin=False)
def _r_store(req):
    catalog.ensure()
    return catalog.list_apps()


@route("GET", "/store/app/([a-z0-9-]+)", admin=False)
def _r_store_app(req, app_id):
    a = catalog.get_app(app_id)
    names = {s["id"]: s["name"] for s in catalog.sources()}
    return {**a, "source_names": names}


@route("GET", "/store/sources")
def _r_sources(req):
    return catalog.sources_status()


@route("POST", "/store/sources")
def _r_source_add(req):
    return catalog.add_source(req.json())


@route("POST", "/store/sources/([a-z0-9]+)")
def _r_source_set(req, sid):
    return catalog.set_source(sid, req.json().get("enabled"))


@route("DELETE", "/store/sources/([a-z0-9]+)")
def _r_source_del(req, sid):
    return catalog.remove_source(sid)


@route("POST", "/store/refresh")
def _r_refresh(req):
    catalog.start_build()
    return catalog.sources_status()


@route("GET", "/hub/search", admin=False)
def _r_hub(req):
    q = req.query.get("q", "")
    res = registry.hub_search(q)
    return {"results": res, "store": catalog.find_by_image(q) if q else []}


@route("GET", "/hub/inspect")
def _r_hub_inspect(req):
    return registry.image_config(req.query.get("image", ""))


@route("POST", "/apps/prepare")
def _r_prepare(req):
    b = req.json()
    if b.get("image"):
        return apps.prepare_image(b["image"])
    return apps.prepare_catalog(b.get("app"), b.get("source"))


@route("POST", "/apps/render")
def _r_render(req):
    return apps.render(req.json())


@route("GET", "/fs/dirs")
def _r_dirs(req):
    return system.list_dirs(req.query.get("path", "/"))


@route("GET", "/apps/([a-z0-9][a-z0-9_-]*)/edit")
def _r_app_edit(req, name):
    return apps.prepare_edit(name)


@route("POST", "/apps/([a-z0-9][a-z0-9_-]*)/reconfigure")
def _r_app_reconf(req, name):
    return apps.reconfigure(name, req.json())


@route("POST", "/apps/install")
def _r_install(req):
    return apps.install(req.json())


# --- le mie app -----------------------------------------------------------------------------------------

@route("GET", "/apps", admin=False)
def _r_apps(req):
    return apps.list_apps()


@route("POST", "/apps/check")
def _r_check(req):
    return apps.start_check()


@route("POST", "/apps/update-all")
def _r_update_all(req):
    return apps.start_update_all()


@route("POST", "/apps/settings")
def _r_app_settings(req):
    return apps.save_settings(req.json())


@route("POST", "/apps/([a-z0-9][a-z0-9_.-]*)/(start|stop|restart)")
def _r_action(req, name, what):
    return apps.action(name, what)


@route("POST", "/apps/([a-z0-9][a-z0-9_-]*)/update")
def _r_update(req, name):
    return apps.start_update(name)


@route("GET", "/apps/([a-z0-9][a-z0-9_.-]*)/logs")
def _r_logs(req, name):
    return apps.logs(name, req.query.get("tail", 300))


@route("GET", "/apps/([a-z0-9][a-z0-9_-]*)/compose")
def _r_compose(req, name):
    return apps.get_compose(name)


@route("POST", "/apps/([a-z0-9][a-z0-9_-]*)")
def _r_app_set(req, name):
    return apps.set_app(name, req.json())


@route("DELETE", "/apps/([a-z0-9][a-z0-9_-]*)")
def _r_app_del(req, name):
    return apps.remove(name, req.query.get("data") == "1")


@route("GET", "/jobs", admin=False)
def _r_jobs(req):
    return {"jobs": jobs.active()}


@route("GET", "/jobs/([0-9a-f]+)", admin=False)
def _r_job(req, jid):
    return jobs.get(jid)


# --- file ----------------------------------------------------------------------------------------------

@route("GET", "/files/places")
def _r_places(req):
    return files.places(req.user)


@route("GET", "/files/list")
def _r_list(req):
    return files.list_dir(req.query.get("path", "/DATA"), req.query.get("hidden") == "1")


@route("GET", "/files/details")
def _r_details(req):
    return files.details(req.query.get("path", ""))


@route("GET", "/files/text")
def _r_text(req):
    return files.read_text(req.query.get("path", ""))


@route("GET", "/files/search")
def _r_search(req):
    return files.search(req.query.get("path", "/DATA"), req.query.get("q", ""))


@route("POST", "/files/mkdir")
def _r_fmkdir(req):
    b = req.json()
    return files.mkdir(b.get("path", ""), b.get("name", ""))


@route("POST", "/files/rename")
def _r_rename(req):
    b = req.json()
    return files.rename(b.get("path", ""), b.get("name", ""))


@route("POST", "/files/(copy|move)")
def _r_transfer(req, op):
    b = req.json()
    return files.transfer(b.get("paths") or [], b.get("dest", ""), move=op == "move", policy=b.get("policy"))


@route("POST", "/files/conflicts")
def _r_conflicts(req):
    b = req.json()
    return files.conflicts(b.get("dest", ""), b.get("paths") or [], b.get("names") or [])


@route("GET", "/files/edit")
def _r_edit(req):
    return files.read_for_edit(req.query.get("path", ""))


@route("POST", "/files/save")
def _r_save(req):
    b = req.json()
    return files.save_text(b.get("path", ""), b.get("text"), b.get("mtime"), b.get("encoding") or "utf-8",
                           bool(b.get("crlf")), bool(b.get("force")))


@route("POST", "/files/newfile")
def _r_newfile(req):
    b = req.json()
    return files.new_file(b.get("path", ""), b.get("name", ""))


@route("POST", "/files/favorite")
def _r_fav(req):
    b = req.json()
    if "to" in b:
        return files.move_favorite(req.user, b.get("path", ""), b.get("to", 0))
    return files.set_favorite(req.user, b.get("path", ""), b.get("on", True) is not False)


@route("POST", "/files/size")
def _r_size(req):
    return files.dir_size(req.json().get("paths") or [])


@route("GET", "/files/perms")
def _r_perms(req):
    return files.perms_info(req.query.get("path", ""))


@route("POST", "/files/perms")
def _r_perms_set(req):
    b = req.json()
    return files.set_perms(b.get("paths") or [], b.get("owner") or None, b.get("group") or None,
                           b.get("levels"), bool(b.get("recursive")))


@route("POST", "/files/compress")
def _r_compress(req):
    b = req.json()
    return files.compress(b.get("paths") or [], b.get("format") or "zip", b.get("name") or None)


@route("POST", "/files/extract")
def _r_extract(req):
    return files.extract(req.json().get("path", ""))


@route("GET", "/files/upload/status")
def _r_upstatus(req):
    return files.upload_status(req.query.get("dir", ""), req.query.get("name", ""), req.query.get("total", 0))


@route("GET", "/files/ops", admin=False)
def _r_fops(req):
    return {"jobs": jobs.active(queue="files", recent=3600)}


@route("POST", "/jobs/([0-9a-f]+)/cancel")
def _r_job_cancel(req, jid):
    return jobs.cancel(jid)


@route("POST", "/files/delete")
def _r_delete(req):
    b = req.json()
    return files.delete(b.get("paths") or [], bool(b.get("permanent")))


@route("GET", "/files/trash")
def _r_trash(req):
    return files.trash_list()


@route("POST", "/files/trash/restore")
def _r_trash_restore(req):
    b = req.json()
    return files.trash_restore(b.get("trash"), b.get("id"))


@route("POST", "/files/trash/empty")
def _r_trash_empty(req):
    b = req.json()
    return files.trash_empty(b.get("trash"), b.get("id"))


@route("POST", "/files/share")
def _r_share(req):
    b = req.json()
    return files.share_create(b.get("path", ""), b.get("days", 7), req.user)


@route("GET", "/files/shares")
def _r_shares(req):
    return files.share_list()


@route("DELETE", "/files/share/([A-Za-z0-9_-]+)")
def _r_share_del(req, token):
    return files.share_delete(token)


# --- cartelle di rete -----------------------------------------------------------------------------------

@route("GET", "/net/discover")
def _r_discover(req):
    return netmounts.discover()


@route("POST", "/net/shares")
def _r_net_shares(req):
    b = req.json()
    if (b.get("proto") or "smb") == "nfs":
        return netmounts.nfs_exports(b.get("host"))
    return netmounts.smb_shares(b.get("host"), b.get("user", ""), b.get("password", ""), b.get("domain", ""))


@route("GET", "/net/mounts")
def _r_mounts(req):
    return {"mounts": netmounts.list_mounts()}


@route("POST", "/net/test")
def _r_net_test(req):
    return netmounts.test(req.json())


@route("POST", "/net/mounts")
def _r_net_connect(req):
    return netmounts.connect(req.json())


@route("POST", "/net/mounts/([0-9a-f]+)/(mount|unmount)")
def _r_net_mount(req, mid, op):
    return netmounts.mount(mid) if op == "mount" else netmounts.unmount(mid)


@route("POST", "/net/mounts/([0-9a-f]+)")
def _r_net_update(req, mid):
    return netmounts.update(mid, req.json())


@route("DELETE", "/net/mounts/([0-9a-f]+)")
def _r_net_del(req, mid):
    return netmounts.remove(mid)


# --- rete e schermo del NAS -----------------------------------------------------------------------------

@route("GET", "/network")
def _r_network(req):
    return network.status()


@route("POST", "/network/apply")
def _r_network_apply(req):
    return network.apply(req.json() or {})


@route("POST", "/network/confirm")
def _r_network_confirm(req):
    return network.confirm()


@route("POST", "/network/rollback")
def _r_network_rollback(req):
    return network.rollback()


@route("GET", "/network/wifi")
def _r_wifi_scan(req):
    return network.wifi_scan()


@route("POST", "/network/wifi")
def _r_wifi_connect(req):
    return network.wifi_connect(req.json() or {})


@route("DELETE", "/network/wifi/([0-9a-f-]{36})")
def _r_wifi_forget(req, uid):
    return network.wifi_forget(uid)


@route("GET", "/screen")
def _r_screen(req):
    return screen.status()


@route("POST", "/screen/install")
def _r_screen_install(req):
    return screen.install()


@route("POST", "/screen/enabled")
def _r_screen_enabled(req):
    return screen.set_enabled(bool((req.json() or {}).get("enabled")))


# --- servizi cloud (rclone) ----------------------------------------------------------------------------

@route("GET", "/cloud")
def _r_cloud(req):
    return cloud.list_remotes()


@route("POST", "/cloud/remotes")
def _r_cloud_create(req):
    return cloud.create(req.json() or {})


@route("POST", "/cloud/oauth/start")
def _r_cloud_oauth_start(req):
    return cloud.oauth_start(req.json() or {})


@route("POST", "/cloud/oauth/finish")
def _r_cloud_oauth_finish(req):
    return cloud.oauth_finish(req.json() or {})


@route("POST", "/cloud/remotes/([A-Za-z0-9][A-Za-z0-9_-]{0,30})/test")
def _r_cloud_test(req, name):
    return cloud.test(name)


@route("POST", "/cloud/remotes/([A-Za-z0-9][A-Za-z0-9_-]{0,30})/mount")
def _r_cloud_mount(req, name):
    return cloud.mount(name, req.json() or {})


@route("POST", "/cloud/remotes/([A-Za-z0-9][A-Za-z0-9_-]{0,30})/autoboot")
def _r_cloud_autoboot(req, name):
    return cloud.autoboot(name, bool((req.json() or {}).get("enabled")))


@route("DELETE", "/cloud/remotes/([A-Za-z0-9][A-Za-z0-9_-]{0,30})")
def _r_cloud_del(req, name):
    return cloud.remove(name)


# --- sistema -------------------------------------------------------------------------------------------

@route("GET", "/system/overview")
def _overview(req):
    return system.overview()


@route("POST", "/system/(reboot|poweroff)")
def _power(req, action):
    return system.power(action)


@route("POST", "/fs/mkdir")
def _mkdir(req):
    return system.make_dir(req.json().get("path", ""))


@route("GET", "/apikey")
def _apikey(req):
    return {"key": api_key()}


@route("POST", "/apikey/regenerate")
def _apikey_new(req):
    write_file(API_KEY_FILE, secrets.token_urlsafe(32) + "\n", 0o600)
    return {"key": api_key()}


# --- dischi ----------------------------------------------------------------------------------------------

@route("GET", "/disks")
def _disks(req):
    lst = disks.list_disks()
    for d in lst:
        d["standby"] = standby.info_for(d)
        if d["protected"]:
            st = os.statvfs("/")
            d["root"] = {"size": st.f_blocks * st.f_frsize, "used": (st.f_blocks - st.f_bfree) * st.f_frsize}
    return {"disks": lst, "formats": {k: v["label"] for k, v in disks.FORMATS.items()},
            "boot": disks.fstab_entries(), "window": standby.load()["window"],
            "schedule": standby.load()["schedule"], "schedule_now": standby.schedule_now(),
            "standby_service": time.time() - standby.state().get("t", 0) < 120}


@route("GET", "/disks/smart")
def _disk_smart(req):
    path = req.query.get("disk", "")
    if not any(d["path"] == path for d in disks.list_disks(with_smart=False)):
        raise ApiError("Disco non trovato", 404)
    return disks.smart(path, full=True)


@route("POST", "/disks/smart-test")
def _smart_test(req):
    b = req.json()
    return disks.smart_test(b.get("disk"), b.get("kind") or "short")


@route("POST", "/disks/format")
def _format(req):
    b = req.json()
    dev, fs = b.get("device"), b.get("fs")
    disks.check_format(dev, fs, b.get("label"), b.get("confirm"))      # errori subito, prima di partire
    job = jobs.start("format", f"Formattazione {disks.FORMATS[fs]['label']}",
                     lambda j: disks.format_device(dev, fs, b.get("label"), b.get("confirm"), bool(b.get("auto", True)), j),
                     target="disk:" + dev)
    return {"job": job.id}


@route("POST", "/disks/mount")
def _mount(req):
    b = req.json()
    return disks.mount(b.get("device"), b.get("name"), bool(b.get("readonly")), bool(b.get("auto", True)),
                       bool(b.get("share")))


@route("POST", "/disks/unmount")
def _unmount(req):
    return disks.unmount(req.json().get("device"))


@route("POST", "/disks/standby")
def _standby(req):
    return standby.set_disk(req.json())


@route("GET", "/system/power-schedule")
def _power_sched(req):
    return powersched.get()


@route("POST", "/system/power-schedule")
def _power_sched_save(req):
    return powersched.save(req.json())


@route("POST", "/system/power-schedule/test")
def _power_sched_test(req):
    return powersched.test_rtc()


@route("GET", "/system/power-schedule/busy")
def _power_busy(req):
    return {"busy": powersched.busy()}


@route("POST", "/disks/standby-schedule")
def _standby_schedule(req):
    return standby.set_schedule(req.json())


@route("POST", "/disks/standby-window")
def _standby_window(req):
    return standby.set_window(req.json())


@route("POST", "/disks/sleep")
def _sleep(req):
    return standby.sleep_now(req.json().get("disk"))


@route("GET", "/docker/space")
def _docker(req):
    return disks.docker_info()


@route("POST", "/docker/prune")
def _prune(req):
    return disks.docker_prune()


# --- condivisioni e utenti ---------------------------------------------------------------------------

@route("GET", "/shares")
def _shares(req):
    return shares.get()


@route("POST", "/shares")
def _share_save(req):
    b = req.json()
    return shares.save_share(b, b.get("original"))


@route("DELETE", "/shares/(.+)")
def _share_del(req, name):
    return shares.delete_share(urllib.parse.unquote(name))


@route("POST", "/shares-settings")
def _share_settings(req):
    return shares.save_settings(req.json())


@route("GET", "/accounts")
def _r_accounts(req):
    return {"accounts": auth.list_users(), "me": req.user}


@route("POST", "/accounts")
def _r_account_new(req):
    b = req.json()
    return auth.create_user(b.get("user"), b.get("password"), admin=bool(b.get("admin")))


@route("POST", "/accounts/([a-z_][a-z0-9_-]*)")
def _r_account_set(req, name):
    b = req.json()
    if "admin" in b:
        auth.set_role(name, bool(b["admin"]), req.user)
    if b.get("password"):
        auth.set_password(name, b["password"])
    return {"ok": True}


@route("DELETE", "/accounts/([a-z_][a-z0-9_-]*)")
def _r_account_del(req, name):
    return auth.delete_user(name, req.user)


@route("GET", "/wizard")
def _r_wizard(req):
    return wizard.status()


@route("POST", "/wizard")
def _r_wizard_save(req):
    return wizard.save(req.json())


@route("GET", "/selfupdate")
def _r_selfupdate(req):
    return selfupdate.status()


@route("POST", "/selfupdate/inspect")
def _r_selfupdate_inspect(req):
    return selfupdate.inspect()


@route("POST", "/selfupdate/install")
def _r_selfupdate_install(req):
    return selfupdate.start_install(req.json().get("confirm"))


@route("POST", "/selfupdate/rollback")
def _r_selfupdate_rollback(req):
    return selfupdate.start_rollback()


@route("POST", "/selfupdate/discard")
def _r_selfupdate_discard(req):
    return selfupdate.discard()


@route("POST", "/selfupdate/devmode")
def _r_selfupdate_dev(req):
    return selfupdate.set_devmode(bool(req.json().get("enabled")))


@route("GET", "/selfupdate/online")
def _r_online(req):
    return online.status()


@route("POST", "/selfupdate/online")
def _r_online_set(req):
    return online.set_settings(req.json() or {})


@route("POST", "/selfupdate/online/check")
def _r_online_check(req):
    online.check()
    return online.status()


@route("POST", "/selfupdate/online/install")
def _r_online_install(req):
    return online.start_install()


@route("GET", "/selfupdate/log")
def _r_selfupdate_log(req):
    try:
        off = int(req.query.get("offset", 0))
    except ValueError:
        off = 0
    return selfupdate.log_since(off)


@route("POST", "/system/language")
def _r_language(req):
    lang = (req.json() or {}).get("lang")
    if lang not in LANGS:
        raise ApiError("Lingua non supportata")
    os.makedirs(os.path.dirname(LANG_FILE), exist_ok=True)
    with open(LANG_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"lang": lang}, f)
    os.chmod(LANG_FILE + ".tmp", 0o644)
    os.replace(LANG_FILE + ".tmp", LANG_FILE)
    # Schermata della console nella stessa lingua
    try:
        run_rc(["/usr/lib/nido/issue.sh", lang], timeout=10)
    except Exception:  # noqa: BLE001 — la console non deve bloccare il cambio di lingua
        pass
    return {"lang": lang}


@route("GET", "/remote")
def _r_remote(req):
    return remote.status()


@route("POST", "/remote/(tailscale|zerotier)/install")
def _r_remote_install(req, what):
    return remote.start_install(what)


@route("POST", "/remote/(tailscale|zerotier)/uninstall")
def _r_remote_uninstall(req, what):
    return remote.uninstall(what)


@route("POST", "/remote/tailscale/connect")
def _r_ts_connect(req):
    return remote.tailscale_connect()


@route("POST", "/remote/tailscale/disconnect")
def _r_ts_disconnect(req):
    return remote.tailscale_disconnect()


@route("POST", "/remote/tailscale/routes")
def _r_ts_routes(req):
    return remote.tailscale_routes(bool((req.json() or {}).get("enabled")))


@route("POST", "/remote/zerotier/join")
def _r_zt_join(req):
    return remote.zerotier_join((req.json() or {}).get("network"))


@route("POST", "/remote/zerotier/leave")
def _r_zt_leave(req):
    return remote.zerotier_leave((req.json() or {}).get("network"))


@route("GET", "/registry/account")
def _r_hub_account(req):
    return registry.hub_account()


@route("POST", "/registry/account")
def _r_hub_account_set(req):
    return registry.hub_account_set(req.json())


@route("POST", "/registry/account/check")
def _r_hub_account_check(req):
    return registry.hub_account_check()


@route("POST", "/registry/account/remove")
def _r_hub_account_remove(req):
    return registry.hub_account_remove()


@route("POST", "/store/schedule")
def _r_store_sched(req):
    return catalog.set_schedule(req.json())


@route("POST", "/store/refresh/([a-z0-9]+)")
def _r_store_refresh_one(req, sid):
    catalog.start_build(only=[sid])
    return catalog.sources_status()


@route("GET", "/users")
def _users(req):
    return {"users": users.list_users(), "ui": auth.list_users()}


@route("POST", "/users")
def _user_create(req):
    return users.create(req.json())


@route("POST", "/users/([a-z_][a-z0-9_-]*)")
def _user_update(req, name):
    return users.update(name, req.json())


@route("DELETE", "/users/([a-z_][a-z0-9_-]*)")
def _user_delete(req, name):
    return users.delete(name, req.query.get("files") == "1")


# --- backup ----------------------------------------------------------------------------------------------

@route("GET", "/backup")
def _backups(req):
    return backup.list_jobs()


@route("POST", "/backup")
def _backup_new(req):
    return backup.save(req.json())


@route("GET", "/backup/rclone")
def _backup_remotes(req):
    return backup.rclone_remotes()


@route("POST", "/backup/([0-9a-f]+)")
def _backup_edit(req, jid):
    return backup.save(req.json(), jid)


@route("DELETE", "/backup/([0-9a-f]+)")
def _backup_del(req, jid):
    return backup.delete(jid)


@route("POST", "/backup/([0-9a-f]+)/run")
def _backup_run(req, jid):
    return backup.start(jid)


@route("GET", "/backup/([0-9a-f]+)/log")
def _backup_log(req, jid):
    return backup.log(jid)


@route("GET", "/backup/([0-9a-f]+)/key")
def _backup_key(req, jid):
    return backup.key(jid)


@route("GET", "/backup/([0-9a-f]+)/snapshots")
def _backup_snaps(req, jid):
    return backup.snapshots(jid)


@route("POST", "/backup/([0-9a-f]+)/restore")
def _backup_restore(req, jid):
    return backup.restore(jid, req.json())


# --- aggiornamenti di sistema e snapshot ---------------------------------------------------------------

@route("GET", "/release")
def _r_release(req):
    return release.status()


@route("POST", "/release/check")
def _r_release_check(req):
    return release.check()


@route("POST", "/release/start")
def _r_release_start(req):
    b = req.json()
    return release.start(b.get("codename"), b.get("confirm"))


@route("GET", "/release/log")
def _r_release_log(req):
    try:
        off = int(req.query.get("offset", 0))
    except ValueError:
        off = 0
    return release.log_since(off)


@route("POST", "/release/rollback")
def _r_release_rollback(req):
    return release.rollback()


@route("GET", "/apps/location")
def _r_apploc(req):
    return appmove.status()


@route("POST", "/apps/location/move")
def _r_apploc_move(req):
    b = req.json()
    return appmove.start(b.get("path", ""), b.get("confirm"))


@route("POST", "/apps/location/back")
def _r_apploc_back(req):
    return appmove.start_back(req.json().get("confirm"))


@route("POST", "/apps/location/free")
def _r_apploc_free(req):
    return appmove.free_old()


@route("GET", "/apps/location/log")
def _r_apploc_log(req):
    try:
        off = int(req.query.get("offset", 0))
    except ValueError:
        off = 0
    return appmove.log_since(off)


@route("GET", "/updates")
def _updates(req):
    return updates.status()


@route("GET", "/updates/log")
def _updates_log(req):
    return updates.log_since(int(req.query.get("from", 0) or 0))


@route("POST", "/updates/check")
def _upd_check(req):
    return updates.check()


@route("POST", "/updates/install")
def _upd_install(req):
    return updates.install()


@route("POST", "/updates/settings")
def _upd_auto(req):
    return updates.save_settings(req.json())


@route("GET", "/snapshots")
def _snaps(req):
    return updates.snapshots()


@route("POST", "/snapshots")
def _snap_new(req):
    return updates.create_snapshot(req.json().get("description"))


@route("POST", "/snapshots/(\\d+)/restore")
def _snap_restore(req, n):
    return updates.restore_snapshot(n)


@route("DELETE", "/snapshots/(\\d+)")
def _snap_del(req, n):
    return updates.delete_snapshot(n)


# --- terminale e SSH ----------------------------------------------------------------------------------

@route("GET", "/term/targets")
def _term_targets(req):
    return terminal.targets(req.user)


@route("GET", "/ssh")
def _ssh(req):
    return sshd.status()


@route("POST", "/ssh")
def _ssh_save(req):
    return sshd.save(req.json())


@route("POST", "/ssh/keys")
def _ssh_key_add(req):
    b = req.json()
    return sshd.add_key(b.get("user"), b.get("key"), b.get("name"))


@route("POST", "/ssh/keys/delete")
def _ssh_key_del(req):
    b = req.json()
    return sshd.remove_key(b.get("user"), b.get("fingerprint"))


# --- notifiche -----------------------------------------------------------------------------------------

@route("GET", "/notify")
def _notify(req):
    return notify.get()


@route("POST", "/notify")
def _notify_save(req):
    return notify.save(req.json())


@route("POST", "/notify/test")
def _notify_test(req):
    return notify.test(req.json().get("channel"))


# --- gestore HTTP ---------------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = re.sub(r"[^A-Za-z0-9._-]", "", product()[0]) or "NAS"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 300

    def log_message(self, fmt, *args):
        if os.environ.get("NIDO_DEBUG"):
            sys.stderr.write("%s %s\n" % (self.client_ip(), fmt % args))

    # --- utilità ---
    def client_ip(self):
        ip = self.client_address[0]
        # Dietro Caddy (127.0.0.1) l'indirizzo vero arriva in X-Forwarded-For
        if ip in ("127.0.0.1", "::1") and self.headers.get("X-Forwarded-For"):
            ip = self.headers["X-Forwarded-For"].split(",")[-1].strip()
        return ip

    def https(self):
        return self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("X-Forwarded-Proto") == "https"

    def body(self, limit=MAX_JSON):
        if not hasattr(self, "_body"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ApiError("Richiesta troppo grande", 413)
            self._body = self.rfile.read(n) if n else b""
        return self._body

    def drain(self):
        """Legge e scarta il corpo non ancora letto (o chiude la connessione se è troppo grande)."""
        if hasattr(self, "_body") or self.command in ("GET", "HEAD"):
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            self.close_connection = True
            return
        if n:
            self.rfile.read(n)
        self._body = b""

    def json(self):
        raw = self.body()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            raise ApiError("JSON non valido")
        if not isinstance(data, dict):
            raise ApiError("JSON non valido")
        return data

    def cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def headers_common(self, extra=None):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for k, v in (extra or {}).items():
            if isinstance(v, list):
                for x in v:
                    self.send_header(k, x)
            else:
                self.send_header(k, v)

    def send(self, status, payload, ctype="application/json; charset=utf-8", extra=None, head=False, cache="no-store"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.headers_common(extra)
        self.end_headers()
        if not head:
            self.wfile.write(data)

    # --- metodi ---
    def do_HEAD(self):
        self.handle_request("HEAD")

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PUT(self):
        self.handle_request("PUT")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def handle_request(self, method):
        # Con le connessioni persistenti (HTTP/1.1) lo stesso oggetto serve più richieste:
        # niente stato rimasto dalla richiesta precedente
        self.__dict__.pop("_body", None)
        self._sent_headers = False
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        self.query = dict(urllib.parse.parse_qsl(parsed.query))
        self.user = None
        try:
            if path == "/api/term/ws" and method == "GET":
                return self.terminal_ws()
            if path.startswith("/api/"):
                return self.api(method, path[4:])
            if method not in ("GET", "HEAD"):
                raise ApiError("Metodo non consentito", 405)
            if path.startswith("/s/"):
                return self.public_share(path[3:].strip("/"), head=method == "HEAD")
            if path.startswith("/static/"):
                return self.static(UI, path[len("/static/"):], method == "HEAD", cache="public, max-age=300")
            if path == "/certificato-casa.crt":       # pubblico: è solo la parte pubblica della CA di casa
                return self.send(200, https.ca_pem().encode(), "application/x-x509-ca-cert",
                                 extra={"Content-Disposition": f'attachment; filename="{socket.gethostname()}-casa.crt"'},
                                 head=method == "HEAD")
            if path in ("/favicon.ico", "/favicon.svg"):
                return self.static(UI, "img/favicon.svg", method == "HEAD", cache="public, max-age=86400")
            if path == "/" or re.match(r"^/[a-z]*$", path):
                return self.static(UI, "index.html", method == "HEAD")
            raise ApiError("Non trovato", 404)
        except ApiError as e:
            self.drain()
            if not getattr(self, "_sent_headers", False):
                self.send(e.status, {"error": e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                self.send(500, {"error": f"Errore interno: {e}"})
            except OSError:
                pass

    # --- accesso ---
    def session_user(self):
        return auth.session_user(self.cookie(auth.COOKIE))

    def csrf(self, method):
        if method not in ("GET", "HEAD") and self.headers.get("X-Nido") != "1":
            raise ApiError("Richiesta non consentita (manca X-Nido)", 403)

    def set_cookie(self, token, ttl):
        attrs = ["Path=/", "HttpOnly", "SameSite=Strict"]
        if ttl is not None:
            attrs.append(f"Max-Age={ttl}")
        if self.https():
            attrs.append("Secure")
        return f"{auth.COOKIE}={token}; " + "; ".join(attrs)

    def auth_api(self, method, sub):
        if sub == "/auth/state" and method == "GET":
            u = self.session_user()
            st = {"setup": auth.setup_needed(), "user": u, "admin": auth.is_admin(u) if u else False, "about": _about()}
            # Schermo del NAS (richiesta diretta da 127.0.0.1, non da Caddy): indirizzi per gli altri dispositivi
            if self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("X-Forwarded-For"):
                st["local_screen"] = True
                st["addresses"] = _local_addresses()
            return self.send(200, st)
        self.csrf(method)
        if sub == "/auth/login" and method == "POST":
            b = self.json()
            token, ttl = auth.login(b.get("user"), b.get("password"), bool(b.get("remember")),
                                    self.client_ip(), self.headers.get("User-Agent"))
            return self.send(200, {"ok": True}, extra={"Set-Cookie": self.set_cookie(token, ttl if b.get("remember") else None)})
        if sub == "/auth/setup" and method == "POST":
            if not auth.setup_needed():
                raise ApiError("L'account amministratore esiste già", 409)
            b = self.json()
            auth.create_user(b.get("user"), b.get("password"), admin=True)
            token, ttl = auth.login(b.get("user"), b.get("password"), True, self.client_ip(), self.headers.get("User-Agent"))
            return self.send(200, {"ok": True}, extra={"Set-Cookie": self.set_cookie(token, ttl)})
        if sub == "/auth/logout" and method == "POST":
            auth.logout(self.cookie(auth.COOKIE))
            return self.send(200, {"ok": True}, extra={"Set-Cookie": f"{auth.COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
        if sub == "/auth/password" and method == "POST":
            u = self.session_user()
            if not u:
                raise ApiError("Accesso scaduto", 401)
            b = self.json()
            auth.verify(u, b.get("old"), self.client_ip())
            auth.set_password(u, b.get("new"))
            return self.send(200, {"ok": True})
        raise ApiError("Operazione non trovata", 404)

    def api(self, method, sub):
        if sub.startswith("/auth/"):
            return self.auth_api(method, sub)
        if sub.startswith("/v1/"):
            return self.ha_api(method, sub)
        self.user = self.session_user()
        if not self.user:
            raise ApiError("Accesso scaduto: accedi di nuovo", 401)
        self.csrf(method)
        # Streaming dei file (non JSON)
        if sub == "/files/raw" and method in ("GET", "HEAD"):
            return self.file_raw(self.query.get("path", ""), method == "HEAD", self.query.get("dl") == "1")
        if sub == "/files/download" and method == "GET":
            paths = [p for p in self.query.get("paths", "").split("\n") if p] or [self.query.get("path", "")]
            return self.download(paths)
        if sub == "/files/upload" and method in ("PUT", "POST"):
            return self.upload()
        if sub == "/selfupdate/upload" and method in ("PUT", "POST"):
            if not auth.is_admin(self.user):
                raise ApiError("Serve un account amministratore", 403)
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_CHUNK:
                raise ApiError("Blocco troppo grande", 413)
            try:
                offset = int(self.query.get("offset", 0))
                total = int(self.query.get("total", n))
            except ValueError:
                raise ApiError("Parametri non validi")
            return self.send(200, selfupdate.upload_chunk(self.query.get("name", ""), offset, total, self.rfile, n))
        if sub == "/files/thumb" and method in ("GET", "HEAD"):
            return self.thumb(self.query.get("path", ""), self.query.get("s", "256"), method == "HEAD")
        for m, rx, fn, admin in ROUTES:
            if m != method:
                continue
            match = rx.match(sub)
            if match:
                if admin and not auth.is_admin(self.user):
                    raise ApiError("Serve un account amministratore", 403)
                return self.send(200, fn(self, *match.groups()))
        raise ApiError("Operazione non trovata", 404)

    def terminal_ws(self):
        """Terminale: passaggio a WebSocket (solo amministratori, solo dalla stessa origine)."""
        self.user = self.session_user()
        if not self.user:
            raise ApiError("Accesso scaduto: accedi di nuovo", 401)
        if not auth.is_admin(self.user):
            raise ApiError("Serve un account amministratore", 403)
        origin = urllib.parse.urlsplit(self.headers.get("Origin") or "").netloc
        if not origin or origin != (self.headers.get("X-Forwarded-Host") or self.headers.get("Host")):
            raise ApiError("Origine non consentita", 403)
        key = self.headers.get("Sec-WebSocket-Key")
        if (self.headers.get("Upgrade") or "").lower() != "websocket" or not key:
            raise ApiError("Serve una connessione WebSocket", 400)
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", terminal.accept_key(key))
        self.end_headers()
        self.wfile.flush()
        self._sent_headers = True
        self.close_connection = True
        token = self.cookie(auth.COOKIE)
        try:
            cols, rows = int(self.query.get("cols", 100)), int(self.query.get("rows", 30))
        except ValueError:
            cols, rows = 100, 30
        terminal.serve(self.connection, self.query.get("target", "root"), self.user,
                       lambda: auth.session_user(token) == self.user, cols, rows)

    def ha_api(self, method, sub):
        """API per Home Assistant (integrazione rfd_nas e sensori REST), con la chiave API (X-API-Key)."""
        key = self.headers.get("X-API-Key") or ""
        expected = api_key(create=False)
        if not ((expected and hmac.compare_digest(key, expected)) or self.session_user()):
            raise ApiError("Chiave API mancante o errata", 401)
        if sub == "/v1/status" and method == "GET":
            st = system.ha_status()
            try:
                st["apps"] = [{"name": a["name"], "title": a["title"], "state": a["state"], "managed": a["managed"],
                               "version": a.get("version"), "update": bool(a.get("update")),
                               "port": (a.get("web") or {}).get("port") or ""} for a in apps.list_apps()["apps"]]
            except Exception:  # noqa: BLE001 — Docker fermo: niente app
                st["apps"] = []
            try:
                st["disk_standby"] = {d["name"]: standby.info_for(d)["state"]
                                      for d in disks.list_disks(with_smart=False) if not d["protected"]}
            except Exception:  # noqa: BLE001
                st["disk_standby"] = {}
            try:   # aggiornamento del sistema disponibile online (sensore "update" di Home Assistant)
                last = online.status().get("last") or {}
                st["system_update"] = {"available": bool(last.get("available")), "installed": product()[1],
                                       "latest": last.get("version") or product()[1], "notes": (last.get("notes") or "")[:255],
                                       "checked": last.get("checked")}
            except Exception:  # noqa: BLE001
                st["system_update"] = {"available": False}
            st["power_schedule"] = {k: v for k, v in powersched.get().items() if k in ("off", "on", "next_off", "next_on")}
            return self.send(200, st)
        if method != "POST":
            raise ApiError("Operazione non trovata", 404)
        m = re.match(r"^/v1/apps/([a-z0-9][a-z0-9_.-]*)/(start|stop|restart|update)$", sub)
        if m:
            res = apps.start_update(m.group(1)) if m.group(2) == "update" and hasattr(apps, "start_update") \
                else apps.action(m.group(1), m.group(2))
            return self.send(200, res or {"ok": True})
        m = re.match(r"^/v1/system/(reboot|poweroff)$", sub)
        if m:
            return self.send(200, system.power(m.group(1)))
        if sub == "/v1/system/update":   # aggiornamento online del sistema (entità "update" di Home Assistant)
            return self.send(200, online.start_install())
        if sub == "/v1/updates/check":
            return self.send(200, updates.check())
        if sub == "/v1/apps/check":
            return self.send(200, apps.start_check())
        m = re.match(r"^/v1/disks/([a-z0-9]+)/sleep$", sub)
        if m:
            return self.send(200, standby.sleep_now("/dev/" + m.group(1)))
        raise ApiError("Operazione non trovata", 404)

    # --- file statici ---
    def static(self, base, rel, head=False, cache="no-cache"):
        rel = os.path.normpath(urllib.parse.unquote(rel)).lstrip("/")
        if rel.startswith("..") or "\x00" in rel:
            raise ApiError("Non trovato", 404)
        full = os.path.join(base, rel)
        if not os.path.isfile(full):
            raise ApiError("Non trovato", 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml", "application/json"):
            ctype += "; charset=utf-8"
        extra = {"Content-Security-Policy": CSP} if rel.endswith(".html") else None
        with open(full, "rb") as f:
            self.send(200, f.read(), ctype, extra=extra, head=head, cache=cache)

    # --- file dell'utente ---
    def stream_file(self, real, head=False, attachment=False, name=None):
        size = os.path.getsize(real)
        ctype = mimetypes.guess_type(real)[0] or "application/octet-stream"
        # HTML e SVG dell'utente: mai mostrati come pagina (niente script dal NAS)
        if ctype in ("text/html", "image/svg+xml", "application/xhtml+xml", "text/xml", "application/xml"):
            attachment = attachment or ctype != "image/svg+xml"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        m = re.match(r"^bytes=(\d*)-(\d*)$", rng or "")
        if m and size:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2) or 0))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, no-cache")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; sandbox")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        fname = name or os.path.basename(real)
        disp = "attachment" if attachment else "inline"
        self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{urllib.parse.quote(fname)}")
        self.headers_common()
        self.end_headers()
        self._sent_headers = True
        if head or not size:
            return
        with open(real, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                buf = f.read(min(1024 * 1024, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def file_raw(self, path, head, dl):
        real = files.safe(path)
        if os.path.isdir(real):
            raise ApiError("È una cartella")
        self.stream_file(real, head, attachment=dl)

    def zip_stream(self, paths, name):
        """Cartelle o più file: zip creato al volo (senza compressione, parte subito)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.headers_common()
        self.end_headers()
        self._sent_headers = True
        self.close_connection = True

        class W(io.RawIOBase):
            def __init__(s, out):
                s.out, s.n = out, 0

            def writable(s):
                return True

            def write(s, b):
                s.out.write(b)
                s.n += len(b)
                return len(b)

            def tell(s):
                return s.n
        w = W(self.wfile)
        with zipfile.ZipFile(w, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for p in paths:
                base = os.path.dirname(p)
                if os.path.isdir(p):
                    for root, dirs, fs in os.walk(p):
                        dirs[:] = [d for d in dirs if d != files.TRASH]
                        for f in fs:
                            full = os.path.join(root, f)
                            if os.path.isfile(full) and not f.endswith(files.PART):
                                z.write(full, os.path.relpath(full, base))
                else:
                    z.write(p, os.path.basename(p))

    def download(self, paths):
        reals = [files.safe(p) for p in paths if p]
        if not reals:
            raise ApiError("Niente da scaricare")
        if len(reals) == 1 and os.path.isfile(reals[0]):
            return self.stream_file(reals[0], attachment=True)
        name = (os.path.basename(reals[0]) if len(reals) == 1 else "file") + ".zip"
        return self.zip_stream(reals, name)

    def upload(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_CHUNK:
            raise ApiError("Blocco troppo grande", 413)
        try:
            offset = int(self.query.get("offset", 0))
            total = int(self.query.get("total", n))
        except ValueError:
            raise ApiError("Parametri non validi")
        try:
            res = files.upload_chunk(self.query.get("dir", ""), self.query.get("name", ""), offset, total, self.rfile, n,
                                     conflict=self.query.get("conflict", "rename"))
        except ApiError as e:
            m = re.match(r"^received=(\d+)$", e.message)
            if m:
                # Il blocco non comincia dove si era fermato il file: il browser riprende da qui.
                # Il corpo della richiesta va letto comunque, se no la connessione si rompe.
                left = n
                while left > 0:
                    b = self.rfile.read(min(1 << 20, left))
                    if not b:
                        break
                    left -= len(b)
                return self.send(409, {"error": "Il caricamento riprende da dove si era fermato", "received": int(m.group(1))})
            raise
        self.send(200, res)

    def thumb(self, path, size, head=False):
        real = files.safe(path)
        try:
            out = files.thumbnail(real, int(size) if str(size).isdigit() else 256)
        except OSError:
            out = None
        if not out:
            raise ApiError("Miniatura non disponibile", 404)
        with open(out, "rb") as f:
            data = f.read()
        # L'indirizzo contiene la data del file: la miniatura si può tenere in cache a lungo
        self.send(200, data, "image/jpeg", head=head, cache="private, max-age=604800")

    def public_share(self, token, head=False):
        link = files.share_resolve(token.split("/")[0])
        if not link:
            return self.send(404, "<!doctype html><meta charset=utf-8><title>Link non valido</title>"
                                  "<p style='font:16px system-ui;padding:40px'>Questo link non esiste più o è scaduto.</p>".encode(),
                             "text/html; charset=utf-8")
        real = link["path"]
        if os.path.isdir(real):
            return self.zip_stream([real], os.path.basename(real) + ".zip")
        return self.stream_file(real, head, attachment=True)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def main():
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("font/woff2", ".woff2")
    api_key()
    metrics.start()
    listen = os.environ.get("NIDO_LISTEN", "0.0.0.0:80")
    host, _, port = listen.rpartition(":")
    srv = Server((host or "0.0.0.0", int(port)), Handler)
    print(f"Interfaccia in ascolto su {host}:{srv.server_port}", flush=True)
    if host in ("127.0.0.1", "localhost"):          # dietro Caddy: porta 80 di riserva se Caddy non parte
        server_fallback.configure(Server, Handler)
        threading.Thread(target=server_fallback.watchdog, daemon=True).start()
        # Caddy sta per partire (ExecStartPre di caddy.service): libera la porta 80 di riserva
        signal.signal(signal.SIGUSR1, lambda *_: threading.Thread(target=server_fallback.release, args=(90,), daemon=True).start())
    threading.Thread(target=catalog.ensure, daemon=True).start()
    from . import uptime as uptime_mod
    uptime_mod.start_thread()

    def thumbs_cleaner():
        while True:
            time.sleep(3600)
            try:
                files.clean_thumbs()
            except Exception as e:  # noqa: BLE001
                print(f"miniature: {e}", flush=True)
            time.sleep(23 * 3600)
    threading.Thread(target=thumbs_cleaner, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
