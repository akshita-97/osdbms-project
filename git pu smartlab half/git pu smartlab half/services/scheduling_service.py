

from algorithms.fcfs import run_fcfs
from algorithms.sjf import run_sjf
from algorithms.priority import run_priority
from algorithms.round_robin import run_round_robin
from services.maintenance_service import get_pending_tasks_for_scheduling, ValidationError

ALGORITHMS = {
    "FCFS": run_fcfs,
    "SJF": run_sjf,
    "Priority": run_priority,
}


def run_scheduling(algorithm_name, quantum=None):
    tasks = get_pending_tasks_for_scheduling()
    if not tasks:
        return {"order": [], "gantt": [], "metrics": [], "averages": {},
                "algorithm": algorithm_name, "message": "No pending tasks to schedule."}

    if algorithm_name == "Round Robin":
        result = run_round_robin(tasks, quantum=quantum or 10)
    elif algorithm_name in ALGORITHMS:
        result = ALGORITHMS[algorithm_name](tasks)
    else:
        raise ValidationError(f"Unknown scheduling algorithm '{algorithm_name}'.")

    result["algorithm"] = algorithm_name
    return result
