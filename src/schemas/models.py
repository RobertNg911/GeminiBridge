"""
OpenAI-Compatible API Schemas
Pydantic models chuẩn OpenAI format để tương thích với mọi SDK client.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional, Literal

from pydantic import BaseModel, Field


# ============================================================
# Request Models
# ============================================================

class ChatMessage(BaseModel):
    """Một message trong conversation."""
    role: Literal["system", "user", "assistant"] = "user"
    content: str = Field(default="", max_length=100_000)  # [FIX M6] Max 100KB per message


class ChatCompletionRequest(BaseModel):
    """
    Request body cho POST /v1/chat/completions.
    Tuân thủ chuẩn OpenAI Chat Completions API.
    """
    model: str = "gemini-flash"
    messages: list[ChatMessage] = Field(default_factory=list, max_length=100)  # [FIX M6] Max 100 messages
    stream: bool = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    # Custom extension — client có thể gửi session_id để tái sử dụng session
    # Nếu không gửi, server sẽ tự tạo session_id dựa trên model
    session_id: Optional[str] = Field(
        default=None,
        pattern=r'^[a-zA-Z0-9_\-]{1,64}$'
    )


# ============================================================
# Response Models — Non-Streaming
# ============================================================

class ResponseMessage(BaseModel):
    role: str = "assistant"
    content: str = ""


class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: Optional[str] = "stop"


class Usage(BaseModel):
    prompt_tokens: int = -1
    completion_tokens: int = -1
    total_tokens: int = -1


class GeminiMeta(BaseModel):
    """Metadata mở rộng — thông báo model thực tế, fallback, session info."""
    requested_model: str = ""
    actual_model: str = ""
    actual_model_normalized: str = ""  # [FIX M3] Tên model chuẩn hóa
    fallback: bool = False
    fallback_reason: str = ""
    session_id: str = ""


class ChatCompletionResponse(BaseModel):
    """Response body chuẩn OpenAI cho non-streaming request."""
    id: str = Field(default_factory=lambda: f"chatcmpl-gemini-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[Choice] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    system_fingerprint: str = "gemini-web-noapi"
    x_gemini_meta: Optional[GeminiMeta] = None


# ============================================================
# Response Models — Streaming (SSE Chunks)
# ============================================================

class DeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage = Field(default_factory=DeltaMessage)
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """Một chunk trong SSE stream — chuẩn OpenAI format."""
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[StreamChoice] = Field(default_factory=list)
    system_fingerprint: str = "gemini-web-noapi"


# ============================================================
# Model Listing
# ============================================================

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "gemini-web"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = Field(default_factory=list)


# ============================================================
# Error Response
# ============================================================

class ErrorDetail(BaseModel):
    message: str
    type: str = "server_error"
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ============================================================
# Health Check
# ============================================================

class HealthResponse(BaseModel):
    status: str = "ok"
    active_sessions: int = 0
    uptime_seconds: float = 0.0


# ============================================================
# Session Info (Bonus endpoint)
# ============================================================

class SessionInfo(BaseModel):
    session_id: str
    model: str
    is_ready: bool
    message_count: int
    idle_seconds: float
    last_active_iso: str
