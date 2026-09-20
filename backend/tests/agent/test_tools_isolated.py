"""
Isolated unit tests for agent tools (search_emails, get_email_thread)
running against a temporary test database populated with the 30 mock emails.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Add backend/src at the front of sys.path, and fixtures at the end
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(FIXTURES_DIR) not in sys.path:
    sys.path.append(str(FIXTURES_DIR))

from storage.database import Database
from agent.tools import init_tools, search_emails, get_email_thread
from mock_data import MOCK_EMAILS, seed_test_database


class TestToolsIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = Database(
            store_dir=cls.temp_dir.name,
            sqlite_filename="test_isolated.db",
            search_email_fields=(
                "id", "thread_id", "sender", "recipient", "subject", "snippet", "labels", "date"
            ),
            email_thread_fields=(
                "id", "thread_id", "sender", "recipient", "subject", "labels", "date", "body"
            ),
        )
        seed_test_database(cls.db)
        # Bind tools to this isolated test DB with mock gmail_sync
        from unittest.mock import MagicMock
        init_tools(db=cls.db, gmail_sync=MagicMock())

    @classmethod
    def tearDownClass(cls):
        cls.db.conn.close()
        cls.temp_dir.cleanup()

    def test_database_populated_with_30_emails(self):
        cls = self.__class__
        cls.db.cursor.execute("SELECT COUNT(*) FROM emails")
        count = cls.db.cursor.fetchone()[0]
        self.assertEqual(count, 30)

    def test_search_by_sender_indeed_all(self):
        results = search_emails(sender="Indeed")
        self.assertEqual(len(results), 3)
        ids = {r["id"] for r in results}
        self.assertEqual(ids, {"em_06", "em_07", "em_08"})

    def test_search_by_sender_indeed_past_2_months(self):
        # Anchor: today is 2026-09-20. Past 2 months: 2026-07-20 to 2026-09-20.
        results = search_emails(sender="Indeed", date_from="2026-07-20", date_to="2026-09-20")
        self.assertEqual(len(results), 2)
        ids = {r["id"] for r in results}
        self.assertEqual(ids, {"em_06", "em_07"})
        self.assertNotIn("em_08", ids)

    def test_search_by_keyword_sqlite(self):
        results = search_emails(keyword="SQLite")
        # Should match em_02, em_03, em_27
        ids = {r["id"] for r in results}
        self.assertIn("em_02", ids)
        self.assertIn("em_03", ids)
        self.assertIn("em_27", ids)

    def test_search_unread_interview_recruiter(self):
        results = search_emails(keyword="Interview", label="UNREAD")
        ids = {r["id"] for r in results}
        self.assertIn("em_09", ids)
        self.assertIn("em_10", ids)

    def test_get_email_thread_with_cached_bodies(self):
        thread = get_email_thread("th_proj_alice")
        self.assertEqual(thread["thread_id"], "th_proj_alice")
        emails = thread["emails"]
        self.assertEqual(len(emails), 3)
        # Check order is oldest-first
        self.assertEqual(emails[0]["id"], "em_01")
        self.assertEqual(emails[1]["id"], "em_02")
        self.assertEqual(emails[2]["id"], "em_03")
        # Check cached body on final decision email
        self.assertIn("Final decision: we will proceed with SQLite", emails[2]["body"])

    def test_negative_search_uber_this_month(self):
        # In Sept 2026, there are no Uber emails (the only one is in June)
        results = search_emails(keyword="Uber", date_from="2026-09-01", date_to="2026-09-20")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
