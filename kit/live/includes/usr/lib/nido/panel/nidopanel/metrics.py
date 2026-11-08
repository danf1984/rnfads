"""Misure in tempo reale per la Home: CPU, memoria, rete, temperatura.

Un thread campiona ogni INTERVAL secondi e tiene l'ultima ora in memoria, così il
grafico della rete è subito pieno quando si apre la pagina. Il traffico di oggi
viene salvato su disco ogni tanto, per non ripartire da zero a ogni riavvio.
"""
import collections
import datetime
import glob
import os
import re
import threading
import time

from .util import STATE, load_json, read_file, save_json

INTERVAL = 3
HISTORY = 3600 // INTERVAL
TODAY_FILE = os.path.join(STATE, "net-today.json")

_lock = threading.Lock()
_hist = collections.deque(maxlen=HISTORY)   # (t, cpu%, mem%, down B/s, up B/s, temp)
_last = {}
_today = None
_started = False


def _cpu_times():
    vals = [int(x) for x in read_file("/proc/stat").splitlines()[0].split()[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return idle, sum(vals)


def _virtual_ifaces():
    try:
        return {n for n in os.listdir("/sys/devices/virtual/net")}
    except OSError:
        return set()


def net_ifaces():
    """Schede fisiche (niente lo, docker, veth, bridge, tun)."""
    virt = _virtual_ifaces()
    res = []
    for line in read_file("/proc/net/dev").splitlines()[2:]:
        name = line.split(":")[0].strip()
        if name == "lo" or name in virt or name.startswith(("docker", "veth", "br-", "virbr", "tun", "tap", "wg", "tailscale")):
            continue
        res.append(name)
    return res


def _net_bytes():
    rx = tx = 0
    ifs = set(net_ifaces())
    for line in read_file("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() not in ifs:
            continue
        f = rest.split()
        rx += int(f[0])
        tx += int(f[8])
    return rx, tx


def link_speed():
    best = 0
    for i in net_ifaces():
        try:
            best = max(best, int(read_file(f"/sys/class/net/{i}/speed").strip() or 0))
        except ValueError:
            pass
    return best or None   # Mbit/s


def memory():
    info = {}
    for line in read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if v.split():
            info[k] = int(v.split()[0]) * 1024
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    cache = info.get("Cached", 0) + info.get("Buffers", 0) + info.get("SReclaimable", 0)
    used = total - avail
    return {"total": total, "used": used, "cache": cache,
            "percent": round(100 * used / total, 1) if total else 0}


def cpu_info():
    model, mhz = "", None
    for line in read_file("/proc/cpuinfo").splitlines():
        if line.startswith("model name") and not model:
            model = line.split(":", 1)[1].strip()
        elif line.startswith("cpu MHz") and mhz is None:
            try:
                mhz = float(line.split(":", 1)[1])
            except ValueError:
                pass
    maxf = read_file("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").strip()
    if maxf.isdigit():
        mhz = int(maxf) / 1000
    model = re.sub(r"\((R|TM)\)|CPU|Processor|\d+(th|nd|rd|st) Gen|@.*$", "", model, flags=re.I)
    model = re.sub(r"\s+", " ", model).strip()
    return {"model": model or "Processore", "cores": os.cpu_count(), "mhz": round(mhz) if mhz else None}


def temperatures():
    """Temperatura della CPU (sensori coretemp/k10temp/acpitz) e dei dischi (drivetemp, nvme)."""
    cpu, disks = None, []
    for hw in glob.glob("/sys/class/hwmon/hwmon*"):
        name = read_file(hw + "/name").strip()
        vals = []
        for p in glob.glob(hw + "/temp*_input"):
            try:
                v = int(read_file(p).strip()) / 1000
            except ValueError:
                continue
            if 0 < v < 130:
                vals.append(v)
        if not vals:
            continue
        if name in ("drivetemp", "nvme"):
            disks.append(max(vals))
        elif name in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "soc_thermal", "x86_pkg_temp"):
            cpu = max(cpu or 0, max(vals))
    if cpu is None:
        for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                v = int(read_file(p).strip()) / 1000
            except ValueError:
                continue
            if 0 < v < 130:
                cpu = max(cpu or 0, v)
    return {"cpu": round(cpu, 1) if cpu is not None else None,
            "disks": [round(min(disks), 1), round(max(disks), 1)] if disks else None}


def _load_today():
    global _today
    d = load_json(TODAY_FILE, {})
    if d.get("date") != datetime.date.today().isoformat():
        d = {"date": datetime.date.today().isoformat(), "rx": 0, "tx": 0}
    _today = d


def _loop():
    global _last
    _load_today()
    saved = time.time()
    i0, t0 = _cpu_times()
    rx0, tx0 = _net_bytes()
    tm0 = time.monotonic()
    while True:
        time.sleep(INTERVAL)
        try:
            i1, t1 = _cpu_times()
            rx1, tx1 = _net_bytes()
            tm1 = time.monotonic()
            dt = max(tm1 - tm0, 0.001)
            cpu = round(100 * (1 - (i1 - i0) / (t1 - t0)), 1) if t1 > t0 else 0.0
            drx, dtx = max(rx1 - rx0, 0), max(tx1 - tx0, 0)
            mem = memory()
            temp = temperatures()
            with _lock:
                today = datetime.date.today().isoformat()
                if _today["date"] != today:
                    _today.update(date=today, rx=0, tx=0)
                _today["rx"] += drx
                _today["tx"] += dtx
                sample = (int(time.time()), cpu, mem["percent"], round(drx / dt), round(dtx / dt), temp["cpu"])
                _hist.append(sample)
                _last = {"t": sample[0], "cpu": cpu, "mem": mem, "down": sample[3], "up": sample[4], "temp": temp}
            if time.time() - saved > 60:
                save_json(TODAY_FILE, _today, 0o644)
                saved = time.time()
            i0, t0, rx0, tx0, tm0 = i1, t1, rx1, tx1, tm1
        except Exception as e:  # noqa: BLE001 — il campionamento non deve mai fermarsi
            print(f"metrics: {e}", flush=True)


def start():
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, daemon=True, name="metrics").start()


def live():
    with _lock:
        last = dict(_last)
        today = dict(_today or {})
    if not last:
        mem = memory()
        last = {"t": int(time.time()), "cpu": 0.0, "mem": mem, "down": 0, "up": 0, "temp": temperatures()}
    last["today"] = (today.get("rx", 0) + today.get("tx", 0)) if today else 0
    return last


def history(points=120):
    """Ultima ora, ridotta a `points` punti (media) per il grafico."""
    with _lock:
        h = list(_hist)
    if not h:
        return []
    if len(h) <= points:
        return [list(x) for x in h]
    step = len(h) / points
    out = []
    for k in range(points):
        chunk = h[int(k * step):int((k + 1) * step)] or [h[-1]]
        n = len(chunk)
        temps = [c[5] for c in chunk if c[5] is not None]
        out.append([chunk[-1][0], round(sum(c[1] for c in chunk) / n, 1), round(sum(c[2] for c in chunk) / n, 1),
                    round(sum(c[3] for c in chunk) / n), round(sum(c[4] for c in chunk) / n),
                    round(sum(temps) / len(temps), 1) if temps else None])
    return out
