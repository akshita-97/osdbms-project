
import os
import platform
import threading
import time

import psutil

_LOGICAL_CORES = psutil.cpu_count(logical=True) or 1
_net_lock = threading.Lock()

MIN_SAMPLE_SECONDS = 2
_sample_lock = threading.Lock()
_cpu_cache, _cpu_time = None, time.time()
_proc_cache, _proc_time = None, time.time()
_last_net = None        


def _prime():
    psutil.cpu_percent(None, percpu=True)
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


_prime()


def _cpu():
    global _cpu_cache, _cpu_time
    with _sample_lock:
        wait = MIN_SAMPLE_SECONDS - (time.time() - _cpu_time)
        if wait > 0:
            if _cpu_cache:
                return _cpu_cache
            time.sleep(wait)             
        _cpu_cache = _read_cpu()
        _cpu_time = time.time()
        return _cpu_cache


def _read_cpu():
    per_core = psutil.cpu_percent(None, percpu=True)
    freq = psutil.cpu_freq()
    try:
        load = [round(x, 2) for x in psutil.getloadavg()]
    except (AttributeError, OSError):
        load = None
    return {
        "percent": round(sum(per_core) / len(per_core), 1),
        "per_core": per_core,
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": _LOGICAL_CORES,
        "freq_mhz": round(freq.current) if freq else None,
        "load_avg": load,
    }


def _memory():
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    return {
        "total": vm.total, "used": vm.total - vm.available,
        "available": vm.available, "percent": vm.percent,
        "swap_total": sw.total, "swap_used": sw.used, "swap_percent": sw.percent,
    }


def _disks():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):      # e.g. empty DVD drive on Windows
            continue
        disks.append({"mount": part.mountpoint, "fstype": part.fstype,
                      "total": u.total, "used": u.used, "percent": u.percent})
    return disks


def _network():
    """Totals plus upload/download speed (bytes/s) since the previous call."""
    global _last_net
    io = psutil.net_io_counters()
    now = time.time()
    up = down = 0.0
    with _net_lock:
        if _last_net:
            dt = max(now - _last_net[0], 0.001)
            up = max(io.bytes_sent - _last_net[1], 0) / dt
            down = max(io.bytes_recv - _last_net[2], 0) / dt
        _last_net = (now, io.bytes_sent, io.bytes_recv)
    return {"sent_total": io.bytes_sent, "recv_total": io.bytes_recv,
            "up_speed": round(up), "down_speed": round(down)}


def _temperature():
    """Highest sensor reading in deg C, or None (not supported on Windows/macOS)."""
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    readings = [t.current for group in sensors.values() for t in group if t.current]
    return round(max(readings), 1) if readings else None


def _battery():
    try:
        b = psutil.sensors_battery()
    except (AttributeError, OSError):
        return None
    return {"percent": round(b.percent), "plugged": b.power_plugged} if b else None


def _top_processes(limit=8):
    global _proc_cache, _proc_time
    with _sample_lock:
        wait = MIN_SAMPLE_SECONDS - (time.time() - _proc_time)
        if wait > 0:
            if _proc_cache:
                return _proc_cache
            time.sleep(wait)
        _proc_cache = _read_top_processes(limit)
        _proc_time = time.time()
        return _proc_cache


def _read_top_processes(limit):
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        info = p.info
        if info["pid"] == 0:                    # Windows "System Idle Process"
            continue
        procs.append({
            "pid": info["pid"],
            "name": info["name"] or "?",
            # per-process CPU is "% of one core"; divide so 100 = whole machine
            "cpu": round((info["cpu_percent"] or 0) / _LOGICAL_CORES, 1),
            "mem": round(info["memory_percent"] or 0, 1),
        })
    procs.sort(key=lambda x: (x["cpu"], x["mem"]), reverse=True)
    return procs[:limit]


def _safe(fn, default):
    """Run one psutil reader; if the OS doesn't support it, use `default` instead of crashing."""
    try:
        return fn()
    except Exception:
        return default


_EMPTY_CPU = {"percent": 0, "per_core": [], "physical_cores": None,
              "logical_cores": _LOGICAL_CORES, "freq_mhz": None, "load_avg": None}
_EMPTY_MEM = {"total": 0, "used": 0, "available": 0, "percent": 0,
              "swap_total": 0, "swap_used": 0, "swap_percent": 0}
_EMPTY_NET = {"sent_total": 0, "recv_total": 0, "up_speed": 0, "down_speed": 0}


def get_stats():
    """Everything the Live Monitoring page shows, read from the local machine via psutil."""
    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "cpu": _safe(_cpu, _EMPTY_CPU),
        "memory": _safe(_memory, _EMPTY_MEM),
        "disks": _safe(_disks, []),
        "network": _safe(_network, _EMPTY_NET),
        "temperature": _safe(_temperature, None),
        "battery": _safe(_battery, None),
        "uptime_seconds": _safe(lambda: int(time.time() - psutil.boot_time()), 0),
        "process_count": _safe(lambda: len(psutil.pids()), 0),
        "top_processes": _safe(_top_processes, []),
    }


def get_system_info():
    """Static facts shown once at the top of the page."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "processor": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "working_drive": os.path.abspath(os.sep),
    }
