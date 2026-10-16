
from flask import Blueprint, render_template
from db.database import fetch_all, fetch_one

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    stats = {
        "total_labs": fetch_one("SELECT COUNT(*) AS c FROM labs")["c"],
        "total_computers": fetch_one("SELECT COUNT(*) AS c FROM computers")["c"],
        "computers_under_maintenance": fetch_one(
            "SELECT COUNT(*) AS c FROM computers WHERE status='Under Maintenance'")["c"],
        "pending_tasks": fetch_one(
            "SELECT COUNT(*) AS c FROM maintenance_tasks WHERE status NOT IN ('Completed','Cancelled')")["c"],
        "critical_faults": fetch_one(
            "SELECT COUNT(*) AS c FROM maintenance_requests WHERE severity='Critical' "
            "AND status NOT IN ('Closed','Rejected')")["c"],
        "available_technicians": fetch_one(
            "SELECT COUNT(*) AS c FROM technicians WHERE availability='Available'")["c"],
        "available_resources": fetch_one(
            "SELECT COALESCE(SUM(available_quantity),0) AS c FROM resources")["c"],
        "active_tasks": fetch_one(
            "SELECT COUNT(*) AS c FROM maintenance_tasks WHERE status='In Progress'")["c"],
    }

    recent_requests = fetch_all(
        "SELECT * FROM maintenance_requests ORDER BY reported_at DESC LIMIT 5")
    pending_tasks = fetch_all(
        "SELECT * FROM maintenance_tasks WHERE status NOT IN ('Completed','Cancelled') "
        "ORDER BY arrival_time LIMIT 5")
    resources = fetch_all("SELECT * FROM resources ORDER BY resource_type LIMIT 6")

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_requests=recent_requests,
        pending_tasks=pending_tasks,
        resources=resources,
    )
