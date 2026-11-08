"""Catalogo unico delle app: tutte le fonti in un solo elenco, senza doppioni.

Fonti supportate: zip di app in formato compose (Apps/<app>/docker-compose.yml con il blocco
di metadati x-casaos, il formato pubblico usato dagli store della comunità): Big Bear, LinuxServer,
CoolStore e fonti personalizzate; in più Runtipi (catalogo GPL-3.0, formato proprio convertito qui sotto
con _ingest_runtipi). Dal 31/10/2026 le fonti CasaOS ufficiale, ZimaOS e Unraid CA sono
state tolte (scelta dell'utente, per evitare problemi con i marchi).

Nella ISO non c'è nessun catalogo: si scarica dai siti degli autori al primo avvio e
poi ogni settimana (o con "Aggiorna catalogo").
"""
import concurrent.futures
import datetime
import hashlib
import io
import os
import re
import shutil
import threading
import urllib.parse
import urllib.request
import zipfile

import yaml

from . import stores
from .util import ApiError, ETC, STATE, load_json, save_json, user_agent

CONF = os.path.join(ETC, "sources.json")
DIR = os.path.join(STATE, "catalog")
INDEX = os.path.join(DIR, "index.json")
UA = {"User-Agent": user_agent("catalog")}

DEFAULT_SOURCES = [
    {"id": "bigbear", "name": "Big Bear", "kind": "v1", "color": "#f59e0b",
     "url": "https://github.com/bigbeartechworld/big-bear-casaos/archive/refs/heads/master.zip"},
    {"id": "lsio", "name": "LinuxServer", "kind": "v1", "color": "#0ea5e9",
     "url": "https://casaos-appstore.paodayag.dev/linuxserver.zip"},
    {"id": "cool", "name": "CoolStore", "kind": "v1", "color": "#10b981",
     "url": "https://casaos-appstore.paodayag.dev/coolstore.zip"},
    {"id": "runtipi", "name": "Runtipi", "kind": "runtipi", "color": "#8b5cf6",
     "url": "https://github.com/runtipi/runtipi-appstore/archive/refs/heads/master.zip"},
]
# Ordine di preferenza quando la stessa app è in più fonti
PRIORITY = ["bigbear", "lsio", "cool", "runtipi"]

# Fonti extra (CasaOS, ZimaOS, Unraid): solo se è installato il pacchetto a parte "nido-extra-store",
# che aggiunge nidopanel/stores_extra.py. Non sono nella ISO né nel pacchetto nido-nas.
try:
    from . import stores_extra as _extra
except ImportError:
    _extra = None
if _extra:
    DEFAULT_SOURCES = list(_extra.SOURCES_FIRST) + DEFAULT_SOURCES + list(_extra.SOURCES_LAST)
    PRIORITY = [s["id"] for s in _extra.SOURCES_FIRST] + PRIORITY + [s["id"] for s in _extra.SOURCES_LAST]
# Fonti tolte: spariscono dal catalogo già scaricato e dalle impostazioni
REMOVED = set() if _extra else {"casaos", "zima", "unraid"}

CATEGORIES = {
    "media": "Media", "entertainment": "Media", "video": "Media", "music": "Media", "photos": "Media",
    "gallery": "Media", "mediaserver": "Media", "downloader": "Download", "downloaders": "Download",
    "download": "Download", "home automation": "Domotica", "homeautomation": "Domotica", "smart home": "Domotica",
    "iot": "Domotica", "network": "Rete", "networking": "Rete", "dns": "Rete", "vpn": "Rete",
    "backup": "Backup", "cloud": "Cloud", "file sync": "Cloud", "storage": "Cloud", "file management": "Cloud",
    "documents": "Documenti", "productivity": "Produttività", "notes": "Produttività", "office": "Produttività",
    "developer": "Sviluppo", "development": "Sviluppo", "dev tools": "Sviluppo", "security": "Sicurezza",
    "password manager": "Sicurezza", "utilities": "Utilità", "utility": "Utilità", "tools": "Utilità",
    "analytics": "Monitoraggio", "monitoring": "Monitoraggio", "dashboard": "Monitoraggio", "games": "Giochi",
    "gaming": "Giochi", "ai": "IA", "llm": "IA", "chat": "Comunicazione", "communication": "Comunicazione",
    "social": "Comunicazione", "finance": "Casa", "recipes": "Casa", "home": "Casa", "database": "Sviluppo",
}
CATEGORY_ORDER = ["Media", "Domotica", "Rete", "Backup", "Cloud", "Documenti", "Download", "Produttività",
                  "Sviluppo", "Sicurezza", "Monitoraggio", "IA", "Comunicazione", "Casa", "Giochi", "Utilità", "Altro"]
