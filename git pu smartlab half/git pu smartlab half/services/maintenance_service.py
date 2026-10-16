
from db.database import fetch_all, fetch_one, execute


class ValidationError(Exception):
    """Raised when a business rule is violated."""
    pass



def list_labs():
    return fetch_all(
        """SELECT l.*,
                  (SELECT COUNT(*) FROM computers c WHERE c.lab_id = l.lab_id) AS computer_count
           FROM labs l ORDER BY l.lab_id"""
    )


def get_lab(lab_id):
    return fetch_one("SELECT * FROM labs WHERE lab_id = %s", (lab_id,))


def create_lab(lab_id, lab_name, location, capacity, status="Active"):
    if capacity is None or int(capacity) < 0:
        raise ValidationError("Capacity cannot be negative.")
    if get_lab(lab_id):
        raise ValidationError(f"Lab ID '{lab_id}' already exists.")
    execute(
        "INSERT INTO labs (lab_id, lab_name, location, capacity, status) VALUES (%s,%s,%s,%s,%s)",
        (lab_id, lab_name, location, capacity, status),
    )


def update_lab(lab_id, lab_name, location, capacity, status):
    if capacity is None or int(capacity) < 0:
        raise ValidationError("Capacity cannot be negative.")
    execute(
        "UPDATE labs SET lab_name=%s, location=%s, capacity=%s, status=%s WHERE lab_id=%s",
        (lab_name, location, capacity, status, lab_id),
    )


def delete_lab(lab_id):
    count = fetch_one("SELECT COUNT(*) AS c FROM computers WHERE lab_id = %s", (lab_id,))["c"]
    if count > 0:
        raise ValidationError(
            f"Cannot delete lab '{lab_id}': {count} computer(s) still reference it."
        )
    execute("DELETE FROM labs WHERE lab_id = %s", (lab_id,))


# =====================================================================
# COMPUTERS
# =====================================================================

VALID_COMPUTER_STATUSES = {"Available", "In Use", "Maintenance Required",
                            "Under Maintenance", "Offline"}


def list_computers(lab_id=None):
    if lab_id:
        return fetch_all(
            "SELECT c.*, l.lab_name FROM computers c JOIN labs l ON c.lab_id = l.lab_id "
            "WHERE c.lab_id = %s ORDER BY c.computer_id", (lab_id,))
    return fetch_all(
        "SELECT c.*, l.lab_name FROM computers c JOIN labs l ON c.lab_id = l.lab_id "
        "ORDER BY c.computer_id")


def get_computer(computer_id):
    return fetch_one(
        "SELECT c.*, l.lab_name FROM computers c JOIN labs l ON c.lab_id = l.lab_id "
        "WHERE c.computer_id = %s", (computer_id,))


