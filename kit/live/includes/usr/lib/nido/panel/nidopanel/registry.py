"""Registri di immagini (protocollo OCI / Docker Registry v2) e ricerca su Docker Hub.

Serve per:
- cercare immagini su Docker Hub (con cache: Docker Hub limita le richieste);
- leggere porte, cartelle e variabili dichiarate da un'immagine senza scaricarla;
- sapere se per un'app c'è una versione nuova (stesso tag con contenuto nuovo,
  oppure un tag di versione più alto).

Configurazione facoltativa in /etc/nido/registry.json:
  {"mirrors": {"docker.io": "https://mio-mirror"}, "hub_api": "https://hub.docker.com",
   "hub_user": "nome", "hub_token": "<cifrato>"}
L'account Docker personale (facoltativo) alza i limiti di Docker Hub.
"""
import base64
import hashlib
import http.client
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .util import ApiError, ETC, STATE, load_json, save_json, user_agent

CONF = os.path.join(ETC, "registry.json")
CACHE_DIR = os.path.join(STATE, "cache", "registry")
UA = user_agent("registry")
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])

_tokens = {}            # {(realm, service, scope): (token, scadenza)}
_search_cache = {}      # {query: (t, risultati)}
_lock = threading.Lock()


def _conf():
    return load_json(CONF, {})


# --- riferimenti alle immagini --------------------------------------------------------------------

def parse_ref(ref):
    """'linuxserver/plex:1.41' -> ('docker.io', 'linuxserver/plex', '1.41', None)"""
    ref = (ref or "").strip()
    if not ref or " " in ref or len(ref) > 300:
        raise ApiError(f"Nome immagine non valido: {ref!r}")
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
    first, _, rest = ref.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, path = first, rest
    else:
        registry, path = "docker.io", ref
    tag = "latest"
    if ":" in path.rsplit("/", 1)[-1]:
        path, tag = path.rsplit(":", 1)
    if registry in ("docker.io", "index.docker.io", "registry-1.docker.io") and "/" not in path:
        path = "library/" + path
    if registry in ("index.docker.io", "registry-1.docker.io"):
        registry = "docker.io"
    if not re.match(r"^[a-z0-9]+([._/-][a-z0-9]+)*$", path):
        raise ApiError(f"Nome immagine non valido: {ref!r}")
    return registry, path, tag, digest


def short_name(ref):
    """Nome leggibile: 'docker.io/library/nginx:latest' -> 'nginx'."""
    reg, path, tag, _ = parse_ref(ref)
    name = path[8:] if path.startswith("library/") else path
    return name if reg == "docker.io" else f"{reg}/{name}"


def _base(registry):
    mirror = (_conf().get("mirrors") or {}).get(registry)
    if mirror:
        return mirror.rstrip("/")
    if registry == "docker.io":
        return "https://registry-1.docker.io"
    return "https://" + registry


# --- HTTP con autenticazione a token -----------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


class _Headers(dict):
    """Intestazioni HTTP senza distinzione tra maiuscole e minuscole (Docker Hub le manda in minuscolo)."""

    def __init__(self, items=()):
        super().__init__((k.lower(), v) for k, v in items)

    def get(self, key, default=None):
        return super().get(key.lower(), default)

    def __getitem__(self, key):
        return super().__getitem__(key.lower())

    def __contains__(self, key):
        return super().__contains__(key.lower())


