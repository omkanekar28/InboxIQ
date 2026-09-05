from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Gmail Sync
    GMAIL_SYNC_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
    GMAIL_SYNC_MAX_RECENT_EMAILS: int = 1000
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