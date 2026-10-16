
import unittest

from algorithms.fcfs import run_fcfs
from algorithms.sjf import run_sjf
from algorithms.priority import run_priority
from algorithms.round_robin import run_round_robin

# The six demo tasks from database/seed.sql (arrival, service, priority).
SEED_TASKS = [
    {"task_id": "J-101", "arrival_time": 0,  "service_time": 40, "priority": 1},
    {"task_id": "J-102", "arrival_time": 5,  "service_time": 20, "priority": 2},
    {"task_id": "J-103", "arrival_time": 10, "service_time": 25, "priority": 3},
    {"task_id": "J-104", "arrival_time": 15, "service_time": 10, "priority": 4},
    {"task_id": "J-105", "arrival_time": 20, "service_time": 15, "priority": 4},
    {"task_id": "J-106", "arrival_time": 25, "service_time": 30, "priority": 3},
]


class SchedulingTests(unittest.TestCase):
    """Expected values are the ones documented in docs/ALGORITHMS.md."""

    def test_fcfs_order_and_averages(self):
        r = run_fcfs(SEED_TASKS)
        self.assertEqual(r["order"], ["J-101", "J-102", "J-103", "J-104", "J-105", "J-106"])
        self.assertEqual(r["averages"]["avg_waiting_time"], 52.5)
        self.assertEqual(r["averages"]["avg_turnaround_time"], 75.83)

    def test_sjf_order_and_averages(self):
        r = run_sjf(SEED_TASKS)
        self.assertEqual(r["order"], ["J-101", "J-104", "J-105", "J-102", "J-103", "J-106"])
        self.assertEqual(r["averages"]["avg_waiting_time"], 45.83)

    def test_priority_order_and_averages(self):
        r = run_priority(SEED_TASKS)
        self.assertEqual(r["order"], ["J-101", "J-102", "J-103", "J-106", "J-104", "J-105"])
        self.assertEqual(r["averages"]["avg_waiting_time"], 58.33)

    def test_sjf_has_lowest_average_waiting_time(self):
        waits = {name: fn(SEED_TASKS)["averages"]["avg_waiting_time"]
                 for name, fn in (("FCFS", run_fcfs), ("SJF", run_sjf), ("Priority", run_priority))}
        self.assertEqual(min(waits, key=waits.get), "SJF")

    def test_metric_formulas_hold_for_every_algorithm(self):
        """TAT = CT - AT and WT = TAT - Service, for every task, every algorithm."""
        for fn in (run_fcfs, run_sjf, run_priority, lambda t: run_round_robin(t, quantum=10)):
            for m in fn(SEED_TASKS)["metrics"]:
                self.assertEqual(m["turnaround_time"], m["completion_time"] - m["arrival_time"])
                self.assertEqual(m["waiting_time"], m["turnaround_time"] - m["service_time"])

    def test_no_task_starts_before_it_arrives(self):
        arrival = {t["task_id"]: t["arrival_time"] for t in SEED_TASKS}
        for fn in (run_fcfs, run_sjf, run_priority, lambda t: run_round_robin(t, quantum=10)):
            for block in fn(SEED_TASKS)["gantt"]:
                self.assertGreaterEqual(block["start"], arrival[block["task_id"]])

    def test_idle_gap_is_handled(self):
        tasks = [{"task_id": "A", "arrival_time": 0, "service_time": 5, "priority": 1},
                 {"task_id": "B", "arrival_time": 20, "service_time": 5, "priority": 1}]
        for fn in (run_fcfs, run_sjf, run_priority):
            gantt = fn(tasks)["gantt"]
            self.assertEqual(gantt[1]["start"], 20)   # CPU idles from 5 to 20

    def test_round_robin_gives_each_task_its_full_service_time(self):
        r = run_round_robin(SEED_TASKS, quantum=10)
        ran = {}
        for b in r["gantt"]:
            ran[b["task_id"]] = ran.get(b["task_id"], 0) + (b["end"] - b["start"])
        self.assertEqual(ran, {t["task_id"]: t["service_time"] for t in SEED_TASKS})
        self.assertTrue(all(b["end"] - b["start"] <= 10 for b in r["gantt"]))

    def test_empty_input(self):
        for fn in (run_fcfs, run_sjf, run_priority, run_round_robin):
            self.assertEqual(fn([])["order"], [])


if __name__ == "__main__":
    unittest.main()
