
def run_round_robin(tasks, quantum=10):
    if not tasks:
        return {"order": [], "gantt": [], "metrics": [], "averages": {}}

    queue_tasks = [dict(t, remaining=t["service_time"], started=False,
                         start_time=None, completion_time=None)
                   for t in tasks]
    queue_tasks.sort(key=lambda t: t["arrival_time"])

    n = len(queue_tasks)
    current_time = queue_tasks[0]["arrival_time"]
    ready_queue = []
    gantt = []
    order = []

    not_arrived = list(queue_tasks)
    finished_count = 0

    def load_arrivals(now):
        arrivals = [t for t in not_arrived if t["arrival_time"] <= now]
        for t in arrivals:
            ready_queue.append(t)
            not_arrived.remove(t)

    load_arrivals(current_time)

    while finished_count < n:
        if not ready_queue:
            # Idle: jump to next arrival
            current_time = min(t["arrival_time"] for t in not_arrived)
            load_arrivals(current_time)
            continue

        task = ready_queue.pop(0)
        if not task["started"]:
            task["started"] = True
            task["start_time"] = current_time

        run_time = min(quantum, task["remaining"])
        seg_start = current_time
        seg_end = current_time + run_time
        gantt.append({"task_id": task["task_id"], "start": seg_start, "end": seg_end})
        order.append(task["task_id"])

        current_time = seg_end
        task["remaining"] -= run_time

        load_arrivals(current_time)

        if task["remaining"] > 0:
            ready_queue.append(task)
        else:
            task["completion_time"] = current_time
            finished_count += 1

    metrics = []
    for t in queue_tasks:
        turnaround = t["completion_time"] - t["arrival_time"]
        waiting = turnaround - t["service_time"]
        response = t["start_time"] - t["arrival_time"]
        metrics.append({
            "task_id": t["task_id"],
            "arrival_time": t["arrival_time"],
            "service_time": t["service_time"],
            "priority": t.get("priority"),
            "completion_time": t["completion_time"],
            "turnaround_time": turnaround,
            "waiting_time": waiting,
            "response_time": response,
        })

    id_to_index = {t["task_id"]: i for i, t in enumerate(tasks)}
    metrics.sort(key=lambda m: id_to_index[m["task_id"]])

    count = len(metrics)
    averages = {
        "avg_waiting_time": round(sum(m["waiting_time"] for m in metrics) / count, 2),
        "avg_turnaround_time": round(sum(m["turnaround_time"] for m in metrics) / count, 2),
        "avg_response_time": round(sum(m["response_time"] for m in metrics) / count, 2),
    }

    return {"order": order, "gantt": gantt, "metrics": metrics, "averages": averages,
            "quantum": quantum, "note": "Academic scheduling simulation (optional)."}
