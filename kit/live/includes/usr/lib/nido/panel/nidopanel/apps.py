"""App (contenitori Docker): installazione, avvio/arresto, log, limiti, aggiornamenti.

Ogni app è un progetto Docker Compose in /var/lib/nido/apps/<nome>/:
  docker-compose.yml   il compose dell'app (dallo store, da Docker Hub o scritto a mano)
  nido.override.yml    quello che aggiunge il NAS: limiti di CPU e RAM, versione bloccata
  .env                 PUID, PGID, TZ, AppID (lette dal compose come variabili)
  app.json             nome, icona, fonte, indirizzo web, impostazioni, storico
  versions/<data>/     copia della configurazione prima di ogni aggiornamento
I dati delle app stanno in /DATA/AppData/<nome>/.

Aggiornamento: copia della configurazione -> scarica le immagini nuove -> riavvia ->
controlla che l'app giri (e risponda, se ha un'interfaccia web). Se non riparte,
rimette le immagini e la configurazione di prima, da solo.
"""
import datetime
import json
import os
import pwd
import re
import shutil
import time
import urllib.request

import yaml

from . import catalog, jobs, registry
from .util import ApiError, ETC, STATE, load_json, read_file, run, run_rc, save_json, user_agent, write_file

APPS_DIR = os.path.join(STATE, "apps")
DATA_ROOT = os.environ.get("NIDO_APPDATA", "/DATA/AppData")
SETTINGS = os.path.join(ETC, "apps.json")
UPDATES = os.path.join(STATE, "apps-updates.json")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
RESERVED_PORTS = {22, 53, 67, 68, 80, 111, 137, 138, 139, 443, 445, 631, 2049, 3702, 5353, 8090}
KEEP_VERSIONS = 5


# --- impostazioni ------------------------------------------------------------------------------------

def settings():
    s = load_json(SETTINGS, {})
    s.setdefault("autoupdate", True)
    s.setdefault("time", "03:30")
    s.setdefault("rollback", True)
    s.setdefault("check_daily", True)
    return s


def save_settings(body):
    s = settings()
    if "autoupdate" in body:
        s["autoupdate"] = bool(body["autoupdate"])
    if "rollback" in body:
        s["rollback"] = bool(body["rollback"])
    if "time" in body:
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(body["time"])):
            raise ApiError("Orario non valido (HH:MM)")
        s["time"] = body["time"]
    save_json(SETTINGS, s, 0o644)
    _write_timer(s["time"])
    return s


def _write_timer(hhmm):
    """Orario dell'aggiornamento notturno (unità nido-apps-update.timer)."""
    d = "/etc/systemd/system/nido-apps-update.timer.d"
    try:
        write_file(os.path.join(d, "orario.conf"), f"[Timer]\nOnCalendar=\nOnCalendar=*-*-* {hhmm}:00\n")
        run_rc(["systemctl", "daemon-reload"], timeout=30)
        run_rc(["systemctl", "restart", "nido-apps-update.timer"], timeout=30)
    except OSError:
        pass


# --- utente, fuso orario, porte ---------------------------------------------------------------------------

def nas_user():
    """Utente proprietario dei file delle app: il primo utente "vero" del NAS (uid >= 1000)."""
    for p in sorted(pwd.getpwall(), key=lambda p: p.pw_uid):
        if 1000 <= p.pw_uid < 60000 and not p.pw_shell.endswith(("nologin", "false")):
            return {"name": p.pw_name, "uid": p.pw_uid, "gid": p.pw_gid}
    return {"name": "admin", "uid": 1000, "gid": 1000}


def timezone():
    tz = read_file("/etc/timezone").strip()
    if not tz:
        link = os.path.realpath("/etc/localtime")
        tz = link.split("zoneinfo/", 1)[1] if "zoneinfo/" in link else "Europe/Rome"
    return tz


def _listening_ports():
    ports = set()
    for f in ("/proc/net/tcp", "/proc/net/tcp6", "/proc/net/udp", "/proc/net/udp6"):
        for line in read_file(f).splitlines()[1:]:
            parts = line.split()
            if len(parts) > 3:
                st = parts[3]
                if f.endswith(("tcp", "tcp6")) and st != "0A":
                    continue
                try:
                    ports.add(int(parts[1].rsplit(":", 1)[1], 16))
                except (ValueError, IndexError):
                    pass
    return ports


def used_ports(exclude_app=None):
    used = set(RESERVED_PORTS) | _listening_ports()
    for c in containers():
        if exclude_app and c["project"] == exclude_app:
            continue
        for p in c["ports"]:
            used.add(p)
    for name in _app_names():
        if name == exclude_app:
            continue
        try:
            data = yaml.safe_load(read_file(os.path.join(APPS_DIR, name, "docker-compose.yml"))) or {}
            env = _env_values(name)
            for svc in (data.get("services") or {}).values():
                for p in _norm_ports(svc.get("ports"), env):
                    if str(p.get("published", "")).isdigit():
                        used.add(int(p["published"]))
        except (yaml.YAMLError, AttributeError):
            pass
    return used


def free_port(wanted, used):
    wanted = int(wanted) if str(wanted).isdigit() else 8080
    if wanted >= 1024 and wanted not in used:
        return wanted
    start = wanted if wanted >= 1024 else 8000 + wanted
    for p in list(range(start + 1, start + 200)) + list(range(20000, 40000)):
        if p not in used and p < 65536:
            return p
    raise ApiError("Nessuna porta libera trovata")


# --- docker ------------------------------------------------------------------------------------------

