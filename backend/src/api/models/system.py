from typing import Literal, Optional
from pydantic import BaseModel, Field


class HardwareResponse(BaseModel):
    gpu_available: bool
    gpu_name: Optional[str] = None
    vram_mb: Optional[int] = None
    active_model: str


class ModelSwitchRequest(BaseModel):
    model: Literal["lightweight", "balanced"] = Field(
        ..., description="Desired active model ('lightweight' or 'balanced')"
    )


class ModelSwitchResponse(BaseModel):
    active_model: str
    status: str = "success"
    message: str
