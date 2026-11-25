
import random
import sys
import threading
import types
import unittest
from unittest import mock

try:
    import mysql.connector  # noqa: F401
except ImportError:                                   # lets the tests run without the MySQL driver installed
    _m, _c = types.ModuleType("mysql"), types.ModuleType("mysql.connector")
    _c.Error = Exception
    _m.connector = _c
    sys.modules.update({"mysql": _m, "mysql.connector": _c})

from services import banker_service as bs
from services import maintenance_service as msvc
from services import resource_service as rs
from services.maintenance_service import ValidationError
from tests.fake_db import FakeDB

TOTALS = [4, 3, 2, 3, 3, 1]
MAX6 = [list(p[4]) for p in bs.DEMO_PCS]
PCS = [p[0] for p in bs.DEMO_PCS]
NAMES = ["Technician", "RAM", "Network Tester", "Keyboard", "Mouse", "OS Kit"]


def valid_sequence(avail, mx, al, order):
    """Independent check: replay a sequence and confirm Need <= Work at every step."""
    work = list(avail)
    for i in order:
        need = [m - a for m, a in zip(mx[i], al[i])]
        if any(n > w for n, w in zip(need, work)):
            return False
        work = [w + a for w, a in zip(work, al[i])]
    return len(set(order)) == len(mx)


def six_pc_db(stress=False):
    db = FakeDB()
    for k, (pc, issue, _f, _s, vec) in enumerate(bs.DEMO_PCS):
        vec = list(vec)
        if stress and k in (0, 2):
            vec[1] = 3                                 # RAM-heavy variant used for the unsafe example
        db.add_task(f"J-10{k + 1}", pc, issue, vec)
    return db


class Env(unittest.TestCase):
    def use(self, db):
        patches = [mock.patch.object(bs, "get_connection", db.connect), mock.patch.object(rs, "get_connection", db.connect),
                   mock.patch.object(rs, "get_task", lambda tid: db.d["tasks"].get(tid)),
                   mock.patch.object(bs, "fetch_all", db.fetch_all), mock.patch.object(bs, "fetch_one", db.fetch_one),
                   mock.patch.object(bs, "execute_transaction", db.execute_transaction),
                   mock.patch.object(msvc, "create_manual_request", db.create_request),
                   mock.patch.object(msvc, "approve_request", db.approve_request)]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return db

    def release_again(self, db, allocation_id):
        """Replay the release statement of an allocation row (a repeated / concurrent release)."""
        db.connect().cursor().execute("UPDATE resource_allocations SET status='Released', released_at=NOW() "
                                      "WHERE allocation_id=%s AND status='Allocated'", (allocation_id,))


