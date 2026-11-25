# Execution Flow: Banker's Algorithm

Page: **Execution Flow** (`/execution-flow`). Code: `services/banker_service.py`, `routes/banker.py`,
`templates/banker.html`, `templates/_banker_state.html`. Reuses `resources`, `task_resources` (Maximum),
`resource_allocations` (Allocation) and the existing triggers on `resource_allocations`; only new table: `allocation_requests`.

## Page (kept minimal)
Only three things: the **Result** (SAFE/UNSAFE with the safe sequence such as `J-103 -> J-104 -> ...`), **Available Resources**
(Total, Allocated, Available) and **Pending Tasks**.

**Pending Tasks** lists every active task (status not Completed or
Cancelled), including tasks approved later on the Maintenance page. Next to each task is one box per resource. Type how many of
each resource the task needs at most (that is its Maximum), and it is saved automatically about half a second after you stop typing. The result is recalculated from the database each time (**Recalculate** saves every row at once). It is computed from
those numbers with the real Banker's Algorithm (Allocation = what the task already holds, Need = Maximum - Allocation).

- **Allocated Resources** (second table): how many of each resource every task holds now. Type a new number and it is saved:
  a higher number adds an allocation, a lower one releases some (allocation history is kept), Available, Allocated and the Result
  update at once. Rules: whole numbers, never above the task's required amount, and the total held of a resource never above what
  exists. Task status follows (Pending, Waiting for Resource, Resources Allocated), so Start still works. If the new allocations
  leave the system unsafe, the message warns and the Result shows UNSAFE.
- Tasks with nothing entered are not counted yet; they are listed under the Result.
- A value of 0 removes that resource row (a wrong entry); a value below what the task already holds is refused; a value above the
  total is refused. All rows are saved together or not at all.
- The page refreshes itself every 5 seconds: new tasks appear, finished ones leave, and numbers you are typing are not overwritten.
- Allocating, starting, completing and cancelling still work from the existing Resources and Maintenance pages (completion and
  cancellation release resources automatically through the one release mechanism below).

## One release mechanism
`resource_service.release_in_tx` is the only code that releases allocations; it works inside the caller's transaction.
It is used by task completion (`complete_task_with_release`: status Completed + history + release + technician in one
transaction, also used by the Maintenance page), by cancellation, and by the Resources page. Only rows still `Allocated`
are released and `task_resources` is recomputed from the allocation records, so repeating a completion or cancellation
frees nothing twice. A trigger on `maintenance_tasks` was not added: the project already keeps stock counters with triggers
on `resource_allocations`, and a second release path could release the same allocation twice.

## Unsafe example
With the six sample Maximum vectors exactly as specified no unsafe state can occur (checked by sampling in the tests), so the
unsafe demo uses a RAM-heavy variant (PC-01 and PC-03 may need all 3 RAM modules): PC-03 holds 1 RAM, PC-01 requests 1 RAM
(available, within Need) and the request is rejected as unsafe.

## Tests
`python -m unittest tests.test_banker` (algorithm, transactions on an in-memory database, task creation, cancellation,
atomic completion, concurrency, dashboard). `SMARTLAB_INTEGRATION=1 python -m unittest tests.test_banker_mysql` checks real
MySQL (test database only); it has not been run.