def create_computer(computer_id, lab_id, ip_address, processor, ram_gb, storage_gb,
                     os_name, status="Available"):
    if ram_gb is not None and int(ram_gb) < 0:
        raise ValidationError("RAM cannot be negative.")
    if storage_gb is not None and int(storage_gb) < 0:
        raise ValidationError("Storage cannot be negative.")
    if not get_lab(lab_id):
        raise ValidationError(f"Lab '{lab_id}' does not exist.")
    if get_computer(computer_id):
        raise ValidationError(f"Computer ID '{computer_id}' already exists.")
    execute(
        """INSERT INTO computers (computer_id, lab_id, ip_address, processor, ram_gb,
                                   storage_gb, os_name, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (computer_id, lab_id, ip_address, processor, ram_gb, storage_gb, os_name,
         status),
    )


def update_computer(computer_id, lab_id, ip_address, processor, ram_gb, storage_gb, os_name):
    if ram_gb is not None and int(ram_gb) < 0:
        raise ValidationError("RAM cannot be negative.")
    if storage_gb is not None and int(storage_gb) < 0:
        raise ValidationError("Storage cannot be negative.")
    execute(
        """UPDATE computers SET lab_id=%s, ip_address=%s, processor=%s, ram_gb=%s,
                                 storage_gb=%s, os_name=%s WHERE computer_id=%s""",
        (lab_id, ip_address, processor, ram_gb, storage_gb, os_name, computer_id),
    )


def set_computer_status(computer_id, status):
    if status not in VALID_COMPUTER_STATUSES:
        raise ValidationError(f"Invalid computer status '{status}'.")

    if status == "Available":
        active = fetch_one(
            """SELECT COUNT(*) AS c FROM maintenance_tasks
               WHERE computer_id = %s AND status NOT IN ('Completed','Cancelled')""",
            (computer_id,))["c"]
        if active > 0:
            raise ValidationError(
                "Cannot mark computer as Available while an active maintenance task exists."
            )

    execute("UPDATE computers SET status=%s WHERE computer_id=%s", (status, computer_id))


def delete_computer(computer_id):
    count = fetch_one(
        "SELECT COUNT(*) AS c FROM maintenance_requests WHERE computer_id = %s",
        (computer_id,))["c"]
    if count > 0:
        raise ValidationError(
            f"Cannot delete computer '{computer_id}': it has {count} maintenance record(s)."
        )
    execute("DELETE FROM computers WHERE computer_id = %s", (computer_id,))


# =====================================================================
# MAINTENANCE REQUESTS
# =====================================================================

VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}
VALID_FAULT_TYPES = {"Hardware", "Software", "Network", "Performance", "Peripheral", "Other"}


def list_requests(status=None):
    """
    One row per request with a single display_status:
    Pending Review -> Approved -> In Progress -> (Completed leaves this list, see History).
    Requests linked to a task not yet started show as Approved.
    """
    rows = fetch_all(
        """SELECT r.*, t.task_id, tech.name AS technician_name,
                  CASE WHEN r.status = 'Converted to Task'
                       THEN IF(t.status = 'In Progress', 'In Progress', 'Approved')
                       ELSE r.status END AS display_status
           FROM maintenance_requests r
           LEFT JOIN maintenance_tasks t ON t.request_id = r.request_id
           LEFT JOIN technicians tech ON t.technician_id = tech.technician_id
           WHERE r.status <> 'Closed'
             AND (t.status IS NULL OR t.status NOT IN ('Completed', 'Cancelled'))
           ORDER BY r.request_id DESC"""
    )
    return [r for r in rows if not status or r["display_status"] == status]


def get_request(request_id):
    return fetch_one("SELECT * FROM maintenance_requests WHERE request_id = %s", (request_id,))


def create_manual_request(computer_id, problem_description, fault_type, severity):
    if fault_type not in VALID_FAULT_TYPES:
        raise ValidationError(f"Invalid fault type '{fault_type}'.")
    if severity not in VALID_SEVERITIES:
        raise ValidationError(f"Invalid severity '{severity}'.")
    if not get_computer(computer_id):
        raise ValidationError(f"Computer '{computer_id}' does not exist.")

    last_id, _ = execute(
        """INSERT INTO maintenance_requests
               (computer_id, problem_description, fault_type, severity, status)
           VALUES (%s, %s, %s, %s, 'Pending Review')""",
        (computer_id, problem_description, fault_type, severity),
    )
    return last_id


def approve_request(request_id):
    req = get_request(request_id)
    if not req:
        raise ValidationError("Maintenance request not found.")
    if req["status"] != "Pending Review":
        raise ValidationError(f"Request is already '{req['status']}'.")
    execute("UPDATE maintenance_requests SET status = 'Approved' WHERE request_id = %s", (request_id,))


def reject_request(request_id):
    execute("UPDATE maintenance_requests SET status = 'Rejected' WHERE request_id = %s", (request_id,))


# =====================================================================
# MAINTENANCE TASKS
# =====================================================================

SEVERITY_TO_PRIORITY = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}

TASK_STATUS_ORDER = [
    "Pending", "Scheduled", "Waiting for Resource",
    "Resources Allocated", "In Progress", "Completed", "Cancelled",
]


def _next_task_id():
    """Next free task id: J-101, J-102, ... (historical J-0xx ids are ignored)."""
    row = fetch_one(
        "SELECT MAX(CAST(SUBSTRING(task_id, 3) AS UNSIGNED)) AS n "
        "FROM maintenance_tasks WHERE task_id LIKE 'J-%'"
    )
    highest = int(row["n"]) if row and row["n"] is not None else 100
    return f"J-{max(highest, 100) + 1}"


# Default estimate (minutes) for scheduling, picked from severity.
DEFAULT_SERVICE_TIME = {"Critical": 40, "High": 30, "Medium": 25, "Low": 15}


def start_request(request_id, technician_id):
    """Approved request + technician -> task goes straight to 'In Progress'."""
    req = get_request(request_id)
    if not req:
        raise ValidationError("Maintenance request not found.")
    tech = fetch_one("SELECT * FROM technicians WHERE technician_id = %s", (technician_id,))
    if not tech:
        raise ValidationError("Please select a technician.")
    if tech["availability"] != "Available":
        raise ValidationError(f"{tech['name']} is {tech['availability']}.")

    task = fetch_one("SELECT * FROM maintenance_tasks WHERE request_id = %s "
                     "AND status NOT IN ('Completed','Cancelled')", (request_id,))
    if task and task["status"] != "In Progress":      # task already created earlier
        execute("UPDATE maintenance_tasks SET status='In Progress', technician_id=%s, "
                "started_at=NOW() WHERE task_id=%s", (technician_id, task["task_id"]))
    elif req["status"] == "Approved" and not task:
        execute(
            """INSERT INTO maintenance_tasks (task_id, request_id, computer_id, arrival_time,
                   service_time, priority, status, technician_id, started_at)
               VALUES (%s,%s,%s,0,%s,%s,'In Progress',%s,NOW())""",
            (_next_task_id(), request_id, req["computer_id"],
             DEFAULT_SERVICE_TIME[req["severity"]], SEVERITY_TO_PRIORITY[req["severity"]],
             technician_id))
        execute("UPDATE maintenance_requests SET status='Converted to Task' WHERE request_id=%s",
                (request_id,))
    else:
        raise ValidationError("Only an Approved request can be started.")

    execute("UPDATE technicians SET availability='Busy' WHERE technician_id=%s", (technician_id,))
    execute("UPDATE computers SET status='Under Maintenance' WHERE computer_id=%s",
            (req["computer_id"],))


def complete_request(request_id, remarks):
    """Finish the running task: log history, free resources + technician."""
    from services.resource_service import release_resources_for_task  # avoids circular import
    task = fetch_one("SELECT * FROM maintenance_tasks WHERE request_id = %s "
                     "AND status = 'In Progress'", (request_id,))
    if not task:
        raise ValidationError("No task in progress for this request.")
    try:
        used = release_resources_for_task(task["task_id"])
    except ValidationError:                            # nothing was allocated
        used = ""
    complete_task_and_log_history(task["task_id"], remarks, used)
    execute("""UPDATE technicians SET availability='Available' WHERE technician_id=%s AND NOT EXISTS
               (SELECT 1 FROM maintenance_tasks WHERE technician_id=%s AND status='In Progress')""",
            (task["technician_id"], task["technician_id"]))


def list_tasks(status=None):
    query = """SELECT t.*, c.lab_id, tech.name AS technician_name
               FROM maintenance_tasks t
               JOIN computers c ON t.computer_id = c.computer_id
               LEFT JOIN technicians tech ON t.technician_id = tech.technician_id"""
    if status:
        query += " WHERE t.status = %s ORDER BY t.arrival_time"
        return fetch_all(query, (status,))
    query += " ORDER BY t.created_at DESC"
    return fetch_all(query)


def get_task(task_id):
    return fetch_one(
        """SELECT t.*, c.lab_id, tech.name AS technician_name
           FROM maintenance_tasks t
           JOIN computers c ON t.computer_id = c.computer_id
           LEFT JOIN technicians tech ON t.technician_id = tech.technician_id
           WHERE t.task_id = %s""", (task_id,))


def get_pending_tasks_for_scheduling():
    """Tasks not yet completed/cancelled -- these feed the scheduling engine."""
    return fetch_all(
        """SELECT task_id, arrival_time, service_time, priority
           FROM maintenance_tasks
           WHERE status NOT IN ('Completed', 'Cancelled')
           ORDER BY arrival_time"""
    )


def assign_technician(task_id, technician_id):
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    tech = fetch_one("SELECT * FROM technicians WHERE technician_id = %s", (technician_id,))
    if not tech:
        raise ValidationError("Technician not found.")
    execute("UPDATE maintenance_tasks SET technician_id = %s WHERE task_id = %s",
            (technician_id, task_id))


def set_task_status(task_id, new_status, completion_time=None):
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    if new_status not in TASK_STATUS_ORDER:
        raise ValidationError(f"Invalid task status '{new_status}'.")

    current = task["status"]
    if current == "Completed":
        raise ValidationError("A completed task cannot be modified or rescheduled.")

    # --- Guard illegal transitions (section 46/47 validation rules) ---
    if new_status == "In Progress" and current not in ("Resources Allocated", "In Progress"):
        raise ValidationError(
            "Cannot start maintenance: required resources have not been allocated yet."
        )
    if new_status == "Completed" and current != "In Progress":
        raise ValidationError("Cannot complete a task that has not started (In Progress).")

    params = [new_status]
    sql = "UPDATE maintenance_tasks SET status=%s"

    if new_status == "In Progress":
        sql += ", started_at = NOW()"
    if new_status == "Completed":
        sql += ", completed_at = NOW()"
        if completion_time is not None:
            sql += ", completion_time = %s"
            params.append(completion_time)

    sql += " WHERE task_id = %s"
    params.append(task_id)
    execute(sql, tuple(params))

    if new_status == "In Progress":
        execute("UPDATE computers SET status = 'Under Maintenance' WHERE computer_id = %s",
                (task["computer_id"],))


def complete_task_and_log_history(task_id, remarks, resources_used_summary):
    """
    Mark a task Completed and write a maintenance_history record.
    Does NOT release resources itself -- that is a separate, explicit
    step (see resource_service.release_resources) so that scheduling
    vs. resource allocation stay conceptually distinct.
    """
    task = get_task(task_id)
    if not task:
        raise ValidationError("Task not found.")
    if task["status"] != "In Progress":
        raise ValidationError("Cannot complete a task that has not started (In Progress).")

    set_task_status(task_id, "Completed")

    execute(
        """INSERT INTO maintenance_history
               (task_id, computer_id, technician_id, started_at, completed_at, remarks, resources_used)
           VALUES (%s, %s, %s, %s, NOW(), %s, %s)""",
        (task_id, task["computer_id"], task["technician_id"], task["started_at"],
         remarks, resources_used_summary),
    )


# =====================================================================
# TECHNICIANS
# =====================================================================

VALID_SPECIALIZATIONS = {"Hardware", "Software", "Networking", "General"}


def list_technicians():
    return fetch_all("SELECT * FROM technicians ORDER BY name")


def create_technician(name, specialization, availability="Available", contact=None):
    if specialization not in VALID_SPECIALIZATIONS:
        raise ValidationError(f"Invalid specialization '{specialization}'.")
    execute(
        "INSERT INTO technicians (name, specialization, availability, contact) VALUES (%s,%s,%s,%s)",
        (name, specialization, availability, contact),
    )


def set_technician_availability(technician_id, availability):
    if availability not in ("Available", "Busy", "Off Duty"):
        raise ValidationError("Invalid availability value.")
    execute("UPDATE technicians SET availability = %s WHERE technician_id = %s",
            (availability, technician_id))


# =====================================================================
# MAINTENANCE HISTORY
# =====================================================================

def get_history_for_computer(computer_id):
    return fetch_all(
        """SELECT h.*, t.priority, t.service_time, tech.name AS technician_name FROM maintenance_history h
           JOIN maintenance_tasks t ON h.task_id = t.task_id
           LEFT JOIN technicians tech ON h.technician_id = tech.technician_id
           WHERE h.computer_id = %s ORDER BY h.completed_at DESC""",
        (computer_id,),
    )


def get_all_history():
    return fetch_all(
        """SELECT h.*, t.priority, t.service_time, tech.name AS technician_name FROM maintenance_history h
           JOIN maintenance_tasks t ON h.task_id = t.task_id
           LEFT JOIN technicians tech ON h.technician_id = tech.technician_id
           ORDER BY h.completed_at DESC"""
    )
