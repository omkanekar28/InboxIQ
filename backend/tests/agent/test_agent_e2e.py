"""
End-to-end integration test suite evaluating the InboxIQ LLM Agent against
an isolated static test database containing 30 realistic emails.

Covers real-life user queries across:
1. Relative Date + Sender filtering
2. Full conversation thread inspection & body synthesis
3. Unread + Keyword filtering
4. Negative case (absence of data / hallucination prevention)
5. Counting / aggregation over a date window
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure backend/src and backend/tests are in sys.path
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(FIXTURES_DIR) not in sys.path:
    sys.path.append(str(FIXTURES_DIR))

from settings import settings
from storage.database import Database
from agent.tools import init_tools
from agent.llm import LLM
from agent.system_prompt import get_system_prompt
from mock_data import seed_test_database


class TestAgentE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Setup isolated test database with 30 mock emails
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = Database(
            store_dir=cls.temp_dir.name,
            sqlite_filename="test_agent_e2e.db",
            search_email_fields=(
                "id", "thread_id", "sender", "recipient", "subject", "snippet", "labels", "date"
            ),
            email_thread_fields=(
                "id", "thread_id", "sender", "recipient", "subject", "labels", "date", "body"
            ),
        )
        seed_test_database(cls.db)

        # 2. Bind agent tools to this test DB and a mock sync client
        cls.mock_gmail_sync = MagicMock()
        init_tools(db=cls.db, gmail_sync=cls.mock_gmail_sync)

        # 3. Start local LLM server (defaults to settings.MODEL_TYPE, overridable via INBOXIQ_MODEL)
        model_type = os.environ.get("INBOXIQ_MODEL", settings.MODEL_TYPE)
        print(f"\n[TestAgentE2E] Running tests against model: {model_type}")
        cls.llm = LLM(model_type=model_type)
        cls.llm.setup()
        cls.llm.start()

    @classmethod
    def tearDownClass(cls):
        # Stop LLM server and clean up temporary database
        cls.llm.stop()
        cls.db.conn.close()
        cls.temp_dir.cleanup()

    def _ask_agent(self, user_query: str) -> str:
        """Helper to send user query with dynamic system prompt to agent."""
        messages = [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": user_query},
        ]
        return self.llm.chat_with_tools(messages)

    def test_01_sender_and_relative_date_filter(self):
        """Query 1: 'Find all emails from Indeed in the past 2 months.'"""
        query = "Find all emails from Indeed in the past 2 months."
        response = self._ask_agent(query).lower()
        print(f"\n[Test 1 Response]\n{response}\n")

        # Ground truth: 2 Indeed emails in range (em_06 from Sept 19, em_07 from Aug 10)
        # em_08 is from April 1 (outside 2 months)
        self.assertTrue(
            "senior ai engineer" in response or "innovatetech" in response or "15 new python" in response,
            "Response should mention at least one of the recent Indeed emails"
        )
        self.assertNotIn(
            "spring surge",
            response,
            "Response should not include the older April email outside the 2-month window"
        )

    def test_02_deep_thread_content_inspection(self):
        """Query 2: 'What was the final decision in Alice's project update thread?'"""
        query = "What was the final decision in Alice's project update thread?"
        response = self._ask_agent(query).lower()
        print(f"\n[Test 2 Response]\n{response}\n")

        # Ground truth: em_03 body states "Final decision: we will proceed with SQLite"
        self.assertIn(
            "sqlite",
            response,
            "Agent should read thread body and identify SQLite as the chosen database"
        )

    def test_03_unread_recruiter_interview_invitations(self):
        """Query 3: 'Show me any unread interview invitations or recruiter messages from this week.'"""
        query = "Show me any unread interview invitations or recruiter messages from this week."
        response = self._ask_agent(query).lower()
        print(f"\n[Test 3 Response]\n{response}\n")

        # Ground truth: em_09 (Sarah Jenkins / Robert Walters) and/or em_10 (Greenhouse / Anthropic partner)
        matches_recruiter = any(
            name in response
            for name in ["sarah", "robert walters", "greenhouse", "fintech global", "anthropic"]
        )
        self.assertTrue(
            matches_recruiter,
            "Agent should identify the unread recruiter or interview invitation"
        )

    def test_04_negative_case_zero_hallucination(self):
        """Query 4: 'Did I get any receipts or ride summaries from Uber this month?'"""
        query = "Did I get any receipts or ride summaries from Uber this month?"
        response = self._ask_agent(query).lower()
        print(f"\n[Test 4 Response]\n{response}\n")

        # Ground truth: The only Uber email was in June 2026. September has NO Uber emails.
        # Agent must report none found and must NOT fabricate rides/receipts for September.
        negative_indicators = [
            "no", "not find", "none", "didn't find", "did not find", "couldn't find", "could not find", "no receipts"
        ]
        self.assertTrue(
            any(ind in response for ind in negative_indicators),
            "Agent must clearly state that no Uber receipts/emails were found for this month"
        )

    def test_05_count_github_notifications_past_week(self):
        """Query 5: 'How many GitHub notifications have I received in the past 7 days?'"""
        query = "How many GitHub notifications have I received in the past 7 days?"
        response = self._ask_agent(query).lower()
        print(f"\n[Test 5 Response]\n{response}\n")

        # Ground truth: exactly 3 GitHub emails (em_13 on Sept 15, em_14 on Sept 17, em_15 on Sept 19)
        # Check that it identifies the GitHub emails or states 3
        has_count_or_items = "3" in response or "three" in response or ("#42" in response or "#50" in response or "dependabot" in response)
        self.assertTrue(
            has_count_or_items,
            "Agent should identify the GitHub notifications from the past week"
        )


if __name__ == "__main__":
    unittest.main()
