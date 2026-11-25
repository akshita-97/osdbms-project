
import hashlib
import os
import random
import secrets

from db.database import execute, execute_transaction, fetch_all, fetch_one

THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "90"))   # CPU / RAM / disk %
SUSTAINED = 3                                            # readings in a row before an alert
STALE_AFTER, OFFLINE_AFTER, KEEP_DAYS = 30, 60, 7        # seconds, seconds, days
EVENT_LABELS = {"login": "User logged in", "logout": "User logged out", "usb_inserted": "USB drive inserted",
                "usb_removed": "USB drive removed", "app_started": "Watched app started"}
DEFAULT_RULES = [("login", "Info", 1), ("logout", "Info", 0), ("usb_inserted", "Warning", 1),
                 ("usb_removed", "Info", 0), ("app_started", "Critical", 1)]
METRICS = {"CPU": "cpu_percent", "RAM": "memory_percent", "Disk": "disk_percent"}

TABLES = ["""
CREATE TABLE IF NOT EXISTS agent_devices (
    computer_id   VARCHAR(10) PRIMARY KEY,
    token_hash    CHAR(64) NOT NULL UNIQUE,
    hostname      VARCHAR(100) NULL,
    agent_version VARCHAR(20) NULL,
    last_seen_at  DATETIME NULL,
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id) ON DELETE CASCADE ON UPDATE CASCADE
)""", """
CREATE TABLE IF NOT EXISTS monitoring_readings (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    computer_id    VARCHAR(10) NOT NULL,
    cpu_percent    FLOAT NOT NULL,
    memory_percent FLOAT NOT NULL,
    disk_percent   FLOAT NOT NULL,
    received_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_readings_pc_time (computer_id, received_at),
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id) ON DELETE CASCADE ON UPDATE CASCADE
)""", """
CREATE TABLE IF NOT EXISTS monitoring_alerts (
    alert_id    INT AUTO_INCREMENT PRIMARY KEY,
    computer_id VARCHAR(10) NOT NULL,
    metric      VARCHAR(30) NOT NULL,
    severity    ENUM('Info','Warning','Critical') NOT NULL DEFAULT 'Warning',
    message     VARCHAR(250) NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME NULL,
    request_id  INT NULL,
    INDEX idx_alerts_open (computer_id, metric, resolved_at),
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id) ON DELETE CASCADE ON UPDATE CASCADE
)""", """
CREATE TABLE IF NOT EXISTS device_events (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    computer_id VARCHAR(10) NOT NULL,
    event_type  VARCHAR(30) NOT NULL,
    detail      VARCHAR(200) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_events_pc_time (computer_id, created_at),
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id) ON DELETE CASCADE ON UPDATE CASCADE
)""", """
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id    INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL UNIQUE,
    severity   ENUM('Info','Warning','Critical') NOT NULL DEFAULT 'Warning',
    enabled    TINYINT(1) NOT NULL DEFAULT 1
)""", """
CREATE TABLE IF NOT EXISTS watched_apps (
    app_name VARCHAR(60) PRIMARY KEY
)"""]


