
from flask import Blueprint, render_template, request
from services import maintenance_service as svc
from services import scheduling_service

scheduling_bp = Blueprint("scheduling", __name__)


@scheduling_bp.route("/scheduling", methods=["GET", "POST"])
def index():
    tasks = svc.list_tasks()
    result = None
    algorithm = request.form.get("algorithm", "FCFS") if request.method == "POST" else None
    quantum = request.form.get("quantum")

    if request.method == "POST":
        result = scheduling_service.run_scheduling(
            algorithm, quantum=int(quantum) if quantum else None
        )

    return render_template(
        "scheduling.html",
        tasks=tasks,
        result=result,
        algorithm=algorithm,
    )
