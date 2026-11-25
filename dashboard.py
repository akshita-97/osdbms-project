
from flask import Blueprint, render_template
from db.database import fetch_one

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    stats = {
        "total_labs": fetch_one("SELECT COUNT(*) AS c FROM labs")["c"],
        "total_computers": fetch_one("SELECT COUNT(*) AS c FROM computers")["c"],
        "pending_tasks": fetch_one(
            "SELECT COUNT(*) AS c FROM maintenance_tasks WHERE status NOT IN ('Completed','Cancelled')")["c"],
        "critical_faults": fetch_one(
            "SELECT COUNT(*) AS c FROM maintenance_requests WHERE severity='Critical' "
            "AND status NOT IN ('Closed','Rejected')")["c"],
    }
    return render_template("dashboard.html", stats=stats)
