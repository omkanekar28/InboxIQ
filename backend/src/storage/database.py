import json
import os
import sqlite3
from functools import wraps
from typing import Any, Callable
from utils import get_logger
from settings import settings

logger = get_logger(name=__name__, log_file="storage.log")


def with_transaction(func: Callable) -> Callable:
    """
    Decorator that automatically commits on success,
    or rolls back changes if an exception occurs.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        try:
            result = func(self, *args, **kwargs)
            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction failed in '{func.__name__}': {e}. Rolled back changes.")
            raise
    return wrapper


class Database:
    """Manages the SQLite database for InboxIQ"""
    
    def __init__(self) -> None:
        """Initialises the database"""
        logger.info("Initialising database...")        
        os.makedirs(settings.DB_STORE_DIR, exist_ok=True)
        db_path = os.path.join(settings.DB_STORE_DIR, settings.DB_SQLITE_FILENAME)
        
        db_exists = os.path.exists(db_path)
        self.conn = sqlite3.connect(db_path)
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
                body TEXT,
                labels TEXT,
                date TEXT,
                internal_date_ms INTEGER,
                is_full INTEGER NOT NULL CHECK (is_full IN (0, 1)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_emails_thread_id ON emails (thread_id);
            CREATE INDEX IF NOT EXISTS idx_emails_internal_date ON emails (internal_date_ms);
            CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails (sender);

            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    @with_transaction
    def ingest_emails(self, emails: list[dict]) -> None:
        """Ingests emails into the database with automatic commit and rollback."""
        for email in emails:
            labels = email.get("labels") or email.get("label_ids", [])
            if isinstance(labels, (list, dict, set)):
                labels = json.dumps(labels)

            self.cursor.execute("""
                INSERT OR REPLACE INTO emails (
                    id, thread_id, sender, recipient, subject, snippet, body, labels, date, internal_date_ms, is_full
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email["id"],
                email["thread_id"],
                email.get("sender") or email.get("from", ""),
                email.get("recipient") or email.get("to", ""),
                email.get("subject", ""),
                email.get("snippet", ""),
                email.get("body") or email.get("text_body", ""),
                labels,
                email.get("date", ""),
                email.get("internal_date_ms"),
                email.get("is_full", 1 if email.get("body") else 0),
            ))

    @with_transaction
    def delete_emails(self, email_ids: list[str]) -> None:
        """Deletes emails by ID from the database."""
        if not email_ids:
            return
        placeholders = ",".join("?" for _ in email_ids)
        self.cursor.execute(f"DELETE FROM emails WHERE id IN ({placeholders})", email_ids)

    @with_transaction
    def update_email_labels(self, email_id: str, labels: list[str]) -> None:
        """Updates the labels for a given email."""
        self.cursor.execute(
            "UPDATE emails SET labels = ? WHERE id = ?",
            (json.dumps(labels), email_id),
        )

    def get_latest_email_date_ms(self) -> int | None:
        """Returns the internal_date_ms of the most recent email in the database."""
        self.cursor.execute("SELECT MAX(internal_date_ms) FROM emails")
        row = self.cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    @with_transaction
    def set_sync_state(self, key: str, value: str) -> None:
        """Stores or updates a key-value pair in sync_state."""
        self.cursor.execute("""
            INSERT OR REPLACE INTO sync_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))

    def get_sync_state(self, key: str) -> str | None:
        """Retrieves a value from sync_state by key."""
        self.cursor.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row[0] if row else None


db = Database()