def docker_ok():
    rc, _, _ = run_rc(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    return rc == 0


def containers():
    """Tutti i contenitori con progetto compose, stato, porte pubblicate e immagine."""
    rc, out, _ = run_rc(["docker", "ps", "-aq", "--no-trunc"], timeout=20)
    ids = out.split()
    if rc != 0 or not ids:
        return []
    rc, out, _ = run_rc(["docker", "inspect"] + ids, timeout=30)
    try:
        data = json.loads(out or "[]")
    except ValueError:
        return []
    res = []
    for c in data:
        labels = (c.get("Config") or {}).get("Labels") or {}
        st = c.get("State") or {}
        ports = set()
        for binds in ((c.get("HostConfig") or {}).get("PortBindings") or {}).values():
            for b in binds or []:
                if str(b.get("HostPort", "")).isdigit():
                    ports.add(int(b["HostPort"]))
        res.append({
            "id": c["Id"][:12], "name": c.get("Name", "").lstrip("/"),
            "project": labels.get("com.docker.compose.project") or "",
            "service": labels.get("com.docker.compose.service") or "",
            "image": (c.get("Config") or {}).get("Image") or "", "image_id": c.get("Image") or "",
            "state": st.get("Status") or "unknown", "running": bool(st.get("Running")),
            "health": (st.get("Health") or {}).get("Status"), "restarts": c.get("RestartCount") or 0,
            "started": st.get("StartedAt"), "exit_code": st.get("ExitCode"),
            "ports": sorted(ports), "network_mode": (c.get("HostConfig") or {}).get("NetworkMode"),
            "version": labels.get("org.opencontainers.image.version") or "",
        })
    return res


def _dir(name):
    if not NAME_RE.match(name or ""):
        raise ApiError("Nome dell'app non valido")
    return os.path.join(APPS_DIR, name)


def _app_names():
    try:
        return sorted(n for n in os.listdir(APPS_DIR)
                      if NAME_RE.match(n) and os.path.isfile(os.path.join(APPS_DIR, n, "docker-compose.yml")))
    except FileNotFoundError:
        return []


def _meta(name):
    return load_json(os.path.join(_dir(name), "app.json"), {})


def _save_meta(name, meta):
    save_json(os.path.join(_dir(name), "app.json"), meta, 0o644)


def _compose_cmd(name, *args):
    d = _dir(name)
    cmd = ["docker", "compose", "-p", name, "--project-directory", d, "-f", os.path.join(d, "docker-compose.yml")]
    if os.path.exists(os.path.join(d, "nido.override.yml")):
        cmd += ["-f", os.path.join(d, "nido.override.yml")]
    return cmd + list(args)


def compose(name, *args, timeout=600, job=None):
    cmd = _compose_cmd(name, *args)
    rc, out, err = run_rc(cmd, timeout=timeout)
    text = (out + "\n" + err).strip()
    if job and text:
        # Le righe di avanzamento di compose sono tante: tengo le più utili
        keep = [ln for ln in text.splitlines() if not re.search(r"(Downloading|Extracting|Waiting)\s", ln)]
        job.log("\n".join(keep[-40:]))
    if rc != 0:
        last = [ln for ln in text.splitlines() if ln.strip()]
        raise ApiError("docker compose: " + (last[-1] if last else f"errore {rc}"), 500)
    return text


# --- lettura e normalizzazione del compose ---------------------------------------------------------------

VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def interpolate(value, env):
    if not isinstance(value, str):
        return value

    def rep(m):
        if m.group(0).startswith("$$"):
            return m.group(0)
        k = m.group(1) or m.group(3)
        return str(env.get(k, m.group(2) if m.group(2) is not None else ""))
    return VAR_RE.sub(rep, value.replace("$$", "\x00")).replace("\x00", "$")


def _env_values(name):
    env = {}
    for line in read_file(os.path.join(APPS_DIR, name, ".env")).splitlines():
        k, _, v = line.partition("=")
        if k and not k.startswith("#"):
            env[k.strip()] = v.strip().strip('"')
    return env


def _norm_ports(ports, env):
    res = []
    for p in ports or []:
        if isinstance(p, dict):
            res.append({"published": str(interpolate(str(p.get("published") or ""), env)),
                        "target": str(interpolate(str(p.get("target") or ""), env)),
                        "protocol": p.get("protocol") or "tcp", "host_ip": p.get("host_ip") or ""})
            continue
        s = interpolate(str(p), env)
        proto = "tcp"
        if "/" in s:
            s, proto = s.rsplit("/", 1)
        parts = s.split(":")
        host_ip = ""
        if len(parts) == 3:
            host_ip, pub, tgt = parts
        elif len(parts) == 2:
            pub, tgt = parts
        else:
            pub, tgt = "", parts[0]
        res.append({"published": pub, "target": tgt, "protocol": proto, "host_ip": host_ip})
    return res


def _norm_volumes(vols, env):
    res = []
    for v in vols or []:
        if isinstance(v, dict):
            res.append({"type": v.get("type") or "bind", "source": interpolate(str(v.get("source") or ""), env),
                        "target": str(v.get("target") or ""), "read_only": bool(v.get("read_only")),
                        "extra": {k: x for k, x in v.items() if k not in ("type", "source", "target", "read_only")}})
            continue
        s = interpolate(str(v), env)
        parts = s.split(":")
        mode = ""
        if len(parts) >= 3:
            src, tgt, mode = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            src, tgt = parts
        else:
            src, tgt = "", parts[0]
        kind = "bind" if src.startswith(("/", ".", "~")) else ("volume" if src else "anon")
        res.append({"type": kind, "source": src, "target": tgt, "read_only": "ro" in mode.split(","), "extra": {}})
    return res


def _norm_env(environment, env):
    out = {}
    if isinstance(environment, dict):
        for k, v in environment.items():
            out[str(k)] = "" if v is None else interpolate(str(v), env)
    elif isinstance(environment, list):
        for item in environment:
            k, _, v = str(item).partition("=")
            out[k] = interpolate(v, env)
    return out


def _dump(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


def _load_yaml(text):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ApiError(f"Compose non valido: {e}".splitlines()[0])
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict) or not data["services"]:
        raise ApiError("Compose non valido: manca la sezione services")
    for sname, svc in data["services"].items():
        if not isinstance(svc, dict) or not (svc.get("image") or svc.get("build")):
            raise ApiError(f"Il servizio {sname} non ha un'immagine")
        if svc.get("build"):
            raise ApiError("Le app che si costruiscono dai sorgenti (build:) non sono supportate")
    return data


# --- preparazione dell'installazione ----------------------------------------------------------------------

def _unique_name(base):
    base = re.sub(r"[^a-z0-9_-]+", "-", (base or "app").lower()).strip("-_")[:34] or "app"
    names = set(_app_names()) | {c["project"] for c in containers()} | {c["name"] for c in containers()}
    name, k = base, 2
    while name in names or os.path.exists(os.path.join(APPS_DIR, name)):
        name, k = f"{base}-{k}", k + 1
    return name


def _default_limits():
    from .metrics import memory
    total = memory()["total"] or 4 * 1024 ** 3
    mem_gb = max(1, min(2, int(total / 1024 ** 3 / 2)))
    return {"cpus": float(min(2, os.cpu_count() or 1)), "memory": f"{mem_gb}g"}


def _base_env(name):
    u = nas_user()
    return {"AppID": name, "PUID": str(u["uid"]), "PGID": str(u["gid"]), "TZ": timezone(),
            "DATA_ROOT": "/DATA", "APP_DATA": f"{DATA_ROOT}/{name}"}


def _form_from(data, env):
    """Vista modificabile del compose: porte, cartelle e variabili di ogni servizio."""
    x = data.get("x-casaos") or {}
    main = x.get("main") if x.get("main") in data["services"] else next(iter(data["services"]))
    svcs = []
    for sname, svc in data["services"].items():
        svcs.append({
            "name": sname, "main": sname == main, "image": interpolate(str(svc.get("image")), env),
            "ports": _norm_ports(svc.get("ports"), env),
            "volumes": [v for v in _norm_volumes(svc.get("volumes"), env)],
            "env": _norm_env(svc.get("environment"), env),
            "network_mode": svc.get("network_mode") or "",
            "privileged": bool(svc.get("privileged")),
            "devices": [str(d) for d in svc.get("devices") or []],
        })
    return main, svcs


def _fix_ports_and_paths(data, env, name):
    """Porte libere scelte da sole. La stessa porta può servire in TCP e in UDP
    (es. Syncthing 22000/tcp e 22000/udp): l'assegnazione tiene conto del protocollo."""
    used = used_ports()
    alloc = set()           # (porta, protocollo) già date in questo compose
    moved = {}              # porta originale -> porta nuova (per lo stesso numero in TCP e UDP)
    main = (data.get("x-casaos") or {}).get("main")
    port_map = interpolate(str((data.get("x-casaos") or {}).get("port_map") or ""), env)
    new_web = None
    for sname, svc in data["services"].items():
        if svc.get("network_mode") == "host":
            continue
        ports = _norm_ports(svc.get("ports"), env)
        for p in ports:
            if not str(p["published"]).isdigit():
                p["published"] = p["target"] if str(p["target"]).isdigit() else ""
            if not str(p["published"]).isdigit():
                continue
            old = int(p["published"])
            proto = p.get("protocol") or "tcp"
            if old in moved and (moved[old], proto) not in alloc:
                cand = moved[old]          # stesso numero già scelto per l'altro protocollo
            else:
                cand = free_port(old, used | {c for c, _ in alloc})
            alloc.add((cand, proto))
            moved[old] = cand
            if port_map == str(old) and (sname == main or new_web is None):
                new_web = cand
            p["published"] = str(cand)
        if ports:
            svc["ports"] = [{k: (int(v) if k in ("published", "target") and str(v).isdigit() else v)
                             for k, v in p.items() if v != ""} for p in ports]
    if new_web:
        data.setdefault("x-casaos", {})["port_map"] = str(new_web)
    return data


def _web_port_guess(ports):
    pref = [80, 8080, 8000, 3000, 5000, 8096, 8123, 8443, 443, 9000, 8081, 8888]
    for want in pref:
        for p in ports:
            if p["target"] == str(want) and p["published"]:
                return p["published"]
    for p in ports:
        if p["protocol"] == "tcp" and p["published"]:
            return p["published"]
    return ""


def prepare_catalog(app_id, src=None):
    text, entry = catalog.compose_text(app_id, src)
    meta = catalog.get_app(app_id)
    data = _load_yaml(text)
    name = _unique_name(data.get("name") or app_id)
    env = _base_env(name)
    data["name"] = name
    data = _fix_ports_and_paths(data, env, name)
    main, svcs = _form_from(data, env)
    x = data.get("x-casaos") or {}
    return {
        "name": name, "title": meta["title"], "icon": meta.get("icon"), "source": entry["src"],
        "catalog_id": app_id, "sources": [s["src"] for s in meta["sources"]],
        "tagline": meta.get("tagline"), "tips": meta.get("tips"),
        "web": {"port": interpolate(str(x.get("port_map") or ""), env) or _web_port_guess(next(s for s in svcs if s["main"])["ports"]),
                "scheme": x.get("scheme") or "http", "index": x.get("index") or "/"},
        "main": main, "services": svcs, "compose": _dump(data), "env": env, "limits": _default_limits(),
        "user": nas_user(), "timezone": env["TZ"],
    }


def prepare_image(image):
    """Prepara un'app da un'immagine di Docker Hub (o di un altro registro), leggendo
    porte, cartelle e variabili dal registro senza scaricare l'immagine."""
    ref = image.strip()
    reg, repo, tag, digest = registry.parse_ref(ref)
    cfg = registry.image_config(ref)
    base = repo.split("/")[-1]
    name = _unique_name(base)
    env = _base_env(name)
    used = used_ports()
    ports = []
    for p in cfg["ports"]:
        pub = free_port(p["port"], used)
        used.add(pub)
        ports.append({"published": str(pub), "target": str(p["port"]), "protocol": p["protocol"], "host_ip": ""})
    vols = []
    for v in cfg["volumes"]:
        leaf = re.sub(r"[^A-Za-z0-9_.-]+", "-", v.strip("/")) or "data"
        vols.append({"type": "bind", "source": f"{DATA_ROOT}/{name}/{leaf}", "target": v, "read_only": False, "extra": {}})
    envs = {}
    lsio = "linuxserver" in repo or reg == "lscr.io"
    if lsio or "PUID" in cfg["env"]:
        envs["PUID"], envs["PGID"] = env["PUID"], env["PGID"]
    envs["TZ"] = env["TZ"]
    for k, v in cfg["env"].items():
        if k in ("PATH", "HOME", "LANG", "LANGUAGE", "TERM", "PS1") or k.startswith(("S6_", "LSIO_", "VIRTUAL_ENV")):
            continue
        if k in ("PUID", "PGID", "TZ"):
            continue
        envs[k] = v
    full = ref if digest or ":" in ref.rsplit("/", 1)[-1] else f"{ref}:{tag}"
    svc = {"image": full, "restart": "unless-stopped"}
    if ports:
        svc["ports"] = [{"target": int(p["target"]), "published": int(p["published"]), "protocol": p["protocol"]} for p in ports]
    if vols:
        svc["volumes"] = [{"type": "bind", "source": v["source"], "target": v["target"]} for v in vols]
    if envs:
        svc["environment"] = envs
    web = _web_port_guess(ports)
    data = {"name": name, "services": {name: svc},
            "x-casaos": {"main": name, "title": {"en_us": base}, "port_map": web, "scheme": "http", "index": "/"}}
    main, svcs = _form_from(data, env)
    return {
        "name": name, "title": base, "icon": "", "source": "hub", "catalog_id": None, "image": full,
        "web": {"port": web, "scheme": "http", "index": "/"}, "main": main, "services": svcs,
        "compose": _dump(data), "env": env, "limits": _default_limits(), "user": nas_user(),
        "timezone": env["TZ"], "size": cfg["size"], "labels": {k: v for k, v in cfg["labels"].items()
                                                               if k.startswith("org.opencontainers.image.")},
        "store_match": catalog.find_by_image(ref),
    }


# --- installazione -------------------------------------------------------------------------------------

def _apply_form(data, services, env):
    """Rimette nel compose porte, cartelle e variabili modificate nel modulo."""
    for f in services or []:
        svc = data["services"].get(f.get("name"))
        if svc is None:
            continue
        if svc.get("network_mode") != "host":
            ports = []
            for p in f.get("ports") or []:
                pub, tgt = str(p.get("published") or "").strip(), str(p.get("target") or "").strip()
                if not tgt.isdigit():
                    continue
                if pub and not pub.isdigit():
                    raise ApiError(f"Porta non valida: {pub}")
                item = {"target": int(tgt), "protocol": p.get("protocol") or "tcp"}
                if pub:
                    item["published"] = int(pub)
                if p.get("host_ip"):
                    item["host_ip"] = p["host_ip"]
                ports.append(item)
            if ports:
                svc["ports"] = ports
            else:
                svc.pop("ports", None)
        vols = []
        for v in f.get("volumes") or []:
            tgt = str(v.get("target") or "").strip()
            if not tgt.startswith("/"):
                continue
            src = str(v.get("source") or "").strip()
            if v.get("type") == "anon" or not src:
                vols.append(tgt)
                continue
            if v.get("type") == "bind" and not src.startswith("/"):
                raise ApiError(f"La cartella {src} deve essere un percorso completo (es. /DATA/...)")
            item = {"type": v.get("type") or "bind", "source": src, "target": tgt}
            if v.get("read_only"):
                item["read_only"] = True
            item.update(v.get("extra") or {})
            vols.append(item)
        if vols:
            svc["volumes"] = vols
        else:
            svc.pop("volumes", None)
        envs = {str(k).strip(): str(v) for k, v in (f.get("env") or {}).items() if str(k).strip()}
        for k in envs:
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_.-]*$", k):
                raise ApiError(f"Nome di variabile non valido: {k}")
        if envs:
            svc["environment"] = {k: v.replace("$", "$$") for k, v in envs.items()}
        else:
            svc.pop("environment", None)
    return data


