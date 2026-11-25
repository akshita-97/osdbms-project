# Lab PCs: live monitoring + activity alerts

**Flow:** agent on each device -> `POST /api/monitoring/readings` (bearer token) -> Flask validates -> MySQL ->
rules turn events into alerts -> `/fleet/stream` (Server-Sent Events) pushes them to every open page (toast + navbar badge).

## Server laptop
1. `set SMARTLAB_HOST=0.0.0.0` then `python app.py` (debug is forced off in this mode). New tables/columns are created on start.
2. Allow port 5000 in Windows Firewall for **Private** networks only. Never port-forward it.
3. **Lab PCs** page -> select a device -> **Generate agent token** (shown once; only its SHA-256 hash is stored).

## Lab PC
`pip install psutil requests`, set `SMARTLAB_SERVER_URL`, `SMARTLAB_DEVICE_ID`, `SMARTLAB_API_TOKEN`, run `python monitor_agent.py`.
Reports CPU/RAM/disk and events: **login, logout, USB inserted/removed, watched app started**. Events are queued while offline.

## Rules (Lab PCs -> Alert rules)
* Each event type: enable/disable and Info / Warning / Critical severity. Watched apps list is editable
  (default `steam.exe`, `utorrent.exe`). Only watched apps are ever reported; no other process names are collected.
* Always on: CPU/RAM/disk >= 90 % for 3 readings (`ALERT_THRESHOLD`), device silent > 60 s (Offline, Critical).
* Alerts can be dismissed or turned into a *Pending Review* maintenance request (approval stays manual).
* Status: Online <= 30 s, Stale <= 60 s, Offline > 60 s; stale/offline devices show `--`, never old values.
* A token works only for its own `computer_id` (mismatch -> 403). Data older than 7 days is deleted.

## Privacy
Only device activity events are collected (no screen, keystrokes, browsing or full process lists). Use only on lab devices
with the lab administration's permission.

## Quick demo
Agent running -> insert a USB drive or start `steam.exe` (or add `notepad.exe` to Watched apps and open Notepad)
-> toast appears within ~5 s on every open page, badge increments, row shows in Recent Activity.
