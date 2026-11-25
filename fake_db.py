
import copy
import threading

from services.maintenance_service import ValidationError

RESOURCES = [(1, "Lab Technician Pool", "Technician", 4), (2, "RAM Module 8GB", "RAM", 3),
             (3, "Network Cable Tester", "Network Tester", 2), (4, "Standard Keyboard", "Keyboard", 3),
             (5, "Optical Mouse", "Mouse", 3), (6, "Windows 10/11 OS Kit", "OS Installation Kit", 1)]
ORDER = ["Technician", "RAM", "Network Tester", "Keyboard", "Mouse", "OS Installation Kit", "Other"]


class FakeDB:
    def __init__(self, totals=None):
        self.lock = threading.RLock()
        self.fail_on_write = None            # raise on the n-th write (to test rollback)
        self.writes = 0
        self.computers = {f"PC-{n:02d}" for n in range(1, 13)}
        res = [dict(resource_id=i, resource_name=n, resource_type=t,
                    total_quantity=(totals[k] if totals else q), available_quantity=(totals[k] if totals else q))
               for k, (i, n, t, q) in enumerate(RESOURCES)]
        self.d = {"res": res, "alloc": [], "tr": {}, "tasks": {}, "requests": {}, "decisions": [], "history": [],
                  "next_alloc": 1, "next_req": 1, "next_task": 201}

    # ---- setup helpers
    def add_task(self, task_id, pc, issue, mx, status="Pending"):
        rid = self.d["next_req"]
        self.d["next_req"] += 1
        self.d["requests"][rid] = dict(computer_id=pc, description=issue)
        self.d["tasks"][task_id] = dict(task_id=task_id, computer_id=pc, request_id=rid, status=status,
                                        problem_description=issue, severity="High", started_at=None, technician_id=None)
        for res_id, q in enumerate(mx, start=1):
            if q:
                self.d["tr"][(task_id, res_id)] = {"max": q, "cur": 0}

    def give(self, task_id, vec):
        """Directly hold resources for a task (as an earlier approved allocation would)."""
        for res_id, q in enumerate(vec, start=1):
            if q:
                self._insert_alloc(task_id, res_id, q)
                self.d["tr"][(task_id, res_id)]["cur"] += q

    def _res(self, rid):
        return next(r for r in self.d["res"] if r["resource_id"] == rid)

    def _insert_alloc(self, task_id, rid, q):
        self.d["alloc"].append(dict(allocation_id=self.d["next_alloc"], task_id=task_id, resource_id=rid, quantity=q, status="Allocated"))
        self.d["next_alloc"] += 1
        self._res(rid)["available_quantity"] -= q                       # trigger trg_after_allocation_insert

    def _release_alloc(self, a):
        if a["status"] == "Allocated":
            a["status"] = "Released"
            self._res(a["resource_id"])["available_quantity"] += a["quantity"]   # trigger ..._release (real change only)

    # ---- numbers for assertions
    def allocated(self):
        return [sum(a["quantity"] for a in self.d["alloc"] if a["resource_id"] == r["resource_id"] and a["status"] == "Allocated")
                for r in self.d["res"]]

    def available(self):
        return [r["total_quantity"] - x for r, x in zip(self.d["res"], self.allocated())]

    def connect(self):
        return Conn(self)

    # ---- replacements for the small db.database helpers used by banker_service.create_task / reset
    def create_request(self, pc, description, fault, severity):
        if pc not in self.computers:
            raise ValidationError(f"Computer '{pc}' does not exist.")
        rid = self.d["next_req"]
        self.d["next_req"] += 1
        self.d["requests"][rid] = dict(computer_id=pc, description=description)
        return rid

    def approve_request(self, rid):
        tid, req = f"J-{self.d['next_task']}", self.d["requests"][rid]
        self.d["next_task"] += 1
        self.d["tasks"][tid] = dict(task_id=tid, computer_id=req["computer_id"], request_id=rid, status="Pending",
                                    problem_description=req["description"], severity="Medium", started_at=None, technician_id=None)

    def fetch_all(self, q, p=()):
        q = " ".join(q.split())
        if q.startswith("SELECT resource_id, resource_name, resource_type, total_quantity FROM resources"):
            return sorted((dict(r) for r in self.d["res"]), key=lambda r: (ORDER.index(r["resource_type"]), r["resource_id"]))
        if q.startswith("SELECT DISTINCT task_id FROM resource_allocations"):
            return [dict(task_id=t) for t in sorted({a["task_id"] for a in self.d["alloc"] if a["status"] == "Allocated"})]
        raise AssertionError("unexpected query: " + q)

    def fetch_one(self, q, p=()):
        q = " ".join(q.split())
        if q.startswith("SELECT task_id FROM maintenance_tasks WHERE request_id=%s"):
            return next((dict(task_id=t["task_id"]) for t in self.d["tasks"].values() if t["request_id"] == p[0]), None)
        if "r.problem_description=%s" in q:
            return {"x": 1} if any(t["computer_id"] == p[0] and t["problem_description"] == p[1] and t["status"] not in ("Completed", "Cancelled")
                                   for t in self.d["tasks"].values()) else None
        raise AssertionError("unexpected query: " + q)

    def execute_transaction(self, statements):
        snap = copy.deepcopy(self.d)
        try:
            for q, p in statements:
                self.writes += 1
                if self.fail_on_write and self.writes == self.fail_on_write:
                    raise RuntimeError("simulated database failure")
                assert " ".join(q.split()).startswith("INSERT INTO task_resources"), q
                self.d["tr"][(p[0], p[1])] = {"max": p[2], "cur": 0}
        except Exception:
            self.d = snap
            raise


