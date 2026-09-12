"""
Settings for the application.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Gmail Sync
    GMAIL_SYNC_SCOPES: list[str] = Field(
        description="OAuth scopes required for accessing Gmail.",
        default=["https://www.googleapis.com/auth/gmail.readonly"]
    )

    # TODO: Set this to a higher value in PROD
    GMAIL_SYNC_MAX_RECENT_EMAILS: int = Field(
        description="Maximum number of recent emails to fetch from Gmail.", default=5
    )

    GMAIL_SYNC_METADATA_HEADERS: list[str] = Field(
        description="Metadata headers to fetch from Gmail.",
        default=["Subject", "From", "To", "Date"]
    )
    GMAIL_SYNC_TOKEN_FILEPATH: str = Field(
        description="Path to the token file.", default="token.json"
    )
    GMAIL_SYNC_CREDENTIALS_FILEPATH: str = Field(
        description="Path to the credentials file.",
        default="credentials.json"
    )

    # Database
    DB_STORE_DIR: str = Field(
        description="Root directory for all database files.",
        default="../data"
    )
    
    ## Sqlite
    DB_SQLITE_FILENAME: str = Field(
        description="Filename for the SQLite database.",
        default="inboxiq.db"
    )

    ## Faiss
    DB_FAISS_INDEX_NAME: str = Field(
        description="Filename for the Faiss index.",
        default="inboxiq.index"
    )
    DB_FAISS_METADATA_FILENAME: str = Field(
        description="Filename for the Faiss metadata JSON file.",
        default="inboxiq.json"
    )

    # Testing
    TEST_DIR: str = Field(
        description="Directory for test data.",
        default="../data/sandbox"
    )
    TEST_DB_SQLITE_FILENAME: str = Field(
        description="Filename for the SQLite database used during testing.",
        default="inboxiq.test.db"
    )

    # Tools
    SEARCH_EMAIL_FIELDS: tuple[str, ...] = Field(
        description="Tuple of fields to return from DB for the search_emails tool call.",
        default=(
            "id",
            "thread_id",
            "sender",
            "subject",
            "snippet",
            "labels",
            "date",
        ))
    EMAIL_THREAD_FIELDS: tuple[str, ...] = Field(
        description="Tuple of fields to return from DB for the get_email_thread tool call.",
        default=(
            "id",
            "thread_id",
            "sender",
            "recipient",
            "subject",
            "labels",
            "date",
            "body",
        ))


settings = Settings()