"""Operazioni lunghe (installazione, aggiornamento, copie di file) eseguite in thread.

L'interfaccia avvia l'operazione, riceve un id e ne legge stato, percentuale e
registro finché non finisce.
"""
import secrets
import threading
import time
import traceback

from .util import ApiError

_jobs = {}
_lock = threading.Lock()


class Job:
    def __init__(self, kind, title, target=None):
        self.id = secrets.token_hex(6)
        self.kind, self.title, self.target = kind, title, target
        self.state = "running"          # queued | running | done | failed
        self.progress = 0
        self.step = ""
        self.lines = []
        self.result = None
        self.error = None
        self.started = time.time()
        self.ended = None
        self.cancel = False
        self.queue = None
        # Avanzamento in byte (copie, archivi): velocità e tempo che manca
        self.bytes_done = 0
        self.bytes_total = 0
        self.speed = 0.0
        self._sp = (time.time(), 0)
        self.items_done = 0
        self.items_total = 0

    def add_bytes(self, n):
        self.bytes_done += n
        now = time.time()
        t0, b0 = self._sp
        if now - t0 >= 1:
            inst = (self.bytes_done - b0) / (now - t0)
            self.speed = inst if not self.speed else self.speed * 0.6 + inst * 0.4
            self._sp = (now, self.bytes_done)
        if self.bytes_total:
            self.progress = min(99, int(100 * self.bytes_done / self.bytes_total))

    def log(self, text):
        for line in str(text).splitlines() or [""]:
            self.lines.append(f"[{time.strftime('%H:%M:%S')}] {line}")
        if len(self.lines) > 400:
            self.lines = self.lines[-400:]

    def set(self, progress=None, step=None):
        if progress is not None:
            self.progress = max(0, min(100, int(progress)))
        if step is not None:
            self.step = step
            self.log(step)

    def public(self, full=False):
        d = {"id": self.id, "kind": self.kind, "title": self.title, "target": self.target,
             "state": self.state, "progress": self.progress, "step": self.step,
             "error": self.error, "result": self.result, "started": int(self.started),
             "ended": int(self.ended) if self.ended else None,
             "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
             "speed": int(self.speed) if self.state == "running" else 0,
             "eta": int((self.bytes_total - self.bytes_done) / self.speed)
             if self.state == "running" and self.speed > 1 and self.bytes_total > self.bytes_done else None,
             "items_done": self.items_done, "items_total": self.items_total, "queue": self.queue,
             "cancelled": bool(self.cancel)}
        if full:
            d["log"] = "\n".join(self.lines[-200:])
        return d


_queues = {}


class Cancelled(ApiError):
    def __init__(self):
        super().__init__("Operazione annullata", 409)


def start(kind, title, fn, target=None, exclusive=True, queue=None):
    """Avvia fn(job) in un thread. Con exclusive non parte se c'è già un'operazione sullo stesso oggetto.
    Con queue le operazioni della stessa coda (es. "files") vanno una alla volta, nell'ordine:
    nel frattempo restano nello stato "queued"."""
    with _lock:
        if exclusive and target:
            for j in _jobs.values():
                if j.target == target and j.state == "running":
                    raise ApiError(f"C'è già un'operazione in corso su {target}", 409)
        job = Job(kind, title, target)
        job.queue = queue
        if queue:
            _queues.setdefault(queue, threading.Lock())
            if any(j.queue == queue and j.state in ("running", "queued") for j in _jobs.values()):
                job.state = "queued"
        _jobs[job.id] = job
        # Tengo solo le ultime 60 operazioni concluse
        done = sorted((j for j in _jobs.values() if j.state != "running"), key=lambda j: j.started)
        for j in done[:-60]:
            _jobs.pop(j.id, None)

    def runner():
        lock = _queues.get(queue) if queue else None
        if lock:
            lock.acquire()
        try:
            if job.cancel:
                raise Cancelled()
            job.state = "running"
            job.started = time.time()
            job.result = fn(job)
            job.state = "done"
            job.progress = 100
        except ApiError as e:
            job.state, job.error = "failed", e.message
            job.log("ERRORE: " + e.message)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job.state, job.error = "failed", str(e)
            job.log("ERRORE: " + str(e))
        finally:
            job.ended = time.time()
            if lock:
                lock.release()

    threading.Thread(target=runner, daemon=True, name=f"job-{kind}").start()
    return job


def get(jid):
    j = _jobs.get(jid)
    if not j:
        raise ApiError("Operazione non trovata", 404)
    return j.public(full=True)


def active(target=None, queue=None, recent=30):
    return [j.public() for j in sorted(_jobs.values(), key=lambda j: -j.started)
            if (target is None or j.target == target) and (queue is None or j.queue == queue)
            and (j.state in ("running", "queued") or time.time() - (j.ended or 0) < recent)]


def cancel(jid):
    j = _jobs.get(jid)
    if not j:
        raise ApiError("Operazione non trovata", 404)
    if j.state in ("running", "queued"):
        j.cancel = True
    return j.public()


def running_for(target):
    return any(j.target == target and j.state in ("running", "queued") for j in _jobs.values())


class Inline:
    """Stessa interfaccia di Job, per l'uso da riga di comando (aggiornamento notturno)."""
    def __init__(self, title=""):
        self.title, self.progress, self.step, self.lines, self.cancel = title, 0, "", [], False

    def log(self, text):
        print(text, flush=True)

    def set(self, progress=None, step=None):
        if step:
            self.log(step)
