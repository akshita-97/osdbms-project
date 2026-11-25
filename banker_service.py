
import json

from db.database import execute, execute_transaction, fetch_all, fetch_one, get_connection
from services import maintenance_service as msvc
from services import resource_service as rs
from services.maintenance_service import ValidationError

ACTIVE = ("Pending", "Scheduled", "Waiting for Resource", "Resources Allocated", "In Progress")
TYPE_ORDER = ("Technician", "RAM", "Network Tester", "Keyboard", "Mouse", "OS Installation Kit", "Other")
DEMO_PREFIX = "[Banker demo] "

# (PC, issue, fault type, severity, Max over (Technician, RAM, Network Tester, Keyboard, Mouse, OS Kit))
DEMO_PCS = [
    ("PC-01", "RAM issue", "Hardware", "High", (1, 2, 0, 0, 0, 0)),
    ("PC-02", "Network issue", "Network", "Medium", (1, 0, 1, 0, 0, 0)),
    ("PC-03", "RAM and network issue", "Hardware", "High", (1, 2, 1, 0, 0, 0)),
    ("PC-04", "Network issue", "Network", "Low", (1, 0, 1, 0, 0, 0)),
    ("PC-05", "General maintenance", "Other", "Low", (1, 1, 0, 1, 1, 0)),
    ("PC-06", "OS repair", "Software", "Critical", (1, 0, 0, 0, 0, 1)),
]
DEMO_TYPES = TYPE_ORDER[:6]
DEFAULT_TOTALS = (4, 3, 2, 3, 3, 1)


# ------------------------------------------------------------ the algorithm (pure)
def safe_sequence(available, maximum, allocation):
    """
    Banker's safety algorithm. Work = Available; Finish[i] = False. Repeatedly pick an unfinished task with
    Need <= Work, let it finish and add its Allocation back to Work. Returns (is_safe, steps, need, work).
    A step holds: the task index, Work before, Need, Max (what it releases on completion) and Work after.
    """
    n = len(maximum)
    need = [[m - a for m, a in zip(maximum[i], allocation[i])] for i in range(n)]
    work, finish, steps = list(available), [False] * n, []
    while True:
        i = next((k for k in range(n) if not finish[k] and all(x <= w for x, w in zip(need[k], work))), None)
        if i is None:
            return all(finish), steps, need, work
        before, work = work, [w + a for w, a in zip(work, allocation[i])]
        finish[i] = True
        steps.append({"i": i, "before": before, "need": need[i], "release": maximum[i], "after": work})


def _fmt(vec, names):
    return ", ".join(f"{q} x {n}" for q, n in zip(vec, names) if q) or "nothing"


def evaluate_request(available, maximum, allocation, i, request, names, labels):
    """
    Banker's resource-request algorithm for task i. Nothing is modified: the allocation is tentative (done on
    copies), so a rejected request leaves the committed state untouched.
    Returns {approved, code, message, steps, stuck}; code is OK, INVALID, EXCEEDS_NEED, INSUFFICIENT or UNSAFE.
    """
    need = [m - a for m, a in zip(maximum[i], allocation[i])]
    base = {"approved": False, "steps": [], "stuck": []}
    if any(q < 0 for q in request) or not any(request):
        return {**base, "code": "INVALID", "message": "Request at least one resource (whole numbers, 0 or more)."}
    over = [(q, n, d) for q, n, d in zip(request, names, need) if q > d]
    if over:
        q, n, d = over[0]
        return {**base, "code": "EXCEEDS_NEED", "message":
                f"Request exceeds maximum Need: {labels[i]} asked for {q} x {n} but needs only {d} more."}
    short = [(q, n, a) for q, n, a in zip(request, names, available) if q > a]
    if short:
        q, n, a = short[0]
        return {**base, "code": "INSUFFICIENT", "message":
                f"Insufficient resources: {labels[i]} asked for {q} x {n} but only {a} available. It keeps waiting."}
    trial_avail = [a - q for a, q in zip(available, request)]
    trial_alloc = [list(row) for row in allocation]
    trial_alloc[i] = [a + q for a, q in zip(trial_alloc[i], request)]
    safe, steps, _, _ = safe_sequence(trial_avail, maximum, trial_alloc)
    if not safe:
        done = {s["i"] for s in steps}
        stuck = [labels[k] for k in range(len(maximum)) if k not in done]
        return {**base, "code": "UNSAFE", "stuck": stuck, "message":
                "UNSAFE ALLOCATION REQUEST: the resources are available, but granting them would leave no safe "
                f"sequence. Tasks that could not finish: {', '.join(stuck)}. Nothing was allocated."}
    return {"approved": True, "code": "OK", "steps": steps, "stuck": [],
            "message": f"Approved: {_fmt(request, names)} allocated to {labels[i]}. The state stays safe."}