def render(body):
    """Compose risultante dai campi del modulo (per passare dalla modalità semplice/avanzata a Compose)."""
    name = (body.get("name") or "app").strip().lower()
    env = _base_env(name)
    data = _apply_form(_load_yaml(body.get("compose") or ""), body.get("services"), env)
    data["name"] = name
    if (body.get("web") or {}).get("port") is not None:
        data.setdefault("x-casaos", {})["port_map"] = str(body["web"]["port"] or "")
    return {"compose": _dump(data)}


def _check_conflicts(data, env, name):
    used = used_ports(exclude_app=name)
    seen = set()
    for sname, svc in data["services"].items():
        for p in _norm_ports(svc.get("ports"), env):
            if not str(p["published"]).isdigit():
                continue
            n = int(p["published"])
            key = (n, p["protocol"])
            if (n in used and n not in {k for k, _ in seen}) or key in seen:
                raise ApiError(f"La porta {n} è già usata da un'altra app o servizio: scegline un'altra")
            seen.add(key)


def _limits_override(data, limits, pins=None):
    over = {"services": {}}
    for sname in data["services"]:
        s = {}
        if limits:
            if limits.get("cpus"):
                s["cpus"] = float(limits["cpus"])
            if limits.get("memory"):
                s["mem_limit"] = str(limits["memory"])
        if pins and sname in pins:
            s["image"] = pins[sname]
        if s:
            over["services"][sname] = s
    return over if over["services"] else {"services": {}}


