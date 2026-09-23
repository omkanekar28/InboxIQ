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

    def test_09_startup_status(self):
        """Verify GET /api/system/startup returns boot steps and progress info."""
        resp = self.client.get("/api/system/startup")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("completed", data)
        self.assertIn("steps", data)
        self.assertIsInstance(data["steps"], list)
        self.assertEqual(len(data["steps"]), 4)
        step_ids = [s["id"] for s in data["steps"]]
        self.assertIn("database", step_ids)
        self.assertIn("models", step_ids)
        self.assertIn("runtime", step_ids)
        self.assertIn("server", step_ids)

    def test_10_startup_progress_tracking(self):
        """Verify update_startup_step stores progress dict and GET returns it."""
        progress_data = {
            "percent": 45.5,
            "downloaded_bytes": 1024 * 1024 * 500,
            "total_bytes": 1024 * 1024 * 1024,
            "downloaded_str": "500.0 MB",
            "total_str": "1.00 GB",
            "speed_str": "25.0 MB/s",
            "detail": "Model 1/2: test.gguf",
        }
        endpoints_module.update_startup_step(
            "models",
            "in_progress",
            message="Downloading test model...",
            progress=progress_data,
        )

        resp = self.client.get("/api/system/startup")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        models_step = next(s for s in data["steps"] if s["id"] == "models")
        self.assertEqual(models_step["status"], "in_progress")
        self.assertEqual(models_step["message"], "Downloading test model...")
        self.assertIsNotNone(models_step["progress"])
        self.assertEqual(models_step["progress"]["percent"], 45.5)
        self.assertEqual(models_step["progress"]["speed_str"], "25.0 MB/s")
        self.assertEqual(models_step["progress"]["total_str"], "1.00 GB")

        # Test completion sets 100%
        endpoints_module.update_startup_step(
            "models",
            "completed",
            message="Models ready.",
        )
        resp2 = self.client.get("/api/system/startup")
        models_step2 = next(s for s in resp2.json()["steps"] if s["id"] == "models")
        self.assertEqual(models_step2["status"], "completed")
        self.assertEqual(models_step2["progress"]["percent"], 100)

    def test_11_download_file_with_progress_callback(self):
        """Verify download_file triggers progress_callback with byte counts and speed."""
        from utils.file_utils import download_file

        mock_chunks = [b"A" * 65536, b"B" * 65536, b"C" * 32768]
        total_len = sum(len(c) for c in mock_chunks)

        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(total_len)}
        mock_resp.iter_content.return_value = iter(mock_chunks)
        mock_resp.raise_for_status.return_value = None

        progress_calls = []

        def callback(downloaded, total, speed=0.0):
            progress_calls.append((downloaded, total, speed))

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("requests.get", return_value=mock_resp):
                out_path = download_file(
                    url="http://example.com/test_model.gguf",
                    output_dir=tmp_dir,
                    show_progress=False,
                    progress_callback=callback,
                )

                self.assertTrue(out_path.exists())
                self.assertEqual(out_path.stat().st_size, total_len)
                self.assertGreater(len(progress_calls), 0)
                final_call = progress_calls[-1]
                self.assertEqual(final_call[0], total_len)  # downloaded == total
                self.assertEqual(final_call[1], total_len)


if __name__ == "__main__":
    unittest.main()
