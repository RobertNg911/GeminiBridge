"""
OpenAI-Compatible API Server — Biến Gemini Web thành REST API chuẩn OpenAI.

Endpoints:
  POST /v1/chat/completions  — Chat completion (streaming + non-streaming)
  GET  /v1/models            — Liệt kê models
  GET  /health               — Health check
  GET  /v1/sessions          — Xem trạng thái session pool
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from src.schemas.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
    ModelListResponse,
    ModelInfo,
    HealthResponse,
    ErrorResponse,
    GeminiMeta,
    AnthropicRequest,
)
from src.core.adapter import (
    convert_messages_to_prompt,
    normalize_model_name,
    build_completion_response,
    build_stream_chunk,
    build_error_response,
    MODEL_ALIASES,
    convert_anthropic_to_prompt,
    build_anthropic_response,
    build_anthropic_stream_event,
)
from src.core.session import SessionManager
from src.api.router import select_best_model, get_all_supported_models
from src.core.resilience import BrowserWatchdog, RequestThrottler

logger = logging.getLogger("api_server")

# ============================================================
# Global State — được khởi tạo trong lifespan
# ============================================================

_manager: Optional[SessionManager] = None
_watchdog: Optional[BrowserWatchdog] = None
_throttler: Optional[RequestThrottler] = None
_server_config: dict = {}
_start_time: float = 0


def load_server_config(path: str = "server_config.json") -> dict:
    """Load server configuration."""
    import os
    defaults = {
        "host": "127.0.0.1",
        "port": 8765,
        "api_key": "CHANGE_ME",
        "max_sessions": 3,
        "idle_timeout_seconds": 300,
        "min_request_delay_seconds": 2.0,
        "max_request_delay_seconds": 5.0,
        "default_model": "gemini-pro",
        "headless": True,
        "guest_mode": True,
        "log_level": "INFO",
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            defaults.update(user_cfg)
        except Exception as e:
            logger.warning(f"⚠ Lỗi đọc {path}: {e}. Dùng cấu hình mặc định.")
    return defaults


# ============================================================
# Lifespan — Startup & Shutdown
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo và dọn dẹp tài nguyên."""
    global _manager, _watchdog, _throttler, _server_config, _start_time

    _start_time = time.time()
    _server_config = load_server_config()

    # [FIX] Đặt exception handler triệt tiêu lỗi nodriver spam console vào chính event loop của Uvicorn
    loop = asyncio.get_running_loop()
    def handle_async_exception(loop, context):
        msg = context.get("exception", context.get("message", ""))
        if isinstance(msg, ConnectionRefusedError) or "WinError 1225" in str(msg) or "WebSocket" in str(msg):
            pass
        else:
            # Lấy reference đến handler mặc định trước khi override
            loop.default_exception_handler(context)
    loop.set_exception_handler(handle_async_exception)

    _api_key = _server_config.get("api_key", "")
    if _api_key in ("CHANGE_ME", "", "your-secret-key-here"):
        logger.critical("=" * 60)
        logger.critical("🚨 CẢNH BÁO: api_key chưa được đổi khỏi giá trị mặc định!")
        logger.critical("   Sửa 'api_key' trong server_config.json trước khi dùng API!")
        logger.critical("=" * 60)

    # Setup logging
    log_level = getattr(logging, _server_config.get("log_level", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s [%(name)s] %(message)s")

    logger.info("=" * 60)
    logger.info("🚀 Gemini Web → OpenAI-Compatible API Server")
    logger.info(f"   Port: {_server_config['port']}")
    logger.info(f"   Max Sessions: {_server_config['max_sessions']}")
    logger.info(f"   Default Model: {_server_config['default_model']}")
    logger.info(f"   Headless: {_server_config['headless']}")
    logger.info(f"   Guest Mode: {_server_config['guest_mode']}")
    logger.info("=" * 60)

    # Khởi tạo Session Manager
    _manager = SessionManager(
        max_sessions=_server_config["max_sessions"],
        idle_timeout=_server_config["idle_timeout_seconds"],
        headless=_server_config["headless"],
        guest_mode=_server_config["guest_mode"],
    )
    await _manager.start()

    # Khởi tạo Watchdog
    _watchdog = BrowserWatchdog(_manager)
    await _watchdog.start()

    # Khởi tạo rate limiter
    _throttler = RequestThrottler(
        min_delay=_server_config["min_request_delay_seconds"],
        max_delay=_server_config["max_request_delay_seconds"],
    )

    logger.info("✓ Server sẵn sàng nhận request!")

    yield

    # Shutdown
    logger.info("→ Đang shutdown server...")
    if _watchdog:
        await _watchdog.stop()
    if _manager:
        await _manager.stop()
    logger.info("✓ Server đã shutdown sạch sẽ")


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="Gemini Web API (OpenAI-Compatible)",
    description="Proxy server biến Gemini Web thành OpenAI-compatible REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# [FIX C3] CORS — chỉ cho phép localhost, không dùng wildcard + credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# ============================================================
# Auth Dependency
# ============================================================

async def verify_api_key(request: Request):
    """Kiểm tra API key nếu được cấu hình."""
    expected_key = _server_config.get("api_key", "nokey")
    if expected_key == "nokey":
        return  # Bỏ qua auth

    # Debug: log all headers
    logger.info(f"DEBUG Headers: {dict(request.headers)}")

    # Thử Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if hmac.compare_digest(token.encode(), expected_key.encode()):
            return

    # Thử x-api-key header (Claude Code / many clients)
    api_key_header = request.headers.get("x-api-key", "")
    if api_key_header and hmac.compare_digest(api_key_header.encode(), expected_key.encode()):
        return

    # Thử Anthropic-Auth-Token header
    auth_token = request.headers.get("anthropic-auth-token", "")
    if auth_token and hmac.compare_digest(auth_token.encode(), expected_key.encode()):
        return

    # Debug: log failed key
    logger.warning(f"DEBUG Auth failed. Received keys - Authorization: {auth_header[:20]}..., x-api-key: {api_key_header[:20] if api_key_header else None}...")

    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "message": "Invalid API key",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        },
    )