def _check_limits(limits):
    if not limits:
        return {}
    out = {}
    if limits.get("cpus") not in (None, "", 0, "0"):
        try:
            c = float(limits["cpus"])
        except (TypeError, ValueError):
            raise ApiError("Limite CPU non valido")
        if not 0.1 <= c <= (os.cpu_count() or 1):
            raise ApiError(f"Limite CPU tra 0,1 e {os.cpu_count()}")
        out["cpus"] = c
    if limits.get("memory") not in (None, "", "0"):
        m = str(limits["memory"]).strip().lower().replace(" ", "")
        if not re.match(r"^\d+(\.\d+)?[mg]$", m):
            raise ApiError("Limite RAM non valido: es. 512m o 2g")
        out["memory"] = m
    return out


def _mkdirs(data, env):
    u = nas_user()
    for svc in data["services"].values():
        for v in _norm_volumes(svc.get("volumes"), env):
            src = v["source"]
            if v["type"] != "bind" or not src.startswith("/"):
                continue
            if os.path.splitext(src)[1] and not os.path.exists(src):
                continue      # sembra un file (es. config.yml): lo lascio creare all'app
            if not os.path.exists(src):
                os.makedirs(src, exist_ok=True)
                if src.startswith(DATA_ROOT + "/"):
                    # Cartelle nuove dell'app: proprietario l'utente del NAS
                    p = DATA_ROOT
                    for part in os.path.relpath(src, DATA_ROOT).split("/"):
                        p = os.path.join(p, part)
                        try:
                            os.chown(p, u["uid"], u["gid"])
                        except OSError:
                            pass


def install(body):
    mode = body.get("mode") or "simple"
    name = (body.get("name") or "").strip().lower()
    if not NAME_RE.match(name):
        raise ApiError("Nome dell'app non valido: lettere minuscole, numeri e trattini")
    if os.path.exists(os.path.join(APPS_DIR, name)) or any(c["project"] == name for c in containers()):
        raise ApiError(f"Esiste già un'app chiamata {name}")
    env = _base_env(name)
    if mode == "compose":
        data = _load_yaml(body.get("compose") or "")
    else:
        data = _load_yaml(body.get("compose") or "")
        data = _apply_form(data, body.get("services"), env)
    data["name"] = name
    x = data.setdefault("x-casaos", {})
    web = body.get("web") or {}
    if web.get("port") is not None:
        x["port_map"] = str(web.get("port") or "")
    for sname, svc in data["services"].items():
        svc.setdefault("restart", "unless-stopped")
        if body.get("autostart") is False:
            svc["restart"] = "no"
    _check_conflicts(data, env, name)
    limits = _check_limits(body.get("limits"))
    title = (body.get("title") or "").strip()[:60] or name
    meta = {
        "name": name, "title": title, "icon": body.get("icon") or "", "source": body.get("source") or "manuale",
        "catalog_id": body.get("catalog_id"), "web": {"port": x.get("port_map") or "", "scheme": x.get("scheme") or "http",
                                                         "index": x.get("index") or "/"},
        "main": x.get("main") if x.get("main") in data["services"] else next(iter(data["services"])),
        "installed": int(time.time()), "updated": None, "autoupdate": body.get("autoupdate", True) is not False,
        "limits": limits, "history": [],
    }
    d = _dir(name)

    def work(job):
        job.set(5, "Preparo la configurazione")
        os.makedirs(os.path.join(d, "versions"), exist_ok=True)
        write_file(os.path.join(d, "docker-compose.yml"), _dump(data))
        write_file(os.path.join(d, "nido.override.yml"), _dump(_limits_override(data, limits)))
        write_file(os.path.join(d, ".env"), "".join(f"{k}={v}\n" for k, v in env.items()))
        _save_meta(name, meta)
        _mkdirs(data, env)
        try:
            job.set(15, "Controllo la configurazione")
            compose(name, "config", "--quiet", timeout=60)
            job.set(25, "Scarico le immagini (può richiedere qualche minuto)")
            compose(name, "pull", "--quiet", "--ignore-buildable", timeout=3600, job=job)
            job.set(80, "Avvio l'app")
            compose(name, "up", "-d", "--remove-orphans", timeout=600, job=job)
        except ApiError:
            job.log("Installazione non riuscita: tolgo quello che era stato creato")
            run_rc(_compose_cmd(name, "down", "--remove-orphans"), timeout=300)
            shutil.rmtree(d, ignore_errors=True)
            raise
        job.set(90, "Controllo che l'app sia partita")
        ok, why = _wait_healthy(name, meta, timeout=60, job=job)
        meta["history"].append({"t": int(time.time()), "event": "installata", "ok": ok,
                                "version": _versions_now(name).get(meta["main"], "")})
        _save_meta(name, meta)
        if not ok:
            job.log(f"Attenzione: {why}")
        return {"name": name, "ok": ok, "warning": None if ok else why}

    job = jobs.start("install", f"Installo {title}", work, target=name)
    return {"job": job.id, "name": name}


# --- modifica dell'installazione ------------------------------------------------------------------------

