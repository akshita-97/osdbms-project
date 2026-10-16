# SmartLab -- OS Concepts &amp; Algorithms

> **Academic framing (read this first):** every algorithm below is an
> **application-level simulation/decision module** used only to plan
> *maintenance-job* scheduling. Technicians are not CPU processes. This project does not replace,
> patch, or interact with the operating system's own scheduler in any
> way -- it is entirely userspace Python running inside the Flask app.

All examples below use the demo scenario shipped in `database/seed.sql`.

## Common Task Attributes

| Task  | Computer | Fault | Arrival | Service Time | Priority |
|-------|----------|-------|---------|---------------|----------|
| J-101 | PC-04 | OS failure | 0 | 40 | 1 (Critical) |
| J-102 | PC-07 | Network problem | 5 | 20 | 2 (High) |
| J-103 | PC-10 | RAM problem | 10 | 25 | 3 (Medium) |
| J-104 | PC-13 | Keyboard problem | 15 | 10 | 4 (Low) |
| J-105 | PC-16 | Software install | 20 | 15 | 4 (Low) |
| J-106 | PC-08 | Screen/mouse issue | 25 | 30 | 3 (Medium) |

"Service time represents the estimated time required to perform a
maintenance job, and is used as the burst-time equivalent for
scheduling simulation." It is **not** claimed to be an OS burst time.

Formulas used throughout (`algorithms/fcfs.py`, `sjf.py`, `priority.py`):

```
Turnaround Time = Completion Time - Arrival Time
Waiting Time    = Turnaround Time - Service Time
Response Time   = Start Time - Arrival Time      (non-preemptive: equals waiting time)
```

## FCFS (First Come First Serve)

Sort strictly by arrival time; process in that order, letting the clock
idle forward if the technician/queue is empty when the next job arrives.

Running the demo tasks through `algorithms/fcfs.py` gives execution
order **J-101 -> J-102 -> J-103 -> J-104 -> J-105 -> J-106** (arrival
order, since no two arrivals tie), with:

| Task | AT | Service | CT | TAT | WT | RT |
|------|----|---------|----|-----|----|----|
| J-101 | 0 | 40 | 40 | 40 | 0 | 0 |
| J-102 | 5 | 20 | 60 | 55 | 35 | 35 |
| J-103 | 10 | 25 | 85 | 75 | 50 | 50 |
| J-104 | 15 | 10 | 95 | 80 | 70 | 70 |
| J-105 | 20 | 15 | 110 | 90 | 75 | 75 |
| J-106 | 25 | 30 | 140 | 115 | 85 | 85 |

Average Waiting Time = 52.5 min, Average Turnaround = 75.83 min.

## SJF (Shortest Job First, non-preemptive)

At every decision point, only tasks that have *already arrived* are
eligible; among those, the smallest `service_time` wins (ties -> earlier
arrival, then original order). If nothing has arrived yet, the clock
jumps to the next arrival.

Running the demo tasks gives execution order
**J-101 -> J-104 -> J-105 -> J-102 -> J-103 -> J-106**
(J-101 must go first since nothing else has arrived by time 0; after
that, the shortest *already-arrived* remaining job is always chosen).
Average Waiting Time = 45.83 min -- lower than FCFS, as expected for
SJF, at the cost of J-102/J-103 waiting longer than they would have
under FCFS.

## Priority Scheduling (non-preemptive)

Priority mapping: 1 = Critical, 2 = High, 3 = Medium, 4 = Low (lower
number = served first). Ties -> earlier arrival, then original order.

Running the demo tasks gives execution order
**J-101 -> J-102 -> J-103 -> J-106 -> J-104 -> J-105**
(J-106, Medium priority, jumps ahead of the two Low-priority jobs even
though it arrived after them). Average Waiting Time = 58.33 min in this
particular mix -- Priority Scheduling optimizes for urgency, not
average wait, which is exactly the trade-off worth explaining in a viva.

## Round Robin (OPTIONAL academic simulation)

Configurable time quantum (default 10 minutes). Implemented in
`algorithms/round_robin.py` purely to demonstrate the OS concept --
**it is not SmartLab's real-world maintenance policy**, since
maintenance work realistically runs to completion once a technician
starts it rather than being time-sliced. Available from the Scheduling
Queue page's algorithm dropdown for demonstration purposes.

## Gantt Chart

The Scheduling Queue page renders a proportional-width Gantt chart
(`templates/scheduling.html`) directly from each algorithm's `gantt`
output (`[{task_id, start, end}, ...]`) -- plain HTML/CSS flex boxes,
no chart library required.