FEATURED = ["immich", "paperless-ngx", "esphome", "jellyfin", "home-assistant", "nextcloud"]

_lock = threading.Lock()
_index = None
_build = {"running": False, "pending": False, "log": [], "started": None, "ended": None}


# --- configurazione delle fonti --------------------------------------------------------------------

def _conf():
    c = load_json(CONF, {})
    c.setdefault("enabled", {})
    c.setdefault("urls", {})
    c.setdefault("custom", [])
    return c


def sources():
    c = _conf()
    res = []
    for s in DEFAULT_SOURCES:
        s = dict(s)
        s["enabled"] = bool(c["enabled"].get(s["id"], not s.get("optional")))
        if s["id"] in c["urls"]:
            ov = c["urls"][s["id"]]
            if isinstance(ov, list):
                s["urls"] = ov
            else:
                s["url"] = ov
        res.append(s)
    for s in c["custom"]:
        if s.get("kind") != "v1" and not _extra:
            continue  # gli store ZimaOS (v2) solo con il pacchetto delle fonti extra
        res.append({**s, "custom": True, "enabled": bool(c["enabled"].get(s["id"], True))})
    return res


def set_source(sid, enabled):
    c = _conf()
    if not any(s["id"] == sid for s in sources()):
        raise ApiError("Fonte non trovata", 404)
    c["enabled"][sid] = bool(enabled)
    save_json(CONF, c, 0o644)
    start_build()
    return sources_status()


def add_source(body):
    url = (body.get("url") or "").strip()
    if not re.match(r"^https?://[^\s]+$", url):
        raise ApiError("Indirizzo non valido: deve iniziare con http:// o https://")
    kind = "v1" if url.lower().split("?")[0].endswith(".zip") else "v2"
    if kind == "v2":
        if not _extra:
            raise ApiError("Serve l'indirizzo di uno zip di app (che finisce con .zip)")
        url = re.sub(r"/(index|store)\.json$", "", url).rstrip("/")
    c = _conf()
    if any(s.get("url") == url for s in c["custom"]):
        raise ApiError("Questa fonte c'è già")
    name = (body.get("name") or "").strip()[:40] or urllib.parse.urlparse(url).netloc
    sid = "x" + hashlib.sha1(url.encode()).hexdigest()[:7]
    palette = ["#14b8a6", "#8b5cf6", "#ef4444", "#84cc16", "#06b6d4", "#d946ef"]
    c["custom"].append({"id": sid, "name": name, "kind": kind, "url": url,
                        "color": palette[len(c["custom"]) % len(palette)]})
    save_json(CONF, c, 0o644)
    start_build()
    return sources_status()


def remove_source(sid):
    c = _conf()
    before = len(c["custom"])
    c["custom"] = [s for s in c["custom"] if s["id"] != sid]
    if len(c["custom"]) == before:
        raise ApiError("Si possono togliere solo le fonti aggiunte da te", 400)
    c["enabled"].pop(sid, None)
    save_json(CONF, c, 0o644)
    start_build()
    return sources_status()


# --- lettura dei compose ------------------------------------------------------------------------------

def _loc(v):
    if isinstance(v, dict):
        for k in ("it_it", "it_IT", "it", "en_us", "en_US", "en", "en_GB"):
            if v.get(k):
                return str(v[k])
        for x in v.values():
            if x:
                return str(x)
        return ""
    return str(v) if v not in (None, {}, []) else ""


