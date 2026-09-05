import base64
from unittest.mock import MagicMock, patch
import pytest
from googleapiclient.errors import HttpError
import httplib2

from sync.gmail_sync import GmailSync


@pytest.fixture
def mock_gmail_service():
    """Mock Google API discovery service."""
    return MagicMock()


@pytest.fixture
def gmail_sync(mock_gmail_service):
    """GmailSync instance with mocked authentication/service."""
    with patch.object(GmailSync, "_get_gmail_service", return_value=mock_gmail_service):
        sync_instance = GmailSync()
        sync_instance.service = mock_gmail_service
        return sync_instance


class TestHeaderAndBodyExtraction:
    def test_get_header_case_insensitive(self, gmail_sync):
        headers = [
            {"name": "Subject", "value": "Welcome to InboxIQ"},
            {"name": "FROM", "value": "alice@example.com"},
            {"name": "to", "value": "bob@example.com"},
        ]

        assert gmail_sync._get_header(headers, "subject") == "Welcome to InboxIQ"
        assert gmail_sync._get_header(headers, "From") == "alice@example.com"
        assert gmail_sync._get_header(headers, "TO") == "bob@example.com"
        assert gmail_sync._get_header(headers, "Cc") == ""

    def test_extract_body_plain_text(self, gmail_sync):
        raw_text = "Hello, this is a plain text email."
        encoded_data = base64.urlsafe_b64encode(raw_text.encode("utf-8")).decode("utf-8")

        part = {
            "mimeType": "text/plain",
            "body": {"data": encoded_data},
        }

        assert gmail_sync._extract_body(part) == raw_text

    def test_extract_body_multipart_ignores_html(self, gmail_sync):
        plain_text = "Plain text version."
        html_text = "<p>HTML version</p>"

        plain_encoded = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("utf-8")
        html_encoded = base64.urlsafe_b64encode(html_text.encode("utf-8")).decode("utf-8")

        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain_encoded}},
                {"mimeType": "text/html", "body": {"data": html_encoded}},
            ],
        }

        extracted = gmail_sync._extract_body(payload)
        assert extracted == plain_text
        assert "HTML" not in extracted


class TestEmailDetails:
    def test_get_email_details_parsing(self, gmail_sync, mock_gmail_service):
        body_text = "Detailed email body content."
        body_encoded = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("utf-8")

        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg123",
            "threadId": "thread456",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "Detailed snippet",
            "internalDate": "1788597377000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "receiver@example.com"},
                    {"name": "Date", "value": "Sat, 05 Sep 2026 08:36:17 +0000"},
                ],
                "body": {"data": body_encoded},
            },
        }

        details = gmail_sync._get_email_details("msg123")

        assert details["id"] == "msg123"
        assert details["thread_id"] == "thread456"
        assert details["subject"] == "Test Subject"
        assert details["from"] == "sender@example.com"
        assert details["to"] == "receiver@example.com"
        assert details["internal_date_ms"] == 1788597377000
        assert details["text_body"] == body_text

    def test_get_email_details_fallback_to_snippet(self, gmail_sync, mock_gmail_service):
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg_empty",
            "threadId": "thread_empty",
            "labelIds": ["INBOX"],
            "snippet": "Fallback preview snippet",
            "internalDate": "1788597377000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"data": ""},
            },
        }

        details = gmail_sync._get_email_details("msg_empty")
        assert details["text_body"] == "Fallback preview snippet"


class TestEmailFetchAndPagination:
    def test_fetch_all_emails_pagination(self, gmail_sync, mock_gmail_service):
        page1 = {
            "messages": [{"id": "m1"}, {"id": "m2"}],
            "nextPageToken": "token_page_2",
        }
        page2 = {
            "messages": [{"id": "m3"}],
            "nextPageToken": None,
        }

        mock_gmail_service.users().messages().list().execute.side_effect = [page1, page2]

        with patch.object(
            gmail_sync,
            "_get_email_details",
            side_effect=lambda mid: {"id": mid, "subject": f"Sub {mid}"},
        ):
            with patch("settings.settings.GMAIL_SYNC_MAX_RECENT_EMAILS", 10):
                emails = gmail_sync._fetch_all_emails()

        assert len(emails) == 3
        assert [e["id"] for e in emails] == ["m1", "m2", "m3"]

    def test_fetch_all_emails_respects_max_limit(self, gmail_sync, mock_gmail_service):
        page = {
            "messages": [{"id": f"m{i}"} for i in range(10)],
            "nextPageToken": "more",
        }
        mock_gmail_service.users().messages().list().execute.return_value = page

        with patch.object(
            gmail_sync,
            "_get_email_details",
            side_effect=lambda mid: {"id": mid},
        ):
            with patch("settings.settings.GMAIL_SYNC_MAX_RECENT_EMAILS", 3):
                emails = gmail_sync._fetch_all_emails()

        assert len(emails) == 3
        assert [e["id"] for e in emails] == ["m0", "m1", "m2"]


class TestSyncFlows:
    @patch("sync.gmail_sync.db")
    def test_sync_emails_first_boot(self, mock_db, gmail_sync):
        # When no historyId exists in sync_state, it must execute first_boot backfill
        mock_db.get_sync_state.return_value = None

        with patch.object(gmail_sync, "_get_current_history_id", return_value="100500"):
            with patch.object(
                gmail_sync,
                "_fetch_all_emails",
                return_value=[{"id": "m1"}, {"id": "m2"}],
            ):
                gmail_sync.sync_emails()

        mock_db.ingest_emails.assert_called_once_with([{"id": "m1"}, {"id": "m2"}])
        mock_db.set_sync_state.assert_any_call("gmail_last_history_id", "100500")

    @patch("sync.gmail_sync.db")
    def test_incremental_sync_processes_changes(self, mock_db, gmail_sync, mock_gmail_service):
        history_response = {
            "historyId": "200000",
            "history": [
                {
                    "messagesAdded": [{"message": {"id": "new_1"}}],
                    "messagesDeleted": [{"message": {"id": "del_1"}}],
                    "labelsAdded": [{"message": {"id": "mod_1", "labelIds": ["STARRED"]}}],
                }
            ],
            "nextPageToken": None,
        }

        mock_gmail_service.users().history().list().execute.return_value = history_response

        with patch.object(
            gmail_sync,
            "_get_email_details",
            return_value={"id": "new_1", "subject": "New Email"},
        ):
            gmail_sync._incremental_sync(start_history_id="100000")

        mock_db.ingest_emails.assert_called_once_with([{"id": "new_1", "subject": "New Email"}])
        mock_db.delete_emails.assert_called_once_with(["del_1"])
        mock_db.update_email_labels.assert_called_once_with("mod_1", ["STARRED"])
        mock_db.set_sync_state.assert_any_call("gmail_last_history_id", "200000")

    @patch("sync.gmail_sync.db")
    def test_incremental_sync_404_triggers_fallback(self, mock_db, gmail_sync, mock_gmail_service):
        # Simulate Gmail 404 response on expired historyId
        resp = httplib2.Response({"status": 404})
        error = HttpError(resp, b"History id expired")
        mock_gmail_service.users().history().list().execute.side_effect = error

        with patch.object(gmail_sync, "_fallback_date_sync") as mock_fallback:
            gmail_sync._incremental_sync(start_history_id="old_expired_id")
            mock_fallback.assert_called_once()
