"""Accesso sicuro (HTTPS) con Caddy davanti all'interfaccia.

Caddy ascolta sulle porte 80 e 443 e passa le richieste all'interfaccia su 127.0.0.1:8090.
Tipi di certificato:
- "home": certificato "di casa". Il NAS crea una sua piccola autorità (CA) e un certificato per
  <nome>.local, *.<nome>.local e i suoi indirizzi IP. Si scarica la CA e la si installa una volta sui
  dispositivi: da lì il browser non mostra più avvisi.
- "letsencrypt": certificato pubblico per un tuo dominio (Caddy lo chiede e lo rinnova da solo). In casa
  continua a valere il certificato di casa.
- "custom": certificato caricato (file .crt e .key).
- "off": solo HTTP.
Opzioni: reindirizzamento da HTTP a HTTPS, sottodomini per le app (jellyfin.<nome>.local),
pubblicati in rete con mDNS (avahi-publish) dal servizio nido-mdns.
"""
import datetime
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import time

from .util import ApiError, ETC, have, load_json, read_file, run_rc, save_json, systemd_running, write_file

CONF = os.path.join(ETC, "https.json")
TLS = os.path.join(ETC, "tls")
CA_CRT, CA_KEY = os.path.join(TLS, "ca.crt"), os.path.join(TLS, "ca.key")
SRV_CRT, SRV_KEY = os.path.join(TLS, "server.crt"), os.path.join(TLS, "server.key")
CUS_CRT, CUS_KEY = os.path.join(TLS, "custom.crt"), os.path.join(TLS, "custom.key")
CADDYFILE = os.environ.get("NIDO_CADDYFILE", "/etc/caddy/Caddyfile")
UPSTREAM = os.environ.get("NIDO_UPSTREAM", "127.0.0.1:8090")
LEAF_DAYS = 800          # sotto gli 825 giorni accettati da Apple per le CA private
DEFAULT = {"mode": "home", "redirect": False, "app_subdomains": False, "domain": "", "email": ""}
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def load():
    return {**DEFAULT, **(load_json(CONF, {}) or {})}


def _hostname():
    return socket.gethostname().split(".")[0].lower()


def _ips():
    from .system import ip_addresses
    res = ["127.0.0.1"]
    for i in ip_addresses():
        if i.get("ip") and i["ip"] not in res:
            res.append(i["ip"])
    return res


def _caddy_group():
    import grp
    try:
        return grp.getgrnam("caddy").gr_gid
    except KeyError:
        return 0


# --- certificati -------------------------------------------------------------------------------------

def _x509():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    return x509, hashes, serialization, ec, NameOID, ExtendedKeyUsageOID


def _name():
    c = {}
    for line in read_file(os.path.join(ETC, "nido.conf")).splitlines():
        k, _, v = line.partition("=")
        c[k.strip()] = v.strip().strip('"')
    return c.get("NIDO_NAME", "NAS")


