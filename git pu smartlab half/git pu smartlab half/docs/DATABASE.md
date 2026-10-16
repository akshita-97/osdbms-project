# SmartLab -- Database Design

Database name: `smartlab_db` (MySQL). Full DDL in `database/schema.sql`;
sample data in `database/seed.sql`.

## Tables (9)

| # | Table | Purpose |
|---|-------|---------|
| 1 | `labs` | Physical computer labs |
| 2 | `computers` | Computers within a lab |
| 3 | `maintenance_requests` | Manual fault reports, pending admin decision |
| 4 | `maintenance_tasks` | Scheduling-engine input: arrival/service time, priority, status |
| 5 | `technicians` | Lab maintenance staff |
| 6 | `resources` | Limited resource pool (technicians as a countable resource, RAM, keyboards, etc.) |
| 7 | `task_resources` | N:M junction: each task's maximum requirement + current allocation per resource |
| 8 | `resource_allocations` | Audit trail of every allocate/release event |
| 9 | `maintenance_history` | Completed-task record: technician, timestamps, remarks, resources used |

## Entity-Relationship Summary

```
labs (1) ----< (N) computers
computers (1) ----< (N) maintenance_requests
maintenance_requests (1) ----< (N) maintenance_tasks     (usually 1:1 in practice)
maintenance_tasks (N) ----< task_resources >---- (N) resources
maintenance_tasks (1) ----< (N) resource_allocations >---- (N) resources
maintenance_tasks (1) ----< (N) maintenance_history
technicians (1) ----< (N) maintenance_tasks   (technician_id, nullable)
technicians (1) ----< (N) maintenance_history
```

Primary keys are declared on every table; every relationship above is
enforced with a `FOREIGN KEY` (with `ON DELETE`/`ON UPDATE` rules chosen
per relationship -- e.g. deleting a lab is `RESTRICT`ed while it still has
computers, but deleting a computer cascades its maintenance requests).

## Normalization

The schema is in Third Normal Form (3NF):
- Every non-key column depends only on its table's primary key (e.g.
  `resources.available_quantity` lives once, on the resource, not
  duplicated per task).
- The many-to-many relationship between tasks and resources is broken
  out into its own junction table (`task_resources`) rather than
  repeating resource columns inside `maintenance_tasks`.
- Derived/duplicate data is avoided: `available_quantity` is maintained
  by triggers rather than recomputed-and-stored redundantly elsewhere.

## Constraints Used

- **PRIMARY KEY** on every table.
- **FOREIGN KEY** for every relationship listed above.
- **NOT NULL** on every column that must always have a value (e.g.
  `service_time`, `severity`, `resource_type`).
- **UNIQUE** implicitly via primary keys on business identifiers
  (`lab_id`, `computer_id`, `task_id`).
- **CHECK** constraints: `capacity >= 0`, `service_time > 0`,
  `priority BETWEEN 1 AND 4`, `total_quantity >= 0`,
  `available_quantity <= total_quantity`,
  `currently_allocated <= maximum_required`, and more.
- **Indexes** on every foreign key and frequently-filtered column
  (`status`, `(computer_id, recorded_at)`, etc.) -- see the `CREATE
  INDEX` block at the end of `schema.sql`.

## Transactions

Resource allocation and release are each executed as a **single
transaction** (`db/database.py::execute_transaction`, used by
`services/resource_service.py`). If any statement in the sequence
fails, the whole operation is rolled back -- the system never ends up
with, say, an `resource_allocations` row inserted but
`task_resources.currently_allocated` left un-updated.

## Triggers

Three triggers keep derived state consistent automatically:

1. `trg_after_allocation_insert` -- when a `resource_allocations` row
   is inserted with status `'Allocated'`, decrements
   `resources.available_quantity`.
2. `trg_after_allocation_release` -- when an allocation's status flips
   to `'Released'`, restores `resources.available_quantity`.
3. `trg_after_task_completed` -- when a task's status flips to
   `'Completed'`, sets its computer's status back to `'Available'`.

All other business logic (validation, the scheduling
algorithms, workflow ordering) stays in Python, as required -- triggers
here only keep two numeric columns in sync with the events that change
them.

## Useful SQL Query Examples

```sql
-- 1. All computers in a lab
SELECT * FROM computers WHERE lab_id = 'LAB-01';

-- 2. All pending maintenance tasks
SELECT * FROM maintenance_tasks WHERE status = 'Pending';

-- 3. Critical maintenance requests
SELECT * FROM maintenance_requests WHERE severity = 'Critical' AND status <> 'Closed';

-- 4. Available resources
SELECT resource_name, available_quantity FROM resources WHERE available_quantity > 0;

-- 5. Technician task history
SELECT h.* FROM maintenance_history h WHERE h.technician_id = 1 ORDER BY h.completed_at DESC;

-- 6. Maintenance history of a specific computer
SELECT * FROM maintenance_history WHERE computer_id = 'PC-04' ORDER BY completed_at DESC;

-- 7. Number of maintenance requests by lab
SELECT c.lab_id, COUNT(*) AS request_count
FROM maintenance_requests r JOIN computers c ON r.computer_id = c.computer_id
GROUP BY c.lab_id;

-- 8. Most frequently maintained computers
SELECT computer_id, COUNT(*) AS times_maintained
FROM maintenance_history GROUP BY computer_id ORDER BY times_maintained DESC;

-- 9. Current resource allocation
SELECT r.resource_name, ra.task_id, ra.quantity
FROM resource_allocations ra JOIN resources r ON ra.resource_id = r.resource_id
WHERE ra.status = 'Allocated';
```
