"""Impostazioni di rete dall'interfaccia (NetworkManager): indirizzo automatico (DHCP) o fisso, gateway, DNS, Wi-Fi.

Cambiare l'indirizzo può chiudere fuori dal NAS. Per questo ogni modifica di una scheda si applica con il
ritorno automatico: le impostazioni di prima vengono salvate in /var/lib/nido/net-rollback.json e, se entro
ROLLBACK_S secondi nessuno preme "Conferma" (dall'indirizzo nuovo, o dallo schermo del NAS), un timer di
systemd (nido-net-rollback) le rimette. Le password del Wi-Fi vanno nel file della connessione di
NetworkManager (permessi 600), mai sulla riga di comando.
"""
import ipaddress
import os
import re
import time
import uuid as uuidlib

from .util import ApiError, STATE, have, load_json, run_rc, save_json

ROLLBACK = os.path.join(STATE, "net-rollback.json")
ROLLBACK_S = 180
NM_DIR = "/etc/NetworkManager/system-connections"
KEYS = ("ipv4.method", "ipv4.addresses", "ipv4.gateway", "ipv4.dns", "ipv4.ignore-auto-dns")


def _nm(args, timeout=30):
    return run_rc(["nmcli", "-t", "-e", "yes"] + args, timeout=timeout)


