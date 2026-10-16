# SmartLab -- Project Overview

## 1. Project Introduction

SmartLab is a college computer-lab maintenance management system built for a
3rd-year BTech CSE Operating Systems / DBMS academic project. It manages
labs, computers, faults, maintenance tasks, technicians and a pool of
limited maintenance resources, and it uses classic OS concepts --
CPU-scheduling-style algorithms -- as an **application-level decision
engine** for planning that maintenance work.

## 2. Problem Statement

A college computer lab can have many maintenance jobs open at the same
time (OS failures, network faults, RAM problems, broken peripherals,
software installs), but the people and equipment needed to fix them --
technicians, RAM modules, keyboards, network testers, OS installation
kits -- are limited. Without a system, there is no principled way to
decide (a) which job to work on next, and (b) whether the resources a
job needs are available right now.

## 3. Motivation

Operating-systems courses teach CPU scheduling as an abstract
process problem. SmartLab gives those same algorithms a concrete,
relatable home: instead of abstract processes P1..Pn competing for a
CPU, students see real maintenance jobs competing for real (if
simulated) lab resources, which makes the concepts easier to explain and
defend in a viva.

## 4. Objectives

1. Track labs, computers, and their status.
2. Let staff report faults manually.
3. Turn verified faults into Maintenance Requests, then Maintenance Tasks.
4. Schedule pending tasks with FCFS / SJF / Priority Scheduling (Round
   Robin included as an optional academic extra).
5. Track a limited pool of maintenance resources and allocate/release
   them per task.
6. Persist everything in a properly normalized MySQL schema with
   transactions and triggers.
7. Present it all through a simple, dependency-free Flask dashboard.

## 5. Existing Problem (Manual Process)

Typically a lab administrator tracks faults on paper or in an ad-hoc
spreadsheet, assigns technicians by memory/gut feel, and has no
systematic way to check whether committing the last spare RAM module or
the only network tester to one job will strand two other jobs. There is
no historical record tying a computer to its repeated fault pattern.

## 6. Proposed Solution

A single-laptop Flask + MySQL application that walks every fault through
a fixed pipeline (Section 7) and uses a scheduling simulation to make
the "what next" decision explicit, auditable, and demonstrable, with a
separate transactional resource-allocation workflow.

## 7. System Workflow

```
Lab / Computer Management
        |
Manual Fault Report  --->  Maintenance Request
        |
   Administrator Approves
        |
Maintenance Task (arrival time, service time, priority)
        |
 Scheduling Engine (FCFS / SJF / Priority / optional Round Robin)
        |
 Scheduling Metrics + Gantt Chart
        |
 Resource Requirement Check  --->  Availability Check
        |                              |
        |             Available ---+--- Not enough (task waits)
        v
 Resources Allocated --> Maintenance In Progress --> Maintenance Completed
        |
 Resources Released --> Computer Status Updated --> Maintenance History Stored
        |
 Dashboard / Reports reflect the new state
```

## 8. System Architecture

Flask app (`app.py`) registers five Blueprints (dashboard, computers,
maintenance, scheduling, resources). Each route module calls
into a `services/` module for business logic and validation, which in
turn calls `db/database.py` for parameterized SQL against MySQL. The
scheduling algorithms themselves live in `algorithms/` as
plain, dependency-free Python -- no library hides the logic.

```
Browser  <-->  Flask routes  <-->  services (business rules)  <-->  db/database.py  <-->  MySQL
                                          |
                                   algorithms/ (FCFS, SJF, Priority, Round Robin)
```

## 9. Functional Requirements

See the CORE feature list in the project brief: lab/computer management,
manual fault reporting, maintenance requests -> tasks, technician
management, resource inventory, FCFS/SJF/Priority scheduling with Gantt
chart and metrics, resource allocation, resource release,
maintenance history, and a Flask dashboard -- all implemented in this
codebase.

## 10. Non-Functional Requirements

- Runs entirely on one Windows/Linux laptop; no cloud, no Docker.
- No external runtime dependency (no CDN scripts; CSS/JS are all local).
- SQL-injection safe (parameterized queries throughout).
- Resource allocation is transactional (all-or-nothing).
- Readable, modular, beginner-explainable code -- no algorithm hidden
  inside a third-party library.

## 11-12. Database Design / ER Diagram

See `docs/DATABASE.md` for the full schema, relationships, and an ER
description.

## 13-18. OS Concepts (FCFS, SJF, Priority, Round Robin)

See `docs/ALGORITHMS.md` for a full walkthrough with worked examples,
including the exact numbers used in the seed data.

## 19. Resource Allocation

Resource allocation is implemented as its own transactional workflow
(`services/resource_service.py::allocate_resources_for_task`):
1. Read the task's resource requirements (`task_resources`).
2. Check current availability (`resources.available_quantity`).
3. If every required resource is available, commit the allocation
   (INSERT into `resource_allocations`, update
   `task_resources.currently_allocated`) as one atomic transaction; a
   database trigger then auto-decrements `resources.available_quantity`.
4. If any resource is short, nothing is written except the task's status
   moving to "Waiting for Resource" -- the allocation is postponed,
   never partially applied.

## 20. Flask Architecture

Five Blueprints, one per module (see Section 8). Business logic and
validation live in `services/`, never inside the route handlers or
inside HTML templates.

## 21. MySQL Integration

`mysql-connector-python`, parameterized queries only, credentials read
from a local `.env` file via `config.py` (never hard-coded). See
`db/database.py` for the connection/transaction helpers.

## 22. Testing

See `docs/TESTING.md` for the test-case table (expected vs actual
result structure) covering every core workflow, including a rollback
test.

## 23. Limitations

- The lab computers in the database are simulated records; physical
  faults are reported manually.
- The scheduling algorithms are an application-level simulation for
  ordering maintenance work; they do not touch the OS's own process
  scheduler.
- Resource allocation is an availability check against the resource
  model represented in this application.
- No cloud deployment is included in this prototype.

## 24. Future Scope

- Preemptive scheduling variants (SRTF, preemptive priority).
- Role-based login for technicians to update their own task status.
- Exportable PDF maintenance reports per lab/computer.

## 25. Conclusion

SmartLab demonstrates, in a single runnable Flask + MySQL project small
enough for one student to fully explain in a viva, how classic OS
scheduling concepts can be applied,
honestly and without hand-waving, to a genuinely resource-constrained
real-world workflow: keeping a college computer lab running.

---

## Validation Rules Implemented

- RAM/storage/resource quantities cannot be negative (`services/*.py`).
- Service time must be > 0; priority must be 1-4.
- Available quantity can never exceed total quantity (DB `CHECK`
  constraint + service-layer guard on every update).
- A completed task cannot be rescheduled or re-allocated
  (`set_task_status` / `allocate_resources_for_task` raise
  `ValidationError`).
- A task cannot be marked "In Progress" before resources are allocated,
  and cannot be "Completed" before it is "In Progress"
  (`maintenance_service.set_task_status`).
- Resources cannot be released for a task that holds none allocated.
- A computer cannot be set back to "Available" while it still has an
  active (non-completed/cancelled) maintenance task.
- Labs/computers with dependent records cannot be deleted (`delete_lab`,
  `delete_computer` check for references first).
- All identifiers passed from forms are validated against the database
  before use; missing records raise a friendly `ValidationError`, never
  a raw stack trace, in every route (`try/except` + `flash()`).