# ============================================================
# POST /v1/chat/completions — Core Endpoint
# ============================================================

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(body: ChatCompletionRequest):
    """
    Chat completion endpoint — chuẩn OpenAI format.
    Hỗ trợ cả streaming (SSE) và non-streaming.
    """
    if not body.messages:
        return JSONResponse(
            status_code=400,
            content=build_error_response("messages cannot be empty", "invalid_request_error").model_dump(),
        )

    model = normalize_model_name(body.model or _server_config.get("default_model", "gemini-pro"))
    session_id = body.session_id or f"default_{model}"
    request_id = f"chatcmpl-gemini-{uuid.uuid4().hex[:12]}"

    try:
        # Lấy hoặc tạo session
        session = await _manager.get_or_create(session_id, model)

        if not session.is_ready:
            return JSONResponse(
                status_code=503,
                content=build_error_response(
                    "Session browser is not ready. Auto-recovery in progress.",
                    "server_error",
                    "browser_not_ready",
                ).model_dump(),
            )

        # Throttle — đảm bảo delay giữa các request
        await _throttler.wait_if_needed(session_id)

        # Chuyển model nếu cần
        model_result = await select_best_model(session.client, model, session.current_model)
        session.current_model = model_result.actual_model_normalized

        # Xác định session mới hay cũ
        is_new = session.message_count == 0

        # Convert messages → prompt
        prompt = convert_messages_to_prompt(body.messages, is_new_session=is_new)

        if not prompt:
            return JSONResponse(
                status_code=400,
                content=build_error_response("Could not extract prompt from messages", "invalid_request_error").model_dump(),
            )

        # Build metadata
        meta = GeminiMeta(
            requested_model=body.model,
            actual_model=model_result.actual_model,
            actual_model_normalized=model_result.actual_model_normalized,
            fallback=model_result.fallback,
            fallback_reason=model_result.fallback_reason,
            session_id=session_id,
        )

        if body.stream:
            return EventSourceResponse(
                _stream_response(session, prompt, model_result.actual_model_normalized, request_id, meta),
                media_type="text/event-stream",
            )

        # Non-streaming: gửi và chờ response hoàn chỉnh
        async with session.lock:
            response_text = await session.client.chat(prompt)

        session.message_count += 1
        session.touch()
        _throttler.record_request(session_id)

        if not response_text:
            return JSONResponse(
                status_code=500,
                content=build_error_response(
                    "No response received from Gemini. Browser may be unresponsive.",
                    "server_error",
                    "no_response",
                ).model_dump(),
            )

        result = build_completion_response(
            content=response_text,
            model=model_result.actual_model_normalized,
            request_id=request_id,
            meta=meta,
        )
        return JSONResponse(content=result.model_dump())

    except Exception as e:
        logger.error(f"✗ Chat completion error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content=build_error_response(
                f"Internal server error: {str(e)}",
                "server_error",
                "internal_error",
            ).model_dump(),
        )


# ============================================================
# Streaming Implementation
# ============================================================