def prepare_edit(name):
    """Stessa finestra dell'installazione, già compilata con la configurazione attuale dell'app."""
    d = _dir(name)
    if not os.path.isfile(os.path.join(d, "docker-compose.yml")):
        raise ApiError("Si possono modificare solo le app installate da qui", 404)
    meta = _meta(name)
    text = read_file(os.path.join(d, "docker-compose.yml"))
    data = _load_yaml(text)
    env = {**_base_env(name), **_env_values(name)}
    main, svcs = _form_from(data, env)
    autostart = any(str(svc.get("restart") or "") not in ("no", "") for svc in data["services"].values())
    return {
        "edit": True, "name": name, "title": meta.get("title") or name, "icon": meta.get("icon") or "",
        "source": meta.get("source") or "manuale", "catalog_id": meta.get("catalog_id"),
        "sources": [], "tagline": "", "tips": "",
        "web": {"port": str((meta.get("web") or {}).get("port") or ""), "scheme": (meta.get("web") or {}).get("scheme") or "http",
                "index": (meta.get("web") or {}).get("index") or "/"},
        "main": main, "services": svcs, "compose": text, "env": env,
        "limits": meta.get("limits") or {}, "user": nas_user(), "timezone": env.get("TZ") or timezone(),
        "autostart": autostart, "autoupdate": meta.get("autoupdate", True),
        "image": next((s["image"] for s in svcs if s["main"]), ""),
    }


def reconfigure(name, body):
    """Applica le modifiche all'installazione: controllo delle porte, copia della configurazione,
    contenitori ricreati con docker compose up -d e, se l'app non riparte, ritorno da soli alla
    configurazione di prima. I dati in AppData non vengono toccati."""
    d = _dir(name)
    if not os.path.isfile(os.path.join(d, "docker-compose.yml")):
        raise ApiError("App non trovata", 404)
    meta = _meta(name)
    env = {**_base_env(name), **_env_values(name)}
    mode = body.get("mode") or "simple"
    data = _load_yaml(body.get("compose") or "")
    if mode != "compose":
        data = _apply_form(data, body.get("services"), env)
    data["name"] = name
    x = data.setdefault("x-casaos", {})
    web = body.get("web") or {}
    if web.get("port") is not None:
        x["port_map"] = str(web.get("port") or "")
    for svc in data["services"].values():
        if body.get("autostart") is False:
            svc["restart"] = "no"
        elif str(svc.get("restart") or "no") == "no":
            svc["restart"] = "unless-stopped"
    _check_conflicts(data, env, name)
    limits = _check_limits(body.get("limits"))
    new_compose = _dump(data)
    over_old = load_json_yaml(os.path.join(d, "nido.override.yml"))
    pins = {s: v.get("image") for s, v in (over_old.get("services") or {}).items()
            if v.get("image") and s in data["services"]}
    new_meta = dict(meta)
    new_meta.update({
        "title": (body.get("title") or "").strip()[:60] or meta.get("title") or name,
        "web": {"port": x.get("port_map") or "", "scheme": x.get("scheme") or (meta.get("web") or {}).get("scheme") or "http",
                "index": x.get("index") or (meta.get("web") or {}).get("index") or "/"},
        "main": x.get("main") if x.get("main") in data["services"] else (
            meta.get("main") if meta.get("main") in data["services"] else next(iter(data["services"]))),
        "autoupdate": body.get("autoupdate", True) is not False, "limits": limits,
    })
    was_running = _state([c for c in containers() if c["project"] == name]) not in ("ferma", "assente")

    def work(job):
        job.set(5, "Copio la configurazione attuale")
        vd = _snapshot_config(name)
        job.log(f"Copia salvata in {vd}")
        old_images = _service_images(name)
        write_file(os.path.join(d, "docker-compose.yml"), new_compose)
        write_file(os.path.join(d, "nido.override.yml"), _dump(_limits_override(data, limits, pins)))
        _save_meta(name, new_meta)
        _mkdirs(data, env)

        def back(reason):
            job.log(f"Le modifiche non funzionano: {reason}")
            job.set(85, "Torno alla configurazione di prima")
            _restore_config(name, vd)
            _save_meta(name, meta)
            try:
                if was_running:
                    compose(name, "up", "-d", "--pull", "never", "--force-recreate", "--remove-orphans", timeout=600, job=job)
                    ok2, why2 = _wait_healthy(name, meta, timeout=90, job=job)
                else:
                    ok2, why2 = True, ""
            except ApiError as e:
                ok2, why2 = False, e.message
            if ok2:
                raise ApiError(f"Le modifiche non funzionavano ({reason}): l'app è tornata alla configurazione di prima")
            raise ApiError(f"Le modifiche non funzionavano ({reason}) e il ripristino non è completo: {why2}")

        try:
            job.set(15, "Controllo la configurazione")
            compose(name, "config", "--quiet", timeout=60)
        except ApiError as e:
            _restore_config(name, vd)
            _save_meta(name, meta)
            raise ApiError(f"Configurazione non valida, niente è stato cambiato: {e.message}")
        try:
            if _service_images(name) != old_images:
                job.set(25, "Scarico le immagini nuove")
                compose(name, "pull", "--quiet", "--ignore-buildable", timeout=3600, job=job)
            job.set(60, "Ricreo i contenitori con le modifiche")
            compose(name, "up", "-d", "--remove-orphans", timeout=600, job=job)
            if body.get("autostart") is False and not was_running:
                compose(name, "stop", timeout=300, job=job)
                ok, why = True, ""
            else:
                job.set(75, "Controllo che l'app riparta")
                ok, why = _wait_healthy(name, new_meta, timeout=120, job=job)
        except ApiError as e:
            ok, why = False, e.message
        if not ok:
            back(why)
        m2 = _meta(name)
        m2.setdefault("history", []).append({"t": int(time.time()), "event": "modificata", "ok": True})
        m2["history"] = m2["history"][-30:]
        _save_meta(name, m2)
        job.log("Modifiche applicate")
        return {"name": name, "ok": True}

    job = jobs.start("reconfigure", f"Modifico {new_meta['title']}", work, target=name)
    return {"job": job.id, "name": name}


# --- stato delle app --------------------------------------------------------------------------------

def _versions_now(name):
    """Versione in uso per ogni servizio (etichetta OCI o tag dell'immagine)."""
    res = {}
    for c in containers():
        if c["project"] == name:
            tag = c["image"].rsplit(":", 1)[1] if ":" in c["image"].rsplit("/", 1)[-1] else "latest"
            res[c["service"]] = c["version"] or tag
    return res


def _state(cs):
    if not cs:
        return "assente"
    running = sum(1 for c in cs if c["running"])
    if any(c["state"] == "restarting" for c in cs):
        return "riavvio"
    if running == len(cs):
        return "attiva"
    if running == 0:
        return "ferma"
    return "parziale"


