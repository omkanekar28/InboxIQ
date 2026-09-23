from typing import Any, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the author ('user', 'assistant', 'system')")
    content: str = Field(..., description="Content of the message")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., description="List of messages in conversation")
    stream: bool = Field(default=True, description="Whether to stream the response via Server-Sent Events (SSE)")


class ToolCallInfo(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    tools_called: list[ToolCallInfo] = Field(default_factory=list)
    latency_seconds: float
