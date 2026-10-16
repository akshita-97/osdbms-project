

from flask import Blueprint, render_template, request, redirect, url_for, flash
from services import maintenance_service as svc

maintenance_bp = Blueprint("maintenance", __name__)


@maintenance_bp.route("/maintenance")
def index():
    status_filter = request.args.get("status")
    requests_list = svc.list_requests(status_filter)
    computers = svc.list_computers()
    technicians = svc.list_technicians()
    available_technicians = [t for t in technicians if t["availability"] == "Available"]
    return render_template(
        "maintenance.html",
        requests=requests_list,
        computers=computers,
        technicians=technicians,
        available_technicians=available_technicians,
        status_filter=status_filter,
        severities=sorted(svc.VALID_SEVERITIES, key=lambda s: svc.SEVERITY_TO_PRIORITY[s]),
        fault_types=sorted(svc.VALID_FAULT_TYPES),
        specializations=sorted(svc.VALID_SPECIALIZATIONS),
    )


@maintenance_bp.route("/maintenance/report-fault", methods=["POST"])
def report_fault():
    try:
        svc.create_manual_request(
            request.form["computer_id"],
            request.form["problem_description"].strip(),
            request.form["fault_type"],
            request.form["severity"],
        )
        flash("Fault reported. A maintenance request has been created for review.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error reporting fault: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/maintenance/requests/<int:request_id>/approve", methods=["POST"])
def approve_request(request_id):
    try:
        svc.approve_request(request_id)
        flash("Request approved.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/maintenance/requests/<int:request_id>/reject", methods=["POST"])
def reject_request(request_id):
    try:
        svc.reject_request(request_id)
        flash("Request rejected.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/maintenance/requests/<int:request_id>/start", methods=["POST"])
def start_request(request_id):
    try:
        svc.start_request(request_id, int(request.form.get("technician_id") or 0))
        flash("Technician assigned and maintenance started.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/maintenance/requests/<int:request_id>/complete", methods=["POST"])
def complete_request(request_id):
    try:
        svc.complete_request(request_id, request.form.get("remarks", "").strip())
        flash("Marked as completed. Moved to History.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/technicians/add", methods=["POST"])
def add_technician():
    try:
        svc.create_technician(
            request.form["name"].strip(),
            request.form["specialization"],
            request.form.get("availability", "Available"),
            request.form.get("contact", "").strip() or None,
        )
        flash("Technician added.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error adding technician: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/technicians/<int:technician_id>/availability", methods=["POST"])
def set_technician_availability(technician_id):
    try:
        svc.set_technician_availability(technician_id, request.form["availability"])
        flash("Technician availability updated.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("maintenance.index"))


@maintenance_bp.route("/tasks/<task_id>/assign-technician", methods=["POST"])
def assign_technician(task_id):
    try:
        svc.assign_technician(task_id, int(request.form["technician_id"]))
        flash("Technician assigned to task.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))


@maintenance_bp.route("/history")
def history():
    computer_id = request.args.get("computer_id")
    if computer_id:
        records = svc.get_history_for_computer(computer_id)
    else:
        records = svc.get_all_history()
    computers = svc.list_computers()
    return render_template("history.html", records=records, computers=computers,
                            computer_filter=computer_id)