def _write_key(path, key, group_read=False):
    _, _, serialization, _, _, _ = _x509()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    os.makedirs(TLS, mode=0o750, exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(pem)
    os.chmod(path + ".tmp", 0o640 if group_read else 0o600)
    if group_read:
        os.chown(path + ".tmp", 0, _caddy_group())
    os.replace(path + ".tmp", path)


def _write_cert(path, cert):
    _, _, serialization, _, _, _ = _x509()
    os.makedirs(TLS, mode=0o750, exist_ok=True)
    os.chown(TLS, 0, _caddy_group())
    with open(path + ".tmp", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(path + ".tmp", 0o644)
    os.replace(path + ".tmp", path)


def _load_cert(path):
    x509 = _x509()[0]
    try:
        with open(path, "rb") as f:
            return x509.load_pem_x509_certificate(f.read())
    except (OSError, ValueError):
        return None


def _ensure_ca():
    x509, hashes, serialization, ec, NameOID, _ = _x509()
    ca = _load_cert(CA_CRT)
    if ca and os.path.exists(CA_KEY) and ca.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=400):
        with open(CA_KEY, "rb") as f:
            return ca, serialization.load_pem_private_key(f.read(), None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{_name()} - certificato di casa ({_hostname()})"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, _name())])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                       key_encipherment=False, data_encipherment=False, key_agreement=False,
                                       encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
          .sign(key, hashes.SHA256()))
    _write_key(CA_KEY, key)
    _write_cert(CA_CRT, ca)
    try:
        os.unlink(SRV_CRT)          # nuova CA: anche il certificato del NAS va rifatto
    except OSError:
        pass
    return ca, key


def _wanted_names():
    h = _hostname()
    return [h, f"{h}.local", f"*.{h}.local", "localhost"], _ips()


def _sans(cert):
    x509 = _x509()[0]
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return [], []
    return ext.get_values_for_type(x509.DNSName), [str(i) for i in ext.get_values_for_type(x509.IPAddress)]


def ensure_home_cert(force=False):
    """Crea o rinnova il certificato di casa quando serve (scadenza vicina, nome o indirizzi cambiati)."""
    x509, hashes, _, ec, NameOID, EKU = _x509()
    names, ips = _wanted_names()
    cur = _load_cert(SRV_CRT)
    now = datetime.datetime.now(datetime.timezone.utc)
    if cur and not force and os.path.exists(SRV_KEY) and cur.not_valid_after_utc > now + datetime.timedelta(days=30):
        dns, ipl = _sans(cur)
        if set(names) <= set(dns) and set(ips) <= set(ipl):
            return False
    ca, ca_key = _ensure_ca()
    key = ec.generate_private_key(ec.SECP256R1())
    alt = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{_hostname()}.local")]))
            .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=LEAF_DAYS))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([EKU.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write_key(SRV_KEY, key, group_read=True)
    _write_cert(SRV_CRT, cert)
    return True


def _cert_info(path):
    c = _load_cert(path)
    if not c:
        return None
    from cryptography.hazmat.primitives import hashes
    dns, ipl = _sans(c)
    cn = c.subject.rfc4514_string()
    return {"subject": cn, "issuer": c.issuer.rfc4514_string(), "not_after": int(c.not_valid_after_utc.timestamp()),
            "not_before": int(c.not_valid_before_utc.timestamp()), "names": dns + ipl,
            "sha256": c.fingerprint(hashes.SHA256()).hex(":").upper()}


def ca_pem():
    if not os.path.exists(CA_CRT):
        ensure_home_cert()
    return read_file(CA_CRT)


def upload(cert_pem, key_pem):
    """Certificato caricato: controllo che chiave e certificato vadano insieme e che non sia scaduto."""
    x509, _, serialization, _, _, _ = _x509()
    try:
        chain = x509.load_pem_x509_certificates((cert_pem or "").encode())
    except ValueError:
        raise ApiError("Il file del certificato non è valido (serve il formato PEM: -----BEGIN CERTIFICATE-----)")
    try:
        key = serialization.load_pem_private_key((key_pem or "").encode(), None)
    except (ValueError, TypeError):
        raise ApiError("La chiave non è valida o è protetta da password (serve una chiave PEM senza password)")
    if not chain:
        raise ApiError("Nessun certificato nel file")
    pub = lambda k: k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)  # noqa: E731
    if pub(chain[0].public_key()) != pub(key.public_key()):
        raise ApiError("La chiave non corrisponde al certificato")
    if chain[0].not_valid_after_utc < datetime.datetime.now(datetime.timezone.utc):
        raise ApiError("Il certificato è scaduto")
    os.makedirs(TLS, mode=0o750, exist_ok=True)
    write_file(CUS_CRT, "".join(c.public_bytes(serialization.Encoding.PEM).decode() for c in chain), 0o644)
    _write_key(CUS_KEY, key, group_read=True)
    return _cert_info(CUS_CRT)


# --- Caddy -------------------------------------------------------------------------------------------

def _app_routes():
    """[(sottodominio, porta, schema)] per le app con un'interfaccia web."""
    try:
        from . import apps
        lst = apps.list_apps().get("apps", [])
    except Exception:  # noqa: BLE001 — Docker spento: nessun sottodominio
        return []
    res, seen = [], set()
    for a in lst:
        w = a.get("web") or {}
        if not w.get("port"):
            continue
        sub = re.sub(r"[^a-z0-9-]+", "-", (a.get("name") or "").lower()).strip("-")[:40]
        if not sub or sub in seen or sub in ("www", "nas"):
            continue
        seen.add(sub)
        res.append((sub, int(w["port"]), "https" if w.get("scheme") == "https" else "http"))
    return res


def _proxy(port, scheme, indent="\t"):
    if scheme == "https":
        return (f"{indent}reverse_proxy https://127.0.0.1:{port} {{\n{indent}\ttransport http {{\n"
                f"{indent}\t\ttls_insecure_skip_verify\n{indent}\t}}\n{indent}}}\n")
    return f"{indent}reverse_proxy 127.0.0.1:{port}\n"


def caddyfile(c=None):
    c = c or load()
    h = _hostname()
    mode = c["mode"]
    apps = _app_routes() if c["app_subdomains"] and mode != "off" else []
    out = ["# Generato dall'interfaccia del NAS (Impostazioni > Accesso sicuro): non modificare a mano.", "{"]
    if mode == "letsencrypt":
        out.append("\tauto_https disable_redirects")
        if c.get("email"):
            out.append(f"\temail {c['email']}")
    else:
        out.append("\tauto_https off")
    if mode in ("home", "letsencrypt", "custom"):
        out.append(f"\tdefault_sni {h}.local")
    out += ["}", ""]
    tls = ""
    if mode in ("home", "letsencrypt"):
        tls = f"\ttls {SRV_CRT} {SRV_KEY}\n"
    elif mode == "custom":
        tls = f"\ttls {CUS_CRT} {CUS_KEY}\n"
    nas = f"\treverse_proxy {UPSTREAM}\n"
    if mode == "off":
        out += [":80 {", nas.rstrip(), "}"]
        return "\n".join(out) + "\n"
    if mode == "letsencrypt":
        d = c["domain"]
        out += [f"{d} {{", nas.rstrip(), "}", ""]
        for sub, port, scheme in apps:
            out += [f"{sub}.{d} {{", _proxy(port, scheme).rstrip(), "}", ""]
    # accesso dalla rete di casa (nome .local o indirizzo IP)
    for sub, port, scheme in apps:
        out += [f"https://{sub}.{h}.local {{", tls.rstrip(), _proxy(port, scheme).rstrip(), "}", ""]
    out += [":443 {", tls.rstrip(), nas.rstrip(), "}", ""]
    if c["redirect"]:
        out += [":80 {", "\thandle /certificato-casa.crt {", f"\t\treverse_proxy {UPSTREAM}", "\t}",
                "\thandle {", "\t\tredir https://{host}{uri} 308", "\t}", "}"]
    else:
        for sub, port, scheme in apps:
            out += [f"http://{sub}.{h}.local {{", _proxy(port, scheme).rstrip(), "}", ""]
        out += [":80 {", nas.rstrip(), "}"]
    return "\n".join(out) + "\n"


def _caddy_validate(path):
    if not have("caddy"):
        raise ApiError("Caddy non è installato")
    rc, out, err = run_rc(["caddy", "validate", "--config", path, "--adapter", "caddyfile"], timeout=60,
                          env={"HOME": "/var/lib/caddy", "XDG_DATA_HOME": "/var/lib/caddy/.local/share",
                               "XDG_CONFIG_HOME": "/var/lib/caddy/.config"})
    if rc != 0:
        lines = [l for l in (err or out).splitlines() if "Error" in l or "error" in l] or (err or out).splitlines()
        raise ApiError("Configurazione di Caddy non valida: " + (lines[-1] if lines else "errore")[-300:])


def caddy_active():
    if systemd_running():
        rc, out, _ = run_rc(["systemctl", "is-active", "caddy"], timeout=10)
        return out.strip() == "active"
    rc, _, _ = run_rc(["curl", "-s", "-o", "/dev/null", "http://localhost:2019/config/"], timeout=5)
    return rc == 0


def reload_caddy():
    """Ricarica Caddy con la configurazione nuova (o lo avvia se è fermo)."""
    from . import server_fallback
    server_fallback.release()           # libera la porta 80 se l'interfaccia la stava usando al posto di Caddy
    if systemd_running():
        rc, _, err = run_rc(["systemctl", "reload-or-restart", "caddy"], timeout=90)
        if rc != 0:
            rc, _, err = run_rc(["systemctl", "restart", "caddy"], timeout=90)
        return rc == 0, err
    rc, out, err = run_rc(["caddy", "reload", "--config", CADDYFILE, "--adapter", "caddyfile"], timeout=60)
    return rc == 0, err or out


def apply(c=None):
    c = c or load()
    if c["mode"] in ("home", "letsencrypt"):
        ensure_home_cert()
    if c["mode"] == "custom" and not (os.path.exists(CUS_CRT) and os.path.exists(CUS_KEY)):
        raise ApiError("Carica prima il certificato e la chiave")
    text = caddyfile(c)
    d = os.path.dirname(CADDYFILE)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".nido-", suffix=".caddy")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    try:
        _caddy_validate(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, CADDYFILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    ok, err = reload_caddy()
    return {"applied": ok, "error": None if ok else (err or "Caddy non è ripartito").strip()[-300:]}


# --- API -----------------------------------------------------------------------------------------------

def status():
    c = load()
    h = _hostname()
    home = _cert_info(SRV_CRT)
    active_cert = _cert_info(CUS_CRT) if c["mode"] == "custom" else home
    urls = []
    if c["mode"] != "off":
        urls.append(f"https://{h}.local")
        if c["mode"] == "letsencrypt" and c["domain"]:
            urls.insert(0, f"https://{c['domain']}")
    return {**c, "hostname": h, "home_cert": home, "ca": _cert_info(CA_CRT), "custom_cert": _cert_info(CUS_CRT),
            "cert": active_cert, "caddy": caddy_active(), "installed": have("caddy"), "urls": urls,
            "apps": [{"name": s, "port": p, "url": f"https://{s}.{h}.local"} for s, p, _ in _app_routes()]
            if c["app_subdomains"] else []}


def save(body):
    c = load()
    mode = body.get("mode", c["mode"])
    if mode not in ("off", "home", "letsencrypt", "custom"):
        raise ApiError("Tipo di certificato non valido")
    c["mode"] = mode
    for k in ("redirect", "app_subdomains"):
        if k in body:
            c[k] = bool(body[k])
    if "domain" in body:
        c["domain"] = (body.get("domain") or "").strip().lower().rstrip(".")
    if "email" in body:
        c["email"] = (body.get("email") or "").strip()
    if mode == "letsencrypt":
        if not DOMAIN_RE.match(c["domain"]) or c["domain"].endswith(".local"):
            raise ApiError("Scrivi un dominio pubblico valido (es. nas.miodominio.it)")
        if c["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", c["email"], re.I):
            raise ApiError("Email non valida")
    if mode == "off":
        c["redirect"] = False
    res = apply(c)
    save_json(CONF, c, 0o644)
    return {**status(), **res}


def renew_home():
    ensure_home_cert(force=True)
    res = apply()
    return {**status(), **res}


def app_domain():
    """Dominio delle app per l'interfaccia (None se i sottodomini sono spenti)."""
    c = load()
    if not c["app_subdomains"] or c["mode"] == "off":
        return None
    return f"{_hostname()}.local"


# --- nomi .local delle app (servizio nido-mdns) ------------------------------------------------------

AVAHI_CONF = "/etc/avahi/avahi-daemon.conf"
VIRTUAL = ("docker", "br-", "veth", "virbr", "lo", "tun", "tap", "wg", "tailscale", "zt")


def avahi_interfaces():
    """Fa annunciare <nome>.local solo sulle schede di rete vere: senza, avahi lo annuncia anche sulle reti
    interne di Docker (172.17.x.x) e i PC di casa possono ricevere l'indirizzo sbagliato."""
    if not os.path.exists(AVAHI_CONF):
        return False
    want = set()
    for n in sorted(os.listdir("/sys/class/net")):
        if n.startswith(VIRTUAL):
            continue
        if os.path.exists(f"/sys/class/net/{n}/device") or os.path.exists(f"/sys/class/net/{n}/bridge") \
                or os.path.exists(f"/sys/class/net/{n}/bonding"):
            want.add(n)
    if not want:
        return False
    line = "allow-interfaces=" + ",".join(sorted(want))
    txt = read_file(AVAHI_CONF)
    lines = txt.splitlines()
    out, done, in_server = [], False, False
    for l in lines:
        st = l.strip()
        if st.startswith("["):
            if in_server and not done:
                out.append(line)
                done = True
            in_server = st == "[server]"
        if in_server and re.match(r"^#?\s*allow-interfaces\s*=", st):
            if not done:
                out.append(line)
                done = True
            continue
        out.append(l)
    if in_server and not done:
        out.append(line)
        done = True
    new = "\n".join(out) + "\n"
    if new == txt or not done:
        return False
    write_file(AVAHI_CONF, new)
    run_rc(["systemctl", "try-restart", "avahi-daemon"], timeout=60)
    return True


def run_mdns():
    """Pubblica in rete <app>.<nome>.local con avahi-publish finché il servizio resta acceso."""
    procs = {}
    while True:
        try:
            if avahi_interfaces():
                for p, _ in procs.values():
                    p.terminate()
                procs = {}
                time.sleep(5)
        except OSError:
            pass
        want = {}
        if app_domain() and have("avahi-publish"):
            ips = [i for i in _ips() if i != "127.0.0.1" and ":" not in i]
            if ips:
                for sub, _, _ in _app_routes():
                    want[f"{sub}.{_hostname()}.local"] = ips[0]
        for name in list(procs):
            p, ip = procs[name]
            if want.get(name) != ip or p.poll() is not None:
                p.terminate()
                procs.pop(name)
        for name, ip in want.items():
            if name not in procs:
                procs[name] = (subprocess.Popen(["avahi-publish", "-a", "-R", name, ip],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), ip)
        time.sleep(60)


def daily():
    """Controllo giornaliero (dal monitor): rinnova il certificato di casa se scade o se cambia l'IP."""
    c = load()
    if c["mode"] in ("home", "letsencrypt") and os.path.exists(CA_CRT):
        if ensure_home_cert():
            apply(c)
    return json.dumps({"ok": True})
