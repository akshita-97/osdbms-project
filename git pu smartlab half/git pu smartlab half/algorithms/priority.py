
def run_priority(tasks):
    if not tasks:
        return {"order": [], "gantt": [], "metrics": [], "averages": {}}

    remaining = [dict(t, _orig_index=i) for i, t in enumerate(tasks)]

    current_time = 0
    gantt = []
    metrics = []
    order = []

    while remaining:
        arrived = [t for t in remaining if t["arrival_time"] <= current_time]

        if not arrived:
            next_arrival = min(t["arrival_time"] for t in remaining)
            current_time = next_arrival
            arrived = [t for t in remaining if t["arrival_time"] <= current_time]

        chosen = min(arrived, key=lambda t: (t["priority"], t["arrival_time"], t["_orig_index"]))

        start_time = current_time
        completion_time = start_time + chosen["service_time"]
        response_time = start_time - chosen["arrival_time"]
        turnaround_time = completion_time - chosen["arrival_time"]
        waiting_time = turnaround_time - chosen["service_time"]

        gantt.append({"task_id": chosen["task_id"], "start": start_time, "end": completion_time})
        order.append(chosen["task_id"])
        metrics.append({
            "task_id": chosen["task_id"],
            "arrival_time": chosen["arrival_time"],
            "service_time": chosen["service_time"],
            "priority": chosen.get("priority"),
            "completion_time": completion_time,
            "turnaround_time": turnaround_time,
            "waiting_time": waiting_time,
            "response_time": response_time,
        })

        current_time = completion_time
        remaining.remove(chosen)

    n = len(metrics)
    averages = {
        "avg_waiting_time": round(sum(m["waiting_time"] for m in metrics) / n, 2),
        "avg_turnaround_time": round(sum(m["turnaround_time"] for m in metrics) / n, 2),
        "avg_response_time": round(sum(m["response_time"] for m in metrics) / n, 2),
    }

    return {"order": order, "gantt": gantt, "metrics": metrics, "averages": averages}