def ensure_tables():
    for sql in TABLES:
        execute(sql)
    # databases created by the first version: add severity, widen metric (safe to repeat)
    if not fetch_one("SELECT 1 AS x FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                     "AND TABLE_NAME='monitoring_alerts' AND COLUMN_NAME='severity'"):
        execute("ALTER TABLE monitoring_alerts ADD COLUMN severity "
                "ENUM('Info','Warning','Critical') NOT NULL DEFAULT 'Warning' AFTER metric")
    execute("ALTER TABLE monitoring_alerts MODIFY metric VARCHAR(30) NOT NULL")
    execute("DELETE FROM alert_rules WHERE event_type IN ('battery_low', 'network_changed')")
    for t, sev, on in DEFAULT_RULES:
        execute("INSERT IGNORE INTO alert_rules (event_type, severity, enabled) VALUES (%s,%s,%s)", (t, sev, on))
    for app in ("steam.exe", "utorrent.exe"):
        execute("INSERT IGNORE INTO watched_apps (app_name) VALUES (%s)", (app,))


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(cid):
    """New token for a computer (old one stops working). Returned once; only its hash is stored."""
    if not fetch_one("SELECT 1 AS x FROM computers WHERE computer_id=%s", (cid,)):
        return None
    token = secrets.token_urlsafe(32)
    h = _hash(token)
    execute("INSERT INTO agent_devices (computer_id, token_hash) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE token_hash=%s", (cid, h, h))
    return token


def computer_for_token(token):
    row = fetch_one("SELECT computer_id FROM agent_devices WHERE token_hash=%s", (_hash(token),))
    return row["computer_id"] if row else None


# ---------------------------------------------------------------- alerts
def _open_alert(cid, metric):
    return fetch_one("SELECT alert_id FROM monitoring_alerts "
                     "WHERE computer_id=%s AND metric=%s AND resolved_at IS NULL", (cid, metric))


def _raise(cid, metric, message, severity="Warning"):
    if not _open_alert(cid, metric):
        execute("INSERT INTO monitoring_alerts (computer_id, metric, severity, message) VALUES (%s,%s,%s,%s)",
                (cid, metric, severity, message))


def _resolve(cid, metric):
    execute("UPDATE monitoring_alerts SET resolved_at=NOW() "
            "WHERE computer_id=%s AND metric=%s AND resolved_at IS NULL", (cid, metric))


def _check_thresholds(cid):
    rows = fetch_all("SELECT cpu_percent, memory_percent, disk_percent FROM monitoring_readings "
                     "WHERE computer_id=%s ORDER BY id DESC LIMIT %s", (cid, SUSTAINED))
    for metric, col in METRICS.items():
        vals = [r[col] for r in rows]
        if len(vals) == SUSTAINED and min(vals) >= THRESHOLD:
            _raise(cid, metric, f"{metric} at {vals[0]:.0f}% for {SUSTAINED} readings in a row")
        elif vals and vals[0] < THRESHOLD:
            _resolve(cid, metric)


def _handle_event(cid, etype, detail):
    execute("INSERT INTO device_events (computer_id, event_type, detail) VALUES (%s,%s,%s)", (cid, etype, detail))
    rule = fetch_one("SELECT severity FROM alert_rules WHERE event_type=%s AND enabled=1", (etype,))
    msg = EVENT_LABELS[etype] + (f": {detail}" if detail else "")
    if rule and not fetch_one(      # same alert within 60 s = duplicate (e.g. agent retry)
            "SELECT 1 AS x FROM monitoring_alerts WHERE computer_id=%s AND metric=%s AND message=%s "
            "AND created_at > NOW() - INTERVAL 60 SECOND", (cid, etype, msg)):
        execute("INSERT INTO monitoring_alerts (computer_id, metric, severity, message) VALUES (%s,%s,%s,%s)",
                (cid, etype, rule["severity"], msg))


def save_report(cid, metrics=None, hostname=None, version=None, events=()):
    """One agent report: (cpu, ram, disk) + optional events.
    Returns the list of watched app names so the agent knows what to look for."""
    stmts = [("UPDATE agent_devices SET last_seen_at=NOW(), hostname=%s, agent_version=%s WHERE computer_id=%s",
              (hostname, version, cid))]
    if metrics:
        stmts.insert(0, ("INSERT INTO monitoring_readings (computer_id, cpu_percent, memory_percent, disk_percent) "
                         "VALUES (%s,%s,%s,%s)", (cid, *metrics)))
    execute_transaction(stmts)
    _resolve(cid, "Offline")
    if metrics:
        _check_thresholds(cid)
    for etype, detail in events:
        _handle_event(cid, etype, detail)
    if random.random() < 0.01:                    # retention: drop data older than KEEP_DAYS
        for t in ("monitoring_readings", "device_events"):
            execute(f"DELETE FROM {t} WHERE {'received_at' if t == 'monitoring_readings' else 'created_at'} "
                    "< NOW() - INTERVAL %s DAY", (KEEP_DAYS,))
    return [r["app_name"] for r in fetch_all("SELECT app_name FROM watched_apps")]


def check_offline():
    for r in fetch_all("SELECT * FROM (SELECT computer_id, TIMESTAMPDIFF(SECOND, last_seen_at, NOW()) AS age "
                       "FROM agent_devices WHERE last_seen_at IS NOT NULL) t WHERE age > %s", (OFFLINE_AFTER,)):
        _raise(r["computer_id"], "Offline", f"No data for {r['age']} s", "Critical")


# ---------------------------------------------------------------- dashboard data
def _status(row):
    if row["age"] is None:
        return "Waiting" if row["enrolled"] else "Not enrolled"
    return "Online" if row["age"] <= STALE_AFTER else "Stale" if row["age"] <= OFFLINE_AFTER else "Offline"


def overview():
    check_offline()
    rows = fetch_all("""
        SELECT c.computer_id, c.lab_id, d.hostname, d.agent_version, d.last_seen_at,
               d.computer_id IS NOT NULL AS enrolled,
               TIMESTAMPDIFF(SECOND, d.last_seen_at, NOW()) AS age,
               r.cpu_percent, r.memory_percent, r.disk_percent
        FROM computers c
        LEFT JOIN agent_devices d ON d.computer_id = c.computer_id
        LEFT JOIN monitoring_readings r ON r.id =
             (SELECT MAX(id) FROM monitoring_readings WHERE computer_id = c.computer_id)
        ORDER BY c.computer_id""")
    pcs = []
    for r in rows:
        status = _status(r)
        live = status in ("Online", "Stale")      # old readings are never shown as current values
        pcs.append({"computer_id": r["computer_id"], "lab_id": r["lab_id"], "status": status,
                    "hostname": r["hostname"], "version": r["agent_version"], "age": r["age"],
                    "last_seen": r["last_seen_at"].strftime("%H:%M:%S") if r["last_seen_at"] else None,
                    "cpu": r["cpu_percent"] if live else None,
                    "ram": r["memory_percent"] if live else None,
                    "disk": r["disk_percent"] if live else None})
    alerts = [{**a, "created_at": a["created_at"].strftime("%H:%M:%S")} for a in fetch_all(
        "SELECT alert_id, computer_id, metric, severity, message, created_at, request_id "
        "FROM monitoring_alerts WHERE resolved_at IS NULL ORDER BY alert_id DESC")]
    events = [{"computer_id": e["computer_id"], "type": e["event_type"], "detail": e["detail"],
               "time": e["created_at"].strftime("%H:%M:%S")} for e in fetch_all(
        "SELECT computer_id, event_type, detail, created_at FROM device_events ORDER BY id DESC LIMIT 12")]
    return {"computers": pcs, "alerts": alerts, "events": events}


def history(cid, minutes=5):
    return fetch_all("SELECT cpu_percent AS cpu, memory_percent AS ram, disk_percent AS disk "
                     "FROM monitoring_readings WHERE computer_id=%s "
                     "AND received_at >= NOW() - INTERVAL %s MINUTE ORDER BY id", (cid, minutes))


def raise_request(alert_id):
    """Create a Pending Review maintenance request from an alert (a human still approves it)."""
    a = fetch_one("SELECT * FROM monitoring_alerts WHERE alert_id=%s", (alert_id,))
    if not a:
        return None
    if a["request_id"]:
        return a["request_id"]
    fault, sev = ("Network", "High") if a["metric"] == "Offline" else ("Performance", "Medium")
    rid, _ = execute(
        "INSERT INTO maintenance_requests (computer_id, problem_description, fault_type, severity, status) "
        "VALUES (%s,%s,%s,%s,'Pending Review')",
        (a["computer_id"], "Detected by live monitoring: " + a["message"], fault, sev))
    execute("UPDATE monitoring_alerts SET request_id=%s WHERE alert_id=%s", (rid, alert_id))
    return rid


def dismiss_alert(alert_id):
    execute("UPDATE monitoring_alerts SET resolved_at=NOW() WHERE alert_id=%s AND resolved_at IS NULL", (alert_id,))


# ---------------------------------------------------------------- live stream + rules
def new_alerts_since(last_id):
    return fetch_all("SELECT alert_id, computer_id, metric, severity, message FROM monitoring_alerts "
                     "WHERE alert_id > %s ORDER BY alert_id", (last_id,))


def open_count():
    return fetch_one("SELECT COUNT(*) AS n FROM monitoring_alerts WHERE resolved_at IS NULL")["n"]


def max_alert_id():
    return fetch_one("SELECT COALESCE(MAX(alert_id), 0) AS m FROM monitoring_alerts")["m"]


def rules():
    return fetch_all("SELECT rule_id, event_type, severity, enabled FROM alert_rules ORDER BY rule_id")


def update_rule(rule_id, severity, enabled):
    if severity in ("Info", "Warning", "Critical"):
        execute("UPDATE alert_rules SET severity=%s, enabled=%s WHERE rule_id=%s", (severity, enabled, rule_id))


def watched_apps():
    return [r["app_name"] for r in fetch_all("SELECT app_name FROM watched_apps ORDER BY app_name")]


def add_app(name):
    name = name.strip().lower()[:60]
    if name:
        execute("INSERT IGNORE INTO watched_apps (app_name) VALUES (%s)", (name,))


def remove_app(name):
    execute("DELETE FROM watched_apps WHERE app_name=%s", (name,))
