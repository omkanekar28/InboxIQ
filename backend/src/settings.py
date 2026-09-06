from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Gmail Sync
    GMAIL_SYNC_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
    # GMAIL_SYNC_MAX_RECENT_EMAILS: int = 1000
    GMAIL_SYNC_MAX_RECENT_EMAILS: int = 3    # TODO: set to a higher value for production
    GMAIL_SYNC_EMAIL_FORMAT: Literal["full", "metadata"] = "metadata"
    GMAIL_SYNC_METADATA_HEADERS: list[str] = ["Subject", "From", "To", "Date"]
    GMAIL_SYNC_CREDENTIALS_FILEPATH: str = "credentials.json"
    GMAIL_SYNC_TOKEN_FILEPATH: str = "token.json"

    # Database
    DB_STORE_DIR: str = "../data"
    
    ## Sqlite
    DB_SQLITE_FILENAME: str = "inboxiq.db"

    ## Faiss
    DB_FAISS_INDEX_NAME: str = "inboxiq.index"
    DB_FAISS_METADATA_FILENAME: str = "inboxiq.json"


settings = Settings()