def slug(text):
    t = (text or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", "", t)
    t = re.sub(r"^(binhex|linuxserver|lsio|bigbear|big-bear|casaos)[-_ ]", "", t.strip())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "app"


# Le fonti usano poche categorie generiche ("Others", "Home"…): prima provo con parole chiave
# nel nome e nella descrizione, poi con la categoria della fonte.
KEYWORDS = [
    ("Download", r"torrent|qbittorrent|transmission|deluge|sonarr|radarr|lidarr|readarr|prowlarr|jackett|sabnzbd|nzb|usenet|jdownloader|pyload|youtube-dl|yt-dlp|metube|downloader"),
    ("Domotica", r"home ?assistant|homebridge|openhab|domoticz|zigbee|z-wave|zwave|mqtt|mosquitto|esphome|node-red|tasmota|frigate|scrypted|smart home|domotic|automation|iot\b"),
    ("Media", r"plex|jellyfin|emby|kodi|music|video|movie|film|photo|foto|gallery|immich|photoprism|audiobook|podcast|stream|navidrome|airsonic|subsonic|tv\b|iptv|media"),
    ("Documenti", r"paperless|document|pdf|ocr|scanner|ebook|calibre|kavita|komga|wiki|bookstack|notes?\b|markdown|outline"),
    ("Backup", r"backup|duplicati|restic|borg|kopia|syncthing|rsync|snapshot|resilio"),
    ("Cloud", r"nextcloud|owncloud|seafile|cloud|file ?brows|file ?shar|filebrowser|webdav|s3\b|minio"),
    ("Rete", r"dns|pi-?hole|adguard|vpn|wireguard|openvpn|tailscale|proxy|nginx proxy|traefik|caddy|ddns|duckdns|cloudflare|speedtest|network|firewall|unifi"),
    ("Sicurezza", r"password|vault|bitwarden|vaultwarden|2fa|authelia|authentik|keycloak|crowdsec|fail2ban|security"),
    ("Monitoraggio", r"monitor|uptime|grafana|prometheus|influx|netdata|glances|dashdot|status page|metrics|log viewer|dozzle|portainer|dashboard|homepage|heimdall|homarr|organizr"),
    ("IA", r"\bai\b|llm|ollama|gpt|openai|stable diffusion|whisper|machine learning|chatbot|localai"),
    ("Sviluppo", r"\bgit\b|gitea|gitlab|forgejo|code-?server|\bide\b|jenkins|\bci\b|database|postgres|mysql|mariadb|redis|mongo|adminer|pgadmin|developer|api\b"),
    ("Comunicazione", r"chat|matrix|mastodon|discord|telegram|signal|mail|email|smtp|irc|forum|rss|freshrss|miniflux|social"),
    ("Giochi", r"minecraft|game|gaming|steam|retro|emulat|valheim|terraria|palworld"),
    ("Produttività", r"todo|task|kanban|calendar|calendario|office|onlyoffice|collabora|spreadsheet|project|planka|vikunja|wekan|time track|bookmark|linkding|productivity"),
    ("Casa", r"recipe|ricett|grocy|mealie|tandoor|budget|finance|firefly|actual|inventory|home ?box|baby|famil|pet\b"),
]
_KW = [(c, re.compile(rx, re.I)) for c, rx in KEYWORDS]


def _category(raw, title="", text=""):
    for c, rx in _KW:
        if rx.search(title):
            return c
    for c, rx in _KW:
        if rx.search(text[:400]):
            return c
    r = (raw or "").strip().lower()
    if r == "home":
        return "Domotica"
    if r in CATEGORIES:
        return CATEGORIES[r]
    for k, v in CATEGORIES.items():
        if k in r:
            return v
    return "Altro"


def parse_compose(text, fallback_name=""):
    """Legge un docker-compose in formato CasaOS e restituisce le informazioni per lo store."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict) or not data["services"]:
        return None
    x = data.get("x-casaos") or {}
    if not isinstance(x, dict):
        x = {}
    archs = x.get("architectures")
    if isinstance(archs, list) and archs and "amd64" not in [str(a).lower() for a in archs]:
        return None
    svcs = data["services"]
    main = x.get("main") if x.get("main") in svcs else next(iter(svcs))
    image = str((svcs.get(main) or {}).get("image") or "")
    if not image:
        return None
    title = _loc(x.get("title")) or data.get("name") or fallback_name
    tag = image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else "latest"
    shots = x.get("screenshot_link") or []
    return {
        "title": str(title)[:60],
        "tagline": _loc(x.get("tagline"))[:200],
        "description": _loc(x.get("description"))[:4000],
        "icon": str(x.get("icon") or ""),
        "thumbnail": str(x.get("thumbnail") or ""),
        "screenshots": [str(s) for s in shots if isinstance(s, str)][:6] if isinstance(shots, list) else [],
        "category": _category(str(x.get("category") or ""), str(title), _loc(x.get("tagline")) + " " + _loc(x.get("description"))),
        "developer": str(x.get("developer") or "")[:60],
        "author": str(x.get("author") or "")[:60],
        "image": image,
        "version": tag,
        "port": str(x.get("port_map") or ""),
        "scheme": str(x.get("scheme") or "http"),
        "index": str(x.get("index") or "/"),
        "services": len(svcs),
        "tips": _loc((x.get("tips") or {}).get("before_install")) if isinstance(x.get("tips"), dict) else "",
    }


APP_RE = re.compile(r"(?:^|/)Apps/([^/]+)/docker-compose\.ya?ml$", re.I)


def _ingest_zip(sid, data, out_dir):
    """Estrae i compose da uno zip e restituisce l'elenco delle app lette."""
    apps = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            m = APP_RE.search(info.filename)
            if not m or info.file_size > 512 * 1024:
                continue
            text = z.read(info).decode("utf-8", "replace")
            meta = parse_compose(text, m.group(1))
            if not meta:
                continue
            fname = re.sub(r"[^A-Za-z0-9_.-]+", "-", m.group(1))[:80] + ".yml"
            with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
                f.write(text)
            apps.append({**meta, "file": fname, "src": sid})
    return apps


# --- Runtipi (github.com/runtipi/runtipi-appstore, GPL-3.0) -------------------------------------------
# Ogni app ha config.json (nome, porta, campi da compilare) e docker-compose.json (formato "dinamico" v2).
# Qui diventano compose normali con il blocco x-casaos, così installazione e aggiornamenti sono gli stessi
# delle altre fonti. Le app con il solo docker-compose.yml vecchio (Traefik) vengono saltate.

RUNTIPI_RAW = "https://raw.githubusercontent.com/runtipi/runtipi-appstore/master/apps/{id}/metadata/logo.jpg"
RT_KEYS = {"command": "command", "entrypoint": "entrypoint", "user": "user", "privileged": "privileged",
           "capAdd": "cap_add", "capDrop": "cap_drop", "devices": "devices", "hostname": "hostname",
           "networkMode": "network_mode", "securityOpt": "security_opt", "sysctls": "sysctls", "ulimits": "ulimits",
           "shmSize": "shm_size", "workingDir": "working_dir", "stopGracePeriod": "stop_grace_period",
           "stopSignal": "stop_signal", "tty": "tty", "stdinOpen": "stdin_open", "logging": "logging",
           "deploy": "deploy", "pid": "pid", "extraHosts": "extra_hosts", "readOnly": "read_only"}
RT_VAR = re.compile(r"\$\{([A-Za-z0-9_]+)(?::?-([^}]*))?\}")


def _rt_value(field):
    """Valore iniziale di un campo del modulo di Runtipi (modificabile poi in modalità avanzata)."""
    import secrets
    t, d = field.get("type"), field.get("default")
    if d is not None and d != "":
        return str(d).lower() if isinstance(d, bool) else str(d)
    if t == "random":
        n = int(field.get("min") or field.get("max") or 32)
        return secrets.token_hex(max(8, min(n, 64)) // 2 + 1)[:max(8, min(n, 64))]
    if t == "password" and field.get("required"):
        return secrets.token_urlsafe(18)[:max(12, int(field.get("min") or 12))]
    if t == "boolean":
        return "false"
    return ""


def _rt_convert(cfg, dyn):
    port = cfg.get("port")
    gui = not cfg.get("no_gui") and port
    fields = {f["env_variable"]: _rt_value(f) for f in (cfg.get("form_fields") or []) if f.get("env_variable")}
    fixed = {"APP_DATA_DIR": "/DATA/AppData/$AppID", "ROOT_FOLDER_HOST": "/DATA", "APP_ID": "$AppID",
             "TZ": "$TZ", "APP_PORT": str(port or ""), "APP_DOMAIN": f"localhost:{port}" if port else "localhost",
             "APP_HOST": "localhost", "APP_PROTOCOL": "http", "LOCAL_DOMAIN": "local", "TIPI_UID": "$PUID",
             "TIPI_GID": "$PGID", "UID": "$PUID", "GID": "$PGID"}

    def sub(v):
        if isinstance(v, bool):
            return str(v).lower()
        if not isinstance(v, str):
            return v
        def rep(m):
            k = m.group(1)
            if k in fixed:
                return fixed[k]
            if k in fields and fields[k] != "":
                return fields[k].replace("$", "$$")
            return m.group(0)       # resta ${VAR:-predefinito}: lo risolve docker compose
        return RT_VAR.sub(rep, v.replace("{{RUNTIPI_APP_ID}}", "$AppID"))

    services, main = {}, None
    for sv in dyn.get("services") or []:
        name = re.sub(r"[^a-z0-9_.-]", "-", str(sv.get("name") or "app").lower())
        out = {"image": sub(sv.get("image") or ""), "restart": "unless-stopped"}
        env = {}
        for e in sv.get("environment") or []:
            if isinstance(e, dict) and e.get("key"):
                env[str(e["key"])] = str(sub(e.get("value", "")))
        if env:
            out["environment"] = env
        vols = []
        for v in sv.get("volumes") or []:
            if isinstance(v, dict) and v.get("hostPath") and v.get("containerPath"):
                vols.append(f"{sub(v['hostPath'])}:{v['containerPath']}" + (":ro" if v.get("readOnly") else ""))
        if vols:
            out["volumes"] = vols
        ports = []
        if sv.get("isMain") and sv.get("internalPort") and gui:
            ports.append(f"{port}:{sub(str(sv['internalPort']))}")
        for ap in sv.get("addPorts") or []:
            hp, cp = sub(str(ap.get("hostPort"))), sub(str(ap.get("containerPort")))
            if ap.get("udp"):
                ports.append(f"{hp}:{cp}/udp")
            if ap.get("tcp", not ap.get("udp")):
                ports.append(f"{hp}:{cp}")
        if ports and sv.get("networkMode") != "host":
            out["ports"] = ports
        for k, ck in RT_KEYS.items():
            if k in sv:
                out[ck] = sub(sv[k]) if isinstance(sv[k], str) else sv[k]
        if sv.get("dependsOn"):
            out["depends_on"] = sv["dependsOn"]
        hc = sv.get("healthCheck")
        if isinstance(hc, dict) and hc.get("test"):
            out["healthcheck"] = {"test": ["CMD-SHELL", hc["test"]] if isinstance(hc["test"], str) else hc["test"],
                                  **{ck: hc[k] for k, ck in (("interval", "interval"), ("timeout", "timeout"),
                                     ("retries", "retries"), ("startPeriod", "start_period"),
                                     ("startInterval", "start_interval")) if k in hc}}
        labels = {k: str(v) for k, v in (sv.get("extraLabels") or {}).items() if not k.startswith(("traefik", "runtipi"))}
        if labels:
            out["labels"] = labels
        services[name] = out
        if sv.get("isMain") or main is None:
            main = name if sv.get("isMain") or main is None else main
    if not services:
        return None
    auto = [k for k, f in ((f.get("env_variable"), f) for f in cfg.get("form_fields") or [])
            if k and f.get("type") in ("random", "password") and fields.get(k)]
    empty = [f.get("label") or f.get("env_variable") for f in cfg.get("form_fields") or []
             if f.get("required") and not fields.get(f.get("env_variable"))]
    tips = []
    if auto:
        tips.append("Password e chiavi create da sole: " + ", ".join(auto) + " (le vedi in modalità avanzata).")
    if empty:
        tips.append("Da compilare in modalità avanzata prima di installare: " + ", ".join(map(str, empty)) + ".")
    x = {"main": main, "title": {"en_us": cfg.get("name") or cfg.get("id")},
         "tagline": {"en_us": cfg.get("short_desc") or ""}, "description": {"en_us": cfg.get("description") or ""},
         "icon": RUNTIPI_RAW.format(id=cfg["id"]), "category": " ".join(cfg.get("categories") or []),
         "developer": cfg.get("author") or "", "author": "Runtipi", "architectures": cfg.get("supported_architectures") or ["amd64"],
         "port_map": str(port) if gui else "", "scheme": "https" if cfg.get("https") else "http",
         "index": cfg.get("url_suffix") or "/"}
    if tips:
        x["tips"] = {"before_install": {"en_us": " ".join(tips)}}
    return {"name": cfg["id"], "services": services, "x-casaos": x}


def _ingest_runtipi(sid, data, out_dir):
    import json
    apps = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        for n in sorted(names):
            m = re.search(r"(?:^|/)apps/([a-z0-9._-]+)/config\.json$", n)
            if not m:
                continue
            base = n[: -len("config.json")]
            if base + "docker-compose.json" not in names:
                continue
            try:
                cfg = json.loads(z.read(n))
                dyn = json.loads(z.read(base + "docker-compose.json"))
            except (ValueError, KeyError):
                continue
            if not cfg.get("available", True) or cfg.get("deprecated") or not cfg.get("id"):
                continue
            if "amd64" not in (cfg.get("supported_architectures") or ["amd64"]):
                continue
            try:
                comp = _rt_convert(cfg, dyn)
            except Exception:  # noqa: BLE001 — un'app strana non ferma il catalogo
                comp = None
            if not comp:
                continue
            text = "# Convertita dal catalogo Runtipi (GPL-3.0): github.com/runtipi/runtipi-appstore\n" + \
                yaml.safe_dump(comp, sort_keys=False, allow_unicode=True, width=200)
            meta = parse_compose(text, m.group(1))
            if not meta:
                continue
            fname = "rt-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", m.group(1))[:77] + ".yml"
            with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
                f.write(text)
            apps.append({**meta, "file": fname, "src": sid})
    return apps


def _fetch(url, timeout=120):
    data = stores._fetch(url, timeout=timeout, tries=3)
    if len(data) > 300 * 1024 * 1024:
        raise RuntimeError("file troppo grande")
    return data


def _log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print("catalog: " + msg, flush=True)
    with _lock:
        _build["log"] = (_build["log"] + [line])[-80:]


def _build_source(s, conf):
    tmp = os.path.join(DIR, "apps", f".{s['id']}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    apps = []
    if s["kind"] == "v1":
        apps = _ingest_zip(s["id"], _fetch(s["url"]), tmp)
    elif s["kind"] == "runtipi":
        apps = _ingest_runtipi(s["id"], _fetch(s["url"]), tmp)
    elif _extra and s["kind"] in _extra.KINDS:
        apps = _extra.build(s, conf, _ingest_zip, tmp)
    if not apps:
        raise RuntimeError("nessuna app valida trovata")
    final = os.path.join(DIR, "apps", s["id"])
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)
    save_json(os.path.join(final, "_apps.json"), apps, 0o644)
    return apps


def _merge(per_source, srcs):
    order = {sid: i for i, sid in enumerate(PRIORITY + [s["id"] for s in srcs if s.get("custom")])}
    merged = {}
    for sid in sorted(per_source, key=lambda x: order.get(x, 99)):
        for a in per_source[sid]:
            key = slug(a["title"])
            entry = {"src": sid, "file": a["file"], "image": a["image"], "version": a["version"]}
            if key in merged:
                m = merged[key]
                if not any(x["src"] == sid for x in m["sources"]):
                    m["sources"].append(entry)
                for k in ("tagline", "description", "icon", "thumbnail", "developer", "port"):
                    if not m.get(k) and a.get(k):
                        m[k] = a[k]
                if m["category"] == "Altro" and a["category"] != "Altro":
                    m["category"] = a["category"]
            else:
                merged[key] = {**{k: v for k, v in a.items() if k not in ("file", "src")},
                               "id": key, "sources": [entry]}
    apps = sorted(merged.values(), key=lambda a: (-len(a["sources"]), a["title"].lower()))
    return apps


SCHEDULE = os.path.join(ETC, "catalog-schedule.json")
TIMER_DROPIN = "/etc/systemd/system/nido-catalog.timer.d/10-frequenza.conf"
EVERY = {"6h": "6h", "12h": "12h", "24h": "24h", "weekly": "7d"}


def schedule():
    c = load_json(SCHEDULE, {})
    return {"every": c.get("every", "6h"), "boot": c.get("boot", True)}


def set_schedule(body):
    """Frequenza dell'aggiornamento automatico delle fonti: all'avvio e ogni 6/12/24 ore, ogni settimana o mai."""
    every = body.get("every", "6h")
    if every not in list(EVERY) + ["never"]:
        raise ApiError("Frequenza non valida")
    boot = bool(body.get("boot", True))
    save_json(SCHEDULE, {"every": every, "boot": boot}, 0o644)
    from .util import run_rc, systemd_running
    if systemd_running():
        if every == "never" and not boot:
            run_rc(["systemctl", "disable", "--now", "nido-catalog.timer"], timeout=30)
        else:
            os.makedirs(os.path.dirname(TIMER_DROPIN), exist_ok=True)
            lines = ["[Timer]", "OnCalendar=", "OnBootSec=", "OnUnitActiveSec="]
            if boot:
                lines.append("OnBootSec=3min")
            if every != "never":
                lines.append(f"OnUnitActiveSec={EVERY[every]}")
                if not boot:
                    lines.append(f"OnActiveSec={EVERY[every]}")
            with open(TIMER_DROPIN, "w") as f:
                f.write("# Scritto dall'interfaccia (Impostazioni → App store)\n" + "\n".join(lines) + "\n")
            run_rc(["systemctl", "daemon-reload"], timeout=30)
            run_rc(["systemctl", "enable", "nido-catalog.timer"], timeout=30)
            run_rc(["systemctl", "restart", "nido-catalog.timer"], timeout=30)
    return sources_status()


def _next_run():
    from .util import run_rc
    rc, out, _ = run_rc(["systemctl", "show", "nido-catalog.timer", "-p", "NextElapseUSecMonotonic,NextElapseUSecRealtime,LastTriggerUSec", "--value"], timeout=10)
    return out.strip().splitlines() if rc == 0 else []


def build(only=None):
    """Scarica le fonti attive e ricostruisce l'indice (chiamata da thread o da cli).
    Con only si scaricano solo quelle fonti: le altre restano come all'ultimo aggiornamento."""
    srcs = [s for s in sources() if s["enabled"]]
    conf = _conf()
    os.makedirs(os.path.join(DIR, "apps"), exist_ok=True)
    old = load_json(INDEX, {})
    status = {}
    per_source = {}
    _log(f"aggiorno {len(only) if only else len(srcs)} fonti")

    def one(s):
        if only and s["id"] not in only:
            prev = load_json(os.path.join(DIR, "apps", s["id"], "_apps.json"), None)
            if prev is not None:
                return s["id"], prev, "__skip__"
        try:
            apps = _build_source(s, conf)
            return s["id"], apps, None
        except Exception as e:  # noqa: BLE001 — una fonte guasta non ferma le altre
            import traceback
            print(traceback.format_exc(), flush=True)
            msg = stores.explain(e) if not isinstance(e, RuntimeError) else str(e)
            return s["id"], None, msg

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for sid, apps, err in ex.map(one, srcs):
            name = next(s["name"] for s in srcs if s["id"] == sid)
            if err == "__skip__":
                per_source[sid] = apps
                status[sid] = (old.get("status") or {}).get(sid) or {"ok": True, "count": len(apps)}
                continue
            if err:
                # Tengo l'ultima versione buona, se c'è
                prev = load_json(os.path.join(DIR, "apps", sid, "_apps.json"), None)
                if prev:
                    per_source[sid] = prev
                status[sid] = {"ok": False, "error": err[:300], "count": len(prev or []),
                               "updated": (old.get("status") or {}).get(sid, {}).get("updated")}
                _log(f"{name}: ERRORE {err}")
            else:
                per_source[sid] = apps
                status[sid] = {"ok": True, "count": len(apps),
                               "updated": datetime.datetime.now().isoformat(timespec="seconds")}
                _log(f"{name}: {len(apps)} app")
    # Le fonti spente spariscono dal catalogo
    for d in os.listdir(os.path.join(DIR, "apps")):
        if not d.startswith(".") and d not in {s["id"] for s in srcs}:
            shutil.rmtree(os.path.join(DIR, "apps", d), ignore_errors=True)
    apps = _merge(per_source, srcs)
    index = {"built": datetime.datetime.now().isoformat(timespec="seconds"), "status": status, "apps": apps}
    save_json(INDEX, index, 0o644)
    global _index
    with _lock:
        _index = index
    _log(f"catalogo pronto: {len(apps)} app")
    return index


def start_build(only=None):
    """Avvia l'aggiornamento del catalogo. Se ce n'è già uno in corso (per esempio quello
    dell'avvio) ne segna un altro da fare subito dopo: così una fonte appena attivata
    non resta "non ancora scaricata"."""
    with _lock:
        if _build["running"]:
            _build["pending"] = True
            return False
        _build.update(running=True, pending=False, log=[],
                      started=datetime.datetime.now().isoformat(timespec="seconds"))

    def run():
        first = True
        while True:
            try:
                build(only if first else None)
                first = False
            except Exception as e:  # noqa: BLE001
                _log(f"ERRORE: {e}")
            with _lock:
                if _build["pending"]:
                    _build["pending"] = False
                    _build["log"] = _build["log"] + ["— le fonti sono cambiate durante l'aggiornamento: aggiorno di nuovo"]
                    continue
                _build.update(running=False, ended=datetime.datetime.now().isoformat(timespec="seconds"))
                return

    threading.Thread(target=run, daemon=True, name="catalog-build").start()
    return True


def _prune(idx):
    """Toglie dal catalogo già scaricato le app delle fonti che non esistono più."""
    known = {s["id"] for s in sources()}
    apps = []
    for a in idx.get("apps", []):
        srcs = [x for x in a.get("sources", []) if x.get("src") in known]
        if srcs:
            apps.append({**a, "sources": srcs})
    idx["apps"] = apps
    idx["status"] = {k: v for k, v in (idx.get("status") or {}).items() if k in known}
    return idx


def index():
    global _index
    with _lock:
        if _index is None:
            _index = _prune(load_json(INDEX, {"apps": [], "status": {}, "built": None}))
        return _index


def ensure():
    """Al primo avvio (o se manca) il catalogo si costruisce da solo."""
    if not index().get("built"):
        start_build()


# --- API per l'interfaccia --------------------------------------------------------------------------

def sources_status():
    idx = index()
    st = idx.get("status") or {}
    with _lock:
        b = dict(_build)
    return {
        "sources": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "color": s.get("color"),
                     "enabled": s["enabled"], "optional": bool(s.get("optional")), "custom": bool(s.get("custom")),
                     "url": s.get("url") or ", ".join(s.get("urls") or []), **(st.get(s["id"]) or {})}
                    for s in sources()],
        "built": idx.get("built"), "building": b["running"] or b["pending"], "log": b["log"][-30:],
        "schedule": schedule(),
    }