# ------------------------------------------------------------ database state
TABLE = """
CREATE TABLE IF NOT EXISTS allocation_requests (
    request_id     INT AUTO_INCREMENT PRIMARY KEY,
    task_id        VARCHAR(15) NOT NULL,
    request_vector VARCHAR(200) NOT NULL,
    decision       ENUM('Approved','Rejected') NOT NULL,
    reason_code    ENUM('OK','INVALID','EXCEEDS_NEED','INSUFFICIENT','UNSAFE') NOT NULL,
    message        VARCHAR(500) NOT NULL,
    decided_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_alloc_req_task (task_id, request_id),
    FOREIGN KEY (task_id) REFERENCES maintenance_tasks(task_id) ON DELETE CASCADE ON UPDATE CASCADE
)"""


def ensure_tables():
    execute(TABLE)


def _load_state(cur, lock=False):
    """Everything Banker's needs, read from the real tables. lock=True locks the resource rows (FOR UPDATE)."""
    order = "FIELD(resource_type, " + ", ".join(f"'{t}'" for t in TYPE_ORDER) + "), resource_id"
    cur.execute("SELECT resource_id, resource_name, resource_type, total_quantity, available_quantity "
                f"FROM resources WHERE status='Active' ORDER BY {order}" + (" FOR UPDATE" if lock else ""))
    res = cur.fetchall()
    cur.execute("SELECT resource_id, task_id, SUM(quantity) AS q FROM resource_allocations "
                "WHERE status='Allocated' GROUP BY resource_id, task_id")
    held = {(r["task_id"], r["resource_id"]): int(r["q"]) for r in cur.fetchall()}
    cur.execute("SELECT t.task_id, t.computer_id, t.request_id, t.status, r.problem_description, r.severity "
                "FROM maintenance_tasks t JOIN maintenance_requests r ON r.request_id = t.request_id "
                f"WHERE t.status IN ({','.join(['%s'] * len(ACTIVE))}) ORDER BY t.priority, t.arrival_time, t.task_id",
                ACTIVE)
    tasks = cur.fetchall()
    cur.execute("SELECT task_id, resource_id, maximum_required FROM task_resources")
    maxes = {(r["task_id"], r["resource_id"]): r["maximum_required"] for r in cur.fetchall()}
    for t in tasks:
        t["max"] = [maxes.get((t["task_id"], r["resource_id"]), 0) for r in res]
        t["alloc"] = [held.get((t["task_id"], r["resource_id"]), 0) for r in res]
        t["need"] = [m - a for m, a in zip(t["max"], t["alloc"])]
        t["label"] = f"{t['computer_id']} ({t['task_id']})"
    for r in res:
        r["allocated"] = sum(q for (tid, rid), q in held.items() if rid == r["resource_id"])
        r["available"] = r["total_quantity"] - r["allocated"]
    return {"resources": res, "tasks": tasks, "in_algo": [t for t in tasks if any(t["max"])],
            "drift": [r["resource_name"] for r in res if r["available"] != r["available_quantity"]]}


def _matrices(state):
    ok = state["in_algo"]
    return ([r["available"] for r in state["resources"]], [t["max"] for t in ok], [t["alloc"] for t in ok],
            [r["resource_name"] for r in state["resources"]], [t["label"] for t in ok])


def _vec(res, request):
    return [int(request.get(r["resource_id"], 0) or 0) for r in res]