# ----------------------------------------------------------------------------- pure algorithm
class PureAlgorithm(unittest.TestCase):
    def test_spec_example_t1_t2_t3(self):
        ok, steps, _, _ = bs.safe_sequence([2, 1, 1], [[1, 1, 0], [1, 0, 1], [1, 1, 1]], [[0, 0, 0]] * 3)
        self.assertTrue(ok)
        self.assertEqual([s["i"] for s in steps], [0, 1, 2])

    def test_six_pc_maximum_and_need_matrices(self):
        self.assertEqual(MAX6, [[1, 2, 0, 0, 0, 0], [1, 0, 1, 0, 0, 0], [1, 2, 1, 0, 0, 0],
                                [1, 0, 1, 0, 0, 0], [1, 1, 0, 1, 1, 0], [1, 0, 0, 0, 0, 1]])
        alloc = [[0] * 6 for _ in PCS]
        _, _, need, _ = bs.safe_sequence(TOTALS, MAX6, alloc)
        self.assertEqual(need, MAX6)                   # nothing allocated, so Need = Maximum

    def test_six_pc_safe_sequence_is_mathematically_valid(self):
        alloc = [[0] * 6 for _ in PCS]
        ok, steps, _, work = bs.safe_sequence(TOTALS, MAX6, alloc)
        self.assertTrue(ok)
        self.assertTrue(valid_sequence(TOTALS, MAX6, alloc, [s["i"] for s in steps]))
        self.assertEqual(work, TOTALS)                 # everything is back after all six finish

    def test_request_outcomes_have_different_messages(self):
        mx = [list(v) for v in MAX6]
        mx[0][1], mx[2][1] = 3, 3
        alloc = [[0] * 6 for _ in PCS]
        alloc[2][1] = 1
        avail = [t - sum(r[j] for r in alloc) for j, t in enumerate(TOTALS)]
        ask = lambda pc, k, q: bs.evaluate_request(avail, mx, alloc, PCS.index(pc), [q if j == k else 0 for j in range(6)], NAMES, PCS)
        unsafe, insufficient, exceeds = ask("PC-01", 1, 1), ask("PC-01", 1, 3), ask("PC-02", 0, 2)
        self.assertEqual((unsafe["code"], insufficient["code"], exceeds["code"]), ("UNSAFE", "INSUFFICIENT", "EXCEEDS_NEED"))
        self.assertEqual(len({unsafe["message"], insufficient["message"], exceeds["message"]}), 3)
        self.assertIn("PC-01", unsafe["stuck"])
        self.assertEqual(ask("PC-06", 5, 1)["code"], "OK")

    def test_unsafe_request_is_valid_available_and_within_need(self):
        """The unsafe example is real: before = safe, request <= Need, request <= Available, after = unsafe."""
        mx = [list(v) for v in MAX6]
        mx[0][1], mx[2][1] = 3, 3
        alloc = [[0] * 6 for _ in PCS]
        alloc[2][1] = 1
        avail = [t - sum(r[j] for r in alloc) for j, t in enumerate(TOTALS)]
        self.assertTrue(bs.safe_sequence(avail, mx, alloc)[0])
        req = [0, 1, 0, 0, 0, 0]
        need = [m - a for m, a in zip(mx[0], alloc[0])]
        self.assertTrue(all(r <= n and r <= a for r, n, a in zip(req, need, avail)))
        alloc[0] = [a + r for a, r in zip(alloc[0], req)]
        after = [a - r for a, r in zip(avail, req)]
        self.assertFalse(bs.safe_sequence(after, mx, alloc)[0])
        self.assertTrue(all(t <= x for t, x in zip(after, TOTALS)) and min(after) >= 0)

    def test_sample_workload_never_reaches_an_unsafe_state(self):
        """With the six specified maxima every feasible allocation is safe (sampled), hence the RAM-heavy variant."""
        rnd = random.Random(7)
        for _ in range(20000):
            al = [[rnd.randint(0, x) if rnd.random() < 0.7 else 0 for x in mx] for mx in MAX6]
            tot = [sum(r[j] for r in al) for j in range(6)]
            if all(tot[j] <= TOTALS[j] for j in range(6)):
                self.assertTrue(bs.safe_sequence([t - u for t, u in zip(TOTALS, tot)], MAX6, al)[0])

    def test_reallocation_after_release(self):
        mx, al = [[1, 2], [1, 2]], [[0, 1], [0, 1]]
        names, labels = ["T", "R"], ["A", "B"]
        before = bs.evaluate_request([4, 0], mx, al, 0, [0, 1], names, labels)
        self.assertEqual(before["code"], "INSUFFICIENT")
        al_after = [[0, 1], [0, 0]]                    # B completed and released its RAM
        self.assertTrue(bs.evaluate_request([4, 1], mx, al_after, 0, [0, 1], names, labels)["approved"])

    def test_multiple_completions_return_everything(self):
        al = [[1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0]] + [[0] * 6] * 4
        avail = [t - sum(r[j] for r in al) for j, t in enumerate(TOTALS)]
        ok, steps, _, work = bs.safe_sequence(avail, MAX6, al)
        self.assertTrue(ok and work == TOTALS)


