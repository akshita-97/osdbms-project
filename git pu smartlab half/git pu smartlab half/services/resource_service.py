

from db.database import fetch_all, fetch_one, execute, execute_transaction
from services.maintenance_service import ValidationError, get_task



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



def allocate_resources_for_task(task_id):
    
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    if task["status"] in ("Completed", "Cancelled"):
        raise ValidationError(f"Cannot allocate resources to a {task['status']} task.")

    requirements = get_task_requirements(task_id)
    if not requirements:
        raise ValidationError("This task has no defined resource requirements.")

    needs = [
        (r, r["maximum_required"] - r["currently_allocated"])
        for r in requirements
    ]

    if all(qty == 0 for _, qty in needs):
        raise ValidationError("This task's resources are already fully allocated.")

    for r, qty in needs:
        if qty > r["available_quantity"]:
            execute("UPDATE maintenance_tasks SET status='Waiting for Resource' WHERE task_id=%s",
                    (task_id,))
            raise ValidationError(
                f"Not enough '{r['resource_name']}' available "
                f"(need {qty}, available {r['available_quantity']}). "
                f"Task set to Waiting for Resource."
            )

    statements = []
    for r, qty in needs:
        if qty > 0:
            statements.append((
                "INSERT INTO resource_allocations (task_id, resource_id, quantity, status) "
                "VALUES (%s,%s,%s,'Allocated')",
                (task_id, r["resource_id"], qty),
            ))
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


def release_resources_for_task(task_id):
   
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")

    allocations = fetch_all(
        "SELECT * FROM resource_allocations WHERE task_id=%s AND status='Allocated'",
        (task_id,),
    )
    if not allocations:
        raise ValidationError("No allocated resources to release for this task.")

    statements = []
    for a in allocations:
        statements.append((
            "UPDATE resource_allocations SET status='Released', released_at=NOW() WHERE allocation_id=%s",
            (a["allocation_id"],),
        ))
        # Trigger trg_after_allocation_release auto-increments resources.available_quantity
        statements.append((
            "UPDATE task_resources SET currently_allocated = currently_allocated - %s "
            "WHERE task_id=%s AND resource_id=%s",
            (a["quantity"], task_id, a["resource_id"]),
        ))
    execute_transaction(statements)

    summary = ", ".join(
        f"{fetch_one('SELECT resource_name FROM resources WHERE resource_id=%s', (a['resource_id'],))['resource_name']} x{a['quantity']}"
        for a in allocations
    )
    return summary
