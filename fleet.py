

import json
import time

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for

from services import fleet_service as svc

fleet_bp = Blueprint("fleet", __name__)
REFRESH_SECONDS = 5


@fleet_bp.route("/fleet")
def page():
    return render_template("fleet.html", refresh_seconds=REFRESH_SECONDS, threshold=svc.THRESHOLD)


@fleet_bp.route("/fleet/api/overview")
def overview():
    return jsonify(svc.overview())


@fleet_bp.route("/fleet/api/history/<cid>")
def history(cid):
    return jsonify(svc.history(cid))


@fleet_bp.route("/fleet/token/<cid>", methods=["POST"])
def token(cid):
    t = svc.issue_token(cid)
    return (jsonify(token=t), 200) if t else (jsonify(error="unknown computer"), 404)


@fleet_bp.route("/fleet/alerts/<int:alert_id>/request", methods=["POST"])
def alert_request(alert_id):
    rid = svc.raise_request(alert_id)
    return (jsonify(request_id=rid), 200) if rid else (jsonify(error="unknown alert"), 404)


@fleet_bp.route("/fleet/alerts/<int:alert_id>/dismiss", methods=["POST"])
def alert_dismiss(alert_id):
    svc.dismiss_alert(alert_id)
    return jsonify(ok=True)


@fleet_bp.route("/fleet/stream")
def stream():
    """Server-Sent Events: pushes new alerts + the open-alert count to every open page."""
    last = request.headers.get("Last-Event-ID", type=int) or svc.max_alert_id()

    def gen():
        nonlocal last
        count, tick = None, 0
        while True:
            try:
                tick += 1
                if tick % 5 == 1:
                    svc.check_offline()
                for a in svc.new_alerts_since(last):
                    last = a["alert_id"]
                    yield f"id: {last}\nevent: alert\ndata: {json.dumps(a)}\n\n"
                n = svc.open_count()
                yield f"event: count\ndata: {n}\n\n" if n != count else ": ping\n\n"
                count = n
            except Exception as exc:                  # DB hiccup: keep the stream alive
                yield f": error {type(exc).__name__}\n\n"
            time.sleep(2)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@fleet_bp.route("/fleet/rules")
def rules():
    return render_template("fleet_rules.html", rules=svc.rules(), apps=svc.watched_apps(), labels=svc.EVENT_LABELS)


@fleet_bp.route("/fleet/rules/<int:rule_id>", methods=["POST"])
def rule_update(rule_id):
    svc.update_rule(rule_id, request.form.get("severity"), 1 if request.form.get("enabled") else 0)
    return redirect(url_for("fleet.rules"))


@fleet_bp.route("/fleet/apps", methods=["POST"])
def app_add():
    svc.add_app(request.form.get("app_name", ""))
    return redirect(url_for("fleet.rules"))


@fleet_bp.route("/fleet/apps/delete", methods=["POST"])
def app_delete():
    svc.remove_app(request.form.get("app_name", ""))
    return redirect(url_for("fleet.rules"))


@fleet_bp.route("/api/monitoring/readings", methods=["POST"])
def ingest():
    """Agent endpoint (no login; authenticated by the per-device bearer token instead).
    Body: computer_id, cpu/memory/disk percent, optional events [{type, detail}]."""
    auth = request.headers.get("Authorization", "")
    cid = svc.computer_for_token(auth[7:].strip()) if auth.startswith("Bearer ") else None
    if not cid:
        return jsonify(error="invalid token"), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or str(data.get("computer_id")) != cid:
        return jsonify(error="computer_id does not match token"), 403
    keys = ("cpu_percent", "memory_percent", "disk_percent")
    metrics = []
    for key in keys:
        v = data.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
            return jsonify(error=f"invalid {key}"), 400
        metrics.append(float(v))
    events = data.get("events") or []
    if not isinstance(events, list) or len(events) > 20:
        return jsonify(error="events must be a list of at most 20"), 400
    clean = []
    for e in events:
        if not isinstance(e, dict) or e.get("type") not in svc.EVENT_LABELS:
            return jsonify(error="unknown event type"), 400
        clean.append((e["type"], str(e.get("detail") or "")[:200] or None))
    apps = svc.save_report(cid, metrics, str(data.get("hostname") or "")[:100] or None,
                           str(data.get("agent_version") or "")[:20] or None, clean)
    return jsonify(ok=True, watch_apps=apps)
