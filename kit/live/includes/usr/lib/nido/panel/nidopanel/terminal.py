"""Terminale nel browser: WebSocket (RFC 6455, senza librerie esterne) collegato a uno pseudo-terminale.

Bersagli:
- "user": shell di login dell'utente del NAS con lo stesso nome dell'account dell'interfaccia (se è
  amministratore), altrimenti come "root";
- "root": shell di root;
- "c:<contenitore>": shell dentro un contenitore Docker (bash se c'è, altrimenti sh).

Protocollo con la pagina: il browser manda testo "0<dati>" per i tasti e "1{"cols":..,"rows":..}"
per le dimensioni; il NAS manda l'uscita del terminale in messaggi binari.
"""
import base64
import fcntl
import hashlib
import json
import os
import pwd
import re
import select
import signal
import socket
import struct
import subprocess
import termios
import time

from .util import ApiError, run_rc

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_SESSIONS = 16
_sessions = {}          # id -> info (per l'elenco delle sessioni aperte)


def targets(ui_user):
    """Dove si può aprire un terminale."""
    res = []
    linux = _linux_admin(ui_user)
    if linux:
        res.append({"id": "user", "label": f"{linux}@{os.uname().nodename}", "kind": "host"})
    res.append({"id": "root", "label": f"root@{os.uname().nodename}", "kind": "host"})
    rc, out, _ = run_rc(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"], timeout=10)
    if rc == 0:
        for line in sorted(out.splitlines()):
            name, _, image = line.partition("\t")
            if name:
                res.append({"id": "c:" + name, "label": name, "image": image, "kind": "container"})
    return {"targets": res, "sessions": len(_sessions)}


def _linux_admin(ui_user):
    """L'utente del NAS con lo stesso nome dell'account dell'interfaccia, se è amministratore."""
    try:
        p = pwd.getpwnam(ui_user or "")
    except KeyError:
        return None
    if p.pw_uid < 1000:
        return None
    import grp
    try:
        if ui_user in grp.getgrnam("sudo").gr_mem:
            return ui_user
    except KeyError:
        pass
    return None


def _command(target, ui_user):
    if target == "user":
        u = _linux_admin(ui_user)
        if not u:
            raise ApiError("Nessun utente amministratore del NAS con il tuo nome: apri il terminale come root")
        return ["/usr/sbin/runuser", "-l", u], u
    if target == "root":
        return ["/bin/bash", "-l"], "root"
    if target.startswith("c:"):
        name = target[2:]
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", name):
            raise ApiError("Nome del contenitore non valido")
        rc, out, _ = run_rc(["docker", "inspect", "-f", "{{.State.Running}}", name], timeout=10)
        if rc != 0 or out.strip() != "true":
            raise ApiError("Il contenitore non è acceso")
        return ["docker", "exec", "-it", "-e", "TERM=xterm-256color", name, "sh", "-c",
                "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi"], name
    raise ApiError("Terminale non valido")


# --- WebSocket ----------------------------------------------------------------------------------

def accept_key(key):
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


class WS:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""
        self.frag = b""
        self.frag_op = None
        self.closed = False

    def _send_frame(self, op, data):
        n = len(data)
        if n < 126:
            head = struct.pack("!BB", 0x80 | op, n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | op, 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | op, 127, n)
        self.sock.sendall(head + data)

    def send_bin(self, data):
        self._send_frame(2, data)

    def close(self, code=1000, reason=""):
        if not self.closed:
            self.closed = True
            try:
                self._send_frame(8, struct.pack("!H", code) + reason.encode()[:120])
            except OSError:
                pass

    def feed(self, data):
        """Aggiunge byte ricevuti e restituisce i messaggi completi [(op, payload)]."""
        self.buf += data
        out = []
        while True:
            if len(self.buf) < 2:
                break
            b1, b2 = self.buf[0], self.buf[1]
            fin, op, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
            pos = 2
            if n == 126:
                if len(self.buf) < 4:
                    break
                n = struct.unpack("!H", self.buf[2:4])[0]
                pos = 4
            elif n == 127:
                if len(self.buf) < 10:
                    break
                n = struct.unpack("!Q", self.buf[2:10])[0]
                pos = 10
            if n > 4 * 1024 * 1024:
                raise ValueError("messaggio troppo grande")
            if not masked:
                raise ValueError("messaggio del browser senza maschera")
            if len(self.buf) < pos + 4 + n:
                break
            mask = self.buf[pos:pos + 4]
            raw = self.buf[pos + 4:pos + 4 + n]
            self.buf = self.buf[pos + 4 + n:]
            payload = _unmask(raw, mask)
            if op == 0:                     # continuazione
                self.frag += payload
                if fin:
                    out.append((self.frag_op, self.frag))
                    self.frag, self.frag_op = b"", None
            elif op in (1, 2):
                if fin:
                    out.append((op, payload))
                else:
                    self.frag, self.frag_op = payload, op
            elif op == 8:
                out.append((8, payload))
            elif op == 9:                   # ping -> pong
                self._send_frame(10, payload)
        return out


def _unmask(raw, mask):
    n = len(raw)
    key = (mask * (n // 4 + 1))[:n]
    return (int.from_bytes(raw, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")


def _set_size(fd, cols, rows):
    cols = max(10, min(int(cols), 500))
    rows = max(3, min(int(rows), 300))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def serve(sock, target, ui_user, alive, cols=100, rows=30):
    """Collega il WebSocket allo pseudo-terminale finché uno dei due non si chiude.
    alive(): False quando la sessione dell'interfaccia non è più valida."""
    ws = WS(sock)
    if len(_sessions) >= MAX_SESSIONS:
        ws.close(1013, "Troppi terminali aperti")
        return
    try:
        cmd, who = _command(target, ui_user)
    except ApiError as e:
        ws.send_bin(("\r\n\x1b[31m" + e.message + "\x1b[0m\r\n").encode())
        ws.close(1008, "rifiutato")
        return
    env = {"TERM": "xterm-256color", "COLORTERM": "truecolor", "LANG": os.environ.get("LANG", "C.UTF-8"),
           "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root"}
    # Pseudo-terminale con subprocess (niente fork() a mano in un processo con più thread);
    # "setsid -c" rende il terminale quello di controllo, così Ctrl+C e i programmi a schermo intero funzionano
    fd, slave = os.openpty()
    try:
        _set_size(fd, cols, rows)
        proc = subprocess.Popen(["/usr/bin/setsid", "-c"] + cmd, stdin=slave, stdout=slave, stderr=slave,
                                env=env, cwd="/root" if who == "root" else "/", close_fds=True)
    except OSError as e:
        os.close(fd)
        ws.send_bin(f"\r\nImpossibile aprire il terminale: {e}\r\n".encode())
        ws.close(1011, "errore")
        return
    finally:
        os.close(slave)
    pid = proc.pid
    sid = f"{pid}"
    _sessions[sid] = {"target": target, "user": ui_user, "started": time.time()}
    try:
        sock.settimeout(None)
        last_check = time.time()
        while True:
            r, _, _ = select.select([sock, fd], [], [], 5)
            if fd in r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    break
                ws.send_bin(data)
            if sock in r:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                for op, payload in ws.feed(chunk):
                    if op == 8:
                        raise ConnectionResetError
                    text = payload.decode("utf-8", "replace")
                    if text[:1] == "0":
                        os.write(fd, text[1:].encode())
                    elif text[:1] == "1":
                        try:
                            sz = json.loads(text[1:])
                            _set_size(fd, sz.get("cols", 100), sz.get("rows", 30))
                        except (ValueError, TypeError):
                            pass
            if time.time() - last_check > 30:
                last_check = time.time()
                if not alive():
                    ws.send_bin(b"\r\n\x1b[33mAccesso scaduto: terminale chiuso.\x1b[0m\r\n")
                    break
    except (OSError, ValueError, ConnectionResetError):
        pass
    finally:
        _sessions.pop(sid, None)
        try:
            os.killpg(os.getpgid(pid), signal.SIGHUP)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        ws.close(1000, "fine")
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
