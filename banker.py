
from flask import Blueprint, jsonify, render_template, request

from services import banker_service as svc

banker_bp = Blueprint("banker", __name__)


@banker_bp.route("/execution-flow")
def index():
    return render_template("banker.html", s=svc.get_state())


@banker_bp.route("/execution-flow/partial")
def partial():
    """Available Resources + matrices (polled); the Result panel is included only after the Result button (?result=1)."""
    return render_template("_banker_state.html", s=svc.get_state(), show_result=request.args.get("result") == "1")


@banker_bp.route("/execution-flow/tasks")
def tasks():
    """Rows of the task table (polled and merged, so typing is never overwritten)."""
    return render_template("_banker_tasks.html", s=svc.get_state())


@banker_bp.route("/execution-flow/allocated")
def allocated():
    """Rows of the Request table (polled and merged like the task table)."""
    return render_template("_banker_alloc.html", s=svc.get_state())


@banker_bp.route("/execution-flow/request", methods=["POST"])
def request_resources():
    """Request resources for one task. Granted in full only if Request <= Need, <= Available and the state stays SAFE."""
    task_id = request.form.get("task_id", "")
    try:
        req = {int(k[2 + len(task_id):]): int(v or 0) for k, v in request.form.items()
               if k.startswith(f"r_{task_id}_") and (v or "0").strip().isdigit()}
        res = svc.request_resources(task_id, req)
    except svc.ValidationError as e:
        return jsonify(ok=False, message=str(e)), 400
    except Exception as e:                      # database error: transaction rolled back
        return jsonify(ok=False, message=f"Something went wrong, nothing was saved: {e}"), 500
    return jsonify(ok=res["approved"], message=res["message"])


@banker_bp.route("/execution-flow/start", methods=["POST"])
def start():
    task_id = request.form.get("task_id", "")
    try:
        req = {}
        for key, value in request.form.items():
            prefix = f"r_{task_id}_"
            if key.startswith(prefix):
                raw = (value or "").strip() or "0"          # an empty box counts as 0
                if not raw.isdigit():
                    raise svc.ValidationError("Enter whole-number resource quantities (0 or more).")
                req[int(key[len(prefix):])] = int(raw)
        return jsonify(ok=True, message=svc.start_task(task_id, req))
    except svc.ValidationError as e:
        return jsonify(ok=False, message=str(e)), 400


@banker_bp.route("/execution-flow/complete", methods=["POST"])
def complete():
    try:
        return jsonify(ok=True, message=svc.complete_task(request.form.get("task_id", "")))
    except svc.ValidationError as e:
        return jsonify(ok=False, message=str(e)), 400


@banker_bp.route("/execution-flow/calculate", methods=["POST"])
def calculate():
    try:
        errors = svc.save_requirements(request.form)
    except Exception as e:                      # database error: nothing was saved
        return jsonify(ok=False, message=f"Something went wrong, nothing was saved: {e}"), 500
    return jsonify(ok=not errors, message=" ".join(errors) if errors else "Saved. The result is updated.")
