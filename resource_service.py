
from db.database import fetch_all, fetch_one, execute, execute_transaction, get_connection
from services.maintenance_service import ValidationError, get_task


# =====================================================================
# RESOURCE INVENTORY (CRUD)
# =====================================================================

VALID_RESOURCE_TYPES = {"Technician", "RAM", "Keyboard", "Mouse",
                         "Network Tester", "OS Installation Kit", "Other"}


def list_resources():
    return fetch_all("SELECT * FROM resources ORDER BY resource_type, resource_name")


def get_resource(resource_id):
    return fetch_one("SELECT * FROM resources WHERE resource_id = %s", (resource_id,))


def create_resource(resource_name, resource_type, total_quantity):
    if resource_type not in VALID_RESOURCE_TYPES:
        raise ValidationError(f"Invalid resource type '{resource_type}'.")
    if total_quantity is None or int(total_quantity) < 0:
        raise ValidationError("Resource quantity cannot be negative.")
    execute(
        """INSERT INTO resources (resource_name, resource_type, total_quantity,
                                   available_quantity, status)
           VALUES (%s,%s,%s,%s,'Active')""",
        (resource_name, resource_type, total_quantity, total_quantity),
    )


def update_resource_total(resource_id, new_total):
    res = get_resource(resource_id)
    if not res:
        raise ValidationError("Resource not found.")
    if new_total is None or int(new_total) < 0:
        raise ValidationError("Resource quantity cannot be negative.")
    allocated = res["total_quantity"] - res["available_quantity"]
    if new_total < allocated:
        raise ValidationError(
            f"Cannot reduce total below currently-allocated amount ({allocated})."
        )
    new_available = new_total - allocated
    execute("UPDATE resources SET total_quantity=%s, available_quantity=%s WHERE resource_id=%s",
            (new_total, new_available, resource_id))


# =====================================================================
# TASK RESOURCE REQUIREMENTS (task_resources junction table)
# =====================================================================

def set_task_requirement(task_id, resource_id, maximum_required):
    if maximum_required is None or int(maximum_required) <= 0:
        raise ValidationError("Maximum required quantity must be greater than 0.")
    existing = fetch_one(
        "SELECT * FROM task_resources WHERE task_id=%s AND resource_id=%s",
        (task_id, resource_id),
    )
    if existing:
        if maximum_required < existing["currently_allocated"]:
            raise ValidationError(
                "New maximum cannot be less than the amount already allocated."
            )
        execute(
            "UPDATE task_resources SET maximum_required=%s WHERE task_id=%s AND resource_id=%s",
            (maximum_required, task_id, resource_id),
        )
    else:
        execute(
            "INSERT INTO task_resources (task_id, resource_id, maximum_required, currently_allocated) "
            "VALUES (%s,%s,%s,0)",
            (task_id, resource_id, maximum_required),
        )


def get_task_requirements(task_id):
    return fetch_all(
        """SELECT tr.*, r.resource_name, r.resource_type, r.available_quantity, r.total_quantity
           FROM task_resources tr
           JOIN resources r ON tr.resource_id = r.resource_id
           WHERE tr.task_id = %s
           ORDER BY r.resource_type""",
        (task_id,),
    )


# =====================================================================
# RESOURCE ALLOCATION / RELEASE (transactional)
# =====================================================================

def allocate_resources_for_task(task_id):
    """
    Attempt to allocate a task's FULL remaining need (Maximum - Allocation)
    in one go.

    Workflow:
      1. Read the task's resource requirements.
      2. Check current availability for every required resource.
      3. If everything needed is available -> commit the allocation
         transactionally and set the task to 'Resources Allocated'.
         Otherwise -> set the task to 'Waiting for Resource' and report
         which resource is short.
    """
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    if task["status"] in ("Completed", "Cancelled"):
        raise ValidationError(f"Cannot allocate resources to a {task['status']} task.")

    requirements = get_task_requirements(task_id)
    if not requirements:
        raise ValidationError("This task has no defined resource requirements.")

    # Remaining need per resource = maximum_required - currently_allocated.
    # (get_task_requirements joins the live available_quantity from `resources`.)
    needs = [
        (r, r["maximum_required"] - r["currently_allocated"])
        for r in requirements
    ]

    if all(qty == 0 for _, qty in needs):
        raise ValidationError("This task's resources are already fully allocated.")

    # Availability check (clear error before touching any data)
    for r, qty in needs:
        if qty > r["available_quantity"]:
            execute("UPDATE maintenance_tasks SET status='Waiting for Resource' WHERE task_id=%s",
                    (task_id,))
            raise ValidationError(
                f"Not enough '{r['resource_name']}' available "
                f"(need {qty}, available {r['available_quantity']}). "
                f"Task set to Waiting for Resource."
            )

    # Everything is available -> commit as one atomic transaction.
    statements = []
    for r, qty in needs:
        if qty > 0:
            statements.append((
                "INSERT INTO resource_allocations (task_id, resource_id, quantity, status) "
                "VALUES (%s,%s,%s,'Allocated')",
                (task_id, r["resource_id"], qty),
            ))
            # Trigger trg_after_allocation_insert auto-decrements resources.available_quantity
            statements.append((
                "UPDATE task_resources SET currently_allocated = currently_allocated + %s "
                "WHERE task_id=%s AND resource_id=%s",
                (qty, task_id, r["resource_id"]),
            ))
    statements.append((
        "UPDATE maintenance_tasks SET status='Resources Allocated' WHERE task_id=%s",
        (task_id,),
    ))

    execute_transaction(statements)

    return {
        "success": True,
        "message": "Resources allocated successfully.",
    }


