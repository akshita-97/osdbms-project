
import sys
import types
import unittest
from unittest import mock

try:
    import mysql.connector  # noqa: F401
except ImportError:
    _m, _c = types.ModuleType("mysql"), types.ModuleType("mysql.connector")
    _c.Error = Exception
    _m.connector = _c
    sys.modules.update({"mysql": _m, "mysql.connector": _c})

from services import banker_service as bs
from services import maintenance_service as msvc
from services import resource_service as rs
from services.maintenance_service import ValidationError
from tests.fake_db import FakeDB


def seed_db():
    db = FakeDB()
    spec = [("J-101", "PC-04", [3, 0, 2, 0, 0, 0], "In Progress", [1, 0, 1, 0, 0, 0]),
            ("J-102", "PC-07", [2, 1, 0, 0, 0, 0], "In Progress", [1, 1, 0, 0, 0, 0]),
            ("J-103", "PC-10", [2, 2, 1, 0, 0, 0], "Resources Allocated", [1, 1, 1, 0, 0, 0]),
            ("J-104", "PC-11", [1, 1, 1, 0, 0, 0], "Pending", None),
            ("J-105", "PC-12", [0, 0, 0, 1, 0, 0], "Pending", None),
            ("J-106", "PC-08", [0, 0, 0, 0, 1, 1], "Pending", None)]
    for tid, pc, mx, status, held in spec:
        db.add_task(tid, pc, "issue " + tid, mx, status)
        if held:
            db.give(tid, held)
    return db


class FlowRules(unittest.TestCase):
    def setUp(self):
        self.db = db = seed_db()

        def fake_execute(q, p=()):
            q = " ".join(q.split())
            assert q.startswith("UPDATE maintenance_tasks SET status='Resources Allocated'"), q
            t = db.d["tasks"][p[0]]
            if t["status"] in ("Pending", "Scheduled", "Waiting for Resource"):
                t["status"] = "Resources Allocated"

        def fake_set_status(tid, new, completion_time=None):
            cur = db.d["tasks"][tid]["status"]
            if new == "In Progress" and cur not in ("Resources Allocated", "In Progress"):
                raise ValidationError("Cannot start maintenance: required resources have not been allocated yet.")
            db.d["tasks"][tid]["status"] = new

        def fake_complete(request_id, remarks):
            tid = next(t["task_id"] for t in db.d["tasks"].values() if t["request_id"] == request_id)
            if db.d["tasks"][tid]["status"] != "In Progress":
                raise ValidationError("Cannot complete a task that has not started (In Progress).")
            rs.release_resources_for_task(tid)
            db.d["tasks"][tid]["status"] = "Completed"

        for target, name, val in [(bs, "get_connection", db.connect), (rs, "get_connection", db.connect),
                                  (rs, "get_task", lambda tid: db.d["tasks"].get(tid)),
                                  (bs, "execute", fake_execute), (msvc, "set_task_status", fake_set_status),
                                  (msvc, "get_task", lambda tid: db.d["tasks"].get(tid)),
                                  (msvc, "complete_request", fake_complete)]:
            p = mock.patch.object(target, name, val)
            p.start()
            self.addCleanup(p.stop)

    def top(self):
        s = bs.get_state()
        t = next((x for x in s["tasks"] if x["task_id"] == s["steps"][0]["label"]), None) if s["steps"] else None
        return s, t

    def exact(self, s, t):
        return {r["resource_id"]: n for r, n in zip(s["resources"], t["need"])}

    def test_empty_request_names_the_resource(self):
        s, t = self.top()
        self.assertEqual(t["task_id"], "J-102")                       # the task from the report
        with self.assertRaises(ValidationError) as cm:
            bs.start_task("J-102", {r["resource_id"]: 0 for r in s["resources"]})
        self.assertEqual(str(cm.exception), "Lab Technician Pool: this task needs exactly 1, but the Request "
                                            "Resources table has 0. Correct the quantity before starting.")

    def test_top_task_shows_start_not_complete_even_if_marked_in_progress(self):
        _, t = self.top()
        self.assertTrue(t["actions"]["start"])
        self.assertFalse(t["actions"]["complete"])
        with self.assertRaises(ValidationError):
            bs.complete_task(t["task_id"])                            # cannot be completed before Start

    def test_displayed_status_pending_except_top_task(self):
        s, top = self.top()
        shown = {t["task_id"]: t["flow_status"] for t in s["tasks"]}
        self.assertEqual(shown[top["task_id"]], "Waiting for Resource")
        self.assertEqual([v for k, v in shown.items() if k != top["task_id"]], ["Pending"] * 5)

    def test_every_task_start_then_complete(self):
        done = []
        for _ in range(6):
            s, t = self.top()
            self.assertIsNotNone(t, f"no task at the top, done so far {done}")
            tid = t["task_id"]
            self.assertTrue(t["actions"]["start"] and not t["actions"]["complete"], tid)
            for other in s["tasks"]:                                   # nobody else can start or complete
                if other["task_id"] != tid:
                    self.assertFalse(other["actions"]["start"] or other["actions"]["complete"], other["task_id"])
            with self.assertRaises(ValidationError):
                bs.complete_task(tid)                                  # Complete before Start is refused
            need = self.exact(s, t)
            wrong = dict(need)
            k = next((r for r, n in need.items() if n), None)
            wrong[k] = need[k] + 1 if k else 1                         # one too many (or one on a zero row)
            with self.assertRaises(ValidationError) as cm:
                bs.start_task(tid, wrong)
            self.assertIn("this task needs exactly", str(cm.exception))
            if k and need[k] > 0:
                short = dict(need)
                short[k] = need[k] - 1                                 # one too few
                with self.assertRaises(ValidationError):
                    bs.start_task(tid, short)
            bs.start_task(tid, need)                                   # exact quantities -> started
            s, t = self.top()
            self.assertEqual(t["task_id"], tid)                        # running task stays at the front
            self.assertTrue(t["actions"]["complete"] and not t["actions"]["start"], tid)
            bs.complete_task(tid)
            done.append(tid)
        self.assertEqual(sorted(done), ["J-101", "J-102", "J-103", "J-104", "J-105", "J-106"])
        self.assertEqual(self.db.allocated(), [0] * 6)                 # everything released at the end


if __name__ == "__main__":
    unittest.main()