def _http(url, method="GET", headers=None, timeout=30, max_bytes=8 * 1024 * 1024):
    """Richiesta senza seguire i rimandi (li gestisce _get, senza passare il token ad altri siti)."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, **(headers or {})})
    try:
        r = _opener.open(req, timeout=timeout)
        body = r.read(max_bytes + 1) if method != "HEAD" else b""
        if len(body) > max_bytes:
            raise ApiError("Risposta troppo grande dal registro", 502)
        return r.status, _Headers(r.headers.items()), body
    except urllib.error.HTTPError as e:
        return e.code, _Headers((e.headers or {}).items()), e.read(65536) if method != "HEAD" else b""
    except (urllib.error.URLError, OSError, http.client.HTTPException, ssl.SSLError) as e:
        raise ApiError(f"Registro non raggiungibile ({urllib.parse.urlsplit(url).netloc}): {getattr(e, 'reason', e)}", 502)


def _challenge(h):
    m = re.match(r"^\s*Bearer\s+(.*)$", h or "", re.I)
    if not m:
        return None
    return dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))


def _token(ch, registry):
    key = (ch.get("realm"), ch.get("service"), ch.get("scope"))
    with _lock:
        hit = _tokens.get(key)
        if hit and hit[1] > time.time():
            return hit[0]
    q = {k: v for k, v in (("service", ch.get("service")), ("scope", ch.get("scope"))) if v}
    url = ch["realm"] + ("&" if "?" in ch["realm"] else "?") + urllib.parse.urlencode(q)
    headers = {}
    c = _conf()
    if registry == "docker.io" and c.get("hub_user") and c.get("hub_token"):
        from .secretbox import decrypt
        cred = f"{c['hub_user']}:{decrypt(c['hub_token'])}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(cred).decode()
    st, _, body = _http(url, headers=headers)
    if st != 200:
        raise ApiError(f"Accesso al registro rifiutato ({st})", 502)
    data = json.loads(body or b"{}")
    tok = data.get("token") or data.get("access_token")
    ttl = int(data.get("expires_in") or 300)
    with _lock:
        _tokens[key] = (tok, time.time() + max(30, ttl - 30))
    return tok


def _get(registry, path, method="GET", accept=None, timeout=30, max_bytes=8 * 1024 * 1024):
    url = _base(registry) + path
    headers = {"Accept": accept} if accept else {}
    st, h, body = _http(url, method, headers, timeout, max_bytes)
    if st == 401:
        ch = _challenge(h.get("WWW-Authenticate") or h.get("Www-Authenticate"))
        if not ch:
            raise ApiError("Il registro chiede un accesso non supportato", 502)
        headers["Authorization"] = "Bearer " + _token(ch, registry)
        st, h, body = _http(url, method, headers, timeout, max_bytes)
    hops = 0
    while st in (301, 302, 303, 307, 308) and hops < 5:
        loc = urllib.parse.urljoin(url, h.get("Location") or h.get("location") or "")
        same = urllib.parse.urlsplit(loc).netloc == urllib.parse.urlsplit(url).netloc
        nh = dict(headers) if same else ({"Accept": accept} if accept else {})
        url = loc
        st, h, body = _http(url, method, nh, timeout, max_bytes)
        hops += 1
    if st == 429:
        raise ApiError("Docker Hub ha raggiunto il limite di richieste: riprova tra qualche minuto "
                       "o collega il tuo account Docker in Impostazioni", 429)
    if st == 404:
        raise ApiError("Immagine o versione non trovata nel registro", 404)
    if st >= 400:
        raise ApiError(f"Errore del registro ({st})", 502)
    return h, body


# --- manifest, configurazione, tag -------------------------------------------------------------------

def remote_digest(ref):
    reg, repo, tag, digest = parse_ref(ref)
    h, _ = _get(reg, f"/v2/{repo}/manifests/{digest or tag}", method="HEAD", accept=ACCEPT)
    d = h.get("Docker-Content-Digest") or h.get("docker-content-digest")
    if not d:
        _, body = _get(reg, f"/v2/{repo}/manifests/{digest or tag}", accept=ACCEPT)
        d = "sha256:" + hashlib.sha256(body).hexdigest()
    return d


def _manifest_for_platform(reg, repo, ref_part, arch="amd64"):
    h, body = _get(reg, f"/v2/{repo}/manifests/{ref_part}", accept=ACCEPT)
    m = json.loads(body)
    mt = m.get("mediaType") or h.get("Content-Type", "")
    if "index" in mt or "list" in mt or "manifests" in m:
        chosen = None
        for x in m.get("manifests", []):
            p = x.get("platform") or {}
            if p.get("os") == "linux" and p.get("architecture") == arch:
                chosen = x
                break
        if not chosen:
            raise ApiError(f"L'immagine non esiste per questo tipo di processore ({arch})")
        _, body = _get(reg, f"/v2/{repo}/manifests/{chosen['digest']}", accept=ACCEPT)
        m = json.loads(body)
    return m


def image_config(ref):
    """Porte, cartelle, variabili ed etichette dichiarate dall'immagine (letto dal registro)."""
    reg, repo, tag, digest = parse_ref(ref)
    m = _manifest_for_platform(reg, repo, digest or tag)
    cdig = (m.get("config") or {}).get("digest")
    if not cdig:
        raise ApiError("Manifest dell'immagine non valido", 502)
    cache = os.path.join(CACHE_DIR, cdig.replace(":", "_") + ".json")
    cfg = load_json(cache, None)
    if cfg is None:
        _, body = _get(reg, f"/v2/{repo}/blobs/{cdig}", timeout=60)
        cfg = json.loads(body)
        os.makedirs(CACHE_DIR, exist_ok=True)
        save_json(cache, cfg, 0o644)
    c = cfg.get("config") or {}
    size = sum(int(layer.get("size") or 0) for layer in m.get("layers", []))
    env = {}
    for e in c.get("Env") or []:
        k, _, v = e.partition("=")
        env[k] = v
    ports = []
    for p in (c.get("ExposedPorts") or {}):
        num, _, proto = p.partition("/")
        if num.isdigit():
            ports.append({"port": int(num), "protocol": proto or "tcp"})
    return {
        "ports": sorted(ports, key=lambda x: x["port"]),
        "volumes": sorted(c.get("Volumes") or {}),
        "env": env,
        "labels": c.get("Labels") or {},
        "user": c.get("User") or "",
        "workdir": c.get("WorkingDir") or "",
        "size": size,
        "created": cfg.get("created"),
    }