def list_apps():
    cs = containers()
    upd = load_json(UPDATES, {}).get("apps", {})
    out = []
    names = _app_names()
    for name in names:
        meta = _meta(name)
        mine = [c for c in cs if c["project"] == name]
        main = next((c for c in mine if c["service"] == meta.get("main")), mine[0] if mine else None)
        u = upd.get(name) or {}
        out.append({
            "name": name, "title": meta.get("title") or name, "icon": meta.get("icon") or "",
            "source": meta.get("source"), "managed": True, "state": _state(mine),
            "health": main["health"] if main else None,
            "web": meta.get("web") or {}, "image": main["image"] if main else "",
            "version": (main["version"] or (main["image"].rsplit(":", 1)[1] if main and ":" in main["image"].rsplit("/", 1)[-1] else "latest")) if main else "",
            "containers": [{"name": c["name"], "service": c["service"], "state": c["state"], "health": c["health"]} for c in mine],
            "limits": meta.get("limits") or {}, "autoupdate": meta.get("autoupdate", True),
            "update": u if u.get("available") else None, "last_update": meta.get("last_update"),
            "busy": jobs.running_for(name),
        })
    # Contenitori avviati fuori dal NAS (a mano o con un altro strumento)
    others = {}
    for c in cs:
        key = c["project"] or c["name"]
        if key in names:
            continue
        others.setdefault(key, []).append(c)
    for key, group in sorted(others.items()):
        main = group[0]
        out.append({
            "name": key, "title": key, "icon": "", "source": "esterna", "managed": False,
            "state": _state(group), "health": main["health"], "image": main["image"],
            "version": main["version"] or (main["image"].rsplit(":", 1)[1] if ":" in main["image"].rsplit("/", 1)[-1] else "latest"),
            "web": {"port": str(main["ports"][0]) if main["ports"] else "", "scheme": "http", "index": "/"},
            "containers": [{"name": c["name"], "service": c["service"] or c["name"], "state": c["state"], "health": c["health"]} for c in group],
            "limits": {}, "autoupdate": False, "update": None, "busy": False,
        })
    checked = load_json(UPDATES, {}).get("checked")
    return {"apps": out, "settings": settings(), "checked": checked, "docker": bool(cs) or docker_ok(),
            "jobs": jobs.active()}


def _external(name):
    return [c for c in containers() if (c["project"] or c["name"]) == name]


def action(name, what):
    if what not in ("start", "stop", "restart"):
        raise ApiError("Azione non valida")
    if name in _app_names():
        if jobs.running_for(name):
            raise ApiError("C'è un'operazione in corso su questa app", 409)
        if what == "start":
            compose(name, "up", "-d", "--pull", "never", timeout=300)
        else:
            compose(name, what, timeout=300)
    else:
        group = _external(name)
        if not group:
            raise ApiError("App non trovata", 404)
        run(["docker", what] + [c["id"] for c in group], timeout=300)
    return {"ok": True}


def logs(name, tail=300):
    tail = max(10, min(int(tail or 300), 5000))
    if name in _app_names():
        rc, out, err = run_rc(_compose_cmd(name, "logs", "--no-color", "--timestamps", "--tail", str(tail)), timeout=60)
        return {"log": (out + err)[-400000:]}
    group = _external(name)
    if not group:
        raise ApiError("App non trovata", 404)
    texts = []
    for c in group:
        rc, out, err = run_rc(["docker", "logs", "--timestamps", "--tail", str(tail), c["id"]], timeout=60)
        texts.append(f"=== {c['name']} ===\n{out}{err}")
    return {"log": "\n".join(texts)[-400000:]}


def set_app(name, body):
    meta = _meta(name)
    if not meta:
        raise ApiError("App non trovata", 404)
    restart = False
    if "autoupdate" in body:
        meta["autoupdate"] = bool(body["autoupdate"])
    if "title" in body and str(body["title"]).strip():
        meta["title"] = str(body["title"]).strip()[:60]
    if "limits" in body:
        meta["limits"] = _check_limits(body["limits"])
        data = _load_yaml(read_file(os.path.join(_dir(name), "docker-compose.yml")))
        over = load_json_yaml(os.path.join(_dir(name), "nido.override.yml"))
        pins = {s: v.get("image") for s, v in (over.get("services") or {}).items() if v.get("image")}
        write_file(os.path.join(_dir(name), "nido.override.yml"), _dump(_limits_override(data, meta["limits"], pins)))
        restart = True
    _save_meta(name, meta)
    if restart and _state([c for c in containers() if c["project"] == name]) != "ferma":
        compose(name, "up", "-d", "--pull", "never", timeout=300)
    return {"ok": True, "app": meta}


def load_json_yaml(path):
    try:
        return yaml.safe_load(read_file(path)) or {}
    except yaml.YAMLError:
        return {}


def get_compose(name):
    d = _dir(name)
    if not os.path.isfile(os.path.join(d, "docker-compose.yml")):
        raise ApiError("App non trovata", 404)
    return {"compose": read_file(os.path.join(d, "docker-compose.yml")), "meta": _meta(name)}


def remove(name, delete_data=False):
    d = _dir(name)
    if not os.path.isdir(d):
        raise ApiError("App non trovata", 404)

    def work(job):
        job.set(20, "Fermo e tolgo i contenitori")
        rc, out, err = run_rc(_compose_cmd(name, "down", "--remove-orphans"), timeout=300)
        job.log((out + err).strip()[-2000:])
        if delete_data:
            target = os.path.join(DATA_ROOT, name)
            if os.path.realpath(target).startswith(os.path.realpath(DATA_ROOT) + "/") and os.path.isdir(target):
                job.set(60, f"Cancello i dati in {target}")
                shutil.rmtree(target, ignore_errors=True)
        job.set(90, "Tolgo la configurazione")
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True}

    job = jobs.start("remove", f"Disinstallo {_meta(name).get('title') or name}", work, target=name)
    return {"job": job.id}


# --- controllo della salute -----------------------------------------------------------------------

def _http_ok(port, scheme, index):
    url = f"{scheme or 'http'}://127.0.0.1:{port}{index or '/'}"
    try:
        import ssl
        ctx = ssl._create_unverified_context()   # certificati autofirmati delle app: va bene in locale
        req = urllib.request.Request(url, headers={"User-Agent": user_agent("healthcheck")})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:  # noqa: BLE001
        return False


def _last_log(cid, n=3):
    rc, out, err = run_rc(["docker", "logs", "--tail", str(n), cid], timeout=15)
    lines = [ln.strip() for ln in (out + err).splitlines() if ln.strip()]
    return " / ".join(lines[-n:])[:300]


def _wait_healthy(name, meta, timeout=90, job=None):
    """L'app è sana se tutti i contenitori girano da almeno 10 secondi senza riavvii,
    il controllo di salute (se c'è) è "healthy" e l'interfaccia web risponde.
    Un contenitore che si ferma o si riavvia di continuo fa fallire subito il controllo."""
    t0 = time.time()
    first = {c["name"]: c["restarts"] for c in containers() if c["project"] == name}
    stable_since = None
    web = meta.get("web") or {}

    def why(c, text):
        log = _last_log(c["id"])
        return f"{c['name']} {text}" + (f" (ultime righe: {log})" if log else "")

    while time.time() - t0 < timeout:
        cs = [c for c in containers() if c["project"] == name]
        if not cs:
            return False, "nessun contenitore trovato"
        for c in cs:
            if c["health"] == "unhealthy":
                return False, why(c, "risulta non in salute")
            if c["restarts"] - first.get(c["name"], 0) >= 2 or (c["state"] == "restarting" and time.time() - t0 > 20):
                return False, why(c, "si riavvia di continuo")
            if c["state"] in ("exited", "dead") and time.time() - t0 > 8:
                return False, why(c, f"si è fermato (codice {c['exit_code']})")
        bad = [c for c in cs if not c["running"] or c["restarts"] > first.get(c["name"], 0)]
        starting = [c for c in cs if c["health"] == "starting"]
        if not bad and not starting:
            stable_since = stable_since or time.time()
            if time.time() - stable_since >= 10:
                if web.get("port") and str(web["port"]).isdigit():
                    if _http_ok(web["port"], web.get("scheme"), web.get("index")):
                        return True, ""
                    if time.time() - t0 > timeout - 5:
                        return False, f"l'interfaccia web sulla porta {web['port']} non risponde"
                else:
                    return True, ""
        else:
            stable_since = None
        time.sleep(2)
    return False, "l'app non si è avviata in tempo"


