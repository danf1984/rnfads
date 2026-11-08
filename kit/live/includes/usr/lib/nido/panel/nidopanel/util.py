"""Funzioni comuni: comandi, file di configurazione, validazione."""
import json
import os
import re
import secrets
import subprocess
import tempfile

ETC = os.environ.get("NIDO_ETC", "/etc/nido")
STATE = os.environ.get("NIDO_STATE", "/var/lib/nido")
LOGS = os.environ.get("NIDO_LOGS", "/var/log/nido")

# Cartelle in cui si possono creare condivisioni, backup, ecc.
ALLOWED_ROOTS = ("/DATA", "/media", "/mnt", "/srv")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


def run(cmd, input=None, check=True, timeout=120, env=None):
    """Esegue un comando (lista di argomenti, mai shell) e ne restituisce l'output."""
    full_env = dict(os.environ)
    full_env.setdefault("LC_ALL", "C.UTF-8")
    if env:
        full_env.update(env)
    try:
        p = subprocess.run(
            cmd, input=input, capture_output=True, text=True,
            timeout=timeout, env=full_env,
        )
    except FileNotFoundError:
        raise ApiError(f"Comando non disponibile: {cmd[0]}", 500)
    except subprocess.TimeoutExpired:
        raise ApiError(f"Il comando {cmd[0]} ha impiegato troppo tempo", 500)
    if check and p.returncode != 0:
        msg = (p.stderr or p.stdout or "").strip().splitlines()
        raise ApiError(f"{os.path.basename(cmd[0])}: {msg[-1] if msg else 'errore ' + str(p.returncode)}", 500)
    return p.stdout


def run_rc(cmd, input=None, timeout=120, env=None):
    """Come run() ma restituisce (codice, stdout, stderr) senza sollevare eccezioni."""
    full_env = dict(os.environ)
    full_env.setdefault("LC_ALL", "C.UTF-8")
    if env:
        full_env.update(env)
    try:
        p = subprocess.run(cmd, input=input, capture_output=True, text=True,
                           timeout=timeout, env=full_env)
        return p.returncode, p.stdout, p.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def have(cmd):
    from shutil import which
    return which(cmd) is not None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, data, mode=0o600):
    write_file(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode)


def write_file(path, text, mode=0o644):
    """Scrittura atomica: file temporaneo + rename."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".nido-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_file(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return default


def tail(path, lines=200):
    text = read_file(path)
    return "\n".join(text.splitlines()[-lines:])


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def check_name(value, what="Nome"):
    value = (value or "").strip()
    if not NAME_RE.match(value):
        raise ApiError(f"{what} non valido: usa lettere, numeri, spazi, . _ - (max 40 caratteri)")
    return value


def check_path(path, must_exist=True):
    """Accetta solo percorsi assoluti dentro le cartelle consentite."""
    if not path or not isinstance(path, str):
        raise ApiError("Percorso mancante")
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + "/") for r in ALLOWED_ROOTS):
        raise ApiError(f"Il percorso deve stare dentro {', '.join(ALLOWED_ROOTS)}")
    if must_exist and not os.path.isdir(real):
        raise ApiError(f"La cartella {path} non esiste")
    return real


def new_id():
    return secrets.token_hex(4)


def human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1000 or unit == "PB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} PB"


def systemd_running():
    return os.path.isdir("/run/systemd/system")


def start_job(name, args, log=None):
    """Avvia un'operazione lunga come unità systemd temporanea, così sopravvive
    al riavvio del pannello. Restituisce il nome dell'unità.
    Senza systemd (ambiente di prova) parte come processo staccato con un file .pid."""
    unit = f"nido-job-{name}"
    if job_state(name) in ("active", "activating"):
        raise ApiError("Questa operazione è già in corso", 409)
    if log:
        os.makedirs(os.path.dirname(log), exist_ok=True)
    if not systemd_running():
        out = open(log, "a") if log else subprocess.DEVNULL
        env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   PYTHONUNBUFFERED="1")
        p = subprocess.Popen(["/usr/bin/python3", "-m", "nidopanel.cli"] + list(args), stdout=out,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
        os.makedirs(os.path.join(STATE, "jobs"), exist_ok=True)
        with open(os.path.join(STATE, "jobs", unit + ".pid"), "w") as f:
            f.write(str(p.pid))
        import threading
        threading.Thread(target=p.wait, daemon=True).start()     # niente processi zombie
        return unit
    run(["systemctl", "reset-failed", unit + ".service"], check=False)
    cmd = ["systemd-run", f"--unit={unit}", "--collect", "--quiet", "--no-block",
           "--property=Type=oneshot",
           "--setenv=PYTHONPATH=/usr/lib/nido/panel", "--setenv=PYTHONUNBUFFERED=1"]
    if log:
        cmd += [f"--property=StandardOutput=append:{log}",
                f"--property=StandardError=append:{log}"]
    cmd += ["/usr/bin/python3", "-m", "nidopanel.cli"] + list(args)
    run(cmd, timeout=30)
    return unit


def job_state(name):
    if not systemd_running():
        try:
            with open(os.path.join(STATE, "jobs", f"nido-job-{name}.pid")) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            stat = read_file(f"/proc/{pid}/stat").split()
            return "inactive" if len(stat) > 2 and stat[2] == "Z" else "active"
        except (OSError, ValueError):
            return "inactive"
    rc, out, _ = run_rc(["systemctl", "is-active", f"nido-job-{name}.service"], timeout=10)
    return out.strip() or "inactive"


def unit_active(unit):
    rc, out, _ = run_rc(["systemctl", "is-active", unit], timeout=10)
    return out.strip() == "active"


def product():
    """Nome e versione del sistema da /etc/nido/nido.conf (il nome non è mai scritto nel codice)."""
    conf = {}
    for line in read_file(os.path.join(ETC, "nido.conf")).splitlines():
        k, _, v = line.partition("=")
        if k and not k.startswith("#"):
            conf[k.strip()] = v.strip().strip('"')
    return conf.get("NIDO_NAME", "NAS"), conf.get("NIDO_VERSION", "")


def user_agent(what):
    name, ver = product()
    return f"{re.sub(r'[^A-Za-z0-9._-]', '', name) or 'NAS'}/{ver or '1.0'} (+{what})"
