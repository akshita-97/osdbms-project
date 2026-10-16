

from flask import Blueprint, render_template, request, redirect, url_for, flash
from services import resource_service as rsvc
from services import maintenance_service as msvc

resources_bp = Blueprint("resources", __name__)


@resources_bp.route("/resources")
def index():
    resources = rsvc.list_resources()
    tasks = msvc.list_tasks()
    return render_template("resources.html", resources=resources, tasks=tasks,
                           resource_types=sorted(rsvc.VALID_RESOURCE_TYPES))


@resources_bp.route("/resources/add", methods=["POST"])
def add_resource():
    try:
        rsvc.create_resource(
            request.form["resource_name"].strip(),
            request.form["resource_type"],
            int(request.form["total_quantity"]),
        )
        flash("Resource added.", "success")
    except (rsvc.ValidationError, Exception) as e:
        flash(f"Error adding resource: {e}", "error")
    return redirect(url_for("resources.index"))


@resources_bp.route("/resources/<int:resource_id>/update-total", methods=["POST"])
def update_total(resource_id):
    try:
        rsvc.update_resource_total(resource_id, int(request.form["total_quantity"]))
        flash("Resource quantity updated.", "success")
    except (rsvc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("resources.index"))


@resources_bp.route("/tasks/<task_id>/requirements/add", methods=["POST"])
def add_requirement(task_id):
    try:
        rsvc.set_task_requirement(
            task_id, int(request.form["resource_id"]), int(request.form["maximum_required"])
        )
        flash("Resource requirement saved.", "success")
    except (rsvc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))


# ------------------------------------------------------- MAINTENANCE EXECUTION
@resources_bp.route("/tasks/<task_id>/execution")
def execution(task_id):
    task = msvc.get_task(task_id)
    if not task:
        flash("Task not found.", "error")
        return redirect(url_for("maintenance.index"))
    requirements = rsvc.get_task_requirements(task_id)
    resources = rsvc.list_resources()
    technicians = msvc.list_technicians()
    return render_template(
        "execution.html", task=task, requirements=requirements,
        resources=resources, technicians=technicians,
    )


@resources_bp.route("/tasks/<task_id>/allocate", methods=["POST"])
def allocate(task_id):
    try:
        result = rsvc.allocate_resources_for_task(task_id)
        flash(result["message"], "success" if result["success"] else "error")
    except (rsvc.ValidationError, Exception) as e:
        flash(f"Error allocating resources: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))


@resources_bp.route("/tasks/<task_id>/start", methods=["POST"])
def start_task(task_id):
    try:
        msvc.set_task_status(task_id, "In Progress")
        flash("Maintenance started.", "success")
    except (msvc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))


@resources_bp.route("/tasks/<task_id>/complete", methods=["POST"])
def complete_task(task_id):
    try:
        msvc.complete_task_and_log_history(
            task_id,
            request.form.get("remarks", "").strip(),
            request.form.get("resources_used_summary", "").strip(),
        )
        flash("Maintenance marked as completed. Don't forget to release resources.", "success")
    except (msvc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))


@resources_bp.route("/tasks/<task_id>/release", methods=["POST"])
def release(task_id):
    try:
        summary = rsvc.release_resources_for_task(task_id)
        flash(f"Resources released: {summary}", "success")
    except (rsvc.ValidationError, Exception) as e:
        flash(f"Error releasing resources: {e}", "error")
    return redirect(url_for("resources.execution", task_id=task_id))
