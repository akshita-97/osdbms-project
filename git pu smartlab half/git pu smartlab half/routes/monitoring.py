
from flask import Blueprint, render_template, jsonify

try:
    from services import monitoring_service as svc
    PSUTIL_ERROR = None
except ImportError as exc:            # psutil not installed in this Python environment
    svc = None
    PSUTIL_ERROR = str(exc)

monitoring_bp = Blueprint("monitoring", __name__)

REFRESH_SECONDS = 10


@monitoring_bp.route("/monitoring")
def index():
    if svc is None:
        return render_template("monitoring.html", psutil_error=PSUTIL_ERROR,
                               info={}, stats=None, refresh_seconds=REFRESH_SECONDS)
    return render_template("monitoring.html", psutil_error=None, info=svc.get_system_info(),
                           stats=svc.get_stats(), refresh_seconds=REFRESH_SECONDS)


@monitoring_bp.route("/monitoring/api/stats")
def api_stats():
    if svc is None:
        return jsonify({"error": f"psutil is not installed: {PSUTIL_ERROR}"}), 500
    return jsonify(svc.get_stats())
