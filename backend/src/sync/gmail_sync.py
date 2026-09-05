import json
import os
import time
import base64
from pathlib import Path
from typing import Literal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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
        format: Literal["full", "metadata"] = "metadata"
    ) -> dict:
        """Fetch and parse full message details for a given message ID."""
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=msg_id, format=format)
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
            "text_body": text_body or message.get("snippet", ""),
        }

    def _fetch_all_emails(self) -> list[dict]:
        """Fetch recent emails from Gmail up to GMAIL_SYNC_MAX_RECENT_EMAILS."""
        fetch_emails_start_time = time.time()
        messages = []
        page_token = None
        page = 0

        logger.info(f"Fetching up to {settings.GMAIL_SYNC_MAX_RECENT_EMAILS} recent message IDs...")
        
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
            email_detail = self._get_email_details(message["id"], format="full")
            email_details.append(email_detail)
        
        logger.info(
            f"Fetched {len(email_details)} emails in {time.time() - fetch_emails_start_time:.2f} seconds."
        )
        return email_details

    def _incremental_sync(self):
        """Perform incremental sync since last checkpoint, or trigger backfill on first run."""
        pass

    def sync_emails(self, first_boot: bool) -> None:
        """Sync emails from Gmail to local database."""
        if first_boot:
            logger.info(
                f"First boot detected. Fetching first "
                f"{settings.GMAIL_SYNC_MAX_RECENT_EMAILS} emails..."
            )
            email_details = self._fetch_all_emails()

            logger.info("Saving emails to database...")
            db.ingest_emails(email_details)
        else:
            logger.info("Incremental sync not implemented yet.")
        
        logger.info("Sync complete!")


# FOR DEBUGGING
# if __name__ == "__main__":
#     gmail_sync = GmailSync()

#     ## Full flow (WILL OVERWRITE EXISTING DATABASE!!!)
#     # gmail_sync.sync_emails(first_boot=True)

#     ## Partial flow (Skips DB ingestion part)
#     emails = gmail_sync._fetch_all_emails()
#     print(json.dumps(emails, indent=4))