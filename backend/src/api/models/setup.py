from typing import Optional
from pydantic import BaseModel


class SetupStatusResponse(BaseModel):
    credentials_ok: bool
    authenticated: bool
    models_downloaded: bool
    initial_sync_done: bool


class CredentialsUploadResponse(BaseModel):
    status: str = "success"
    message: str


class AuthResponse(BaseModel):
    status: str = "success"
    message: str
