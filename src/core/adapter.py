"""
Smart API Adapter — Chuyển đổi giữa OpenAI format và Gemini Web Client.

Nhiệm vụ chính:
1. Convert messages[] (OpenAI) → prompt text (cho browser)
2. Phân biệt session mới vs session cũ để tối ưu payload
3. Map tên model giữa OpenAI-style và Gemini Web UI
4. Format response từ Gemini → chuẩn OpenAI JSON
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from src.schemas.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ResponseMessage,
    Usage,
    GeminiMeta,
    ChatCompletionChunk,
    StreamChoice,
    DeltaMessage,
    ErrorResponse,
    ErrorDetail,
    AnthropicMessage,
    AnthropicContentBlock,
)


# ============================================================
# Model Name Mapping
# ============================================================

# Map từ tên OpenAI-style → các tên có thể xuất hiện trên Gemini Web UI
MODEL_ALIASES: dict[str, list[str]] = {
    "gemini-pro":       ["Pro", "Nâng cao", "Advanced", "Gemini Pro", "2.5 Pro"],
    "gemini-flash":     ["Nhanh", "Flash", "Gemini Flash", "3.0 Flash"],
    "gemini-thinking":  ["Tư duy", "Thinking", "Deep Think", "Tư duy sâu"],
    "gemini-basic":     ["Cơ bản", "Basic", "Gemini Basic"],
}

# Thứ tự fallback khi model yêu cầu không khả dụng
FALLBACK_ORDER = ["gemini-pro", "gemini-thinking", "gemini-flash", "gemini-basic"]


def normalize_model_name(model: str) -> str:
    """
    Chuẩn hóa tên model từ request.
    Ví dụ: "gemini-2.5-pro" → "gemini-pro", "flash" → "gemini-flash"
    """
    lower = model.lower().strip()

    # Exact match
    if lower in MODEL_ALIASES:
        return lower

    # Partial match
    if "pro" in lower or "advanced" in lower or "nâng cao" in lower:
        return "gemini-pro"
    if "flash" in lower or "nhanh" in lower or "fast" in lower:
        return "gemini-flash"
    if "think" in lower or "tư duy" in lower:
        return "gemini-thinking"
    if "basic" in lower or "cơ bản" in lower:
        return "gemini-basic"

    # Fallback: giữ nguyên tên, sẽ được xử lý bởi model_router
    return lower


def get_ui_names_for_model(model: str) -> list[str]:
    """Lấy danh sách tên UI có thể match cho model chuẩn hóa."""
    normalized = normalize_model_name(model)
    return MODEL_ALIASES.get(normalized, [model])


def match_model_in_list(requested: str, available_models: list[str]) -> Optional[str]:
    """
    Tìm model khớp nhất trong danh sách available.
    Trả về tên chính xác trên UI nếu match, None nếu không.
    """
    ui_names = get_ui_names_for_model(requested)

    for available in available_models:
        available_lower = available.lower().strip()
        for ui_name in ui_names:
            if ui_name.lower() in available_lower or available_lower in ui_name.lower():
                return available

    return None


# ============================================================
# Message Conversion
# ============================================================

def convert_messages_to_prompt(
    messages: list[ChatMessage],
    is_new_session: bool = True,
) -> str:
    """
    Chuyển đổi danh sách messages OpenAI format → prompt text cho Gemini.

    Quy tắc:
    - is_new_session=True: Gom toàn bộ history thành 1 prompt
      (vì Gemini Web chưa có context nào)
    - is_new_session=False: Chỉ lấy message cuối cùng
      (vì Gemini Web đã nhớ context trong session browser)
    """
    if not messages:
        return ""

    if not is_new_session:
        # Session cũ — chỉ gửi tin nhắn cuối (role=user)
        for msg in reversed(messages):
            if msg.role == "user":
                return msg.content.strip()
        # Nếu không tìm thấy user message, gửi message cuối cùng
        return messages[-1].content.strip()

    # Session mới — gom toàn bộ history
    parts: list[str] = []

    for msg in messages:
        if msg.role == "system":
            parts.append(f"<SYSTEM_TURN>\n{msg.content}\n</SYSTEM_TURN>")
        elif msg.role == "user":
            parts.append(f"<USER_TURN>\n{msg.content}\n</USER_TURN>")
        elif msg.role == "assistant":
            parts.append(f"<ASSISTANT_TURN>\n{msg.content}\n</ASSISTANT_TURN>")

    return "\n\n".join(parts)


# ============================================================
# Response Formatting
# ============================================================

def build_completion_response(
    content: str,
    model: str,
    request_id: Optional[str] = None,
    meta: Optional[GeminiMeta] = None,
) -> ChatCompletionResponse:
    """Tạo response object chuẩn OpenAI từ text response của Gemini."""
    return ChatCompletionResponse(
        id=request_id or f"chatcmpl-gemini-{uuid.uuid4().hex[:12]}",
        model=model,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=-1, completion_tokens=-1, total_tokens=-1),
        x_gemini_meta=meta,
    )


def build_stream_chunk(
    chunk_id: str,
    model: str,
    content: Optional[str] = None,
    role: Optional[str] = None,
    finish_reason: Optional[str] = None,
) -> ChatCompletionChunk:
    """Tạo một SSE chunk chuẩn OpenAI."""
    delta = DeltaMessage(role=role, content=content)
    return ChatCompletionChunk(
        id=chunk_id,
        model=model,
        choices=[
            StreamChoice(
                index=0,
                delta=delta,
                finish_reason=finish_reason,
            )
        ],
    )


def build_error_response(
    message: str,
    error_type: str = "server_error",
    code: Optional[str] = None,
) -> ErrorResponse:
    """Tạo error response chuẩn OpenAI."""
    return ErrorResponse(
        error=ErrorDetail(
            message=message,
            type=error_type,
            code=code,
        )
    )


# ============================================================
# Anthropic API Converters
# ============================================================

def convert_anthropic_to_prompt(
    messages: list[AnthropicMessage],
    system: Optional[str] = None,
    is_new_session: bool = True,
) -> str:
    """
    Chuyển đổi Anthropic messages → prompt text cho Gemini.

    Anthropic format có thể là:
    - content là string
    - content là list of content blocks (text, image, tool_use)
    """
    if not messages:
        return ""

    if not is_new_session:
        for msg in reversed(messages):
            if msg.role == "user":
                if isinstance(msg.content, str):
                    return msg.content.strip()
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if hasattr(block, "text") and block.text:
                            return block.text
        return messages[-1].content.strip() if isinstance(messages[-1].content, str) else ""

    parts: list[str] = []

    if system:
        parts.append(f"<SYSTEM_TURN>\n{system}\n</SYSTEM_TURN>")

    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else ""

        if isinstance(msg.content, list):
            for block in msg.content:
                if hasattr(block, "text") and block.text:
                    content = block.text

        if msg.role == "user":
            parts.append(f"<USER_TURN>\n{content}\n</USER_TURN>")
        elif msg.role == "assistant":
            parts.append(f"<ASSISTANT_TURN>\n{content}\n</ASSISTANT_TURN>")

    return "\n\n".join(parts)


def build_anthropic_response(
    content: str,
    model: str,
    request_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> dict:
    """Tạo response object chuẩn Anthropic từ text response của Gemini."""
    import time
    return {
        "id": message_id or f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": content,
            }
        ],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
        },
    }


def build_anthropic_stream_event(
    event_type: str,
    data: Optional[dict] = None,
) -> str:
    """Tạo một SSE event chuẩn Anthropic."""
    import json
    event = {"type": event_type}
    if data:
        event.update(data)
    return f"data: {json.dumps(event)}\n\n"