def _split(line):
    """Una riga "-t -e yes" di nmcli: campi separati da ":" (i ":" dentro i valori sono "\\:")."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _fields(args):
    """nmcli -t ... con nomi "CHIAVE:valore" (una per riga, anche ripetute come IP4.ADDRESS[1])."""
    rc, out, _ = _nm(args)
    res = {}
    if rc != 0:
        return res
    for line in out.splitlines():
        k, _, v = line.partition(":")
        v = v.replace("\\:", ":").replace("\\\\", "\\")
        k = re.sub(r"\[\d+\]$", "", k)
        res.setdefault(k, []).append(v)
    return res


def _first(d, k):
    return (d.get(k) or [""])[0]


def status():
    if not have("nmcli"):
        return {"available": False, "devices": []}
    rc, out, _ = _nm(["-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    devices = []
    for line in out.splitlines():
        dev, typ, state, con = (_split(line) + ["", "", "", ""])[:4]
        if typ not in ("ethernet", "wifi"):
            continue
        cur = _fields(["-f", "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS", "device", "show", dev])
        d = {"device": dev, "type": typ, "state": state, "connected": state.startswith("connected") or state == "connesso",
             "connection": con if con not in ("", "--") else None, "mac": _first(cur, "GENERAL.HWADDR"),
             "addresses": [a for a in cur.get("IP4.ADDRESS", []) if a], "gateway": _first(cur, "IP4.GATEWAY"),
             "dns": [a for a in cur.get("IP4.DNS", []) if a]}
        if d["connection"]:
            c = _fields(["-f", "connection.uuid," + ",".join(KEYS), "connection", "show", d["connection"]])
            d.update({"uuid": _first(c, "connection.uuid"), "method": _first(c, "ipv4.method") or "auto",
                      "set_addresses": [a for a in _first(c, "ipv4.addresses").split(",") if a.strip()],
                      "set_gateway": _first(c, "ipv4.gateway").replace("--", ""),
                      "set_dns": [a for a in _first(c, "ipv4.dns").split(",") if a.strip() and a != "--"]})
        devices.append(d)
    rb = load_json(ROLLBACK, None)
    pending = None
    if rb and rb.get("deadline", 0) > time.time():
        pending = {"device": rb.get("device"), "seconds": int(rb["deadline"] - time.time()), "url": rb.get("url")}
    wifi = any(d["type"] == "wifi" for d in devices)
    return {"available": True, "devices": devices, "pending": pending, "wifi": wifi,
            "hostname": os.uname().nodename}


# --- indirizzo di una scheda ------------------------------------------------------------------------------

def _check_ipv4(text, what, prefix=False):
    try:
        if prefix:
            n = ipaddress.IPv4Interface(text)
            if n.network.prefixlen < 8 or n.network.prefixlen > 30:
                raise ValueError
            return str(n)
        return str(ipaddress.IPv4Address(text))
    except ValueError:
        raise ApiError(f"{what} non valido: {text}") from None


def _current(uuid):
    c = _fields(["-f", ",".join(KEYS), "connection", "show", uuid])
    return {k: _first(c, k).replace("--", "") for k in KEYS}


def _mod_args(v):
    args = []
    for k in KEYS:
        args += [k, v.get(k, "")]
    return args


def apply(body):
    dev = body.get("device")
    st = status()
    d = next((x for x in st["devices"] if x["device"] == dev), None)
    if not d or not d.get("uuid"):
        raise ApiError("Scheda di rete non trovata o senza connessione")
    if st["pending"]:
        raise ApiError("C'è già una modifica da confermare: confermala o annullala prima", 409)
    method = body.get("method")
    dns = [_check_ipv4(x.strip(), "DNS") for x in (body.get("dns") or []) if x.strip()][:3]
    if method == "auto":
        new = {"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "",
               "ipv4.dns": ",".join(dns), "ipv4.ignore-auto-dns": "yes" if dns else "no"}
        url = None
    elif method == "manual":
        addr = _check_ipv4((body.get("address") or "").strip(), "Indirizzo", prefix=True)
        gw = _check_ipv4((body.get("gateway") or "").strip(), "Gateway")
        if ipaddress.IPv4Address(gw) not in ipaddress.IPv4Interface(addr).network:
            raise ApiError("Il gateway non è nella stessa rete dell'indirizzo")
        if not dns:
            dns = [gw]
        new = {"ipv4.method": "manual", "ipv4.addresses": addr, "ipv4.gateway": gw,
               "ipv4.dns": ",".join(dns), "ipv4.ignore-auto-dns": "yes"}
        url = "http://" + addr.split("/")[0]
    else:
        raise ApiError("Scegli automatico o fisso")
    old = _current(d["uuid"])
    save_json(ROLLBACK, {"uuid": d["uuid"], "device": dev, "old": old, "deadline": time.time() + ROLLBACK_S,
                         "url": url}, 0o600)
    rc, _, err = run_rc(["nmcli", "connection", "modify", d["uuid"]] + _mod_args(new), timeout=30)
    if rc != 0:
        os.unlink(ROLLBACK)
        raise ApiError("NetworkManager ha rifiutato le impostazioni: " + (err or "").strip()[:200])
    # Il timer del ritorno parte prima; la scheda si riattiva tra 2 secondi, così questa risposta arriva al browser
    run_rc(["systemctl", "stop", "nido-net-rollback.timer", "nido-net-rollback.service"], timeout=15)
    run_rc(["systemctl", "reset-failed", "nido-net-rollback.timer", "nido-net-rollback.service"], timeout=15)
    run_rc(["systemd-run", "--unit", "nido-net-rollback", f"--on-active={ROLLBACK_S}", "--timer-property=AccuracySec=1s",
            "/usr/bin/env", "PYTHONPATH=/usr/lib/nido/panel", "/usr/bin/python3", "-m", "nidopanel.cli", "network-rollback"],
           timeout=15)
    run_rc(["systemd-run", "--unit", f"nido-net-up-{int(time.time())}", "--on-active=2",
            "/usr/bin/nmcli", "connection", "up", d["uuid"]], timeout=15)
    return {"ok": True, "seconds": ROLLBACK_S, "url": url}


def confirm():
    run_rc(["systemctl", "stop", "nido-net-rollback.timer"], timeout=15)
    try:
        os.unlink(ROLLBACK)
    except OSError:
        pass
    return status()


def rollback():
    """Rimette le impostazioni salvate (dal timer, o con "Annulla" dall'interfaccia)."""
    rb = load_json(ROLLBACK, None)
    run_rc(["systemctl", "stop", "nido-net-rollback.timer"], timeout=15)
    if not rb:
        return status()
    run_rc(["nmcli", "connection", "modify", rb["uuid"]] + _mod_args(rb["old"]), timeout=30)
    try:
        os.unlink(ROLLBACK)
    except OSError:
        pass
    run_rc(["systemd-run", "--unit", f"nido-net-up-{int(time.time())}", "--on-active=2",
            "/usr/bin/nmcli", "connection", "up", rb["uuid"]], timeout=15)
    return status()


# --- Wi-Fi -----------------------------------------------------------------------------------------------

def wifi_scan():
    rc, out, err = _nm(["-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], timeout=40)
    if rc != 0:
        raise ApiError("Ricerca delle reti Wi-Fi non riuscita: " + (err or "").strip()[:160])
    seen = {}
    for line in out.splitlines():
        inuse, ssid, signal, sec = (_split(line) + ["", "", "", ""])[:4]
        if not ssid:
            continue
        s = {"ssid": ssid, "signal": int(signal or 0), "secure": bool(sec and sec != "--"), "security": sec,
             "active": inuse == "*"}
        if ssid not in seen or s["signal"] > seen[ssid]["signal"] or s["active"]:
            seen[ssid] = s
    return {"networks": sorted(seen.values(), key=lambda x: (not x["active"], -x["signal"]))}


def _kf(value):
    """Valore per un file keyfile di NetworkManager (GKeyFile)."""
    v = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
    return ("\\s" + v[1:]) if v.startswith(" ") else v


def wifi_connect(body):
    ssid = body.get("ssid") or ""
    psk = body.get("password") or ""
    if not ssid or len(ssid.encode()) > 32:
        raise ApiError("Nome della rete Wi-Fi non valido")
    if psk and not (8 <= len(psk) <= 63):
        raise ApiError("La password del Wi-Fi deve avere da 8 a 63 caratteri")
    dev = next((d["device"] for d in status()["devices"] if d["type"] == "wifi"), None)
    if not dev:
        raise ApiError("Questo NAS non ha una scheda Wi-Fi")
    uid = str(uuidlib.uuid4())
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", ssid)[:40] or "wifi"
    path = os.path.join(NM_DIR, f"nido-wifi-{slug}-{uid[:8]}.nmconnection")
    ssid_bytes = ";".join(str(b) for b in ssid.encode()) + ";"
    text = (f"[connection]\nid={_kf('Wi-Fi ' + ssid)}\nuuid={uid}\ntype=wifi\ninterface-name={dev}\nautoconnect=true\n\n"
            f"[wifi]\nmode=infrastructure\nssid={ssid_bytes}\n" + ("hidden=true\n" if body.get("hidden") else "") + "\n")
    if psk:
        text += f"[wifi-security]\nkey-mgmt=wpa-psk\npsk={_kf(psk)}\n\n"
    text += "[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n"
    os.makedirs(NM_DIR, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    run_rc(["nmcli", "connection", "load", path], timeout=20)
    rc, _, err = run_rc(["nmcli", "-w", "45", "connection", "up", uid], timeout=60)
    if rc != 0:
        run_rc(["nmcli", "connection", "delete", uid], timeout=20)
        try:
            os.unlink(path)
        except OSError:
            pass
        e = (err or "").lower()
        if "secrets were required" in e or "802-1x" in e or "psk" in e or "password" in e:
            raise ApiError("Password del Wi-Fi sbagliata")
        raise ApiError("Collegamento al Wi-Fi non riuscito: " + (err or "").strip()[:160])
    return status()


def wifi_forget(con_uuid):
    if not re.match(r"^[0-9a-f-]{36}$", con_uuid or ""):
        raise ApiError("Connessione non valida")
    run_rc(["nmcli", "connection", "delete", con_uuid], timeout=30)
    return status()
