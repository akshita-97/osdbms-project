# SmartLab -- Test Cases

Manual/functional test cases covering every core workflow. Each row
gives the expected result; "Actual Result" is left for the person
running the tests to fill in during a demo/viva.

| # | Test Case | Steps | Expected Result | Actual Result |
|---|-----------|-------|------------------|----------------|
| 1 | Add lab | Labs page -> fill Lab ID/Name/Location/Capacity -> Add Lab | New lab appears in the labs table immediately | |
| 2 | Add lab with duplicate ID | Add a lab using an existing `lab_id` | Friendly error flash: "Lab ID '...' already exists." No duplicate row created | |
| 3 | Add computer | Computers page -> fill form with a valid `lab_id` -> Add Computer | Computer appears under the correct lab | |
| 4 | Add computer with negative RAM | Enter `ram_gb = -4` | Friendly error: "RAM cannot be negative." No row inserted | |
| 5 | Report fault (manual) | Maintenance page -> Report a Fault form -> submit | A new row appears in Maintenance Requests with status "Pending Review" | |
| 6 | Approve, assign technician and start | Approve a Pending Review request -> pick a technician -> Assign & Start | Status becomes "In Progress" with the technician shown; a new `J-xxx` task is created; computer status becomes "Under Maintenance"; technician becomes Busy | |
| 6b | Mark completed | Type remarks on an In Progress row -> Mark Completed | Row leaves the Requests table and appears in History; computer becomes Available; technician Available again | |
| 7 | Run FCFS | Scheduling Queue -> select FCFS -> Run Scheduling | Execution order = tasks sorted by arrival time; Gantt chart segments match each task's start/end; metrics table's Waiting/Turnaround/Response times satisfy `TAT = CT - AT`, `WT = TAT - Service` | |
| 8 | Run SJF | Scheduling Queue -> select SJF -> Run Scheduling | Among already-arrived tasks, the shortest remaining service time is always chosen next; no task is scheduled before its arrival time | |
| 9 | Run Priority Scheduling | Scheduling Queue -> select Priority -> Run Scheduling | Lower priority-number (more urgent) tasks are scheduled ahead of already-arrived, lower-urgency tasks | |
| 10 | Resource allocation -- success case | Open a task whose required resources are all available (e.g. J-105 from the seed data) -> Allocate Resources | Flash: "Resources allocated successfully."; task status becomes "Resources Allocated"; `resources.available_quantity` decreases by the allocated amount | |
| 11 | Resource allocation -- resource unavailable | Try to allocate a task that needs more of a resource than is currently available | Flash explains exactly which resource and by how much is short; task status set to "Waiting for Resource"; no allocation row inserted | |
| 12 | Start maintenance without allocation | On a task still "Pending"/"Waiting for Resource", click Start Maintenance | Friendly error: "Cannot start maintenance: required resources have not been allocated yet." Status unchanged | |
| 13 | Complete maintenance | On an "In Progress" task, submit Complete Maintenance with remarks | Task status becomes "Completed"; `maintenance_history` gets a new row; computer status trigger sets it back to "Available" | |
| 14 | Complete a task that hasn't started | Try Complete Maintenance on a "Pending" task | Friendly error: "Cannot complete a task that has not started (In Progress)." | |
| 15 | Resource release | On a Completed task that still shows allocated resources, click Release Resources | All related `resource_allocations` rows move to "Released"; `resources.available_quantity` increases back by the released amount (verified via the `trg_after_allocation_release` trigger) | |
| 16 | Release with nothing allocated | Click Release Resources on a task with no active allocations | Friendly error: "No allocated resources to release for this task." | |
| 17 | Database transaction rollback | Simulate a failure mid-allocation (e.g. disconnect MySQL between statements, or induce a bad foreign key) | No partial state: either every statement in the allocation transaction commits, or none do (verified via `execute_transaction`'s try/rollback) | |
| 18 | Invalid input | Submit a maintenance request with an invalid `fault_type` (via a modified request, since the UI only offers valid options) | Friendly `ValidationError` message, no row inserted, no stack trace shown to the user | |
| 19 | Duplicate record | Add a lab or computer using an ID that already exists | Friendly "already exists" error; no duplicate row | |
| 20 | Delete lab with computers | Try to delete a lab that still has computers assigned | Friendly error: "Cannot delete lab '...': N computer(s) still reference it." Lab is not deleted | |
| 21 | Computer cannot go Available with an active task | Try to manually set a computer's status to "Available" while it has a task that is not Completed/Cancelled | Friendly error explaining an active maintenance task exists; status unchanged | |
| 22 | Live monitoring | Open Live Monitoring from the sidebar, wait 10 s, open Task Manager and start a heavy program | CPU/RAM/disk/network cards fill in, countdown reaches 0 and values refresh by themselves; CPU graph moves; Pause stops updates, Refresh now updates immediately | |

## Automated Tests

In addition to the manual table above, the project ships automated tests
in the `tests/` folder (Python's built-in `unittest`, nothing extra to
install):

| File | What it checks | Needs MySQL? |
|------|----------------|--------------|
| `tests/test_algorithms.py` | FCFS / SJF / Priority orders and average times match this documentation exactly; Round Robin runs every task for its full service time; TAT/WT formulas hold; idle gaps | No |
| `tests/test_app_smoke.py` | Every page loads (HTTP 200); each scheduling algorithm renders a Gantt chart | Yes (auto-skipped if MySQL isn't set up) |

Run them with `python -m unittest discover -s tests -t . -v`, or open the
**Testing** panel in VS Code (flask icon) and press Run All.
