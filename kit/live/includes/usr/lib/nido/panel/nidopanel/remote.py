"""Accesso da fuori casa con Tailscale e ZeroTier (Impostazioni → Accesso remoto).

Niente è incluso nella ISO: su richiesta dell'utente si installano i pacchetti ufficiali dagli archivi
apt dei produttori (pkgs.tailscale.com, download.zerotier.com), così chi li usa accetta le loro condizioni.
- Tailscale: client open source (BSD-3-Clause). Collegamento con il link di accesso di Tailscale.
- ZeroTier: si usa solo l'agente (MPL-2.0) per entrare nelle reti create su my.zerotier.com; il controller
  "nonfree" (licenza source-available, non commerciale) non viene usato.
"""
import ipaddress
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request

from .util import ApiError, LOGS, read_file, run_rc, start_job, job_state, tail, user_agent, write_file

LOG = os.path.join(LOGS, "remote.log")
KEYRINGS = "/usr/share/keyrings"
SOURCES = "/etc/apt/sources.list.d"
SYSCTL = "/etc/sysctl.d/99-nido-remote.conf"
FALLBACK_SUITE = "noble"      # se il produttore non ha ancora i pacchetti per la versione di Ubuntu installata

TS = {
    "key": "https://pkgs.tailscale.com/stable/ubuntu/{suite}.noarmor.gpg",
    "keyfile": "tailscale-archive-keyring.gpg",
    "list": "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu {suite} main",
    "listfile": "tailscale.list", "pkg": "tailscale", "service": "tailscaled",
    "probe": "https://pkgs.tailscale.com/stable/ubuntu/dists/{suite}/Release",
}
ZT = {
    "key": ["https://raw.githubusercontent.com/zerotier/ZeroTierOne/main/doc/contact%40zerotier.com.gpg",
            "https://download.zerotier.com/contact%40zerotier.com.gpg"],
    "keyfile": "zerotier.asc",
    "list": "deb [signed-by=/usr/share/keyrings/zerotier.asc] http://download.zerotier.com/debian/{suite} {suite} main",
    "listfile": "zerotier.list", "pkg": "zerotier-one", "service": "zerotier-one",
    "probe": "http://download.zerotier.com/debian/{suite}/dists/{suite}/Release",
}
WHAT = {"tailscale": TS, "zerotier": ZT}