def list_apps():
    idx = index()
    light = []
    for a in idx.get("apps", []):
        light.append({k: a.get(k) for k in ("id", "title", "tagline", "icon", "category", "version", "developer")}
                     | {"sources": [s["src"] for s in a["sources"]]})
    cats = sorted({a["category"] for a in light}, key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99)
    featured = [f for f in FEATURED if any(a["id"] == f for a in light)][:3]
    return {"apps": light, "categories": cats, "featured": featured, "built": idx.get("built"),
            **{k: v for k, v in sources_status().items() if k in ("sources", "building")}}


def get_app(app_id):
    for a in index().get("apps", []):
        if a["id"] == app_id:
            return a
    raise ApiError("App non trovata nel catalogo", 404)


def compose_text(app_id, src=None):
    a = get_app(app_id)
    entry = next((s for s in a["sources"] if s["src"] == src), None) if src else a["sources"][0]
    if not entry:
        raise ApiError("Questa fonte non ha l'app richiesta", 404)
    path = os.path.join(DIR, "apps", entry["src"], entry["file"])
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), entry
    except FileNotFoundError:
        raise ApiError("File dell'app non trovato: aggiorna il catalogo", 404)


def find_by_image(image):
    """App del catalogo che usa questa immagine (per suggerire la versione dello store)."""
    from .registry import parse_ref
    try:
        _, repo, _, _ = parse_ref(image)
    except ApiError:
        return []
    base = repo.split("/")[-1]
    res = []
    for a in index().get("apps", []):
        for s in a["sources"]:
            try:
                _, r2, _, _ = parse_ref(s["image"])
            except ApiError:
                continue
            if r2 == repo or (a["id"] == slug(base)):
                res.append({"id": a["id"], "title": a["title"], "icon": a.get("icon"),
                            "sources": [x["src"] for x in a["sources"]]})
                break
    return res[:3]
