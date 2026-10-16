
def run_fcfs(tasks):
    if not tasks:
        return {"order": [], "gantt": [], "metrics": [], "averages": {}}

    indexed = list(enumerate(tasks))
    ordered = sorted(indexed, key=lambda pair: (pair[1]["arrival_time"], pair[0]))

    current_time = 0
    gantt = []
    metrics = []
    order = []

    for _, task in ordered:
        arrival = task["arrival_time"]
        service = task["service_time"]

        start_time = max(current_time, arrival)
        completion_time = start_time + service

        response_time = start_time - arrival       
        turnaround_time = completion_time - arrival
        waiting_time = turnaround_time - service

        gantt.append({"task_id": task["task_id"], "start": start_time, "end": completion_time})
        order.append(task["task_id"])
        metrics.append({
            "task_id": task["task_id"],
            "arrival_time": arrival,
            "service_time": service,
            "priority": task.get("priority"),
            "completion_time": completion_time,
            "turnaround_time": turnaround_time,
            "waiting_time": waiting_time,
            "response_time": response_time,
        })

        current_time = completion_time

    n = len(metrics)
    averages = {
        "avg_waiting_time": round(sum(m["waiting_time"] for m in metrics) / n, 2),
        "avg_turnaround_time": round(sum(m["turnaround_time"] for m in metrics) / n, 2),
        "avg_response_time": round(sum(m["response_time"] for m in metrics) / n, 2),
    }

    return {"order": order, "gantt": gantt, "metrics": metrics, "averages": averages}
