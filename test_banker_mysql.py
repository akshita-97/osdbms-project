
import os
import unittest

from db.database import fetch_all, fetch_one
from services import banker_service as bs
from services import resource_service as rs


@unittest.skipUnless(os.getenv("SMARTLAB_INTEGRATION"), "set SMARTLAB_INTEGRATION=1 to run against MySQL")
class RealDatabase(unittest.TestCase):
    def test_allocate_complete_release_cycle(self):
        bs.ensure_tables()
        bs.load_demo()
        bs.reset_allocations()
        st = bs.get_state()
        self.assertEqual([r["allocated"] for r in st["resources"]], [0] * len(st["resources"]))
        demo = {t["computer_id"]: t for t in st["tasks"] if t["problem_description"].startswith(bs.DEMO_PREFIX)}
        t = demo["PC-06"]
        ids = {r["resource_type"]: r["resource_id"] for r in fetch_all("SELECT resource_id, resource_type FROM resources")}
        out = bs.request_resources(t["task_id"], {ids["Technician"]: 1, ids["OS Installation Kit"]: 1})
        self.assertTrue(out["approved"], out["message"])
        counters = {r["resource_id"]: r["available_quantity"] for r in fetch_all("SELECT * FROM resources")}
        self.assertEqual(counters[ids["OS Installation Kit"]], 0)               # trigger lowered the stock counter
        rs.release_resources_for_task(t["task_id"])
        with self.assertRaises(Exception):
            rs.release_resources_for_task(t["task_id"])                          # second release must be refused
        row = fetch_one("SELECT available_quantity, total_quantity FROM resources WHERE resource_id=%s", (ids["OS Installation Kit"],))
        self.assertEqual(row["available_quantity"], row["total_quantity"])
        self.assertEqual(bs.get_state()["drift"], [])                            # counters equal the allocation records


if __name__ == "__main__":
    unittest.main()