async def _stream_response(
    session,
    prompt: str,
    model: str,
    request_id: str,
    meta: GeminiMeta,
) -> AsyncGenerator[dict, None]:
    """
    Generator cho SSE streaming response.
    Poll DOM mỗi 500ms và gửi delta (phần text mới).
    """
    prev_text_backup = ""
    try:
        async with session.lock:
            # Gửi tin nhắn
            ok = await session.client.send_message(prompt)
            if not ok:
                yield {
                    "data": json.dumps(build_error_response("Failed to send message").model_dump())
                }
                return

            # Chunk đầu tiên: role
            first_chunk = build_stream_chunk(request_id, model, role="assistant")
            yield {"data": first_chunk.model_dump_json()}

            # Poll response
            prev_text = session.client.last_bot_response or ""
            prev_text_backup = prev_text
            timeout = session.client.config.response_timeout
            start = time.time()
            stable_count = 0

            await asyncio.sleep(3)  # Chờ Gemini bắt đầu generate

            while time.time() - start < timeout:
                # [FIX D7] Yield execution point — cho phép CancelledError propagate khi client disconnect
                await asyncio.sleep(0)

                generating = await session.client._is_generating()
                current_text = await session.client._get_latest_response() or ""

                # Bỏ qua nếu text chưa thay đổi so với response cũ
                if current_text and current_text != prev_text and current_text != (session.client.last_bot_response or ""):
                    # Tính delta (phần text mới)
                    new_content = current_text
                    if prev_text and current_text.startswith(prev_text):
                        new_content = current_text[len(prev_text):]
                    elif prev_text == session.client.last_bot_response:
                        # Text hoàn toàn mới
                        new_content = current_text

                    if new_content:
                        chunk = build_stream_chunk(request_id, model, content=new_content)
                        yield {"data": chunk.model_dump_json()}

                    prev_text = current_text
                    stable_count = 0

                elif current_text == prev_text and current_text != "" and current_text != session.client.last_bot_response:
                    if not generating:
                        stable_count += 1
                        if stable_count >= 3:
                            # Response hoàn tất
                            break

                await asyncio.sleep(0.5)

            # Cập nhật state
            if prev_text and prev_text != session.client.last_bot_response:
                session.client.last_bot_response = prev_text.strip()

            session.message_count += 1
            session.touch()
            if _throttler:
                _throttler.record_request(meta.session_id)

            # [FIX M5] final_chunk và [DONE] nằm BÊN TRONG lock để tránh interleave
            final_chunk = build_stream_chunk(request_id, model, finish_reason="stop")
            yield {"data": final_chunk.model_dump_json()}
            yield {"data": "[DONE]"}

    except asyncio.CancelledError:
        # [FIX D7] Client disconnect — cập nhật state và giải phóng lock sạch sẽ
        logger.info(f"Client disconnected mid-stream, releasing session lock")
        if prev_text_backup and prev_text_backup != session.client.last_bot_response:
            session.client.last_bot_response = prev_text_backup
            if prev_text_backup:
                session.message_count += 1
                session.touch()
                if _throttler:
                    _throttler.record_request(meta.session_id)
        raise
    except Exception as e:
        logger.error(f"✗ Stream error: {e}", exc_info=True)
        yield {"data": json.dumps(build_error_response(f"Stream error: {str(e)}").model_dump())}


# ============================================================
# GET /v1/models — Model Listing
# ============================================================

@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    """Liệt kê tất cả models hỗ trợ."""
    models = get_all_supported_models()
    data = [
        ModelInfo(id=m["id"], owned_by="gemini-web").model_dump()
        for m in models
    ]
    return {"object": "list", "data": data}


# ============================================================
# GET /health — Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - _start_time
    return HealthResponse(
        status="ok",
        active_sessions=_manager.get_active_count() if _manager else 0,
        uptime_seconds=round(uptime, 1),
    ).model_dump()


# ============================================================
# GET /v1/sessions — Session Info (Bonus)
# ============================================================

@app.get("/v1/sessions", dependencies=[Depends(verify_api_key)])
async def list_sessions():
    """Xem trạng thái tất cả browser sessions."""
    if not _manager:
        return {"sessions": []}
    return {"sessions": _manager.get_all_sessions_info()}


# ============================================================
# Anthropic API Endpoints (for Claude Code compatibility)
# ============================================================

