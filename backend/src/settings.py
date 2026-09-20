from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Literal, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings."""

    # Gmail Sync
    GMAIL_SYNC_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly"
    ]
    GMAIL_SYNC_MAX_RECENT_EMAILS: int = 1000
    GMAIL_SYNC_METADATA_HEADERS: list[str] = ["Subject", "From", "To", "Date"]
    GMAIL_SYNC_TOKEN_FILEPATH: str = "token.json"
    GMAIL_SYNC_CREDENTIALS_FILEPATH: str = "credentials.json"

    # Database
    DB_STORE_DIR: str = str(BACKEND_DIR / "data")

    # SQLite
    DB_SQLITE_FILENAME: str = "inboxiq.db"

    # FAISS
    DB_FAISS_INDEX_NAME: str = "inboxiq.index"
    DB_FAISS_METADATA_FILENAME: str = "inboxiq.json"

    # Tools
    SEARCH_EMAIL_FIELDS: tuple[str, ...] = (
        "id",
        "thread_id",
        "sender",
        "subject",
        "snippet",
        "labels",
        "date",
    )

    EMAIL_THREAD_FIELDS: tuple[str, ...] = (
        "id",
        "thread_id",
        "sender",
        "recipient",
        "subject",
        "labels",
        "date",
        "body",
    )

    # Model
    MODEL_TYPE: Literal["balanced", "lightweight"] = "balanced"
    MODEL_DOWNLOAD_URL_BALANCED: str = "https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/resolve/main/LFM2.5-2.6B-Q4_K_M.gguf"
    MODEL_DOWNLOAD_URL_LIGHTWEIGHT: str = "https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF/resolve/main/LFM2.5-1.2B-Thinking-Q4_K_M.gguf"
    MODEL_STORE_DIR: str = str(BACKEND_DIR / "models")

    # Llama-Cpp Server
    LLAMA_CPP_CPU_BINARIES_URL: str = "https://github.com/ggml-org/llama.cpp/releases/download/b11050/llama-b11050-bin-win-cpu-x64.zip"
    LLAMA_CPP_CUDA_BINARIES_URL: str = "https://github.com/ggml-org/llama.cpp/releases/download/b11050/llama-b11050-bin-win-cuda-13.4-x64.zip"
    LLAMA_CPP_BINARIES_STORE_DIR: str = str(BACKEND_DIR / "llama-cpp")
    LLAMA_CPP_SERVER_PORT_NO: int = 8001
    LLAMA_CPP_SERVER_CONTEXT_WINDOW_SIZE: int = 4096
    LLAMA_CPP_SERVER_N_BATCH: int = 512
    LLAMA_CPP_SERVER_N_THREADS: int = 4
    LLAMA_CPP_SERVER_N_GPU_LAYERS: Optional[int] = None


settings = Settings()