def _require_exact(res, vec, need):
    """Same rule for EVERY task, whatever it already holds: the Request Resources row must equal the remaining Need."""
    for r, asked, needed in zip(res, vec, need):
        if asked != needed:
            raise ValidationError(
                f"{r['resource_name']}: this task needs exactly {needed}, "
                f"but the Request Resources table has {asked}. Correct the quantity before starting.")


# ------------------------------------------------------------ allocation request (transactional)
def request_resources(task_id, request, dry_run=False):
    """
    Request resources for a task. `request` maps resource_id -> quantity. Runs Banker's resource-request
    algorithm inside one transaction (resource rows locked FOR UPDATE, state read inside the lock). Approved
    requests are written (allocation rows + task status); rejected ones change nothing but the decision log.
    dry_run=True only reports what would happen.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        state = _load_state(cur, lock=not dry_run)
        ok = state["in_algo"]
        i = next((k for k, t in enumerate(ok) if t["task_id"] == task_id), None)
        if i is None:
            known = any(t["task_id"] == task_id for t in state["tasks"])
            raise ValidationError("Define the task's maximum requirement first." if known
                                  else "Task not found or already completed.")
        res, task = state["resources"], ok[i]
        vec = _vec(res, request)
        # Execution Flow starts a task only when every requested quantity exactly
        # matches that task's remaining Need (including zero for unused resources).
        _require_exact(res, vec, task["need"])
        avail, mx, al, names, labels = _matrices(state)
        result = evaluate_request(avail, mx, al, i, vec, names, labels)
        if dry_run:
            conn.rollback()
            return result
        cur.execute("INSERT INTO allocation_requests (task_id, request_vector, decision, reason_code, message) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (task_id, json.dumps({str(r["resource_id"]): q for r, q in zip(res, vec) if q}),
                     "Approved" if result["approved"] else "Rejected", result["code"], result["message"][:500]))
        if not result["approved"] and result["code"] in ("INSUFFICIENT", "UNSAFE") \
                and task["status"] in ("Pending", "Scheduled") and not any(task["alloc"]):
            cur.execute("UPDATE maintenance_tasks SET status=%s WHERE task_id=%s", ("Waiting for Resource", task_id))
        if result["approved"]:
            for r, q in zip(res, vec):
                if q:                              # trigger trg_after_allocation_insert keeps the stock counter
                    cur.execute("INSERT INTO resource_allocations (task_id, resource_id, quantity, status) "
                                "VALUES (%s,%s,%s,'Allocated')", (task_id, r["resource_id"], q))
                    cur.execute("UPDATE task_resources SET currently_allocated = currently_allocated + %s "
                                "WHERE task_id=%s AND resource_id=%s", (q, task_id, r["resource_id"]))
            if task["status"] in ("Pending", "Scheduled", "Waiting for Resource", "Resources Allocated"):
                full = all(n - q == 0 for n, q in zip(task["need"], vec))
                cur.execute("UPDATE maintenance_tasks SET status=%s WHERE task_id=%s",
                            ("Resources Allocated" if full else "Waiting for Resource", task_id))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def start_task(task_id, request=None):
    """
    Start only the first task in the current Banker's safe sequence. The same checks run for every task:
    the quantities in the Request Resources row must equal the task's remaining Need, then they are allocated
    (Banker's request check) and only after that does the task become 'In Progress'.
    """
    state = get_state()
    first_id = next((step["label"] for step in state["steps"]), None)
    if not first_id or task_id != first_id:
        raise ValidationError("Only the first task in the Result safe sequence can be started.")

    task = next((t for t in state["tasks"] if t["task_id"] == task_id and any(t["max"])), None)
    if not task:
        raise ValidationError("Task not found or no resource requirement is defined.")
    if task["started"]:
        raise ValidationError("This task has already been started.")
    if request is None:
        raise ValidationError("Enter the exact Need quantities before starting this task.")

    _require_exact(state["resources"], _vec(state["resources"], request), task["need"])
    if any(task["need"]):                      # still has resources to take -> Banker's request check + allocation
        result = request_resources(task_id, request)
        if not result["approved"]:
            raise ValidationError(result["message"])
    # everything is allocated now: make sure the status allows the start, then start
    execute("UPDATE maintenance_tasks SET status='Resources Allocated' "
            "WHERE task_id=%s AND status IN ('Pending','Scheduled','Waiting for Resource')", (task_id,))
    msvc.set_task_status(task_id, "In Progress")
    return f"{task_id} started. Complete it to release its resources and move to the next task."


def complete_task(task_id, remarks="Completed from Execution Flow"):
    """Existing completion workflow: logs history and releases the task's resources (single mechanism).
    Allowed only for a task that was started here (Start first, then Complete)."""
    task = msvc.get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    live = next((t for t in get_state()["tasks"] if t["task_id"] == task_id), None)
    if live is not None and not live["actions"]["complete"]:
        raise ValidationError(f"{task_id} has not been started. Click Start first; Complete is available only after Start.")
    msvc.complete_request(task["request_id"], remarks)
    return f"{task_id} completed. Its resources were released and are available again."


# ------------------------------------------------------------ dashboard data
def _stamp(v):
    return v.strftime("%H:%M:%S") if v else ""


RESULT_TEXT = {   # decision code -> (heading, short explanation, tone)
    "OK": ("ALLOCATION APPROVED", "Resources allocated successfully. The system remains in a safe state.", "success"),
    "UNSAFE": ("ALLOCATION REJECTED", "UNSAFE ALLOCATION REQUEST: this request would make the system unsafe. "
               "No resources were allocated.", "danger"),
    "INSUFFICIENT": ("INSUFFICIENT RESOURCES", "The requested resources are currently unavailable.", "warning"),
    "EXCEEDS_NEED": ("INVALID REQUEST", "The requested quantity exceeds the remaining resource requirement.", "warning"),
    "INVALID": ("INVALID REQUEST", "Request at least one resource, using whole numbers.", "warning"),
}


def list_computers():
    return fetch_all("SELECT computer_id, lab_id FROM computers ORDER BY computer_id")


def get_state():
    """Everything the Execution Flow page shows (read-only; waiting requests are re-evaluated, never auto-allocated)."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        state = _load_state(cur)
        cur.execute("SELECT task_id, request_vector, decision, reason_code, decided_at FROM allocation_requests "
                    "ORDER BY request_id DESC LIMIT 1")
        last = cur.fetchall()
        cur.execute("SELECT a.task_id, a.request_vector FROM allocation_requests a WHERE a.decision='Rejected' "
                    "AND a.reason_code IN ('INSUFFICIENT','UNSAFE') AND a.request_id = "
                    "(SELECT MAX(request_id) FROM allocation_requests WHERE task_id = a.task_id)")
        waiting_rows = cur.fetchall()
        conn.rollback()
    finally:
        conn.close()
    res, ok = state["resources"], state["in_algo"]
    avail, mx, al, names, labels = _matrices(state)
    safe, steps, _, _ = safe_sequence(avail, mx, al)
    for s_ in steps:
        s_["label"] = ok[s_["i"]]["task_id"]
    done = {s_["i"] for s_ in steps}
    waiting = {}
    for w in waiting_rows:
        k = next((n for n, t in enumerate(ok) if t["task_id"] == w["task_id"]), None)
        if k is not None:
            vec = _vec(res, {int(a): b for a, b in json.loads(w["request_vector"]).items()})
            waiting[w["task_id"]] = {"eligible": evaluate_request(avail, mx, al, k, vec, names, labels)["approved"],
                                     "vector": {r["resource_id"]: q for r, q in zip(res, vec) if q}}
    for k, t in enumerate(ok):
        t["finish"] = k in done

    # A task is "started" only when Start was clicked: In Progress AND everything it needs is allocated.
    # (A task that is marked In Progress elsewhere but still lacks resources has NOT been started here.)
    for t in ok:
        t["started"] = t["status"] == "In Progress" and not any(t["need"])
    for t in state["tasks"]:
        t.setdefault("started", False)
        t["status_db"] = t["status"]
        if t["status"] == "In Progress" and not t["started"] and any(t["max"]):
            t["status"] = "Waiting for Resource" if any(t["alloc"]) else "Pending"
    # A running task needs nothing more, so it can always finish: keep it at the front until it is completed.
    steps.sort(key=lambda s_: not ok[s_["i"]]["started"])

    # Put the Request Resources rows in exactly the same order as the Result sequence.
    sequence_ids = [ok[step["i"]]["task_id"] for step in steps]
    task_by_id = {t["task_id"]: t for t in state["tasks"]}
    state["tasks"] = ([task_by_id[tid] for tid in sequence_ids if tid in task_by_id] +
                      [t for t in state["tasks"] if t["task_id"] not in sequence_ids])
    first_sequence_id = sequence_ids[0] if sequence_ids else None

    for t in state["tasks"]:
        w = waiting.get(t["task_id"])
        t["waiting"] = w
        held = sum(t["alloc"])
        t["alloc_status"] = ("No maximum defined" if not any(t["max"])
                             else "Waiting, eligible now" if w and w["eligible"] else "Waiting for resources" if w
                             else "Fully allocated" if not any(t["need"]) else "Partially allocated" if held
                             else "Not allocated")
        has_max = any(t["max"])
        is_first = t["task_id"] == first_sequence_id
        t["actions"] = {
            "allocate": False,
            "start": bool(is_first and has_max and not t["started"]),        # Start first ...
            "complete": bool(is_first and has_max and t["started"]),         # ... Complete only after Start
            "waiting": not (is_first and has_max),
            "cancel": True,
            "approve_waiting": False
        }
        # Shown in both Execution Flow tables: everything is Pending; only the top task is Waiting for Resource.
        t["flow_status"] = ("In Progress" if t["started"] else
                            "Waiting for Resource" if is_first and has_max else "Pending")
        t["need_by_id"] = {r["resource_id"]: n for r, n in zip(res, t["need"]) if n}
        t["request"] = [(w["vector"].get(r["resource_id"], 0) if w else 0) for r in res]
    result = None
    if last:
        heading, text, tone = RESULT_TEXT.get(last[0]["reason_code"], RESULT_TEXT["INVALID"])
        pc = next((t["computer_id"] for t in state["tasks"] if t["task_id"] == last[0]["task_id"]), last[0]["task_id"])
        result = {"heading": heading, "text": text, "tone": tone, "pc": pc, "at": _stamp(last[0]["decided_at"])}
    return {"resources": res, "tasks": state["tasks"], "in_algo": ok, "safe": safe and bool(ok), "steps": steps,
            "available": avail, "result": result, "drift": state["drift"],
            "waiting_tasks": [t for t in state["tasks"] if t["waiting"] or t["status"] == "Waiting for Resource"],
            "unentered": [t["task_id"] for t in state["tasks"] if not any(t["max"])],
            "sequence": " -> ".join(s_["label"] for s_ in steps)}


# ------------------------------------------------------------ resources required per task (typed on the page)
def save_requirements(form):
    """
    Save the numbers typed on the Execution Flow page (fields m_<task>_<resource>) as each task's Maximum
    requirement. All-or-nothing under the resource lock: returns a list of error messages and saves nothing if any.
    A value of 0 removes that resource row; a value below what the task already holds is refused.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        state = _load_state(cur, lock=True)
        errors, changes = [], []
        for t in state["tasks"]:
            for j, r in enumerate(state["resources"]):
                raw = form.get(f"m_{t['task_id']}_{r['resource_id']}")
                if raw is None:
                    continue
                label = f"{t['task_id']} / {r['resource_name']}"
                raw = raw.strip() or "0"
                if not raw.isdigit() or int(raw) > 1000:
                    errors.append(f"{label}: enter a whole number (0 or more).")
                elif int(raw) > r["total_quantity"]:
                    errors.append(f"{label}: only {r['total_quantity']} exist in total.")
                elif int(raw) < t["alloc"][j]:
                    errors.append(f"{label}: cannot be below the {t['alloc'][j]} already allocated.")
                elif int(raw) != t["max"][j]:
                    changes.append((t["task_id"], r["resource_id"], int(raw), t["alloc"][j]))
        if errors:
            conn.rollback()
            return errors
        for tid, rid, q, held in changes:
            if q == 0:
                cur.execute("DELETE FROM task_resources WHERE task_id=%s AND resource_id=%s", (tid, rid))
            else:
                cur.execute("INSERT INTO task_resources (task_id, resource_id, maximum_required, currently_allocated) "
                            "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE maximum_required=%s", (tid, rid, q, held, q))
        conn.commit()
        return []
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------ per-task resource requirements (Maximum)
def get_requirements(task_id):
    """Rows of the Resource Requirements table for one task: Max required, Currently allocated, Available."""
    conn = get_connection()
    try:
        state = _load_state(conn.cursor(dictionary=True))
        conn.rollback()
    finally:
        conn.close()
    task = next((t for t in state["tasks"] if t["task_id"] == task_id), None)
    if task is None:
        raise ValidationError("Task not found or already finished.")
    rows = [{"resource_id": r["resource_id"], "name": r["resource_name"], "max": m, "alloc": a, "available": r["available"]}
            for r, m, a in zip(state["resources"], task["max"], task["alloc"]) if m or a]
    return {"task": task, "rows": rows, "resources": state["resources"]}


def _requirement_context(cur, task_id, resource_id):
    state = _load_state(cur, lock=True)                        # same lock as allocation requests
    task = next((t for t in state["tasks"] if t["task_id"] == task_id), None)
    if task is None:
        raise ValidationError("Task not found or already finished.")
    j = next((k for k, r in enumerate(state["resources"]) if r["resource_id"] == resource_id), None)
    if j is None:
        raise ValidationError("Unknown resource.")
    return state, task, j


def save_requirement(task_id, resource_id, qty):
    """Add or update one Maximum row of a task. Never below what is already allocated, never above the total."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        state, task, j = _requirement_context(cur, task_id, resource_id)
        r = state["resources"][j]
        if qty <= 0:
            raise ValidationError("Max required must be greater than 0 (use Remove to delete the row).")
        if qty > r["total_quantity"]:
            raise ValidationError(f"{r['resource_name']}: only {r['total_quantity']} exist in total.")
        if qty < task["alloc"][j]:
            raise ValidationError(f"Max required cannot be below the {task['alloc'][j]} already allocated.")
        cur.execute("INSERT INTO task_resources (task_id, resource_id, maximum_required, currently_allocated) "
                    "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE maximum_required=%s",
                    (task_id, resource_id, qty, task["alloc"][j], qty))
        conn.commit()
        task["max"][j] = qty
        avail, mx, al, _, _ = _matrices(dict(state, in_algo=[t for t in state["tasks"] if any(t["max"])]))
        note = "" if safe_sequence(avail, mx, al)[0] else " Warning: with this requirement the system is no longer in a safe state."
        return f"{r['resource_name']} requirement for {task_id} saved (max {qty}).{note}"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def remove_requirement(task_id, resource_id):
    """Delete a wrong requirement row. Refused while the task still holds that resource."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        state, task, j = _requirement_context(cur, task_id, resource_id)
        name = state["resources"][j]["resource_name"]
        if not task["max"][j]:
            raise ValidationError(f"{task_id} has no {name} requirement.")
        if task["alloc"][j]:
            raise ValidationError(f"{name} is already allocated to {task_id}. Release it first (cancel the task), then remove the row.")
        cur.execute("DELETE FROM task_resources WHERE task_id=%s AND resource_id=%s", (task_id, resource_id))
        conn.commit()
        return f"{name} requirement removed from {task_id}."
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------ add / cancel a task
def _active_resources():
    return fetch_all("SELECT resource_id, resource_name, resource_type, total_quantity FROM resources WHERE status='Active' "
                     "ORDER BY FIELD(resource_type, " + ", ".join(f"'{t}'" for t in TYPE_ORDER) + "), resource_id")


def _task_for_request(request_id):
    return fetch_one("SELECT task_id FROM maintenance_tasks WHERE request_id=%s", (request_id,))["task_id"]


def _duplicate_active(computer_id, description):
    return fetch_one("SELECT 1 AS x FROM maintenance_tasks t JOIN maintenance_requests r ON r.request_id = t.request_id "
                     "WHERE t.computer_id=%s AND r.problem_description=%s AND t.status NOT IN ('Completed','Cancelled')",
                     (computer_id, description))


def _write_maximum(task_id, rows):
    """All maximum-requirement rows of a new task in ONE transaction (allocation starts at 0)."""
    execute_transaction([("INSERT INTO task_resources (task_id, resource_id, maximum_required, currently_allocated) "
                          "VALUES (%s,%s,%s,0) ON DUPLICATE KEY UPDATE maximum_required=%s", (task_id, rid, q, q))
                         for rid, q in rows])


def create_task(computer_id, description, maximum):
    """
    Create a maintenance task for an existing PC with its Maximum requirement (resource_id -> quantity), through the
    existing request/approval functions. The task joins the Banker's safety check automatically (Allocation 0).
    """
    description = (description or "").strip()
    if not computer_id:
        raise ValidationError("Select a PC.")
    if not description:
        raise ValidationError("Enter the maintenance issue.")
    res, rows = _active_resources(), []
    for r in res:
        q = maximum.get(r["resource_id"], 0)
        if q < 0:
            raise ValidationError(f"{r['resource_name']}: quantity cannot be negative.")
        if q > r["total_quantity"]:
            raise ValidationError(f"{r['resource_name']}: maximum {q} is more than the {r['total_quantity']} that exist in total.")
        if q:
            rows.append((r["resource_id"], q))
    if not rows:
        raise ValidationError("Enter a maximum requirement for at least one resource.")
    if _duplicate_active(computer_id, description):
        raise ValidationError("This PC already has an active task with the same description.")
    kinds = {r["resource_type"] for r in res if maximum.get(r["resource_id"], 0)}
    fault = ("Network" if "Network Tester" in kinds else "Software" if "OS Installation Kit" in kinds
             else "Hardware" if "RAM" in kinds else "Peripheral" if kinds & {"Keyboard", "Mouse"} else "Other")
    rid = msvc.create_manual_request(computer_id, description, fault, "Medium")   # validates that the PC exists
    msvc.approve_request(rid)
    task_id = _task_for_request(rid)
    try:
        _write_maximum(task_id, rows)
    except Exception:
        cancel_task(task_id)                         # never leave a task without its maximum
        raise
    return f"Task {task_id} created for {computer_id}. It is now part of the safety check."


def cancel_task(task_id):
    """Cancel a task and release its allocations in one transaction (history rows are kept, never deleted)."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        rs.lock_resources(cur)
        cur.execute("SELECT status, computer_id FROM maintenance_tasks WHERE task_id=%s FOR UPDATE", (task_id,))
        row = cur.fetchall()
        if not row:
            raise ValidationError("Task not found.")
        if row[0]["status"] in ("Completed", "Cancelled"):
            raise ValidationError(f"A {row[0]['status']} task cannot be cancelled.")
        rs.release_in_tx(cur, task_id)
        cur.execute("UPDATE maintenance_tasks SET status='Cancelled' WHERE task_id=%s", (task_id,))
        cur.execute("UPDATE computers SET status='Available' WHERE computer_id=%s AND status='Under Maintenance' AND NOT EXISTS "
                    "(SELECT 1 FROM maintenance_tasks WHERE computer_id=%s AND status NOT IN ('Completed','Cancelled'))",
                    (row[0]["computer_id"], row[0]["computer_id"]))
        conn.commit()
        return f"{task_id} cancelled. Its resources were released."
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------ demo data + reset
def _resource_by_type():
    by = {}
    for r in fetch_all("SELECT resource_id, resource_type FROM resources WHERE status='Active' ORDER BY resource_id"):
        by.setdefault(r["resource_type"], r["resource_id"])
    return by


def load_demo():
    """Create the six sample maintenance requests (PC-01..PC-06) as tasks with their Maximum. Idempotent."""
    from services.resource_service import set_task_requirement
    by = _resource_by_type()
    missing = [t for t in DEMO_TYPES if t not in by]
    if missing:
        raise ValidationError("Add these resource types on the Resources page first: " + ", ".join(missing))
    created = 0
    for pc, issue, fault, sev, vec in DEMO_PCS:
        if fetch_one("SELECT 1 AS x FROM maintenance_tasks t JOIN maintenance_requests r ON r.request_id = t.request_id "
                     "WHERE t.computer_id=%s AND r.problem_description LIKE %s AND t.status NOT IN ('Completed','Cancelled')",
                     (pc, DEMO_PREFIX + "%")):
            continue
        rid = msvc.create_manual_request(pc, DEMO_PREFIX + issue, fault, sev)
        msvc.approve_request(rid)
        tid = fetch_one("SELECT task_id FROM maintenance_tasks WHERE request_id=%s", (rid,))["task_id"]
        for rtype, qty in zip(DEMO_TYPES, vec):
            if qty:
                set_task_requirement(tid, by[rtype], qty)
        created += 1
    return f"{created} demo request(s) created." if created else "The six demo requests already exist."


def reset_allocations():
    """Demo reset (no button on the page): release every held allocation, history is kept."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        rs.lock_resources(cur)
        for t in fetch_all("SELECT DISTINCT task_id FROM resource_allocations WHERE status='Allocated'"):
            rs.release_in_tx(cur, t["task_id"])
        cur.execute("UPDATE maintenance_tasks SET status='Pending' WHERE status IN ('Resources Allocated','Waiting for Resource')")
        conn.commit()
        return "All allocations released. Allocated = 0, Available = Total."
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------ safe / unsafe demonstration (in memory)
def demonstration():
    """
    Worked examples computed by the real algorithm on the six sample PCs; nothing touches the database.
    Totals come from the resources table (default (4, 3, 2, 3, 3, 1)).
    With the six Maximum vectors exactly as specified, no unsafe state can occur (every PC needs at most one
    technician and the scarce items are never needed in a circular way), so the unsafe example uses a
    RAM-heavy variant where the two RAM repairs may need all 3 modules.
    """
    totals = list(DEFAULT_TOTALS)
    for k, t in enumerate(DEMO_TYPES):
        row = fetch_one("SELECT SUM(total_quantity) AS q FROM resources WHERE status='Active' AND resource_type=%s", (t,))
        if row and row["q"] is not None:
            totals[k] = int(row["q"])
    names = ["Technician", "RAM Module", "Network Tester", "Keyboard", "Mouse", "OS Kit"]
    pcs = [p[0] for p in DEMO_PCS]
    base = [list(p[4]) for p in DEMO_PCS]
    stress = [list(v) for v in base]
    stress[0][1], stress[2][1] = 3, 3                       # PC-01 and PC-03 may need all 3 RAM modules
    hold = [[0] * 6 for _ in pcs]
    hold[2][1] = 1                                          # PC-03 already holds 1 RAM module
    avail0 = list(totals)
    avail1 = [t - sum(h[j] for h in hold) for j, t in enumerate(totals)]

    def seq(avail, mx, al):
        ok, steps, _, _ = safe_sequence(avail, mx, al)
        return {"safe": ok, "order": [pcs[s["i"]] for s in steps],
                "steps": [{"pc": pcs[s["i"]], "before": s["before"], "release": s["release"], "after": s["after"]}
                          for s in steps]}

    def ask(pc, k, q, mx, al, avail):
        vec = [0] * 6
        vec[k] = q
        r = evaluate_request(avail, mx, al, pcs.index(pc), vec, names, pcs)
        return {"pc": pc, "request": _fmt(vec, names), "code": r["code"], "message": r["message"]}

    zero = [[0] * 6 for _ in pcs]
    return {"names": names, "totals": totals,
            "safe": seq(avail0, base, zero),
            "unsafe_before": seq(avail1, stress, hold), "available_before": avail1,
            "cases": [ask("PC-01", 1, 1, stress, hold, avail1),     # unsafe although available and within Need
                      ask("PC-01", 1, 3, stress, hold, avail1),     # more than available
                      ask("PC-02", 0, 2, stress, hold, avail1),     # more than Need
                      ask("PC-06", 5, 1, stress, hold, avail1)]}    # a normal safe approval


def unsafe_demo_message():
    """Short text for the small demo control: the unsafe-request example, computed in memory (live data untouched)."""
    d = demonstration()
    c = next(x for x in d["cases"] if x["code"] == "UNSAFE")
    return (f"Demo scenario (RAM-heavy variant, live data untouched): PC-03 holds 1 RAM Module, so the state is "
            f"{'SAFE' if d['unsafe_before']['safe'] else 'UNSAFE'}. {c['pc']} requests {c['request']}. {c['message']}")