# --- aggiornamenti ------------------------------------------------------------------------------------

def _local_digests(image_ref):
    rc, out, _ = run_rc(["docker", "image", "inspect", image_ref, "--format", "{{json .RepoDigests}}|{{.Id}}"], timeout=20)
    if rc != 0:
        return [], None
    dig, _, iid = out.strip().partition("|")
    try:
        lst = json.loads(dig or "[]")
    except ValueError:
        lst = []
    return [x.split("@", 1)[1] for x in lst if "@" in x], iid


def _service_images(name):
    data = _load_yaml(read_file(os.path.join(_dir(name), "docker-compose.yml")))
    over = load_json_yaml(os.path.join(_dir(name), "nido.override.yml"))
    env = _env_values(name)
    res = {}
    for sname, svc in data["services"].items():
        img = ((over.get("services") or {}).get(sname) or {}).get("image") or svc.get("image")
        res[sname] = interpolate(str(img), env)
    return res


def check_app(name):
    """Confronta le immagini in uso con quelle del registro.
    Le versioni che non sono partite (ritorno automatico) vengono saltate."""
    skip = set(_meta(name).get("skip") or [])
    services = {}
    for sname, ref in _service_images(name).items():
        info = {"image": ref}
        try:
            _, _, tag, digest = registry.parse_ref(ref)
            if digest:
                info["kind"] = None
                services[sname] = info
                continue
            local, _ = _local_digests(ref)
            remote = registry.remote_digest(ref)
            info["digest_changed"] = bool(local) and remote not in local and remote not in skip
            info["remote_digest"] = remote
            nt = registry.newer_tags(ref)
            if nt:
                info["patch"] = nt["patch"] if nt["patch"] not in skip else None
                info["latest"] = nt["latest"] if nt["latest"] not in skip else None
            if info.get("patch"):
                info["kind"], info["new"] = "patch", info["patch"]
            elif info["digest_changed"]:
                info["kind"], info["new"] = "digest", tag
            elif info.get("latest"):
                info["kind"], info["new"] = "major", info["latest"]
            else:
                info["kind"] = None
        except ApiError as e:
            info["error"] = e.message
            info["kind"] = None
        services[sname] = info
    kinds = [s["kind"] for s in services.values() if s.get("kind")]
    meta = _meta(name)
    main = services.get(meta.get("main")) or next(iter(services.values()), {})
    available = [k for k in kinds if k in ("patch", "digest")]
    return {"available": bool(available), "kind": "patch" if "patch" in kinds else ("digest" if "digest" in kinds else (kinds[0] if kinds else None)),
            "new": main.get("new") if main.get("kind") in ("patch", "digest") else next((s.get("new") for s in services.values() if s.get("kind") in ("patch", "digest")), None),
            "major": next((s.get("latest") for s in services.values() if s.get("kind") == "major"), None),
            "services": services, "errors": [s["error"] for s in services.values() if s.get("error")]}


def check_all(job=None):
    res = {}
    names = _app_names()
    for k, name in enumerate(names):
        if job:
            job.set(int(100 * k / max(len(names), 1)), f"Controllo {name}")
        try:
            res[name] = check_app(name)
        except ApiError as e:
            res[name] = {"available": False, "errors": [e.message]}
    data = {"checked": int(time.time()), "apps": res}
    save_json(UPDATES, data, 0o644)
    return data


def start_check():
    job = jobs.start("check", "Cerco aggiornamenti delle app", check_all, target="__check__")
    return {"job": job.id}


def _snapshot_config(name):
    d = _dir(name)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    vd = os.path.join(d, "versions", ts)
    os.makedirs(vd, exist_ok=True)
    for f in ("docker-compose.yml", "nido.override.yml", ".env", "app.json"):
        if os.path.exists(os.path.join(d, f)):
            shutil.copy2(os.path.join(d, f), os.path.join(vd, f))
    # Tengo le ultime KEEP_VERSIONS copie
    vers = sorted(os.listdir(os.path.join(d, "versions")))
    for old in vers[:-KEEP_VERSIONS]:
        shutil.rmtree(os.path.join(d, "versions", old), ignore_errors=True)
    return vd


def _restore_config(name, vd):
    d = _dir(name)
    for f in ("docker-compose.yml", "nido.override.yml", ".env"):
        src = os.path.join(vd, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(d, f))