# ----------------------------------------------------------------------------- transactional service
class Service(Env):
    def test_initial_availability_and_six_tasks(self):
        db = self.use(six_pc_db())
        st = bs.get_state()
        self.assertEqual([r["total_quantity"] for r in st["resources"]], TOTALS)
        self.assertEqual([r["allocated"] for r in st["resources"]], [0] * 6)
        self.assertEqual(st["available"], TOTALS)
        self.assertEqual(len(st["tasks"]), 6)
        self.assertTrue(st["safe"] and len(st["steps"]) == 6)
        self.assertEqual([t["max"] for t in st["in_algo"]], MAX6)
        self.assertEqual([t["alloc"] for t in st["in_algo"]], [[0] * 6] * 6)
        self.assertEqual([t["need"] for t in st["in_algo"]], MAX6)

    def test_safe_allocation_is_approved_and_recorded(self):
        db = self.use(six_pc_db())
        out = bs.request_resources("J-103", {1: 1, 2: 1, 3: 1})
        self.assertTrue(out["approved"])
        self.assertEqual(db.allocated(), [1, 1, 1, 0, 0, 0])
        self.assertEqual(db.available(), [3, 2, 1, 3, 3, 1])
        self.assertEqual([r["available_quantity"] for r in db.d["res"]], db.available())
        self.assertEqual(db.d["tasks"]["J-103"]["status"], "Waiting for Resource")
        self.assertEqual(bs.get_state()["result"]["heading"], "ALLOCATION APPROVED")

    def test_full_allocation_marks_task_ready_and_offers_start(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-106", {1: 1, 6: 1})
        self.assertEqual(db.d["tasks"]["J-106"]["status"], "Resources Allocated")
        t = next(x for x in bs.get_state()["tasks"] if x["task_id"] == "J-106")
        self.assertTrue(t["actions"]["start"] and not t["actions"]["allocate"] and not t["actions"]["complete"])

    def test_unsafe_request_is_rejected_and_state_restored(self):
        db = self.use(six_pc_db(stress=True))
        db.give("J-103", [0, 1, 0, 0, 0, 0])
        before = (db.allocated(), len(db.d["alloc"]), db.d["tasks"]["J-101"]["status"])
        out = bs.request_resources("J-101", {2: 1})
        self.assertEqual(out["code"], "UNSAFE")
        self.assertIn("UNSAFE ALLOCATION REQUEST", out["message"])
        self.assertEqual((db.allocated(), len(db.d["alloc"])), before[:2])      # allocations untouched
        self.assertEqual(db.d["tasks"]["J-101"]["status"], "Waiting for Resource")   # the request keeps waiting
        self.assertEqual(db.d["decisions"][-1]["decision"], "Rejected")
        self.assertTrue(bs.get_state()["available"][1] >= 1)           # RAM was available, yet refused
        self.assertEqual(bs.get_state()["result"]["heading"], "ALLOCATION REJECTED")

    def test_insufficient_and_exceeds_need_have_their_own_results(self):
        db = self.use(six_pc_db(stress=True))
        db.give("J-103", [0, 1, 0, 0, 0, 0])
        self.assertEqual(bs.request_resources("J-101", {2: 3})["code"], "INSUFFICIENT")
        self.assertEqual(bs.get_state()["result"]["heading"], "INSUFFICIENT RESOURCES")
        self.assertEqual(bs.request_resources("J-102", {1: 2})["code"], "EXCEEDS_NEED")
        self.assertEqual(bs.get_state()["result"]["heading"], "INVALID REQUEST")
        self.assertEqual(db.allocated(), [0, 1, 0, 0, 0, 0])

    def test_dry_run_changes_nothing(self):
        db = self.use(six_pc_db())
        out = bs.request_resources("J-106", {1: 1}, dry_run=True)
        self.assertTrue(out["approved"])
        self.assertEqual((db.allocated(), db.d["decisions"], db.d["tasks"]["J-106"]["status"]), ([0] * 6, [], "Pending"))

    # ---- dynamic task creation
    def test_new_task_joins_the_safety_check_and_there_is_no_limit_of_six(self):
        db = self.use(six_pc_db())
        msg = bs.create_task("PC-07", "Keyboard keys stuck", {4: 1, 1: 1})
        self.assertIn("J-201", msg)
        for n in range(8, 13):
            bs.create_task(f"PC-{n:02d}", "Slow startup", {1: 1, 2: 1})
        st = bs.get_state()
        self.assertEqual(len(st["in_algo"]), 12)                       # 6 demo tasks + PC-07 + 5 more
        new = next(t for t in st["in_algo"] if t["computer_id"] == "PC-07")
        self.assertEqual((new["max"], new["alloc"], new["need"]), ([1, 0, 0, 1, 0, 0], [0] * 6, [1, 0, 0, 1, 0, 0]))
        self.assertTrue(st["safe"])
        self.assertTrue(bs.request_resources(new["task_id"], {1: 1, 4: 1})["approved"])    # same algorithm as the demo PCs

    def test_new_task_validation(self):
        db = self.use(six_pc_db())
        bad = [("PC-07", "x", {1: 5}, "exist in total"), ("PC-07", "x", {}, "at least one"), ("PC-07", "", {1: 1}, "issue"),
               ("PC-07", "x", {1: -1}, "negative"), ("", "x", {1: 1}, "Select a PC"), ("PC-99", "x", {1: 1}, "does not exist")]
        for pc, text, mx, word in bad:
            with self.assertRaises(ValidationError) as ctx:
                bs.create_task(pc, text, mx)
            self.assertIn(word, str(ctx.exception))
        bs.create_task("PC-07", "same issue", {1: 1})
        with self.assertRaises(ValidationError):
            bs.create_task("PC-07", "same issue", {1: 1})               # accidental duplicate
        self.assertEqual(len(db.d["tasks"]), 7)

    def test_task_without_maximum_is_never_left_behind(self):
        db = self.use(six_pc_db())
        db.fail_on_write = 1                                           # saving the maximum fails
        with mock.patch.object(bs, "cancel_task", wraps=bs.cancel_task) as cancel:
            with self.assertRaises(RuntimeError):
                bs.create_task("PC-07", "x", {1: 1})
        cancel.assert_called_once()
        self.assertEqual(db.d["tasks"]["J-201"]["status"], "Cancelled")

    # ---- resource requirement rows (Max required) incl. remove and new tasks
    def test_requirement_rules(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 1})
        for rid, qty in ((2, 0), (1, 99)):                              # must be > 0 and at most what exists in total
            with self.assertRaises(ValidationError):
                bs.save_requirement("J-103", rid, qty)
        with self.assertRaises(ValidationError):
            bs.remove_requirement("J-103", 1)                           # technician already allocated: row is locked
        self.assertIn("removed", bs.remove_requirement("J-103", 3))     # the unallocated network tester row can go
        with self.assertRaises(ValidationError):
            bs.remove_requirement("J-103", 3)                           # already gone
        self.assertNotIn(("J-103", 3), db.d["tr"])
        self.assertEqual(db.allocated(), [1, 1, 0, 0, 0, 0])            # allocations untouched

    def test_requirement_below_allocated_is_refused(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 2})
        with self.assertRaises(ValidationError) as ctx:
            bs.save_requirement("J-103", 2, 1)
        self.assertIn("already allocated", str(ctx.exception))
        self.assertEqual(db.d["tr"][("J-103", 2)]["max"], 2)

    def test_new_task_requirements_can_be_edited_and_removed(self):
        db = self.use(six_pc_db())
        bs.create_task("PC-07", "Mouse dead", {5: 1})
        bs.save_requirement("J-201", 1, 1)                              # add a row to the new task
        self.assertEqual(sorted(r["name"] for r in bs.get_requirements("J-201")["rows"]), ["Lab Technician Pool", "Optical Mouse"])
        bs.remove_requirement("J-201", 5)                               # and remove a wrong one
        self.assertEqual([r["name"] for r in bs.get_requirements("J-201")["rows"]], ["Lab Technician Pool"])
        bs.remove_requirement("J-201", 1)
        st = bs.get_state()
        self.assertNotIn("J-201", [t["task_id"] for t in st["in_algo"]])          # no maximum left -> left out of the algorithm
        self.assertEqual(next(t for t in st["tasks"] if t["task_id"] == "J-201")["alloc_status"], "No maximum defined")

    def test_requirement_that_makes_the_state_unsafe_is_flagged(self):
        db = self.use(six_pc_db())
        db.give("J-101", [0, 1, 0, 0, 0, 0])
        db.give("J-103", [0, 1, 0, 0, 0, 0])
        self.assertTrue(bs.get_state()["safe"])
        self.assertNotIn("Warning", bs.save_requirement("J-101", 2, 3))
        self.assertIn("no longer in a safe state", bs.save_requirement("J-103", 2, 3))
        self.assertFalse(bs.get_state()["safe"])

    # ---- editable Allocated Resources table
    def test_release_after_completion_keeps_other_allocations(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 1, 3: 1})
        bs.request_resources("J-106", {1: 1, 6: 1})
        db.d["tasks"]["J-103"]["status"] = "In Progress"
        used = rs.complete_task_with_release(db.d["tasks"]["J-103"], "done")
        self.assertIn("Lab Technician Pool x1", used)
        self.assertEqual(db.d["tasks"]["J-103"]["status"], "Completed")
        self.assertEqual(db.d["history"][0]["task_id"], "J-103")
        self.assertEqual(db.available(), [3, 3, 2, 3, 3, 0])           # only PC-06's technician + OS kit remain held
        self.assertEqual(db.allocated(), [1, 0, 0, 0, 0, 1])
        self.assertEqual([r["available_quantity"] for r in db.d["res"]], db.available())
        self.assertEqual(db.d["tr"][("J-103", 1)]["cur"], 0)

    def test_completing_twice_does_not_release_twice(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1})
        db.d["tasks"]["J-103"]["status"] = "In Progress"
        rs.complete_task_with_release(db.d["tasks"]["J-103"], "done")
        after_first = db.available()
        with self.assertRaises(ValidationError):
            rs.complete_task_with_release(db.d["tasks"]["J-103"], "again")
        self.release_again(db, db.d["alloc"][0]["allocation_id"])       # even a replayed release frees nothing twice
        self.assertEqual(db.available(), after_first)
        self.assertEqual(len(db.d["history"]), 1)
        self.assertTrue(all(a <= t for a, t in zip(db.available(), TOTALS)))

    def test_completion_is_atomic(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 1, 3: 1})
        db.d["tasks"]["J-103"]["status"] = "In Progress"
        db.writes, db.fail_on_write = 0, 5                              # fails while writing the history row
        with self.assertRaises(RuntimeError):
            rs.complete_task_with_release(db.d["tasks"]["J-103"], "done")
        self.assertEqual(db.allocated(), [1, 1, 1, 0, 0, 0])            # release rolled back with it
        self.assertEqual((db.d["tasks"]["J-103"]["status"], db.d["history"]), ("In Progress", []))

    def test_cancel_releases_only_that_task_and_keeps_history(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 1})
        bs.request_resources("J-106", {1: 1, 6: 1})
        msg = bs.cancel_task("J-103")
        self.assertIn("cancelled", msg)
        self.assertEqual(db.d["tasks"]["J-103"]["status"], "Cancelled")
        self.assertEqual(db.allocated(), [1, 0, 0, 0, 0, 1])
        self.assertEqual(len(db.d["alloc"]), 4)                         # rows kept, now marked Released
        self.assertEqual(sum(a["status"] == "Released" for a in db.d["alloc"]), 2)
        self.assertEqual([r["available_quantity"] for r in db.d["res"]], db.available())
        with self.assertRaises(ValidationError):
            bs.cancel_task("J-103")                                     # no second release
        self.assertEqual(db.allocated(), [1, 0, 0, 0, 0, 1])
        self.assertNotIn("J-103", [t["task_id"] for t in bs.get_state()["tasks"]])
        db.d["tasks"]["J-102"]["status"] = "Completed"
        with self.assertRaises(ValidationError):
            bs.cancel_task("J-102")

    def test_resources_after_several_completions_and_reallocation(self):
        db = self.use(six_pc_db())
        for tid, vec in (("J-103", {1: 1, 2: 1, 3: 1}), ("J-106", {1: 1, 6: 1}), ("J-105", {1: 1, 2: 1, 4: 1, 5: 1})):
            self.assertTrue(bs.request_resources(tid, vec)["approved"])
            db.d["tasks"][tid]["status"] = "In Progress"
        self.assertEqual(db.available(), [1, 1, 1, 2, 2, 0])
        for tid in ("J-103", "J-106", "J-105"):
            rs.complete_task_with_release(db.d["tasks"][tid], "done")
        self.assertEqual(db.available(), TOTALS)
        self.assertTrue(bs.request_resources("J-101", {1: 1, 2: 2})["approved"])      # freed resources are reusable

    def test_rollback_when_the_database_fails_midway(self):
        db = self.use(six_pc_db())
        db.fail_on_write = 4
        with self.assertRaises(RuntimeError):
            bs.request_resources("J-103", {1: 1, 2: 1, 3: 1})
        self.assertEqual((db.allocated(), db.d["alloc"], db.d["decisions"]), ([0] * 6, [], []))
        self.assertEqual(db.d["tasks"]["J-103"]["status"], "Pending")

    def test_concurrent_requests_never_over_allocate(self):
        db = FakeDB()
        for k in range(4):
            db.add_task(f"J-10{k + 1}", f"PC-0{k + 1}", "needs the only OS kit", [0, 0, 0, 0, 0, 1])
        self.use(db)
        results, gate = [], threading.Barrier(4)

        def go(tid):
            gate.wait()
            results.append(bs.request_resources(tid, {6: 1})["code"])

        threads = [threading.Thread(target=go, args=(f"J-10{k + 1}",)) for k in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(results), ["INSUFFICIENT"] * 3 + ["OK"])
        self.assertEqual(db.allocated()[5], 1)

    def test_waiting_request_becomes_eligible_after_release(self):
        db = self.use(six_pc_db(stress=True))
        db.give("J-103", [0, 1, 0, 0, 0, 0])
        db.give("J-105", [1, 1, 0, 1, 1, 0])
        self.assertEqual(bs.request_resources("J-101", {2: 3})["code"], "INSUFFICIENT")
        t = next(x for x in bs.get_state()["tasks"] if x["task_id"] == "J-101")
        self.assertEqual(t["alloc_status"], "Waiting for resources")
        self.assertFalse(t["actions"]["approve_waiting"])
        bs.cancel_task("J-105")
        bs.cancel_task("J-103")
        t = next(x for x in bs.get_state()["tasks"] if x["task_id"] == "J-101")
        self.assertTrue(t["actions"]["approve_waiting"])                # eligible, but never auto-allocated
        self.assertEqual(db.allocated(), [0] * 6)
        self.assertTrue(bs.request_resources("J-101", t["waiting"]["vector"])["approved"])   # manual approval re-runs Banker's

    def test_reset_releases_everything_and_keeps_history(self):
        db = self.use(six_pc_db())
        bs.request_resources("J-103", {1: 1, 2: 1, 3: 1})
        bs.reset_allocations()
        self.assertEqual((db.allocated(), db.available()), ([0] * 6, TOTALS))
        self.assertEqual(len(db.d["alloc"]), 3)
        self.assertEqual(db.d["tasks"]["J-103"]["status"], "Pending")