class Conn:
    def __init__(self, db):
        self.db, self.snap, self.locked = db, None, False

    def cursor(self, dictionary=False):
        return Cur(self)

    def _lock(self):
        self.db.lock.acquire()
        self.locked = True
        if self.snap is None:
            self.snap = copy.deepcopy(self.db.d)

    def _unlock(self):
        if self.locked:
            self.locked = False
            self.db.lock.release()

    def commit(self):
        self.snap = None
        self._unlock()

    def rollback(self):
        if self.snap is not None:
            self.db.d = self.snap
            self.snap = None
        self._unlock()

    def close(self):
        self._unlock()


class Cur:
    def __init__(self, conn):
        self.c, self.db, self.rows = conn, conn.db, []

    def fetchall(self):
        return self.rows

    def _write(self):
        if self.c.snap is None:
            self.c.snap = copy.deepcopy(self.db.d)
        self.db.writes += 1
        if self.db.fail_on_write and self.db.writes == self.db.fail_on_write:
            raise RuntimeError("simulated database failure")

    def execute(self, q, p=()):
        q = " ".join(q.split())
        if q.startswith("SELECT resource_id FROM resources WHERE status='Active'") and q.endswith("FOR UPDATE"):
            self.c._lock()                                    # rs.lock_resources
            self.rows = []
            return
        d = self.db.d
        if q.startswith("SELECT resource_id, resource_name, resource_type"):
            if q.endswith("FOR UPDATE"):
                self.c._lock()
                d = self.db.d
            self.rows = sorted(copy.deepcopy(d["res"]), key=lambda r: (ORDER.index(r["resource_type"]), r["resource_id"]))
        elif q.startswith("SELECT resource_id, task_id, SUM(quantity)"):
            sums = {}
            for a in d["alloc"]:
                if a["status"] == "Allocated":
                    sums[(a["resource_id"], a["task_id"])] = sums.get((a["resource_id"], a["task_id"]), 0) + a["quantity"]
            self.rows = [dict(resource_id=k[0], task_id=k[1], q=v) for k, v in sums.items()]
        elif q.startswith("SELECT t.task_id, t.computer_id"):
            self.rows = [copy.deepcopy(t) for t in sorted(d["tasks"].values(), key=lambda t: t["task_id"]) if t["status"] in p]
        elif q.startswith("SELECT task_id, resource_id, maximum_required FROM task_resources"):
            self.rows = [dict(task_id=k[0], resource_id=k[1], maximum_required=v["max"]) for k, v in d["tr"].items()]
        elif "FROM allocation_requests ORDER BY request_id DESC LIMIT 1" in q:
            self.rows = [dict(x, decided_at=None) for x in reversed(d["decisions"])][:1]
        elif "a.decision='Rejected' AND a.reason_code IN" in q:
            latest = {}
            for x in d["decisions"]:
                latest[x["task_id"]] = x
            self.rows = [dict(task_id=t, request_vector=x["request_vector"]) for t, x in latest.items()
                         if x["decision"] == "Rejected" and x["reason_code"] in ("INSUFFICIENT", "UNSAFE")]
        elif q.startswith("SELECT a.allocation_id, a.resource_id, a.quantity, r.resource_name FROM resource_allocations"):
            names = {r["resource_id"]: r["resource_name"] for r in d["res"]}
            self.rows = [dict(a, resource_name=names[a["resource_id"]]) for a in d["alloc"]
                         if a["task_id"] == p[0] and a["status"] == "Allocated"]
        elif q.startswith("SELECT allocation_id, quantity FROM resource_allocations WHERE task_id=%s AND resource_id=%s"):
            self.rows = [dict(allocation_id=a["allocation_id"], quantity=a["quantity"]) for a in reversed(d["alloc"])
                         if a["task_id"] == p[0] and a["resource_id"] == p[1] and a["status"] == "Allocated"]
        elif q.startswith("SELECT status, computer_id FROM maintenance_tasks WHERE task_id=%s FOR UPDATE"):
            t = d["tasks"].get(p[0])
            self.rows = [dict(status=t["status"], computer_id=t["computer_id"])] if t else []
        elif q.startswith("SELECT status, started_at, technician_id FROM maintenance_tasks WHERE task_id=%s FOR UPDATE"):
            t = d["tasks"].get(p[0])
            self.rows = [dict(status=t["status"], started_at=t["started_at"], technician_id=t["technician_id"])] if t else []
        elif q.startswith("INSERT INTO allocation_requests"):
            self._write()
            d["decisions"].append(dict(request_id=len(d["decisions"]) + 1, task_id=p[0], request_vector=p[1], decision=p[2],
                                       reason_code=p[3], message=p[4]))
        elif q.startswith("INSERT INTO resource_allocations"):
            self._write()
            self.db._insert_alloc(p[0], p[1], p[2])
        elif q.startswith("INSERT INTO task_resources"):
            self._write()
            d["tr"][(p[0], p[1])] = {"max": p[2], "cur": d["tr"].get((p[0], p[1]), {"cur": p[3]})["cur"]}
        elif q.startswith("DELETE FROM task_resources WHERE task_id=%s AND resource_id=%s"):
            self._write()
            d["tr"].pop((p[0], p[1]), None)
        elif q.startswith("INSERT INTO maintenance_history"):
            self._write()
            d["history"].append(dict(task_id=p[0], remarks=p[4], resources_used=p[5]))
        elif q.startswith("UPDATE task_resources SET currently_allocated = currently_allocated +"):
            self._write()
            d["tr"][(p[1], p[2])]["cur"] += p[0]
        elif q.startswith("UPDATE task_resources SET currently_allocated = (SELECT"):
            self._write()
            d["tr"][(p[0], p[1])]["cur"] = sum(a["quantity"] for a in d["alloc"] if a["task_id"] == p[0]
                                                and a["resource_id"] == p[1] and a["status"] == "Allocated")
        elif q.startswith("UPDATE resource_allocations SET status='Released', released_at=NOW() WHERE allocation_id=%s"):
            self._write()
            self.db._release_alloc(next(a for a in d["alloc"] if a["allocation_id"] == p[0]))
        elif q.startswith("UPDATE maintenance_tasks SET status=%s WHERE task_id=%s"):
            self._write()
            d["tasks"][p[1]]["status"] = p[0]
        elif q.startswith("UPDATE maintenance_tasks SET status='Cancelled' WHERE task_id=%s"):
            self._write()
            d["tasks"][p[0]]["status"] = "Cancelled"
        elif q.startswith("UPDATE maintenance_tasks SET status='Completed'"):
            self._write()
            d["tasks"][p[0]]["status"] = "Completed"
        elif q.startswith("UPDATE maintenance_tasks SET status='Pending' WHERE status IN"):
            self._write()
            for t in d["tasks"].values():
                if t["status"] in ("Resources Allocated", "Waiting for Resource"):
                    t["status"] = "Pending"
        elif q.startswith("UPDATE computers") or q.startswith("UPDATE technicians"):
            self._write()
        else:
            raise AssertionError("unexpected query: " + q)