def update_app(name, job, only_patch=False):
    """Aggiorna un'app; se non riparte torna da sola alla versione precedente."""
    meta = _meta(name)
    if not meta:
        raise ApiError("App non trovata", 404)
    title = meta.get("title") or name
    job.set(5, f"Controllo le versioni di {title}")
    info = check_app(name)
    todo = {s: v for s, v in info["services"].items() if v.get("kind") in ("patch", "digest")}
    if only_patch:
        todo = {s: v for s, v in todo.items() if v["kind"] == "patch" or registry.version_tuple(
            registry.parse_ref(v["image"])[2]) is not None}
    if not todo:
        job.log("Nessun aggiornamento da installare")
        _clear_update(name)
        return {"updated": False, "message": "Già aggiornata"}
    before = _versions_now(name)
    job.set(10, "Copio la configurazione dell'app")
    vd = _snapshot_config(name)
    job.log(f"Copia salvata in {vd}")
    old_ids = {}
    images = _service_images(name)
    for sname, ref in images.items():
        _, iid = _local_digests(ref)
        if iid:
            old_ids[sname] = (ref, iid)
            # Etichetta di sicurezza: l'immagine vecchia non viene cancellata e si può rimettere
            run_rc(["docker", "tag", iid, f"nido-rollback/{name}-{sname}:prev"], timeout=30)
    m0 = _meta(name)
    m0["rollback_tagged"] = int(time.time())
    _save_meta(name, m0)
    # Versioni nuove con tag diverso: le scrivo nel compose
    data = _load_yaml(read_file(os.path.join(_dir(name), "docker-compose.yml")))
    changed_tag = False
    for sname, v in todo.items():
        if v["kind"] == "patch" and v.get("patch"):
            old = str(data["services"][sname]["image"])
            base = old.rsplit(":", 1)[0] if ":" in old.rsplit("/", 1)[-1] else old
            data["services"][sname]["image"] = f"{base}:{v['patch']}"
            changed_tag = True
            job.log(f"{sname}: {old} -> {base}:{v['patch']}")
    if changed_tag:
        write_file(os.path.join(_dir(name), "docker-compose.yml"), _dump(data))
    try:
        job.set(25, "Scarico la versione nuova")
        compose(name, "pull", "--quiet", timeout=3600, job=job)
        job.set(70, "Riavvio l'app con la versione nuova")
        compose(name, "up", "-d", "--remove-orphans", timeout=600, job=job)
        job.set(85, "Controllo che l'app funzioni")
        ok, why = _wait_healthy(name, meta, timeout=120, job=job)
    except ApiError as e:
        ok, why = False, e.message
    after = _versions_now(name)
    if ok:
        meta = _meta(name)
        meta["updated"] = int(time.time())
        meta["last_update"] = {"t": int(time.time()), "ok": True, "from": before.get(meta.get("main")), "to": after.get(meta.get("main"))}
        meta.setdefault("history", []).append({"t": int(time.time()), "event": "aggiornata", "ok": True,
                                               "from": before.get(meta.get("main")), "to": after.get(meta.get("main"))})
        meta["history"] = meta["history"][-30:]
        _save_meta(name, meta)
        _clear_update(name)
        if changed_tag:
            for sname, (ref, iid) in old_ids.items():
                if ref != _service_images(name).get(sname):
                    run_rc(["docker", "image", "rm", ref], timeout=60)   # solo l'etichetta: l'immagine resta come nido-rollback
        run_rc(["docker", "image", "prune", "-f"], timeout=120)
        job.log(f"{title} aggiornata")
        _notify(f"{title} aggiornata", f"Versione {before.get(meta.get('main')) or '?'} → {after.get(meta.get('main')) or '?'}",
                "info", f"app-upd-{name}-{after.get(meta.get('main'))}")
        return {"updated": True, "from": before, "to": after}
    # --- ritorno alla versione precedente ---
    job.log(f"La versione nuova non funziona: {why}")
    if not settings().get("rollback", True):
        raise ApiError(f"Aggiornamento non riuscito: {why}")
    job.set(90, "Torno alla versione precedente")
    new_refs = _service_images(name)
    _restore_config(name, vd)
    for sname, (ref, iid) in old_ids.items():
        run_rc(["docker", "tag", iid, ref], timeout=30)
    try:
        compose(name, "up", "-d", "--pull", "never", "--force-recreate", "--remove-orphans", timeout=600, job=job)
        ok2, why2 = _wait_healthy(name, meta, timeout=90, job=job)
    except ApiError as e:
        ok2, why2 = False, e.message
    # Tolgo l'etichetta della versione che non partiva (se aveva un tag diverso)
    for sname, ref in new_refs.items():
        if ref != (old_ids.get(sname) or (None,))[0]:
            run_rc(["docker", "image", "rm", ref], timeout=60)
    meta = _meta(name)
    # La versione che non è partita non viene più proposta (né riprovata di notte)
    tried = [v["patch"] if v["kind"] == "patch" else v.get("remote_digest") for v in todo.values()]
    meta["skip"] = list(dict.fromkeys((meta.get("skip") or []) + [t for t in tried if t]))[-20:]
    meta["last_update"] = {"t": int(time.time()), "ok": False, "rolled_back": ok2, "reason": why,
                           "from": before.get(meta.get("main")), "tried": after.get(meta.get("main"))}
    meta.setdefault("history", []).append({"t": int(time.time()), "event": "ripristinata" if ok2 else "errore",
                                           "ok": False, "reason": why})
    _save_meta(name, meta)
    _notify(f"{title}: aggiornamento non riuscito" + (", tornata alla versione di prima" if ok2 else ""),
            f"La versione nuova non partiva: {why}" + ("" if ok2 else f". Anche il ritorno non è riuscito: {why2}"),
            "warning" if ok2 else "error", f"app-rb-{name}-{int(time.time()) // 3600}")
    if ok2:
        job.log(f"{title} è tornata alla versione {before.get(meta.get('main'), 'precedente')}")
        raise ApiError(f"La versione nuova non partiva ({why}): {title} è tornata alla versione precedente")
    raise ApiError(f"Aggiornamento non riuscito e ripristino non completo: {why2}")


def _clear_update(name):
    data = load_json(UPDATES, {})
    if name in (data.get("apps") or {}):
        data["apps"][name] = {"available": False}
        save_json(UPDATES, data, 0o644)


def start_update(name):
    if name not in _app_names():
        raise ApiError("Si possono aggiornare solo le app installate da qui", 400)
    job = jobs.start("update", f"Aggiorno {_meta(name).get('title') or name}", lambda j: update_app(name, j), target=name)
    return {"job": job.id}


def start_update_all():
    names = [n for n, u in (load_json(UPDATES, {}).get("apps") or {}).items() if u.get("available") and n in _app_names()]
    if not names:
        raise ApiError("Nessun aggiornamento disponibile: premi prima \"Controlla\"")

    def work(job):
        done, failed = [], []
        for k, n in enumerate(names):
            job.set(int(100 * k / len(names)), f"Aggiorno {n} ({k + 1} di {len(names)})")
            try:
                sub = jobs.Inline()
                sub.log = job.log
                update_app(n, sub)
                done.append(n)
            except ApiError as e:
                failed.append({"name": n, "error": e.message})
                job.log(f"{n}: {e.message}")
        return {"updated": done, "failed": failed}

    job = jobs.start("update-all", f"Aggiorno {len(names)} app", work, target="__all__")
    return {"job": job.id, "apps": names}


def nightly():
    """Aggiornamento automatico notturno (solo correzioni), chiamato dal timer."""
    try:
        cleanup_rollback()
    except Exception as e:  # noqa: BLE001
        print(f"pulizia delle immagini di riserva: {e}", flush=True)
    s = settings()
    print(f"=== {datetime.datetime.now():%Y-%m-%d %H:%M} controllo aggiornamenti delle app", flush=True)
    data = check_all()
    if not s.get("autoupdate"):
        print("Aggiornamento automatico spento: solo controllo.", flush=True)
        return
    for name, u in data["apps"].items():
        if not u.get("available") or not _meta(name).get("autoupdate", True):
            continue
        sub = jobs.Inline(name)
        try:
            res = update_app(name, sub, only_patch=True)
            print(f"{name}: {res}", flush=True)
        except ApiError as e:
            print(f"{name}: {e.message}", flush=True)


def _notify(title, message, level, key):
    try:
        from . import notify
        notify.event("apps", title, message, level=level, key=key)
    except Exception as e:  # noqa: BLE001 — una notifica non riuscita non ferma l'aggiornamento
        print(f"notifica: {e}", flush=True)


def cleanup_rollback(days=7):
    """Toglie le immagini di riserva (nido-rollback/...:prev) più vecchie di `days` giorni.
    Restano solo per poter tornare indietro subito dopo un aggiornamento."""
    rc, out, _ = run_rc(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", "nido-rollback/*"], timeout=60)
    if rc != 0:
        return []
    now, removed = int(time.time()), []
    names = _app_names()
    for ref in out.split():
        repo = ref.split(":")[0].split("/", 1)[-1]
        app = next((n for n in sorted(names, key=len, reverse=True) if repo.startswith(n + "-")), None)
        meta = _meta(app) if app else {}
        t = meta.get("rollback_tagged")
        if app and not t:
            meta["rollback_tagged"] = now       # etichetta di prima di questa versione: conto da adesso
            _save_meta(app, meta)
            continue
        if not app or now - int(t) > days * 86400:
            rc2, _, _ = run_rc(["docker", "image", "rm", ref], timeout=120)
            if rc2 == 0:
                removed.append(ref)
                print(f"tolta l'immagine di riserva {ref}", flush=True)
    if removed:
        run_rc(["docker", "image", "prune", "-f"], timeout=300)
    return removed