# ----------------------------------------------------------------------------- Execution Flow page
class Page(Env):
    def client(self, db):
        import app as appmod
        self.use(db)
        flask_app = appmod.create_app()
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()
        with client.session_transaction() as s:
            s["user_id"], s["display_name"] = 1, "t"
        return client

    def test_page_is_minimal_and_lists_every_pending_task(self):
        db = FakeDB()
        db.add_task("J-101", "PC-01", "No boot", [0] * 6)                  # pending task, nothing entered yet
        db.add_task("J-102", "PC-02", "Slow", [1, 0, 0, 0, 0, 0], status="Waiting for Resource")
        page = self.client(db).get("/execution-flow").get_data(as_text=True)
        self.assertNotIn("Result:", page)                      # hidden until the Result button is clicked
        self.assertIn('id="btn-result"', page)
        for shown in ("Available Resources", "Pending Tasks", "J-101", "J-102", "Recalculate", "setInterval"):
            self.assertIn(shown, page)
        self.assertEqual(page.count('class="qty-input"'), 2 * 6 * 2)       # required + allocated boxes per task and resource
        self.assertNotIn("Allocation Matrix", page)
        self.assertNotIn("Tasks Waiting for Resources", page)
        self.assertIn("Need Matrix", page)
        for gone in ("Need (Maximum - Allocation)", "Add New Task", "Resource Requirements", "Maintenance Tasks", "Demo"):
            self.assertNotIn(gone, page)

    def test_typed_numbers_generate_the_result(self):
        db = FakeDB()
        for k, vec in enumerate(([1, 1, 0, 0, 0, 0], [1, 0, 1, 0, 0, 0], [1, 0, 0, 0, 0, 1]), start=1):
            db.add_task(f"J-10{k}", f"PC-0{k}", "x", [0] * 6)
        c = self.client(db)
        self.assertIn("NOTHING TO CHECK", c.get("/execution-flow/partial?result=1").get_data(as_text=True))
        form = {"m_J-101_1": "1", "m_J-101_2": "1", "m_J-102_1": "1", "m_J-102_3": "1", "m_J-103_1": "1", "m_J-103_6": "1"}
        out = c.post("/execution-flow/calculate", data=form).get_json()
        self.assertTrue(out["ok"], out)
        part = c.get("/execution-flow/partial?result=1").get_data(as_text=True)
        self.assertIn("SAFE", part)
        self.assertIn("J-101 -&gt; J-102 -&gt; J-103", part)               # the order comes from the algorithm
        rows = c.get("/execution-flow/tasks").get_data(as_text=True)
        self.assertIn('name="m_J-102_3" value="1"', rows)                  # saved numbers come back
        self.assertEqual(db.d["tr"][("J-103", 6)]["max"], 1)

    def test_changing_one_tasks_requirement_recalculates_the_result(self):
        db = FakeDB()
        db.add_task("J-101", "PC-01", "a", [0, 2, 0, 0, 0, 0])
        db.add_task("J-102", "PC-02", "b", [1, 0, 0, 0, 0, 0])
        db.add_task("J-103", "PC-03", "c", [0, 2, 0, 0, 0, 0])
        db.give("J-101", [0, 1, 0, 0, 0, 0])
        db.give("J-103", [0, 1, 0, 0, 0, 0])
        c = self.client(db)
        page = c.get("/execution-flow").get_data(as_text=True)
        self.assertIn('addEventListener("input"', page)                    # edits are saved and recalculated by themselves
        self.assertIn(">SAFE<", c.get("/execution-flow/partial?result=1").get_data(as_text=True))
        row = lambda t, v: c.post("/execution-flow/calculate", data={f"m_{t}_{k}": str(q) for k, q in enumerate(v, start=1)}).get_json()
        self.assertTrue(row("J-101", [0, 3, 0, 0, 0, 0])["ok"])            # only J-101's boxes were sent
        self.assertEqual(db.d["tr"][("J-103", 2)]["max"], 2)               # other tasks untouched
        self.assertIn(">SAFE<", c.get("/execution-flow/partial?result=1").get_data(as_text=True))
        self.assertTrue(row("J-103", [0, 3, 0, 0, 0, 0])["ok"])            # now neither RAM task can ever finish
        self.assertIn(">UNSAFE<", c.get("/execution-flow/partial?result=1").get_data(as_text=True))
        self.assertTrue(row("J-103", [0, 2, 0, 0, 0, 0])["ok"])            # change it back: new result again
        self.assertIn(">SAFE<", c.get("/execution-flow/partial?result=1").get_data(as_text=True))
        db.d["tr"][("J-102", 1)]["max"] = 3                                # changed from another page
        self.assertIn('name="m_J-102_1" value="3"', c.get("/execution-flow/tasks").get_data(as_text=True))

    def test_invalid_numbers_save_nothing(self):
        db = FakeDB()
        db.add_task("J-101", "PC-01", "x", [0] * 6)
        db.add_task("J-102", "PC-02", "y", [0, 0, 0, 0, 0, 0])
        c = self.client(db)
        before = dict(db.d["tr"])
        for bad in ({"m_J-101_1": "abc"}, {"m_J-101_1": "9"}, {"m_J-101_1": "-1"}):
            out = c.post("/execution-flow/calculate", data=dict(bad, **{"m_J-102_1": "1"})).get_json()
            self.assertFalse(out["ok"])
            self.assertEqual(db.d["tr"], before)                            # all-or-nothing, even the valid row

    def test_cannot_go_below_what_is_already_allocated_and_zero_removes_a_row(self):
        db = FakeDB()
        db.add_task("J-101", "PC-01", "x", [2, 1, 0, 0, 0, 0])
        db.give("J-101", [1, 0, 0, 0, 0, 0])
        c = self.client(db)
        out = c.post("/execution-flow/calculate", data={"m_J-101_1": "0"}).get_json()
        self.assertFalse(out["ok"])
        self.assertIn("already allocated", out["message"])
        self.assertTrue(c.post("/execution-flow/calculate", data={"m_J-101_2": "0"}).get_json()["ok"])   # wrong row removed
        self.assertNotIn(("J-101", 2), db.d["tr"])

    def test_task_added_on_the_maintenance_page_shows_up_and_works(self):
        db = FakeDB()
        db.add_task("J-101", "PC-01", "old", [1, 0, 0, 0, 0, 0])
        c = self.client(db)
        self.assertNotIn("J-150", c.get("/execution-flow/tasks").get_data(as_text=True))
        db.add_task("J-150", "PC-07", "approved just now", [0] * 6)         # what approving a request creates
        self.assertIn("J-150", c.get("/execution-flow/tasks").get_data(as_text=True))
        self.assertTrue(c.post("/execution-flow/calculate", data={"m_J-150_5": "1"}).get_json()["ok"])
        self.assertIn("J-150", c.get("/execution-flow/partial?result=1").get_data(as_text=True))   # now part of the result
        db.d["tasks"]["J-101"]["status"] = "Completed"
        self.assertNotIn("J-101", c.get("/execution-flow/tasks").get_data(as_text=True))  # finished tasks leave the list


if __name__ == "__main__":
    unittest.main()
