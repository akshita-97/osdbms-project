
from flask import Blueprint, render_template, request, redirect, url_for, flash
from services import maintenance_service as svc

computers_bp = Blueprint("computers", __name__)


@computers_bp.route("/labs")
def list_labs():
    labs = svc.list_labs()
    return render_template("computers.html", labs=labs, computers=None, view="labs")


@computers_bp.route("/labs/add", methods=["POST"])
def add_lab():
    try:
        svc.create_lab(
            request.form["lab_id"].strip(),
            request.form["lab_name"].strip(),
            request.form["location"].strip(),
            request.form["capacity"],
            request.form.get("status", "Active"),
        )
        flash("Lab added successfully.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error adding lab: {e}", "error")
    return redirect(url_for("computers.list_labs"))


@computers_bp.route("/labs/<lab_id>/edit", methods=["POST"])
def edit_lab(lab_id):
    try:
        svc.update_lab(
            lab_id,
            request.form["lab_name"].strip(),
            request.form["location"].strip(),
            request.form["capacity"],
            request.form["status"],
        )
        flash("Lab updated.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error updating lab: {e}", "error")
    return redirect(url_for("computers.list_labs"))


@computers_bp.route("/labs/<lab_id>/delete", methods=["POST"])
def delete_lab(lab_id):
    try:
        svc.delete_lab(lab_id)
        flash("Lab deleted.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error deleting lab: {e}", "error")
    return redirect(url_for("computers.list_labs"))


# ------------------------------------------------------------ COMPUTERS
@computers_bp.route("/computers")
def list_computers():
    lab_filter = request.args.get("lab_id")
    computers = svc.list_computers(lab_filter)
    labs = svc.list_labs()
    return render_template("computers.html", labs=labs, computers=computers, view="computers",
                           lab_filter=lab_filter)


@computers_bp.route("/computers/add", methods=["POST"])
def add_computer():
    try:
        svc.create_computer(
            request.form["computer_id"].strip(),
            request.form["lab_id"],
            request.form.get("ip_address", "").strip(),
            request.form.get("processor", "").strip(),
            request.form.get("ram_gb") or None,
            request.form.get("storage_gb") or None,
            request.form.get("os_name", "").strip(),
            request.form.get("status", "Available"),
        )
        flash("Computer added successfully.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error adding computer: {e}", "error")
    return redirect(url_for("computers.list_computers"))


@computers_bp.route("/computers/<computer_id>/edit", methods=["POST"])
def edit_computer(computer_id):
    try:
        svc.update_computer(
            computer_id,
            request.form["lab_id"],
            request.form.get("ip_address", "").strip(),
            request.form.get("processor", "").strip(),
            request.form.get("ram_gb") or None,
            request.form.get("storage_gb") or None,
            request.form.get("os_name", "").strip(),
        )
        flash("Computer updated.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error updating computer: {e}", "error")
    return redirect(url_for("computers.list_computers"))


@computers_bp.route("/computers/<computer_id>/status", methods=["POST"])
def change_status(computer_id):
    try:
        svc.set_computer_status(computer_id, request.form["status"])
        flash("Computer status updated.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("computers.list_computers"))


@computers_bp.route("/computers/<computer_id>/delete", methods=["POST"])
def delete_computer(computer_id):
    try:
        svc.delete_computer(computer_id)
        flash("Computer deleted.", "success")
    except (svc.ValidationError, Exception) as e:
        flash(f"Error deleting computer: {e}", "error")
    return redirect(url_for("computers.list_computers"))
