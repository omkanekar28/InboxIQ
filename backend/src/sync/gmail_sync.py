import os
import time
import base64
from typing import Literal
from datetime import datetime, timezone
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from storage import db
from settings import settings
from utils import get_logger

logger = get_logger(
    name=Path(__file__).stem,
    log_file="sync.log",
)


class GmailSync:
    """Sync emails from Gmail to local database"""
    def __init__(self):
        self.service = self._get_gmail_service()

    def _get_gmail_service(self):
        """Authenticates the user and returns the Gmail service object."""
        logger.info("Authenticating user...")
        creds = None
        if os.path.exists(settings.GMAIL_SYNC_TOKEN_FILEPATH):
            logger.info("Token file found. Loading credentials...")
            creds = Credentials.from_authorized_user_file(
                settings.GMAIL_SYNC_TOKEN_FILEPATH, 
                settings.GMAIL_SYNC_SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Token expired. Refreshing token...")
                creds.refresh(Request())
            else:
                logger.info("No valid credentials found. Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.GMAIL_SYNC_CREDENTIALS_FILEPATH, settings.GMAIL_SYNC_SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for subsequent runs
            logger.info("Saving credentials...")
            with open(settings.GMAIL_SYNC_TOKEN_FILEPATH, "w") as token:
                token.write(creds.to_json())

        logger.info("Authentication successful. Building Gmail service...")
        return build("gmail", "v1", credentials=creds)

    def _get_header(self, headers: list[dict], name: str) -> str:
        return next(
            (h["value"] for h in headers if h["name"].lower() == name.lower()),
            "",
        )

    def _extract_body(self, part: dict) -> str:
        text_body = ""
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")

        if data:
            decoded = base64.urlsafe_b64decode(data).decode(
                "utf-8", errors="replace"
            )
            if mime_type == "text/plain":
                text_body = decoded

        # If it's a multipart message, recurse through children parts
        for sub_part in part.get("parts", []):
            sub_text = self._extract_body(sub_part)
            if sub_text:
                text_body += "\n" + sub_text

        return text_body.strip()

    def _get_email_details(
        self, 
        msg_id: str, 
        format: Literal["full", "metadata"] = "metadata",
        metadata_headers: list[str] | None = ["Subject", "From", "To", "Date"],
    ) -> dict:
        """Fetch and parse full message details for a given message ID."""
        if format == "metadata":
            message = (
                self.service.users()
                .messages()
                .get(
                    userId="me", 
                    id=msg_id, 
                    format=format,
                    metadataHeaders=metadata_headers,
                )
                .execute()
            )
        else:
            message = (
                self.service.users()
                .messages()
                .get(
                    userId="me", 
                    id=msg_id, 
                    format=format,
                )
                .execute()
            )

        payload = message.get("payload", {})
        headers = payload.get("headers", [])


        # 1. Parse Headers & Metadata
        subject = self._get_header(headers, "Subject")
        sender = self._get_header(headers, "From")
        recipient = self._get_header(headers, "To")
        date_str = self._get_header(headers, "Date")
        internal_date = message.get("internalDate")  # epoch timestamp in ms

        # 2. Extract Body (handles both single-part and multipart emails)
        text_body = ""
        if format == "full":
            text_body = self._extract_body(payload)

        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "snippet": message.get("snippet", ""),
            "subject": subject,
            "from": sender,
            "to": recipient,
            "date": date_str,
            "internal_date_ms": int(internal_date) if internal_date else None,
            "text_body": text_body,
            "is_full": 1 if format == "full" else 0,
        }

    def _fetch_all_emails(self) -> list[dict]:
        """Fetch recent emails from Gmail up to GMAIL_SYNC_MAX_RECENT_EMAILS."""
        fetch_emails_start_time = time.time()
        messages = []
        page_token = None
        page = 0

        logger.info(
            f"Fetching up to {settings.GMAIL_SYNC_MAX_RECENT_EMAILS} recent message IDs "
            f"format={settings.GMAIL_SYNC_EMAIL_FORMAT}"
        )
        
        # Paginate through messages up to GMAIL_SYNC_MAX_RECENT_EMAILS
        while len(messages) < settings.GMAIL_SYNC_MAX_RECENT_EMAILS:
            page += 1
            remaining = settings.GMAIL_SYNC_MAX_RECENT_EMAILS - len(messages)
            batch_size = min(500, remaining)

            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    pageToken=page_token,
                    maxResults=batch_size,
                )
                .execute()
            )
            batch = results.get("messages", [])
            if not batch:
                break

            messages.extend(batch)

            logger.info(
                f"Fetched page {page}: "
                f"{len(batch)} messages "
                f"(total: {len(messages)}/{settings.GMAIL_SYNC_MAX_RECENT_EMAILS})"
            )
            page_token = results.get("nextPageToken")

            if not page_token:
                break

        messages = messages[: settings.GMAIL_SYNC_MAX_RECENT_EMAILS]

        logger.info(
            f"Fetched {len(messages)} message IDs. "
            "Fetching message details..."
        )

        email_details = []

        for message in messages:
            email_detail = self._get_email_details(
                msg_id=message["id"], 
                format=settings.GMAIL_SYNC_EMAIL_FORMAT,
                metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS,
            )
            email_details.append(email_detail)
        
        logger.info(
            f"Fetched {len(email_details)} emails in {time.time() - fetch_emails_start_time:.2f} seconds."
        )
        return email_details

    def _get_current_history_id(self) -> str | None:
        """Fetch the current historyId of the mailbox from Gmail profile."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("historyId")
        except Exception as e:
            logger.warning(f"Could not fetch mailbox historyId from profile: {e}")
            return None

    def _fallback_date_sync(self) -> None:
        """
        Fallback sync when historyId is expired (>7 days old).
        Queries Gmail for messages after the latest known message date in SQLite.
        """
        logger.info("Running date-based fallback sync...")
        latest_ms = db.get_latest_email_date_ms()
        query = None
        if latest_ms:
            # Buffer by 1 hour (3600 seconds) to avoid missing boundary emails
            after_epoch_sec = max(0, (latest_ms // 1000) - 3600)
            query = f"after:{after_epoch_sec}"
            logger.info(f"Syncing messages with query '{query}'...")
        else:
            logger.info("No prior messages in database. Falling back to recent backfill...")

        page_token = None
        new_message_ids: list[str] = []
        while True:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", pageToken=page_token, q=query, maxResults=500)
                .execute()
            )
            batch = results.get("messages", [])
            if not batch:
                break
            new_message_ids.extend([m["id"] for m in batch if "id" in m])
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Found {len(new_message_ids)} messages in date-range fallback.")
        if new_message_ids:
            new_emails = [self._get_email_details(
                msg_id=mid, 
                format=settings.GMAIL_SYNC_EMAIL_FORMAT,
                metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS,
            ) for mid in new_message_ids]
            db.ingest_emails(new_emails)

        # Update checkpoint to current mailbox state
        fresh_history_id = self._get_current_history_id()
        if fresh_history_id:
            db.set_sync_state("gmail_last_history_id", str(fresh_history_id))
        db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())

    def _incremental_sync(self, start_history_id: str) -> None:
        """
        Perform incremental sync using Gmail's users.history.list.
        Captures new messages, deletions, and label changes since start_history_id.
        """
        logger.info(f"Starting incremental sync from historyId {start_history_id}...")
        page_token = None
        new_history_id = start_history_id

        messages_added_ids: set[str] = set()
        messages_deleted_ids: set[str] = set()
        labels_updated: dict[str, list[str]] = {}  # msg_id -> list of current labels

        try:
            while True:
                results = (
                    self.service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=start_history_id,
                        pageToken=page_token,
                        historyTypes=["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
                    )
                    .execute()
                )

                new_history_id = results.get("historyId", new_history_id)
                history_records = results.get("history", [])

                for record in history_records:
                    # 1. New messages
                    for added in record.get("messagesAdded", []):
                        msg = added.get("message", {})
                        if "id" in msg:
                            messages_added_ids.add(msg["id"])

                    # 2. Deleted messages
                    for deleted in record.get("messagesDeleted", []):
                        msg = deleted.get("message", {})
                        if "id" in msg:
                            messages_deleted_ids.add(msg["id"])

                    # 3. Label updates
                    for label_event in record.get("labelsAdded", []) + record.get("labelsRemoved", []):
                        msg = label_event.get("message", {})
                        msg_id = msg.get("id")
                        if msg_id and "labelIds" in msg:
                            labels_updated[msg_id] = msg["labelIds"]

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as error:
            # 404 indicates historyId is invalid / expired (> 7 days)
            if error.resp.status == 404:
                logger.warning(
                    f"historyId '{start_history_id}' has expired on Gmail servers (404). "
                    "Falling back to date-range sync."
                )
                self._fallback_date_sync()
                return
            else:
                raise

        # Remove deleted IDs from newly added set
        messages_added_ids -= messages_deleted_ids

        # Ingest newly added emails
        if messages_added_ids:
            logger.info(f"Fetching details for {len(messages_added_ids)} new emails...")
            new_emails = [self._get_email_details(
                msg_id=mid, 
                format=settings.GMAIL_SYNC_EMAIL_FORMAT,
                metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS,
            ) for mid in messages_added_ids]
            db.ingest_emails(new_emails)

        # Delete removed emails
        if messages_deleted_ids:
            logger.info(f"Removing {len(messages_deleted_ids)} deleted emails from local database...")
            db.delete_emails(list(messages_deleted_ids))

        # Update labels on modified emails (excluding newly added ones which already have fresh labels)
        for msg_id, labels in labels_updated.items():
            if msg_id not in messages_added_ids and msg_id not in messages_deleted_ids:
                db.update_email_labels(msg_id, labels)

        # Update sync_state checkpoints
        if new_history_id:
            db.set_sync_state("gmail_last_history_id", str(new_history_id))
        db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())

        logger.info(
            f"Incremental sync finished: {len(messages_added_ids)} added, "
            f"{len(messages_deleted_ids)} deleted, {len(labels_updated)} labels updated. "
            f"New historyId: {new_history_id}"
        )

    def sync_emails(self) -> None:
        """Sync emails from Gmail to local database and update sync_state."""
        last_history_id = db.get_sync_state("gmail_last_history_id")

        if last_history_id is None:
            logger.info(
                f"First boot detected. Fetching first "
                f"{settings.GMAIL_SYNC_MAX_RECENT_EMAILS} emails..."
            )
            # 1. Grab current mailbox historyId before/during backfill
            current_history_id = self._get_current_history_id()

            # 2. Fetch and ingest emails
            email_details = self._fetch_all_emails()
            logger.info("Saving emails to database...")
            db.ingest_emails(email_details)

            # 3. Store baseline historyId and timestamp in sync_state
            if current_history_id:
                db.set_sync_state("gmail_last_history_id", str(current_history_id))
                logger.info(f"Stored initial historyId '{current_history_id}' in sync_state.")
            else:
                logger.warning("No historyId retrieved; subsequent sync may trigger full backfill.")
            db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())
        else:
            logger.info(f"Existing historyId found ({last_history_id}). Running incremental sync...")
            self._incremental_sync(last_history_id)

        logger.info("Sync complete!")


# FOR DEBUGGING
# if __name__ == "__main__":
#     gmail_sync = GmailSync()

#     ## Full flow (WILL OVERWRITE EXISTING DATABASE!!!)
#     gmail_sync.sync_emails()

#     ## Partial flow (Skips DB ingestion part)
#     # emails = gmail_sync._fetch_all_emails()
#     # print(json.dumps(emails, indent=4))