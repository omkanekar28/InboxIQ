from typing import Optional
from pydantic import BaseModel, Field


class SyncTriggerResponse(BaseModel):
    job_id: str
    status: str = "started"
    message: str


class SyncStatusResponse(BaseModel):
    state: str = Field(description="'idle', 'running', 'completed', or 'failed'")
    last_sync_at: Optional[str] = None
    total_emails: int = 0
    job_running: bool = False
    last_error: Optional[str] = None
    current_synced: int = 0
    total_to_sync: int = 0
    percent: float = 0.0

