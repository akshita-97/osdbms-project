
import unittest

from db.database import test_connection

DB_OK, DB_MSG = test_connection()

PAGES = [
    "/", "/labs", "/computers", "/maintenance", "/resources",
    "/history", "/fleet", "/fleet/api/overview", "/fleet/rules", "/execution-flow",
]


def create_app_client():
    from app import create_app
    return create_app().test_client()


@unittest.skipUnless(DB_OK, f"MySQL not reachable ({DB_MSG}) - run setup_db.py first")
class PageSmokeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.client = create_app().test_client()
        # Pages require login; fake a logged-in session (no DB write needed).
        with cls.client.session_transaction() as sess:
            sess["user_id"] = 0
            sess["username"] = "smoke-test"
            sess["display_name"] = "smoke-test"

    def test_every_page_loads(self):
        for path in PAGES:
            with self.subTest(page=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_pages_require_login(self):
        anon = create_app_client()
        for path in PAGES:
            with self.subTest(page=path):
                self.assertEqual(anon.get(path).status_code, 302)


if __name__ == "__main__":
    unittest.main()
