"""
Single source of truth for database operations.
"""


import json
import re
import html
from datetime import datetime, timezone
import os
import sqlite3
import threading
from functools import wraps
from typing import Any, Callable
from utils import get_logger, parse_date_from_str

logger = get_logger(name=__name__)


def with_transaction(func: Callable) -> Callable:
    """
    Decorator that automatically commits on success,
    or rolls back changes if an exception occurs.
    Guarantees thread-safe atomic transactions via self.lock.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        with self.lock:
            try:
                result = func(self, *args, **kwargs)
                self.conn.commit()
                return result
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Transaction failed in '{func.__name__}': {e}. Rolled back changes.")
                raise
    return wrapper


def with_lock(func: Callable) -> Callable:
    """
    Decorator ensuring thread-safe read access to SQLite via self.lock.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        with self.lock:
            return func(self, *args, **kwargs)
    return wrapper


class Database:
    """Manages the SQLite database for InboxIQ"""

    def __init__(
        self, 
        store_dir: str = "../data", 
        sqlite_filename: str = "inboxiq.db", 
        search_email_fields: tuple[str, ...] = ("id", "thread_id", "sender", "subject", "snippet", "date"),
        email_thread_fields: tuple[str, ...] = ("id", "thread_id", "sender", "recipient", "subject", "date", "body"),
    ) -> None:
        """Initialises the database"""
        logger.info("Initialising database...")
        self.search_email_fields = search_email_fields
        self.email_thread_fields = email_thread_fields

        os.makedirs(store_dir, exist_ok=True)
        db_path = os.path.join(store_dir, sqlite_filename)

        db_exists = os.path.exists(db_path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

        # Only create tables on first boot
        if not db_exists:
            logger.info("Database does not exist. Creating initial tables...")
            self._create_initial_tables()
        else:
            logger.info("Database exists. Skipping initial table creation.")

        logger.info("Database initialisation complete.")

    @with_transaction
    def _create_initial_tables(self) -> None:
        """Creates the initial tables in the database if they don't exist"""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                sender TEXT,
                recipient TEXT,
                subject TEXT,
                snippet TEXT,
                labels TEXT,
                date TEXT,
                internal_date_ms INTEGER,
                created_at TIMESTAMP DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
            );

            CREATE INDEX IF NOT EXISTS idx_emails_thread_id ON emails (thread_id);
            CREATE INDEX IF NOT EXISTS idx_emails_internal_date ON emails (internal_date_ms);
            CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails (sender);
            CREATE INDEX IF NOT EXISTS idx_emails_recipient ON emails (recipient);

            CREATE TABLE IF NOT EXISTS emails_content (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                body TEXT,
                fetched_at TIMESTAMP DEFAULT (datetime('now', '+5 hours', '+30 minutes')),
                FOREIGN KEY (id) REFERENCES emails(id)
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
            );
        """)

    @with_transaction
    def ingest_emails(self, emails: list[dict]) -> None:
        """Ingests email metadata into the database with automatic commit and rollback.

        Only lightweight metadata is stored here (search_emails reads from this table).
        Full body text is NOT written by this method — that's cached separately,
        on demand, via cache_email_body() when get_email_thread() is actually called.
        """
        for email in emails:
            labels = email.get("labels") or email.get("label_ids", [])
            if isinstance(labels, (list, dict, set)):
                labels = json.dumps(labels)

            self.cursor.execute("""
                INSERT OR REPLACE INTO emails (
                    id, thread_id, sender, recipient, subject, snippet, labels, date, internal_date_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email["id"],
                email["thread_id"],
                email.get("sender") or email.get("from", ""),
                email.get("recipient") or email.get("to", ""),
                email.get("subject", ""),
                email.get("snippet", ""),
                labels,
                email.get("date", ""),
                email.get("internal_date_ms"),
            ))

    @with_transaction
    def delete_emails(self, email_ids: list[str]) -> None:
        """Deletes emails by ID from both metadata and content tables."""
        if not email_ids:
            return
        placeholders = ",".join("?" for _ in email_ids)
        self.cursor.execute(f"DELETE FROM emails WHERE id IN ({placeholders})", email_ids)
        self.cursor.execute(f"DELETE FROM emails_content WHERE id IN ({placeholders})", email_ids)

    @with_transaction
    def update_email_labels(self, email_id: str, labels: list[str]) -> None:
        """Updates the labels for a given email."""
        self.cursor.execute(
            "UPDATE emails SET labels = ? WHERE id = ?",
            (json.dumps(labels), email_id),
        )

    @with_lock
    def get_latest_email_date_ms(self) -> int | None:
        """Returns the internal_date_ms of the most recent email in the database."""
        self.cursor.execute("SELECT MAX(internal_date_ms) FROM emails")
        row = self.cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    @with_lock
    def get_cached_body(self, email_id: str) -> str | None:
        """Returns the cached full body for an email, or None on a cache miss."""
        self.cursor.execute("SELECT body FROM emails_content WHERE id = ?", (email_id,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    @with_transaction
    def cache_email_body(self, email_id: str, thread_id: str, body: str) -> None:
        """Caches the full body text for an email after it's been fetched from Gmail.

        Called by get_email_thread() on a cache miss, right after pulling the
        full content from the Gmail API, so subsequent lookups for the same
        email are served locally without another API round-trip.
        """
        self.cursor.execute("""
            INSERT OR REPLACE INTO emails_content (id, thread_id, body, fetched_at)
            VALUES (?, ?, ?, (datetime('now', '+5 hours', '+30 minutes')))
        """, (email_id, thread_id, body))

    @with_transaction
    def set_sync_state(self, key: str, value: str) -> None:
        """Stores or updates a key-value pair in sync_state."""
        self.cursor.execute("""
            INSERT OR REPLACE INTO sync_state (key, value, updated_at)
            VALUES (?, ?, (datetime('now', '+5 hours', '+30 minutes')))
        """, (key, value))

    @with_lock
    def get_sync_state(self, key: str) -> str | None:
        """Retrieves a value from sync_state by key."""
        self.cursor.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    # |-- USED BY TOOLS --|
    @with_lock
    def get_email_thread(self, thread_id: str) -> dict:
        """Fetch all emails in a thread, including cached body text.

        JOINs emails with emails_content so the body field is available.
        Returns a dict with the thread_id and a list of email dicts ordered
        oldest-first (natural reading order).
        """
        # Build the SELECT list: body comes from emails_content, rest from emails
        select_fields = ", ".join(
            "ec.body" if f == "body" else f"e.{f}"
            for f in self.email_thread_fields
        )
        self.cursor.execute(f"""
            SELECT {select_fields}
            FROM emails e
            LEFT JOIN emails_content ec ON e.id = ec.id
            WHERE e.thread_id = ?
            ORDER BY e.internal_date_ms ASC
        """, (thread_id,))
        rows = self.cursor.fetchall()
        emails = [
            {key: value for key, value in zip(self.email_thread_fields, row)}
            for row in rows
        ]
        return {"thread_id": thread_id, "emails": emails}

    @with_lock
    def search_emails(
        self,
        keyword: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        label: str | None = None,
        limit: int = 25,
    ) -> list[dict]:
        """Search emails with any combination of filters in a single SQL query.

        All supplied arguments are combined with AND — each extra argument
        narrows the result set rather than producing a separate one.
        Returns at most `limit` rows (capped at 25) ordered newest-first.
        """
        limit = min(limit or 25, 25)
        conditions: list[str] = []
        params: list = []

        if keyword:
            terms = [t.strip() for t in keyword.split() if t.strip()]
            if len(terms) <= 1:
                conditions.append("(subject LIKE ? OR snippet LIKE ? OR sender LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
            else:
                term_clauses = ["(subject LIKE ? OR snippet LIKE ? OR sender LIKE ?)"]
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
                for term in terms:
                    term_clauses.append("(subject LIKE ? OR snippet LIKE ? OR sender LIKE ?)")
                    params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
                conditions.append(f"({' OR '.join(term_clauses)})")

        if sender:
            conditions.append("sender LIKE ?")
            params.append(f"%{sender}%")

        if recipient:
            conditions.append("recipient LIKE ?")
            params.append(f"%{recipient}%")

        if date_from:
            parsed_from = parse_date_from_str(date_from)
            dt_from = datetime.strptime(parsed_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append("internal_date_ms >= ?")
            params.append(int(dt_from.timestamp() * 1000))

        if date_to:
            parsed_to = parse_date_from_str(date_to)
            dt_to = datetime.strptime(parsed_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999000, tzinfo=timezone.utc
            )
            conditions.append("internal_date_ms <= ?")
            params.append(int(dt_to.timestamp() * 1000))

        if label:
            conditions.append("labels LIKE ?")
            params.append(f"%{label}%")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        self.cursor.execute(f"""
            SELECT {', '.join(self.search_email_fields)}
            FROM emails
            {where_clause}
            ORDER BY internal_date_ms DESC
            LIMIT ?
        """, params + [limit])
        rows = self.cursor.fetchall()
        results = []
        for row in rows:
            item = {key: value for key, value in zip(self.search_email_fields, row)}
            if "snippet" in item and item["snippet"]:
                cleaned = html.unescape(item["snippet"])
                cleaned = re.sub(r"[\u200b-\u200f\ufeff\u00a0]+", " ", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                item["snippet"] = cleaned
            results.append(item)
        return results

    @with_lock
    def get_total_emails(self) -> int:
        """Returns the total number of indexed emails in the database."""
        self.cursor.execute("SELECT COUNT(*) FROM emails")
        row = self.cursor.fetchone()
        return row[0] if row else 0


# FOR DEBUGGING
# if __name__ == "__main__":
#     from settings import settings
#     db = Database(
#         store_dir=settings.DB_STORE_DIR,
#         sqlite_filename=settings.DB_SQLITE_FILENAME,
#         search_email_fields=settings.SEARCH_EMAIL_FIELDS,
#         email_thread_fields=settings.EMAIL_THREAD_FIELDS,
#     )

#     print(json.dumps(db.search_emails(
#         keyword="AI", 
#         sender="Google", 
#         recipient="me",
#         date_from="2026-01-01",
#         date_to="2026-12-31",
#         label="inbox",
#         limit=10
#     ), indent=4))