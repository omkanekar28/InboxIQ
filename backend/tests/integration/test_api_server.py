"""
Unit and integration tests for the InboxIQ FastAPI server.
"""

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi.testclient import TestClient
from api.server import app
import api.endpoints as endpoints_module


class TestAPIServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_01_health_check(self):
        """Test GET /api/health returns 200 and expected schema."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("llm_ready", data)
        self.assertIn("active_model", data)

    def test_02_setup_status(self):
        """Test GET /api/setup/status returns 200 and boolean fields."""
        resp = self.client.get("/api/setup/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("credentials_ok", data)
        self.assertIn("authenticated", data)
        self.assertIn("models_downloaded", data)
        self.assertIn("initial_sync_done", data)
        self.assertIsInstance(data["credentials_ok"], bool)
        self.assertIsInstance(data["authenticated"], bool)
        self.assertIsInstance(data["models_downloaded"], bool)
        self.assertIsInstance(data["initial_sync_done"], bool)

    def test_03_hardware_profile(self):
        """Test GET /api/system/hardware returns hardware details."""
        resp = self.client.get("/api/system/hardware")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("gpu_available", data)
        self.assertIn("active_model", data)
        self.assertIn(data["active_model"], ["lightweight", "balanced"])

    def test_04_model_switch_validation(self):
        """Test POST /api/system/model validates input."""
        # Invalid model name
        resp = self.client.post("/api/system/model", json={"model": "invalid_model"})
        self.assertEqual(resp.status_code, 422)

    def test_05_sync_status(self):
        """Test GET /api/sync/status reports sync state."""
        resp = self.client.get("/api/sync/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("state", data)
        self.assertIn("total_emails", data)
        self.assertIn("job_running", data)
        self.assertIsInstance(data["total_emails"], int)

    def test_06_setup_credentials_validation(self):
        """Test POST /api/setup/credentials validation."""
        # Empty body
        resp = self.client.post("/api/setup/credentials")
        self.assertEqual(resp.status_code, 400)

        # Invalid JSON
        resp = self.client.post(
            "/api/setup/credentials",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

        # JSON missing installed/web key
        resp = self.client.post(
            "/api/setup/credentials",
            content=json.dumps({"some_key": "val"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_07_chat_endpoint_mocked(self):
        """Test POST /api/chat with mock LLM for non-streaming and streaming."""
        mock_llm = MagicMock()
        mock_llm.is_ready = True
        mock_llm.chat_with_tools_details.return_value = {
            "reply": "You have 3 unread emails.",
            "tools_called": [{"name": "search_emails", "arguments": {"keyword": "test"}}],
            "latency_seconds": 1.25,
        }

        def mock_stream(messages):
            yield {"event": "tool_call", "data": {"name": "search_emails", "arguments": {}}}
            yield {"event": "tool_result", "data": {"name": "search_emails", "count": 3}}
            yield {"event": "token", "data": {"text": "You have "}}
            yield {"event": "token", "data": {"text": "3 unread emails."}}
            yield {
                "event": "done",
                "data": {
                    "reply": "You have 3 unread emails.",
                    "tools_called": [{"name": "search_emails", "arguments": {}}],
                    "latency_seconds": 1.25,
                },
            }

        mock_llm.chat_with_tools_stream.side_effect = mock_stream

        with patch.object(endpoints_module, "llm", mock_llm):
            # Test non-streaming
            resp = self.client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "How many emails?"}],
                    "stream": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["reply"], "You have 3 unread emails.")
            self.assertEqual(len(data["tools_called"]), 1)
            self.assertEqual(data["tools_called"][0]["name"], "search_emails")
            self.assertEqual(data["latency_seconds"], 1.25)

            # Test streaming (SSE)
            resp_stream = self.client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "How many emails?"}],
                    "stream": True,
                },
            )
            self.assertEqual(resp_stream.status_code, 200)
            self.assertIn("text/event-stream", resp_stream.headers.get("content-type", ""))
            body = resp_stream.text
            self.assertIn("event: tool_call", body)
            self.assertIn("event: tool_result", body)
            self.assertIn("event: token", body)
            self.assertIn("event: done", body)

    def test_08_frontend_static_serving(self):
        """Verify that the frontend index.html and static assets are served at /."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("InboxIQ", resp.text)
        self.assertIn("app", resp.text)

        # Verify static CSS asset
        resp_css = self.client.get("/styles/main.css")
        self.assertEqual(resp_css.status_code, 200)
        self.assertIn("accent-green", resp_css.text)


if __name__ == "__main__":
    unittest.main()