def _suite():
    try:
        for line in read_file("/etc/os-release").splitlines():
            if line.startswith("VERSION_CODENAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return FALLBACK_SUITE


def _fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent("remote")})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _exists(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": user_agent("remote")})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _cmd(cmd, timeout=30):
    rc, out, err = run_rc(cmd, timeout=timeout)
    return rc, out, err


# --- stato ------------------------------------------------------------------------------------------

def _svc_active(name):
    rc, out, _ = _cmd(["systemctl", "is-active", name], timeout=10)
    return out.strip() == "active"


def _lan_cidr():
    """Rete di casa della scheda con la via d'uscita predefinita (es. 192.168.1.0/24)."""
    rc, out, _ = _cmd(["ip", "-j", "route", "show", "default"], timeout=10)
    try:
        dev = json.loads(out or "[]")[0]["dev"]
    except (ValueError, IndexError, KeyError):
        return None
    rc, out, _ = _cmd(["ip", "-j", "-4", "addr", "show", "dev", dev], timeout=10)
    try:
        for a in json.loads(out or "[]")[0]["addr_info"]:
            net = ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            if net.is_private:
                return str(net)
    except (ValueError, IndexError, KeyError):
        pass
    return None


def _tailscale():
    st = {"installed": bool(shutil.which("tailscale")), "service": False}
    if not st["installed"]:
        return st
    st["service"] = _svc_active("tailscaled")
    rc, out, err = _cmd(["tailscale", "status", "--json"], timeout=15)
    try:
        d = json.loads(out)
    except ValueError:
        st["error"] = (err or out).strip()[-200:]
        return st
    me = d.get("Self") or {}
    st.update({
        "state": d.get("BackendState"),                 # Running, NeedsLogin, Stopped, NoState, Starting
        "auth_url": d.get("AuthURL") or "",
        "ips": me.get("TailscaleIPs") or [],
        "dns": (me.get("DNSName") or "").rstrip("."),
        "tailnet": (d.get("CurrentTailnet") or {}).get("Name") or "",
        "peers": sum(1 for p in (d.get("Peer") or {}).values() if p.get("Online")),
        "routes": [str(r) for r in (me.get("PrimaryRoutes") or [])],
        "version": d.get("Version", "").split("-")[0],
    })
    rc, out, _ = _cmd(["tailscale", "debug", "prefs"], timeout=10)
    try:
        prefs = json.loads(out)
        st["advertised"] = prefs.get("AdvertiseRoutes") or []
    except ValueError:
        st["advertised"] = []
    st["lan"] = _lan_cidr()
    return st


def _zerotier():
    st = {"installed": bool(shutil.which("zerotier-cli")), "service": False}
    if not st["installed"]:
        return st
    st["service"] = _svc_active("zerotier-one")
    rc, out, err = _cmd(["zerotier-cli", "-j", "info"], timeout=15)
    try:
        info = json.loads(out)
        st.update({"address": info.get("address"), "online": bool(info.get("online")),
                   "version": info.get("version")})
    except ValueError:
        st["error"] = (err or out).strip()[-200:]
        return st
    rc, out, _ = _cmd(["zerotier-cli", "-j", "listnetworks"], timeout=15)
    try:
        nets = json.loads(out)
    except ValueError:
        nets = []
    st["networks"] = [{"id": n.get("nwid") or n.get("id"), "name": n.get("name") or "",
                       "status": n.get("status"), "ips": n.get("assignedAddresses") or [],
                       "device": n.get("portDeviceName") or ""} for n in nets]
    return st


def status():
    return {"tailscale": _tailscale(), "zerotier": _zerotier(),
            "installing": job_state("remote-install") in ("active", "activating"),
            "log": tail(LOG, 60) if os.path.exists(LOG) else ""}


# --- installazione (operazione lunga: nidopanel.cli remote-install <tailscale|zerotier>) -----------

def start_install(what):
    if what not in WHAT:
        raise ApiError("Servizio non supportato")
    if shutil.which("tailscale" if what == "tailscale" else "zerotier-cli"):
        raise ApiError("È già installato")
    write_file(LOG, "")
    start_job("remote-install", ["remote-install", what], log=LOG)
    return status()


def run_install(what):
    """Eseguito come operazione lunga: aggiunge l'archivio ufficiale del produttore e installa il pacchetto."""
    w = WHAT[what]
    name = "Tailscale" if what == "tailscale" else "ZeroTier"
    print(f"Installo {name} dall'archivio ufficiale del produttore", flush=True)
    suite = _suite()
    if not _exists(w["probe"].format(suite=suite)):
        print(f"L'archivio non ha ancora pacchetti per Ubuntu {suite}: uso quelli per {FALLBACK_SUITE} (compatibili)", flush=True)
        suite = FALLBACK_SUITE
    key, last = None, None
    for url in (w["key"] if isinstance(w["key"], list) else [w["key"]]):
        try:
            key = _fetch(url.format(suite=suite))
            break
        except Exception as e:  # noqa: BLE001
            last = e
    if not key:
        print(f"ERRORE: non riesco a scaricare la chiave dell'archivio: {last}", flush=True)
        return False
    os.makedirs(KEYRINGS, exist_ok=True)
    with open(os.path.join(KEYRINGS, w["keyfile"]), "wb") as f:
        f.write(key)
    os.chmod(os.path.join(KEYRINGS, w["keyfile"]), 0o644)
    write_file(os.path.join(SOURCES, w["listfile"]), w["list"].format(suite=suite) + "\n")
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive", NIDO_NO_APT_SNAPSHOT="1")
    for cmd in (["apt-get", "update", "-o", "Dir::Etc::sourcelist=" + os.path.join(SOURCES, w["listfile"]),
                 "-o", "Dir::Etc::sourceparts=-", "-o", "APT::Get::List-Cleanup=0"],
                ["apt-get", "install", "-y", "--no-install-recommends", w["pkg"]]):
        print("$ " + " ".join(cmd), flush=True)
        p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(p.stdout[-3000:], flush=True)
        if p.returncode != 0:
            print(f"ERRORE: comando non riuscito (codice {p.returncode})", flush=True)
            return False
    subprocess.run(["systemctl", "enable", "--now", w["service"]], check=False)
    print(f"{name} installato.", flush=True)
    return True


def uninstall(what):
    if what not in WHAT:
        raise ApiError("Servizio non supportato")
    w = WHAT[what]
    if what == "tailscale" and shutil.which("tailscale"):
        _cmd(["tailscale", "logout"], timeout=30)
    rc, _, err = run_rc(["apt-get", "purge", "-y", w["pkg"]], timeout=300,
                        env=dict(os.environ, DEBIAN_FRONTEND="noninteractive", NIDO_NO_APT_SNAPSHOT="1"))
    if rc != 0:
        raise ApiError("Disinstallazione non riuscita: " + (err.strip()[-200:] or str(rc)), 500)
    for f in (os.path.join(SOURCES, w["listfile"]), os.path.join(KEYRINGS, w["keyfile"])):
        try:
            os.unlink(f)
        except OSError:
            pass
    return status()


# --- Tailscale -----------------------------------------------------------------------------------------

def tailscale_connect():
    """Avvia il collegamento: Tailscale prepara un link di accesso che l'interfaccia mostra."""
    if not shutil.which("tailscale"):
        raise ApiError("Tailscale non è installato")
    if not _svc_active("tailscaled"):
        _cmd(["systemctl", "enable", "--now", "tailscaled"], timeout=30)
    host = os.uname().nodename
    # "tailscale up" aspetta finché l'accesso non è fatto: parte staccato, il link si legge da "status"
    subprocess.Popen(["tailscale", "up", "--accept-dns=false", f"--hostname={host}", "--reset"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(20):
        time.sleep(0.5)
        st = _tailscale()
        if st.get("auth_url") or st.get("state") == "Running":
            break
    return status()


def tailscale_disconnect():
    if not shutil.which("tailscale"):
        raise ApiError("Tailscale non è installato")
    rc, _, err = _cmd(["tailscale", "logout"], timeout=30)
    if rc != 0:
        raise ApiError("Scollegamento non riuscito: " + err.strip()[-200:], 500)
    return status()


def tailscale_routes(enabled):
    """Rende raggiungibile tutta la rete di casa attraverso il NAS ("subnet router")."""
    if not shutil.which("tailscale"):
        raise ApiError("Tailscale non è installato")
    lan = _lan_cidr()
    if enabled and not lan:
        raise ApiError("Non trovo la rete di casa del NAS")
    if enabled:
        write_file(SYSCTL, "# Scritto dal NAS (Accesso remoto): inoltro dei pacchetti per Tailscale\n"
                           "net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n")
        _cmd(["sysctl", "-p", SYSCTL], timeout=10)
    rc, _, err = _cmd(["tailscale", "set", "--advertise-routes=" + (lan if enabled else "")], timeout=30)
    if rc != 0:
        raise ApiError("Tailscale non ha accettato la modifica: " + err.strip()[-200:], 500)
    if not enabled:
        try:
            os.unlink(SYSCTL)
        except OSError:
            pass
        _cmd(["sysctl", "-w", "net.ipv4.ip_forward=0"], timeout=10)
    return status()


# --- ZeroTier ------------------------------------------------------------------------------------------

def zerotier_join(nwid):
    nwid = (nwid or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{16}", nwid):
        raise ApiError("L'ID della rete ZeroTier ha 16 caratteri (cifre e lettere da a a f)")
    if not shutil.which("zerotier-cli"):
        raise ApiError("ZeroTier non è installato")
    rc, out, err = _cmd(["zerotier-cli", "join", nwid], timeout=30)
    if rc != 0:
        raise ApiError("ZeroTier non ha accettato la rete: " + (err or out).strip()[-200:], 500)
    time.sleep(1)
    return status()


def zerotier_leave(nwid):
    nwid = (nwid or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{16}", nwid):
        raise ApiError("ID della rete non valido")
    rc, out, err = _cmd(["zerotier-cli", "leave", nwid], timeout=30)
    if rc != 0:
        raise ApiError("Uscita dalla rete non riuscita: " + (err or out).strip()[-200:], 500)
    return status()