def tags(ref, limit=2000):
    reg, repo, _, _ = parse_ref(ref)
    out, path = [], f"/v2/{repo}/tags/list?n=1000"
    for _ in range(5):
        h, body = _get(reg, path)
        out += json.loads(body or b"{}").get("tags") or []
        link = h.get("Link") or h.get("link") or ""
        m = re.search(r"<([^>]+)>", link)
        if not m or len(out) >= limit:
            break
        nxt = urllib.parse.urlsplit(m.group(1))
        path = nxt.path + ("?" + nxt.query if nxt.query else "")
    return out


SEMVER = re.compile(r"^(v?)(\d+)\.(\d+)(?:\.(\d+))?(.*)$")


def version_tuple(tag):
    m = SEMVER.match(tag or "")
    if not m:
        return None
    return (int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)), m.group(1), m.group(5), m.group(4) is not None


def newer_tags(ref, all_tags=None):
    """Per un tag di versione (1.2.3, v1.2, 1.2.3-ls45…) trova la patch e la versione più alte."""
    reg, repo, tag, _ = parse_ref(ref)
    cur = version_tuple(tag)
    if not cur:
        return None
    (maj, mi, pa), prefix, suffix, has_patch = cur
    # "-ls123" di LinuxServer: confronto anche il numero finale
    suf_re = re.sub(r"\d+", r"\\d+", re.escape(suffix)) if suffix else ""
    best_patch = best_any = None
    for t in all_tags if all_tags is not None else tags(ref):
        v = version_tuple(t)
        if not v or v[1] != prefix or v[3] != has_patch:
            continue
        if suffix and not re.fullmatch(suf_re, v[2]):
            continue
        if not suffix and v[2]:
            continue        # salto -rc, -beta, -alpine…
        key = (v[0], [int(x) for x in re.findall(r"\d+", v[2])])
        mine = ((maj, mi, pa), [int(x) for x in re.findall(r"\d+", suffix)])
        if key <= mine:
            continue
        if v[0][0] == maj and v[0][1] == mi and (best_patch is None or key > best_patch[0]):
            best_patch = (key, t)
        if best_any is None or key > best_any[0]:
            best_any = (key, t)
    return {"patch": best_patch[1] if best_patch else None, "latest": best_any[1] if best_any else None}


# --- ricerca su Docker Hub ----------------------------------------------------------------------------

def hub_search(query, page_size=25):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    if len(q) > 100:
        raise ApiError("Ricerca troppo lunga")
    key = q.lower()
    with _lock:
        hit = _search_cache.get(key)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
    base = (_conf().get("hub_api") or "https://hub.docker.com").rstrip("/")
    url = f"{base}/v2/search/repositories/?" + urllib.parse.urlencode({"query": q, "page_size": page_size})
    st, _, body = _http(url, headers={"Accept": "application/json"}, timeout=20)
    if st == 429:
        raise ApiError("Docker Hub ha raggiunto il limite di ricerche: riprova tra qualche minuto", 429)
    if st != 200:
        raise ApiError(f"Ricerca su Docker Hub non riuscita ({st})", 502)
    res = []
    for r in json.loads(body or b"{}").get("results") or []:
        name = r.get("repo_name") or ""
        if not name:
            continue
        res.append({
            "image": name,
            "description": (r.get("short_description") or "")[:200],
            "stars": int(r.get("star_count") or 0),
            "pulls": int(r.get("pull_count") or 0),
            "official": bool(r.get("is_official")),
            "owner": name.split("/")[0] if "/" in name else "library",
        })
    with _lock:
        if len(_search_cache) > 300:
            _search_cache.clear()
        _search_cache[key] = (time.time(), res)
    return res


