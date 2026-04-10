"""
Multi-Profile Session Manager — Quản lý pool các GeminiClient instances.

Mỗi session = 1 Chrome profile riêng = 1 session cô lập hoàn toàn.
Hỗ trợ:
- Tạo/tái sử dụng session theo session_id
- AsyncLock per session (serialize requests)
- Auto-cleanup sessions nhàn rỗi
- Giới hạn max sessions (tránh OOM)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from src.core.client import GeminiClient

logger = logging.getLogger("session_manager")


@dataclass
class ManagedSession:
    """Đại diện cho một browser session đang được quản lý."""
    session_id: str
    client: GeminiClient
    current_model: str = ""
    last_active: float = field(default_factory=time.time)
    message_count: int = 0
    is_ready: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self):
        """Cập nhật timestamp khi session được sử dụng."""
        self.last_active = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active


class SessionManager:
    """
    Quản lý pool các GeminiClient instances.
    Thread-safe qua asyncio.Lock per session.
    """

    def __init__(
        self,
        max_sessions: int = 3,
        idle_timeout: int = 300,
        headless: bool = True,
        guest_mode: bool = True,
    ):
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.headless = headless
        self.guest_mode = guest_mode
        self.sessions: dict[str, ManagedSession] = {}
        self._global_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Khởi động background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"✓ SessionManager started (max={self.max_sessions}, idle_timeout={self.idle_timeout}s)")

    async def stop(self):
        """Graceful shutdown toàn bộ sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("→ Đang đóng tất cả sessions...")
        for sid, session in list(self.sessions.items()):
            try:
                await session.client.close()
                logger.info(f"  ✓ Đã đóng session: {sid}")
            except Exception as e:
                logger.warning(f"  ⚠ Lỗi khi đóng session {sid}: {e}")
        self.sessions.clear()
        logger.info("✓ Tất cả sessions đã được đóng")

    async def get_or_create(self, session_id: str, model: str = "") -> ManagedSession:
        """
        Lấy session có sẵn hoặc tạo mới.
        Nếu đạt max_sessions, đóng session cũ nhất.
        """
        # [FIX M2+D1] Mọi truy cập dict sessions đều dưới lock để tránh race condition
        async with self._global_lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session.touch()
                return session

            # Kiểm tra giới hạn — evict session cũ nhất nếu đầy
            if len(self.sessions) >= self.max_sessions:
                await self._evict_oldest()

            # Tạo session mới
            session = await self._create_session(session_id, model)
            return session

    async def _create_session(self, session_id: str, model: str) -> ManagedSession:
        """Tạo một session mới với Chrome profile riêng biệt."""
        logger.info(f"→ Tạo session mới: {session_id} (model: {model or 'default'})")

        # Mỗi session dùng config riêng, profile riêng
        profile_name = f"api_{session_id}"

        client = GeminiClient(config_path="config.json", profile_name=profile_name)

        # Override một số settings cho API mode
        client.config._data["headless"] = self.headless
        client.config._data["guest_mode"] = self.guest_mode

        # Khởi tạo browser
        await client.start_browser()

        # Mở Gemini
        if not self.guest_mode:
            # Account mode — dựa vào cookie đã có trong profile
            if not await client.is_logged_in():
                logger.warning(f"⚠ Session {session_id}: Chưa đăng nhập. Hãy dùng CLI đăng nhập trước.")
        
        await client.open_gemini()

        session = ManagedSession(
            session_id=session_id,
            client=client,
            current_model=model,
            is_ready=True,
        )
        self.sessions[session_id] = session
        logger.info(f"✓ Session {session_id} đã sẵn sàng")
        return session

    async def _evict_oldest(self):
        """Đóng session ít active nhất để nhường chỗ."""
        if not self.sessions:
            return

        oldest_sid = min(self.sessions, key=lambda s: self.sessions[s].last_active)
        oldest = self.sessions[oldest_sid]
        logger.info(f"♻ Evict session cũ nhất: {oldest_sid} (idle {oldest.idle_seconds:.0f}s)")
        try:
            await oldest.client.close()
        except Exception:
            pass
        del self.sessions[oldest_sid]

    async def remove_session(self, session_id: str):
        """Đóng và xóa một session cụ thể."""
        session_to_close = None
        async with self._global_lock:
            if session_id in self.sessions:
                session_to_close = self.sessions.pop(session_id)
                logger.info(f"✓ Đã xóa session khỏi pool: {session_id}")
        
        if session_to_close:
            try:
                await session_to_close.client.close()
            except Exception:
                pass

    async def _cleanup_loop(self):
        """Background task: quét và đóng sessions nhàn rỗi."""
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                to_close = []
                # [FIX D1] Lock toàn bộ thao tác đọc/xóa sessions dict
                async with self._global_lock:
                    to_remove = [
                        sid for sid, session in self.sessions.items()
                        if now - session.last_active > self.idle_timeout
                    ]

                    for sid in to_remove:
                        logger.info(f"♻ Auto-cleanup idle session: {sid} (idle >{self.idle_timeout}s)")
                        session = self.sessions.pop(sid, None)
                        if session:
                            to_close.append(session)

                for session in to_close:
                    try:
                        await session.client.close()
                    except Exception:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚠ Lỗi trong cleanup loop: {e}")

    def get_active_count(self) -> int:
        return len(self.sessions)

    def get_all_sessions_info(self) -> list[dict]:
        """Trả về thông tin tất cả sessions (cho API endpoint)."""
        from datetime import datetime
        result = []
        # [FIX] Tránh RuntimeError: dictionary changed size during iteration khi asyncio yield
        session_list = list(self.sessions.items())
        for sid, session in session_list:
            result.append({
                "session_id": sid,
                "model": session.current_model,
                "is_ready": session.is_ready,
                "message_count": session.message_count,
                "idle_seconds": round(session.idle_seconds, 1),
                "last_active_iso": datetime.fromtimestamp(session.last_active).isoformat(),
            })
        return result
