"""
All sync related operations will be here.
"""


import os
import time
import base64
from typing import Literal, Optional, Callable
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from storage import Database
from settings import settings
from utils import get_logger

logger = get_logger(name=__name__)


class GmailSync:
    """Sync emails from Gmail to local database"""
    def __init__(
        self,
        db: Database,
        token_filepath: str | None = None,
        credentials_filepath: str | None = None,
        scopes: list[str] | None = None,
        auto_auth: bool = True,
    ):
        self.db = db
        self.token_filepath = token_filepath or settings.GMAIL_SYNC_TOKEN_FILEPATH
        self.credentials_filepath = credentials_filepath or settings.GMAIL_SYNC_CREDENTIALS_FILEPATH
        self.scopes = scopes or settings.GMAIL_SYNC_SCOPES
        self.service = None
        if auto_auth:
            self._try_init_service()

    def _try_init_service(self) -> None:
        """Attempts to load existing token silently without launching browser OAuth."""
        if os.path.exists(self.token_filepath):
            try:
                creds = Credentials.from_authorized_user_file(self.token_filepath, self.scopes)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_filepath, "w") as token:
                        token.write(creds.to_json())
                if creds and creds.valid:
                    self.service = build("gmail", "v1", credentials=creds)
                    logger.info("Gmail service initialized from existing token.")
                    return
            except Exception as e:
                logger.warning(f"Could not load existing credentials: {e}")
        logger.info("No active Gmail service session. Authentication needed.")

    def authenticate_flow(self) -> bool:
        """Run interactive OAuth consent flow in browser and save token."""
        if not os.path.exists(self.credentials_filepath):
            raise FileNotFoundError(f"Credentials file not found at {self.credentials_filepath}")
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_filepath, self.scopes
        )
        creds = flow.run_local_server(port=0)
        with open(self.token_filepath, "w") as token:
            token.write(creds.to_json())
        self.service = build("gmail", "v1", credentials=creds)
        logger.info("Authentication successful via OAuth flow.")
        return True

    def is_authenticated(self) -> bool:
        """Check if a valid or refreshable token is present."""
        if self.service is not None:
            return True
        if not os.path.exists(self.token_filepath):
            return False
        try:
            creds = Credentials.from_authorized_user_file(self.token_filepath, self.scopes)
            return bool(creds and (creds.valid or creds.refresh_token))
        except Exception:
            return False

    def _get_gmail_service(
        self, 
        scopes: list[str] | None = None, 
        token_filepath: str | None = None, 
        credentials_filepath: str | None = None,
    ):
        """Authenticates the user and returns the Gmail service object"""
        scopes = scopes or self.scopes
        token_filepath = token_filepath or self.token_filepath
        credentials_filepath = credentials_filepath or self.credentials_filepath

        logger.info("Authenticating user...")
        creds = None
        if os.path.exists(token_filepath):
            logger.info("Token file found. Loading credentials...")
            creds = Credentials.from_authorized_user_file(
                token_filepath,
                scopes
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Token expired. Refreshing token...")
                creds.refresh(Request())
            else:
                logger.info("No valid credentials found. Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_filepath, scopes
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for subsequent runs
            logger.info("Saving credentials...")
            with open(token_filepath, "w") as token:
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

    def _parse_message(
        self,
        message: dict,
        format: Literal["full", "metadata"] = "metadata",
    ) -> dict:
        """Parse raw Gmail message dictionary into standardized email dict"""
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # 1. Parse Headers & Metadata
        subject = self._get_header(headers, "Subject")
        sender = self._get_header(headers, "From")
        recipient = self._get_header(headers, "To")
        date_str = self._get_header(headers, "Date")
        internal_date = message.get("internalDate")  # epoch timestamp in ms

        # 2. Extract Body (only when format="full")
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
        }

    def _get_email_details(
        self,
        msg_id: str,
        format: Literal["full", "metadata"] = "metadata",
        metadata_headers: list[str] | None = ["Subject", "From", "To", "Date"],
    ) -> dict:
        """Fetch and parse message details for a single message ID"""
        if self.service is None:
            self.service = self._get_gmail_service()
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
        return self._parse_message(message, format=format)

    def fetch_and_cache_body(self, msg_id: str) -> str:
        """Fetches the full body for a single message from Gmail and caches it"""
        details = self._get_email_details(msg_id=msg_id, format="full")
        self.db.cache_email_body(
            email_id=details["id"],
            thread_id=details["thread_id"],
            body=details["text_body"],
        )
        return details["text_body"]

    def _batch_fetch_metadata(
        self,
        message_ids: list[str],
        metadata_headers: list[str] = ["Subject", "From", "To", "Date"],
        batch_size: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """Fetch metadata for a list of message IDs in parallel batches.

        Uses Gmail API's BatchHttpRequest (batch size 20) to safely stay within
        Gmail's per-user mailbox concurrency limits and avoid 429 errors.
        """
        if not message_ids:
            return []

        total = len(message_ids)
        logger.info(f"Fetching metadata for {total} messages in batches of {batch_size}...")

        if progress_callback:
            try:
                progress_callback(0, total)
            except Exception:
                pass

        email_details: list[dict] = []
        pending_ids = list(message_ids)
        start_time = time.time()
        max_retries = 3

        for attempt in range(max_retries):
            if not pending_ids:
                break

            failed_ids: list[str] = []

            for i in range(0, len(pending_ids), batch_size):
                chunk = pending_ids[i : i + batch_size]
                batch = self.service.new_batch_http_request()

                def make_callback(mid: str):
                    def callback(request_id, response, exception):
                        if exception is not None:
                            failed_ids.append(mid)
                        elif response:
                            email_details.append(self._parse_message(response, format="metadata"))
                    return callback

                for mid in chunk:
                    req = self.service.users().messages().get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=metadata_headers,
                    )
                    batch.add(req, callback=make_callback(mid))

                batch.execute()

                elapsed = time.time() - start_time
                logger.info(
                    f"Progress: {len(email_details)}/{total} emails "
                    f"({(len(email_details) / total) * 100:.0f}%) in {elapsed:.1f}s"
                )
                if progress_callback:
                    try:
                        progress_callback(len(email_details), total)
                    except Exception:
                        pass
                time.sleep(0.05)  # Smooth pacing to respect per-second rate limits

            pending_ids = failed_ids
            if pending_ids and attempt < max_retries - 1:
                wait_time = 1.0 * (attempt + 1)
                logger.warning(
                    f"{len(pending_ids)} messages rate-limited. Retrying in {wait_time:.1f}s "
                    f"(attempt {attempt + 2}/{max_retries})..."
                )
                time.sleep(wait_time)
                batch_size = max(5, batch_size // 2)

        if pending_ids:
            logger.warning(f"Could not fetch metadata for {len(pending_ids)} messages after {max_retries} attempts.")

        logger.info(
            f"Successfully fetched metadata for {len(email_details)}/{total} emails "
            f"in {time.time() - start_time:.2f} seconds."
        )
        return email_details

    def _fetch_all_emails(
        self, 
        max_recent_emails: int = 1000, 
        metadata_headers: list[str] = ["Subject", "From", "To", "Date"], 
        batch_size: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """Fetch recent emails from Gmail up to GMAIL_SYNC_MAX_RECENT_EMAILS"""
        messages = []
        page_token = None
        page = 0

        logger.info(
            f"Fetching up to {max_recent_emails} recent message IDs "
            "(metadata only)"
        )

        # Paginate through messages up to GMAIL_SYNC_MAX_RECENT_EMAILS
        while len(messages) < max_recent_emails:
            page += 1
            remaining = max_recent_emails - len(messages)
            list_page_size = min(500, remaining)

            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    pageToken=page_token,
                    maxResults=list_page_size,
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
                f"(total: {len(messages)}/{max_recent_emails})"
            )
            page_token = results.get("nextPageToken")

            if not page_token:
                break

        messages = messages[: max_recent_emails]
        message_ids = [m["id"] for m in messages if "id" in m]

        return self._batch_fetch_metadata(
            message_ids=message_ids,
            metadata_headers=metadata_headers,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )

    def _get_current_history_id(self) -> str | None:
        """Fetch the current historyId of the mailbox from Gmail profile"""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("historyId")
        except Exception as e:
            logger.warning(f"Could not fetch mailbox historyId from profile: {e}")
            return None

    def _fallback_date_sync(
        self, 
        metadata_headers: list[str] = ["Subject", "From", "To", "Date"]
    ) -> None:
        """
        Fallback sync when historyId is expired (>7 days old).
        Queries Gmail for messages after the latest known message date in SQLite.
        """
        logger.info("Running date-based fallback sync...")
        latest_ms = self.db.get_latest_email_date_ms()
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
            new_emails = self._batch_fetch_metadata(
                message_ids=new_message_ids,
                metadata_headers=metadata_headers,
            )
            self.db.ingest_emails(new_emails)

        # Update checkpoint to current mailbox state
        fresh_history_id = self._get_current_history_id()
        if fresh_history_id:
            self.db.set_sync_state("gmail_last_history_id", str(fresh_history_id))
        self.db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())

    def _incremental_sync(
        self, 
        start_history_id: str, 
        metadata_headers: list[str] = ["Subject", "From", "To", "Date"]
    ) -> None:
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
            logger.info(f"Fetching metadata for {len(messages_added_ids)} new emails...")
            new_emails = self._batch_fetch_metadata(
                message_ids=list(messages_added_ids),
                metadata_headers=metadata_headers,
            )
            self.db.ingest_emails(new_emails)

        # Delete removed emails
        if messages_deleted_ids:
            logger.info(f"Removing {len(messages_deleted_ids)} deleted emails from local database...")
            self.db.delete_emails(list(messages_deleted_ids))

        # Update labels on modified emails (excluding newly added ones which already have fresh labels)
        for msg_id, labels in labels_updated.items():
            if msg_id not in messages_added_ids and msg_id not in messages_deleted_ids:
                self.db.update_email_labels(msg_id, labels)

        # Update sync_state checkpoints
        if new_history_id:
            self.db.set_sync_state("gmail_last_history_id", str(new_history_id))
        self.db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())

        logger.info(
            f"Incremental sync finished: {len(messages_added_ids)} added, "
            f"{len(messages_deleted_ids)} deleted, {len(labels_updated)} labels updated. "
            f"New historyId: {new_history_id}"
        )

    def sync_emails(
        self, 
        max_recent_emails: int = 3, 
        metadata_headers: list[str] = ["Subject", "From", "To", "Date"], 
        batch_size: int = 20,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Sync emails from Gmail to local database and update sync_state"""
        if self.service is None:
            self.service = self._get_gmail_service()
        last_history_id = self.db.get_sync_state("gmail_last_history_id")

        if last_history_id is None:
            logger.info(
                f"First boot detected. Fetching first "
                f"{max_recent_emails} emails..."
            )
            # 1. Grab current mailbox historyId before/during backfill
            current_history_id = self._get_current_history_id()

            # 2. Fetch and ingest email metadata
            email_details = self._fetch_all_emails(
                max_recent_emails=max_recent_emails, 
                metadata_headers=metadata_headers, 
                batch_size=batch_size,
                progress_callback=progress_callback,
            )
            logger.info("Saving emails to database...")
            self.db.ingest_emails(email_details)

            # 3. Store baseline historyId and timestamp in sync_state
            if current_history_id:
                self.db.set_sync_state("gmail_last_history_id", str(current_history_id))
                logger.info(f"Stored initial historyId '{current_history_id}' in sync_state.")
            else:
                logger.warning("No historyId retrieved; subsequent sync may trigger full backfill.")
            self.db.set_sync_state("last_sync_at", datetime.now(timezone.utc).isoformat())
        else:
            logger.info(f"Existing historyId found ({last_history_id}). Running incremental sync...")
            self._incremental_sync(last_history_id)

        logger.info("Sync complete!")


# FOR DEBUGGING
# if __name__ == "__main__":
#     from settings import settings
#     db = Database(
#         store_dir=settings.DB_STORE_DIR, 
#         sqlite_filename=settings.DB_SQLITE_FILENAME
#     )
#     gmail_sync = GmailSync(db)

#     ## Full flow
#     gmail_sync.sync_emails(
#         max_recent_emails=settings.GMAIL_SYNC_MAX_RECENT_EMAILS, 
#         metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS, 
#         batch_size=settings.GMAIL_SYNC_BATCH_SIZE
#     )

#     ## Partial flow (Skips DB ingestion part)
#     # emails = gmail_sync._fetch_all_emails()
#     # print(json.dumps(emails, indent=4))