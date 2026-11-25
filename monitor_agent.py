
import os
import socket
import sys
import time

import psutil
import requests

VERSION = "2.1"
try:
    URL = os.environ["SMARTLAB_SERVER_URL"].rstrip("/") + "/api/monitoring/readings"
    DEVICE_ID = os.environ["SMARTLAB_DEVICE_ID"]
    TOKEN = os.environ["SMARTLAB_API_TOKEN"]
except KeyError as missing:
    sys.exit(f"Set the {missing} environment variable first.")
INTERVAL = float(os.getenv("SMARTLAB_INTERVAL", "5"))


def usb_drives():        # removable drives (Windows marks them 'removable' in the mount options)
    return {p.device for p in psutil.disk_partitions() if "removable" in p.opts.lower()}


def logged_in():
    return {u.name for u in psutil.users()}


def running(watch):      # (name, pid) of watched apps currently running: a 2nd copy has a new pid
    wanted = {w.lower() for w in watch}
    return {((p.info["name"] or "").lower(), p.pid) for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() in wanted}


watch, queue = [], []
seen = {"usb": usb_drives(), "users": logged_in(), "apps": set()}   # first look = baseline, no events
psutil.cpu_percent(None)                                            # first call always returns 0.0
while True:
    start = time.time()
    now = {"usb": usb_drives(), "users": logged_in(), "apps": running(watch)}
    for kind, new, gone in (("usb", "usb_inserted", "usb_removed"), ("users", "login", "logout")):
        queue += [{"type": new, "detail": d} for d in sorted(now[kind] - seen[kind])]
        queue += [{"type": gone, "detail": d} for d in sorted(seen[kind] - now[kind])]
    queue += [{"type": "app_started", "detail": n} for n in sorted({n for n, _ in now["apps"] - seen["apps"]})]
    seen = now
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=5, json={
            "computer_id": DEVICE_ID, "hostname": socket.gethostname(), "agent_version": VERSION,
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(os.path.abspath(os.sep)).percent,
            "events": queue[:20]})
        if r.ok:
            del queue[:20]
            watch = r.json().get("watch_apps", [])
        print(time.strftime("%H:%M:%S"), "sent" if r.ok else f"rejected {r.status_code}: {r.text.strip()}")
    except requests.RequestException as exc:      # server down / Wi-Fi drop: events stay queued, retry
        print(time.strftime("%H:%M:%S"), "server unreachable:", type(exc).__name__)
    del queue[:-100]                              # never grow without limit while offline
    time.sleep(max(INTERVAL - (time.time() - start), 0))