# --- account Docker Hub (Impostazioni → App store) --------------------------------------------------

HUB_AUTH = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull"
HUB_RL = "https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest"
DOCKER_CFG = "/root/.docker/config.json"


def _hub_token(user=None, secret=None):
    headers = {}
    if user and secret:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()
    st, _, body = _http(HUB_AUTH, headers=headers, timeout=20)
    if st == 401:
        raise ApiError("Docker Hub ha rifiutato nome utente o token: controlla e riprova", 400)
    if st != 200:
        raise ApiError(f"Docker Hub non risponde come previsto (errore {st})", 502)
    return json.loads(body or b"{}").get("token")


def _limits(token):
    """Download rimasti su Docker Hub (intestazioni ratelimit della richiesta HEAD di prova)."""
    try:
        st, h, _ = _http(HUB_RL, method="HEAD", headers={"Authorization": "Bearer " + token, "Accept": ACCEPT},
                         timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if st != 200:
        return None
    def num(v):
        m = re.match(r"\s*(\d+)", v or "")
        return int(m.group(1)) if m else None
    lim, rem = num(h.get("ratelimit-limit")), num(h.get("ratelimit-remaining"))
    win = re.search(r"w=(\d+)", h.get("ratelimit-limit") or "")
    return {"limit": lim, "remaining": rem, "window_hours": int(win.group(1)) // 3600 if win else None}


def _docker_logged_in(user=None):
    try:
        with open(DOCKER_CFG, encoding="utf-8") as f:
            auths = (json.load(f) or {}).get("auths") or {}
    except (OSError, ValueError):
        return False
    return any("docker.io" in k for k in auths)


def hub_account():
    c = _conf()
    return {"user": c.get("hub_user") or "", "configured": bool(c.get("hub_user") and c.get("hub_token")),
            "docker_login": _docker_logged_in(), "checked": c.get("hub_checked"), "limits": c.get("hub_limits")}


def hub_account_check():
    """Controlla l'account (o l'accesso anonimo) e legge quanti download restano."""
    c = _conf()
    user, secret = c.get("hub_user"), None
    if user and c.get("hub_token"):
        from .secretbox import decrypt
        secret = decrypt(c["hub_token"])
    lim = _limits(_hub_token(user, secret))
    c["hub_limits"], c["hub_checked"] = lim, int(time.time())
    save_json(CONF, c, 0o600)
    return hub_account()


def hub_account_set(body):
    from .secretbox import encrypt
    from .util import run_rc
    user = (body.get("user") or "").strip()
    secret = (body.get("token") or "").strip()
    if not re.match(r"^[a-z0-9][a-z0-9_.-]{1,63}$", user, re.I):
        raise ApiError("Nome utente di Docker Hub non valido")
    if len(secret) < 8:
        raise ApiError("Inserisci la password o, meglio, un token di accesso di Docker Hub")
    tok = _hub_token(user, secret)          # credenziali sbagliate → errore chiaro, niente salvato
    c = _conf()
    c.update({"hub_user": user, "hub_token": encrypt(secret), "hub_limits": _limits(tok), "hub_checked": int(time.time())})
    save_json(CONF, c, 0o600)
    with _lock:
        _tokens.clear()
    # Anche Docker (download delle immagini delle app) usa l'account
    rc, _, err = run_rc(["docker", "login", "-u", user, "--password-stdin"], input=secret, timeout=60)
    res = hub_account()
    if rc != 0:
        res["warning"] = "Account salvato, ma Docker non ha accettato l'accesso: " + (err.strip()[-200:] or "Docker non risponde")
    return res


def hub_account_remove():
    from .util import run_rc
    c = _conf()
    for k in ("hub_user", "hub_token", "hub_limits", "hub_checked"):
        c.pop(k, None)
    save_json(CONF, c, 0o600)
    with _lock:
        _tokens.clear()
    run_rc(["docker", "logout"], timeout=30)
    return hub_account()
