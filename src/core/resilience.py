"""
Resilience System — Watchdog, Auto-Recovery, Health Monitoring.

Đảm bảo API không bị "treo" khi:
- Browser crash / bị đóng đột ngột
- Chrome chiếm quá nhiều RAM
- WebSocket mất kết nối
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.session import SessionManager

logger = logging.getLogger("resilience")


class BrowserWatchdog:
    """
    Background task kiểm tra sức khỏe của tất cả browser sessions.
    Tự động restart session nếu phát hiện browser đã chết.
    """

    def __init__(
        self,
        manager: SessionManager,
        check_interval: float = 30.0,
    ):
        self.manager = manager
        self.check_interval = check_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Khởi động watchdog loop."""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"✓ BrowserWatchdog started (interval={self.check_interval}s)")

    async def stop(self):
        """Dừng watchdog."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("✓ BrowserWatchdog stopped")

    async def _watch_loop(self):
        """Vòng lặp chính: kiểm tra health cho tất cả sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)

                if not self.manager.sessions:
                    continue

                for sid, session in list(self.manager.sessions.items()):
                    if sid not in self.manager.sessions:
                        continue
                    try:
                        # [FIX D2] Acquire session lock trước khi health check
                        async with session.lock:
                            if sid not in self.manager.sessions:
                                continue
                            alive = await session.client.ensure_browser_alive()
                            if not alive:
                                logger.warning(f"⚠ Session {sid} browser died. Đánh dấu not ready.")
                                session.is_ready = False
                            else:
                                if not session.is_ready:
                                    session.is_ready = True
                                    logger.info(f"✓ Session {sid} recovered successfully")
                    except Exception as e:
                        logger.error(f"✗ Health check failed for session {sid}: {e}")
                        session.is_ready = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"✗ Watchdog loop error: {e}")


class RequestThrottler:
    """
    Rate limiter đơn giản cho mỗi session.
    Đảm bảo khoảng cách tối thiểu giữa các request để tránh bị Google block.
    """

    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request: dict[str, float] = {}  # session_id → timestamp
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait_if_needed(self, session_id: str):
        """Chờ nếu request gần nhất quá gần."""
        # [FIX D4] import đã được chuyển lên module level
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        async with self._locks[session_id]:
            now = time.time()
            last = self._last_request.get(session_id, 0)
            elapsed = now - last

            required_delay = random.uniform(self.min_delay, self.max_delay)

            if elapsed < required_delay:
                wait_time = required_delay - elapsed
                logger.debug(f"⏳ Throttle session {session_id}: chờ {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

            self._last_request[session_id] = time.time()

    def record_request(self, session_id: str):
        """Ghi nhận thời điểm request mới nhất."""
        self._last_request[session_id] = time.time()

    def remove_session(self, session_id: str):
        """Xóa session khỏi throttler để giải phóng bộ nhớ."""
        self._last_request.pop(session_id, None)
        self._locks.pop(session_id, None)