def lock_resources(cur):
    """Lock the resource rows in one fixed order (same order Banker's uses) so concurrent changes cannot deadlock."""
    cur.execute("SELECT resource_id FROM resources WHERE status='Active' ORDER BY FIELD(resource_type, 'Technician', "
                "'RAM', 'Network Tester', 'Keyboard', 'Mouse', 'OS Installation Kit', 'Other'), resource_id FOR UPDATE")
    cur.fetchall()


def release_in_tx(cur, task_id):
    """
    THE release mechanism. Releases every 'Allocated' row of a task inside the caller's transaction and returns a
    summary text ('' if nothing was held). Only rows still 'Allocated' change, and task_resources is recomputed from
    the allocation records, so a repeated or concurrent release frees nothing twice. The existing trigger
    trg_after_allocation_release returns the stock counter only on a real Allocated -> Released change.
    """
    cur.execute("SELECT a.allocation_id, a.resource_id, a.quantity, r.resource_name FROM resource_allocations a "
                "JOIN resources r ON r.resource_id = a.resource_id WHERE a.task_id=%s AND a.status='Allocated' "
                "FOR UPDATE", (task_id,))
    rows = cur.fetchall()
    for a in rows:
        cur.execute("UPDATE resource_allocations SET status='Released', released_at=NOW() "
                    "WHERE allocation_id=%s AND status='Allocated'", (a["allocation_id"],))
        cur.execute("UPDATE task_resources SET currently_allocated = (SELECT COALESCE(SUM(quantity), 0) "
                    "FROM resource_allocations WHERE task_id=%s AND resource_id=%s AND status='Allocated') "
                    "WHERE task_id=%s AND resource_id=%s", (task_id, a["resource_id"], task_id, a["resource_id"]))
    return ", ".join(f"{a['resource_name']} x{a['quantity']}" for a in rows)


def release_resources_for_task(task_id):
    """Release a task's resources on their own (used by the Resources page)."""
    if not get_task(task_id):
        raise ValidationError("Task not found.")
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        lock_resources(cur)
        summary = release_in_tx(cur, task_id)
        if not summary:
            raise ValidationError("No allocated resources to release for this task.")
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_task_with_release(task, remarks):
    """
    Complete a running task AND release its resources in ONE transaction: status Completed, history record,
    resources back to the pool, technician freed. If any step fails everything is rolled back, and completing
    twice cannot release twice (the task must be In Progress and only 'Allocated' rows are released).
    """
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        lock_resources(cur)
        cur.execute("SELECT status, started_at, technician_id FROM maintenance_tasks WHERE task_id=%s FOR UPDATE",
                    (task["task_id"],))
        row = cur.fetchall()
        if not row or row[0]["status"] != "In Progress":
            raise ValidationError("Cannot complete a task that has not started (In Progress).")
        used = release_in_tx(cur, task["task_id"])
        cur.execute("UPDATE maintenance_tasks SET status='Completed', completed_at=NOW() WHERE task_id=%s",
                    (task["task_id"],))
        cur.execute("INSERT INTO maintenance_history (task_id, computer_id, technician_id, started_at, completed_at, "
                    "remarks, resources_used) VALUES (%s,%s,%s,%s,NOW(),%s,%s)",
                    (task["task_id"], task["computer_id"], row[0]["technician_id"], row[0]["started_at"], remarks, used))
        cur.execute("UPDATE technicians SET availability='Available' WHERE technician_id=%s AND NOT EXISTS "
                    "(SELECT 1 FROM maintenance_tasks WHERE technician_id=%s AND status='In Progress')",
                    (row[0]["technician_id"], row[0]["technician_id"]))
        conn.commit()
        return used
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