@app.post("/v1/messages", dependencies=[Depends(verify_api_key)])
async def anthropic_messages(request: Request):
    """
    Anthropic Messages API endpoint — tương thích với Claude Code.
    Format: https://docs.anthropic.com/en/docs/api-clients
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": {"type": "invalid_request_error", "message": "Invalid JSON body"}},
        )

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse(
            status_code=400,
            content={"error": {"type": "invalid_request_error", "message": "messages is required"}},
        )

    model = normalize_model_name(body.get("model") or _server_config.get("default_model", "gemini-pro"))
    session_id = body.get("model", "default")
    request_id = f"msg_{uuid.uuid4().hex[:12]}"
    system = body.get("system")
    stream = body.get("stream", False)

    try:
        session = await _manager.get_or_create(session_id, model)

        if not session.is_ready:
            return JSONResponse(
                status_code=503,
                content={"error": {"type": "server_error", "message": "Browser session not ready"}},
            )

        await _throttler.wait_if_needed(session_id)

        model_result = await select_best_model(session.client, model, session.current_model)
        session.current_model = model_result.actual_model_normalized

        is_new = session.message_count == 0

        # Convert Anthropic messages format to prompt
        from src.core.adapter import AnthropicMessage
        msgs = [AnthropicMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
        prompt = convert_anthropic_to_prompt(msgs, system, is_new_session=is_new)

        if not prompt:
            return JSONResponse(
                status_code=400,
                content={"error": {"type": "invalid_request_error", "message": "Could not extract prompt from messages"}},
            )

        if stream:
            return EventSourceResponse(
                _stream_anthropic_response(session, prompt, model_result.actual_model_normalized, request_id, session_id),
                media_type="text/event-stream",
            )

        async with session.lock:
            response_text = await session.client.chat(prompt)

        session.message_count += 1
        session.touch()
        _throttler.record_request(session_id)

        if not response_text:
            return JSONResponse(
                status_code=500,
                content={"error": {"type": "server_error", "message": "No response from Gemini"}},
            )

        result = build_anthropic_response(
            content=response_text,
            model=model_result.actual_model_normalized,
            message_id=request_id,
        )
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"✗ Anthropic messages error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"type": "server_error", "message": str(e)}},
        )


async def _stream_anthropic_response(
    session,
    prompt: str,
    model: str,
    request_id: str,
    session_id: str = "default",
) -> AsyncGenerator[str, None]:
    """Generator cho Anthropic-style SSE streaming."""
    import json

    prev_text_backup = ""
    try:
        async with session.lock:
            ok = await session.client.send_message(prompt)
            if not ok:
                yield f"data: {json.dumps({'type': 'error', 'error': {'type': 'server_error', 'message': 'Failed to send message'}})}\n\n"
                return

            msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            msg_data = {'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}}
            yield f"data: {json.dumps(msg_data)}\n\n"

            prev_text = session.client.last_bot_response or ""
            prev_text_backup = prev_text
            timeout = session.client.config.response_timeout
            start = time.time()
            stable_count = 0

            await asyncio.sleep(3)

            while time.time() - start < timeout:
                await asyncio.sleep(0)

                generating = await session.client._is_generating()
                current_text = await session.client._get_latest_response() or ""

                if current_text and current_text != prev_text and current_text != (session.client.last_bot_response or ""):
                    new_content = current_text
                    if prev_text and current_text.startswith(prev_text):
                        new_content = current_text[len(prev_text):]
                    elif prev_text == session.client.last_bot_response:
                        new_content = current_text

                    if new_content:
                        yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': new_content}, 'usage': {'output_tokens': 1}})}\n\n"

                    prev_text = current_text
                    stable_count = 0

                elif current_text == prev_text and current_text != "" and current_text != session.client.last_bot_response:
                    if not generating:
                        stable_count += 1
                        if stable_count >= 3:
                            break

                await asyncio.sleep(0.5)

            if prev_text and prev_text != session.client.last_bot_response:
                session.client.last_bot_response = prev_text.strip()

            session.message_count += 1
            session.touch()
            if _throttler:
                _throttler.record_request(session_id)

            yield f"data: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 0}})}\n\n"
            yield f"data: {json.dumps({'type': 'message_stop'})}\n\n"
            yield "data: [DONE]\n\n"

    except asyncio.CancelledError:
        logger.info("Client disconnected mid-stream (Anthropic)")
        if prev_text_backup and prev_text_backup != session.client.last_bot_response:
            session.client.last_bot_response = prev_text_backup
            if prev_text_backup:
                session.message_count += 1
                session.touch()
                if _throttler:
                    _throttler.record_request(session_id)
        raise
    except Exception as e:
        logger.error(f"✗ Anthropic stream error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': {'type': 'server_error', 'message': str(e)}})}\n\n"


@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models_anthropic():
    """Liệt kê models theo format Anthropic."""
    models = get_all_supported_models()
    data = [
        {
            "id": m["id"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": "gemini-web",
        }
        for m in models
    ]
    return {"object": "list", "data": data}


# ============================================================
# Root — Redirect to docs
# ============================================================

@app.get("/")
async def root():
    return {
        "message": "Gemini Web API Server (OpenAI + Anthropic Compatible)",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "openai_chat": "POST /v1/chat/completions",
            "anthropic_chat": "POST /v1/messages",
            "models": "GET /v1/models",
            "sessions": "GET /v1/sessions",
        },
    }
