"""
Gemini Web Client - Anti-Detection Browser Automation
Giao tiếp với Google Gemini qua giao diện web mà không cần API key.
Sử dụng nodriver để tránh bị phát hiện là bot.
"""

import asyncio
import json
import os
import random
import time
import logging
import re
import atexit
from datetime import datetime
from pathlib import Path

try:
    import nodriver as uc
except ImportError:
    print("[!] Thiếu thư viện nodriver. Cài đặt bằng: pip install nodriver")
    exit(1)

logger = logging.getLogger("gemini_client")

class BrowserStartError(Exception):
    pass



# ============================================================
# Configuration
# ============================================================

class Config:
    """Quản lý cấu hình từ file config.json"""

    def __init__(self, config_path="config.json", profile_name="default"):
        self.config_path = config_path
        self.profile_name = profile_name

        self.DEFAULTS = {
            "save_chat_history": False,
            "chat_history_file": f"chat_history_{profile_name}.json" if profile_name != "default" else "chat_history.json",
            "chrome_profile_dir": f"./chrome_profile_{profile_name}" if profile_name != "default" else "./chrome_profile",
            "headless": False,
            "typing_speed_min": 0.03,
            "typing_speed_max": 0.12,
            "action_delay_min": 1.0,
            "action_delay_max": 3.0,
            "response_timeout": 120,
            "language": "vi-VN",
            "selected_model": "Nhanh",
            "guest_mode": False,
            "last_chat_url": "",
            "use_edge": True,
        }

        self._data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        needs_save = False
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Xóa dấu phẩy thừa ở cuối (trailing commas) hay gây lỗi parse
                content = re.sub(r',\s*([\]}])', r'\1', content)
                user_cfg = json.loads(content)
                
                # Cập nhật _data từ user_cfg
                for k, v in user_cfg.items():
                    self._data[k] = v
                
                # Kiểm tra nếu thiếu bất kỳ cấu hình mặc định nào thì sẽ tiến hành bổ sung
                for k in self.DEFAULTS:
                    if k not in user_cfg:
                        needs_save = True
                        
            except Exception as e:
                logger.error(f"⚠ Lỗi đọc file config {self.config_path}: {e}")
                logger.info("→ File config.json lỗi cấu trúc nghiêm trọng. Tự động sửa lỗi và khôi phục!")
                needs_save = True
        else:
            needs_save = True

        # Ghi lại file json nếu nó bị hỏng hoặc thiếu key
        if needs_save:
            self._save()

    def _save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)

    def __getattr__(self, name):
        # [FIX M4] An toàn hơn: dùng super().__getattribute__ để lấy _data, tránh RecursionError
        if name.startswith("_") or name in ("config_path", "profile_name", "DEFAULTS"):
            return super().__getattribute__(name)
        try:
            data = super().__getattribute__("_data")
            return data[name]
        except (AttributeError, KeyError):
            raise AttributeError(f"Config has no attribute '{name}'")
            
    @property
    def last_chat_url(self) -> str:
        return self._data.get("last_chat_url", "")


# ============================================================
# Human‑Like Behaviour Simulator
# ============================================================

class HumanSimulator:
    """Giả lập hành vi người dùng để tránh bị phát hiện bot."""

    def __init__(self, config: Config, api_mode: bool = False):
        self.cfg = config
        self.api_mode = api_mode

    async def random_delay(self, min_s=None, max_s=None):
        lo = min_s if min_s is not None else self.cfg.action_delay_min
        hi = max_s if max_s is not None else self.cfg.action_delay_max
        if self.api_mode:
            # API mode: giảm delay xuống 30-50% để tăng tốc
            lo = lo * 0.3
            hi = hi * 0.5
        await asyncio.sleep(random.uniform(lo, hi))

    async def human_type(self, element, text: str):
        """Gõ từng ký tự với tốc độ ngẫu nhiên như người thật."""
        if self.api_mode:
            # API mode: paste trực tiếp (nhanh hơn 10x)
            # Vẫn giữ delay nhỏ để trông tự nhiên
            await element.send_keys(text)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            return

        for i, ch in enumerate(text):
            await element.send_keys(ch)
            delay = random.uniform(self.cfg.typing_speed_min, self.cfg.typing_speed_max)
            await asyncio.sleep(delay)
            # Đôi khi dừng lâu hơn (giả lập suy nghĩ)
            if random.random() < 0.04:
                await asyncio.sleep(random.uniform(0.25, 0.7))


# ============================================================
# Gemini Client
# ============================================================

class GeminiClient:
    """
    Client chính – khởi tạo browser, đăng nhập Google,
    truy cập Gemini và giao tiếp qua chat.
    """

    GEMINI_URL = "https://gemini.google.com/app"
    LOGIN_URL = "https://accounts.google.com/signin"
    ACCOUNT_URL = "https://myaccount.google.com/"

    def __init__(self, config_path="config.json", profile_name="default"):
        self.config = Config(config_path, profile_name)
        self.human = HumanSimulator(self.config)
        self.browser = None
        self.page = None
        self.logged_in = False
        self.chat_history: list[dict] = []
        self._msg_count = 0
        
        # [FIX] Thêm biến lưu câu trả lời gần nhất để so sánh
        self.last_bot_response = ""

    # ----------------------------------------------------------
    # Browser lifecycle & Window management
    # ----------------------------------------------------------

    async def _prevent_minimize_loop(self):
        """Background task: tự động phát hiện và chặn minimize trình duyệt sau 2 giây."""
        await asyncio.sleep(2)
        import nodriver.cdp.browser as cdp_browser
        while self.browser and self.browser.connection:
            try:
                if not getattr(self.browser, 'main_tab', None):
                    await asyncio.sleep(1)
                    continue
                target_id = self.browser.main_tab.target.target_id
                res = await self.browser.connection.send(cdp_browser.get_window_for_target(target_id=target_id))
                if res and isinstance(res, tuple) and len(res) > 0:
                    window_id = res[0]
                    bounds = await self.browser.connection.send(cdp_browser.get_window_bounds(window_id=window_id))
                    if bounds.window_state == cdp_browser.WindowState.MINIMIZED:
                        new_bounds = cdp_browser.Bounds(window_state=cdp_browser.WindowState.NORMAL)
                        await self.browser.connection.send(cdp_browser.set_window_bounds(window_id=window_id, bounds=new_bounds))
            except Exception:
                pass
            await asyncio.sleep(1)


    async def start_browser(self):
        """Khởi tạo browser với anti‑detection settings."""
        profile = os.path.abspath(self.config.chrome_profile_dir)
        os.makedirs(profile, exist_ok=True)

        try:
            b_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-popup-blocking",
                f"--lang={self.config.language}",
                "--disable-extensions",
            ]
            
            uc_headless = False
            if self.config.headless:
                # Phương pháp "Pseudo-Headless": Mở cửa sổ thật nhưng ném ra ngoài màn hình (-32000, -32000)
                # Render DOM chính xác 100% như người dùng thật, không bị dính các lỗi ẩn UI của Headless thật
                b_args.extend([
                    "--window-position=-32000,-32000",
                    "--window-size=1920,1080",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding"
                ])
            else:
                # [FIX] Ép Chrome mở lại ở toạ độ bình thường hiển thị được trên màn hình
                # Ngăn tình trạng Chrome "nhớ" toạ độ ngoài màn hình từ lần chạy headless trước
                b_args.extend([
                    "--window-position=50,50",
                    "--window-size=1920,1080"
                ])

            if self.config.guest_mode:
                b_args.append("--guest")

            edge_path = None
            if getattr(self.config, "use_edge", True):
                paths = [
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
                ]
                for p in paths:
                    if os.path.exists(p):
                        edge_path = p
                        break
                if edge_path:
                    logger.info(f"→ Sử dụng trình duyệt Edge: {edge_path}")

            self.browser = await uc.start(
                user_data_dir=None if self.config.guest_mode else profile,
                headless=uc_headless,
                browser_executable_path=edge_path,
                browser_args=b_args,
            )
            
            # Bắt đầu vòng lặp tự động chặn minimize sau khi khởi động
            asyncio.create_task(self._prevent_minimize_loop())
            
            # [FIX D8] Chỉ đăng ký atexit handler một lần duy nhất
            if not hasattr(self, '_atexit_registered'):
                atexit.register(self.stop_sync)
                self._atexit_registered = True
            logger.info("✓ Browser đã khởi động")
        except Exception as e:
            if "Failed to connect to browser" in str(e) or "WinError 1225" in str(e) or "ConnectionRefused" in str(e):
                logger.error("=" * 60)
                logger.error("✗ LỖI: KHÔNG THỂ KẾT NỐI VỚI TRÌNH DUYỆT HOẶC BỊ KHÓA")
                logger.error("  Nguyên nhân thường gặp:")
                logger.error(f"  1. Bạn đang mở nhiều client nhưng quên tách profile.")
                logger.error("     → Tham số đúng: python main.py -p <ten_profile> (Vd: -p account2)")
                logger.error(f"  2. Thư mục profile '{profile}' đang bị khóa do Chrome cũ chưa đóng hết.")
                logger.error("     → Giải pháp: Hãy mở Task Manager và END TASK tất cả các tiến trình Chrome đang chạy ngầm.")
                logger.error("  3. Thừa hưởng cấu hình sai từ file config cũ.")
                logger.error(f"     → Thường gặp khi bạn copy file json nhưng không đổi đường dẫn chrome_profile_dir.")
                logger.error("=" * 60)
                raise BrowserStartError("Lỗi kết nối trình duyệt do bị khóa hoặc trùng profile.")
            raise

    def stop_sync(self):
        """Đóng trình duyệt đồng bộ để dùng cho atexit hoặc console close."""
        if self.browser:
            try:
                self.browser.stop()
            except Exception:
                pass
            self.browser = None

    async def close(self):
        """Đóng browser."""
        self.stop_sync()
        logger.info("✓ Browser đã đóng")

    async def ensure_browser_alive(self) -> bool:
        """Kiểm tra và tự khởi động lại trình duyệt nếu đã bị đóng/crash."""
        alive = False
        if self.browser and getattr(self, 'page', None):
            try:
                # Dùng wait_for để tránh treo nếu websocket unresponsive
                res = await asyncio.wait_for(self.page.evaluate("1+1"), timeout=2.0)
                if res == 2:
                    alive = True
            except Exception:
                pass

        if not alive:
            logger.warning("\n⚠ Phát hiện trình duyệt đã bị tắt hoặc mất kết nối.")
            logger.info("→ Đang tự động dọn dẹp và khởi động lại trình duyệt...")
            self.stop_sync()
            try:
                await self.start_browser()
                await self.open_gemini()
                return True
            except Exception as e:
                logger.error(f"✗ Lỗi khi nỗ lực khởi động lại: {e}")
                return False
        return True

    # ----------------------------------------------------------
    # Google Login
    # ----------------------------------------------------------

    async def is_logged_in(self) -> bool:
        """Kiểm tra đã đăng nhập Google chưa (qua cookies/profile)."""
        try:
            tab = await self.browser.get(self.ACCOUNT_URL)
            await asyncio.sleep(3)
            url = tab.url or ""
            # Nếu bị đẩy ra trang accounts (đăng nhập) hoặc trang giới thiệu intro -> Chưa đăng nhập
            if "accounts.google.com" in url or "/intro" in url or "signin" in url:
                return False
            # Nếu về được trang quản lý myaccount thực sự -> Đã có tài khoản
            if "myaccount.google.com" in url:
                return True
            return False
        except Exception:
            return False

    async def minimize_window(self):
        """Thu nhỏ cửa sổ trình duyệt (minimize) thông qua CDP."""
        if not self.browser:
            return
        try:
            import nodriver.cdp.browser as cdp_browser
            target_id = self.browser.main_tab.target.target_id
            res = await self.browser.connection.send(cdp_browser.get_window_for_target(target_id=target_id))
            window_id = res[0]
            bounds = cdp_browser.Bounds(window_state=cdp_browser.WindowState.MINIMIZED)
            await self.browser.connection.send(cdp_browser.set_window_bounds(window_id=window_id, bounds=bounds))
            logger.info("✓ Trình duyệt đã được ẩn (minimized)")
        except Exception as e:
            logger.warning(f"⚠ Không thể thu nhỏ trình duyệt: {e}")

    # ----------------------------------------------------------
    # Google Login
    # ----------------------------------------------------------

    async def login_google(self, email: str, password: str) -> bool:
        """
        Đăng nhập Google account.
        Hỗ trợ 2FA – sẽ tạm dừng để người dùng hoàn tất xác thực.
        """
        # Kiểm tra đã đăng nhập từ profile cũ chưa
        if await self.is_logged_in():
            self.logged_in = True
            logger.info("✓ Đã đăng nhập sẵn từ phiên trước!")
            return True

        logger.info("→ Mở trang đăng nhập Google…")
        self.page = await self.browser.get(self.LOGIN_URL)
        await self.human.random_delay(2, 4)

        # --- Bước 1: Nhập email ---
        logger.info("→ Nhập email…")
        try:
            email_input = await self.page.select('input[type="email"]')
            if not email_input:
                email_input = await self.page.find("Email or phone", best_match=True)
            await self.human.random_delay(0.5, 1.2)
            await self.human.human_type(email_input, email)
            await self.human.random_delay(0.4, 0.9)

            # Nhấn Next
            try:
                next_btn = await self.page.find("Next", best_match=True)
                await next_btn.click()
            except Exception:
                await email_input.send_keys("\r")
            await self.human.random_delay(2, 4)
        except Exception as e:
            logger.error(f"✗ Không nhập được email: {e}")
            return False

        # --- Bước 2: Nhập mật khẩu ---
        logger.info("→ Nhập mật khẩu…")
        try:
            await self.human.random_delay(1, 2)
            pw_input = await self.page.select('input[type="password"]')
            if not pw_input:
                pw_input = await self.page.find("Enter your password", best_match=True)
            await self.human.random_delay(0.5, 1.2)
            await self.human.human_type(pw_input, password)
            await self.human.random_delay(0.4, 0.9)

            try:
                next_btn = await self.page.find("Next", best_match=True)
                await next_btn.click()
            except Exception:
                await pw_input.send_keys("\r")
            await self.human.random_delay(3, 5)
        except Exception as e:
            logger.error(f"✗ Không nhập được mật khẩu: {e}")
            return False

        # --- Bước 3: Xử lý 2FA ---
        cur_url = self.page.url or ""
        needs_2fa = any(kw in cur_url for kw in ("challenge", "signin/v2", "interstitial"))
        if needs_2fa:
            logger.info("=" * 55)
            logger.info("⚠  PHÁT HIỆN XÁC THỰC 2 BƯỚC (2FA)")
            logger.info("   Vui lòng hoàn tất xác thực trên trình duyệt.")
            logger.info("   Đang chờ tối đa 120 giây…")
            logger.info("=" * 55)

            for _ in range(120):
                await asyncio.sleep(1)
                cur_url = self.page.url or ""
                if "accounts.google.com" not in cur_url:
                    break
                if "myaccount" in cur_url:
                    break

        # --- Xác minh kết quả ---
        self.logged_in = await self.is_logged_in()
        if self.logged_in:
            logger.info("✓ Đăng nhập thành công!")
        else:
            logger.warning("⚠ Đăng nhập có thể chưa thành công. Kiểm tra trình duyệt.")
        return self.logged_in

    # ----------------------------------------------------------
    # Gemini Navigation
    # ----------------------------------------------------------

    async def open_gemini(self) -> bool:
        """Mở giao diện chat Gemini và chờ sẵn sàng."""
        target_url = self.config.last_chat_url
        if self.config.guest_mode:
            target_url = "https://gemini.google.com/app"
            logger.info("→ Mở Gemini (Chế độ Khách / Guest Mode)…")
        else:
            if not target_url or "gemini.google.com/app" not in target_url:
                target_url = self.GEMINI_URL
            logger.info(f"→ Mở Gemini ({'Phiên cũ' if len(target_url) > len(self.GEMINI_URL) else 'Mới'})…")

        self.page = await self.browser.get(target_url)
        await self.human.random_delay(3, 5)

        # Chờ giao diện chat load xong
        ready = False
        for attempt in range(15):
            inp = await self._find_input_area()
            if inp:
                ready = True
                break
            await asyncio.sleep(2)

        if ready:
            logger.info("✓ Giao diện Gemini đã sẵn sàng!")
            # Tự động chọn model nếu đã lưu trong config
            saved_model = self.config._data.get("selected_model", "")
            if saved_model:
                logger.info(f"→ Đang áp dụng model đã lưu: {saved_model}...")
                ok = await self.select_model(saved_model)
                if ok:
                    logger.info(f"✓ Đã chọn model: {saved_model}")
                else:
                    logger.warning(f"⚠ Không thể chọn model '{saved_model}'.")
        else:
            logger.warning("⚠ Không xác định được ô nhập liệu, có thể vẫn hoạt động.")
        return ready

    # ----------------------------------------------------------
    # Model Selection Strategy (UI-based)
    # ----------------------------------------------------------

    _JS_OPEN_MODEL_MENU = """
    (() => {
        const buttons = Array.from(document.querySelectorAll('button, [role="button"], [role="combobox"]'));
        for (let b of buttons) {
            // Bỏ qua các nút đã bị vô hiệu hóa
            if (b.disabled || b.getAttribute('aria-disabled') === 'true' || b.classList.contains('disabled')) {
                continue;
            }
            
            // [FIX CỐT LÕI] Bỏ qua các "badge" ghi tên model nằm lẫn trong nội dung chat cũ
            if (b.closest('model-response') || b.closest('message-content') || b.closest('.message-content') || b.closest('.chat-history')) {
                continue;
            }

            const txt = (b.innerText || "").toLowerCase().trim();
            const ariaLabel = (b.getAttribute('aria-label') || "").toLowerCase();
            const tooltip = (b.getAttribute('mattooltip') || "").toLowerCase();
            
            // Nút thường chứa keywords ở text, aria-label hoặc tooltip
            const isModelBtn = txt.includes('gemini') || txt.includes('pro') || txt.includes('ultra') || 
                               txt.includes('nhanh') || txt.includes('tư duy') || txt.includes('flash') ||
                               txt.includes('fast') || txt.includes('thinking') || txt.includes('advanced') || txt.includes('basic') ||
                               ariaLabel.includes('kiểu máy') || ariaLabel.includes('model') || 
                               tooltip.includes('kiểu máy') || tooltip.includes('model');
            
            // [FIX] Nút mở Model phải có đặc tính dropdown (chứa svg mũi tên hoặc có popup menu)
            const isDropdown = b.hasAttribute('aria-haspopup') || b.hasAttribute('aria-expanded') || b.querySelector('svg');
                               
            if (isModelBtn && isDropdown && txt.length < 50) {
                if (b.getAttribute('aria-expanded') !== 'true') {
                    b.click();
                }
                return true; 
            }
        }
        return false;
    })()
    """

    _JS_GET_MODELS_FROM_MENU = """
    (() => {
        // Cập nhật selector chuẩn xác để hốt gọn danh sách trong Material UI mới
        const items = Array.from(document.querySelectorAll('mat-menu-item, gmat-menu-item, [role="menuitem"], [role="option"], [role="menuitemradio"]'));
        const models = [];
        for (let el of items) {
            let name = el.innerText.trim();
            if (name) {
                // Lấy dòng đầu tiên để hiển thị gọn nếu list chứa nhiều dòng mô tả con (VD: Pro\\nGiải toán...)
                let main_name = name.split('\\n')[0].trim();
                if (main_name.length > 0 && main_name.length < 50 && !models.includes(main_name)) {
                    models.push(main_name);
                }
            }
        }
        return models;
    })()
    """

    async def get_available_models(self) -> list[str]:
        """Lấy danh sách các model đang có trên giao diện web."""
        logger.info("→ Đang tìm kiếm các model khả dụng...")
        has_menu = await self.page.evaluate(self._JS_OPEN_MODEL_MENU)
        if not has_menu:
            logger.warning("⚠ Không tìm thấy menu chọn model trên giao diện. Có thể giao diện web đang phản hồi chậm.")
            return []

        await self.human.random_delay(0.5, 1.0) # wait for menu to expand
        raw_models = await self.page.evaluate(self._JS_GET_MODELS_FROM_MENU)
        models = []
        if raw_models:
            for item in raw_models:
                # Bóc tách object do nodriver serialize từ CDP
                val = item.get('value', item) if isinstance(item, dict) else item
                # Lọc bỏ nút "Nâng cấp" hay "Upgrade" chen vào danh sách
                if isinstance(val, str) and "nâng cấp" not in val.lower() and "upgrade" not in val.lower():
                    models.append(val)
        
        # Đóng menu lại 
        await self.page.evaluate("document.body.click();")
        await self.human.random_delay(0.2, 0.4)
        return models

    async def select_model(self, model_name: str) -> bool:
        """Chọn model trên UI bằng cách click vào menu item khớp tên."""
        has_menu = await self.page.evaluate(self._JS_OPEN_MODEL_MENU)
        if not has_menu:
            logger.warning("⚠ Không thể mở danh sách Model.")
            return False

        await self.human.random_delay(0.4, 0.8)
        
        # [FIX C1] Sanitize model_name bằng json.dumps() để chống JS Injection
        safe_name = json.dumps(model_name)
        
        JS_CLICK_MODEL = f"""
        (() => {{
            const targetName = {safe_name};
            const items = Array.from(document.querySelectorAll('mat-menu-item, gmat-menu-item, [role="menuitem"], [role="option"], [role="menuitemradio"]'));
            for (let el of items) {{
                if (el.innerText.trim().includes(targetName)) {{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        clicked = await self.page.evaluate(JS_CLICK_MODEL)
        if not clicked:
            # Fallback đóng menu nếu tìm không thấy
            await self.page.evaluate("document.body.click();")
            return False

        await self.human.random_delay(0.5, 1.0)
        return True

    # ----------------------------------------------------------
    # Element Finders (đa chiến lược để tránh lỗi selector)
    # ----------------------------------------------------------

    async def _find_input_area(self):
        """Tìm ô nhập tin nhắn bằng nhiều chiến lược."""
        combined_sel = 'div.ql-editor[contenteditable="true"], .ql-editor, rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"][aria-label], div[contenteditable="true"], textarea'
        try:
            el = await self.page.select(combined_sel, timeout=2)
            if el:
                return el
        except Exception:
            pass

        # Fallback bằng text
        text_hints = ["Enter a prompt", "Nhập câu lệnh", "Nhập nội dung"]
        for hint in text_hints:
            try:
                el = await self.page.find(hint, best_match=True)
                if el:
                    return el
            except Exception:
                continue
        return None

    async def _find_send_button(self):
        """Tìm nút gửi tin nhắn."""
        css_selectors = [
            'button[aria-label*="Send"]',
            'button[aria-label*="send"]',
            'button[aria-label*="Gửi"]',
            'button[aria-label*="gửi"]',
            'button[mattooltip*="Send"]',
            'button.send-button',
            'button[data-at="send"]',
        ]
        for sel in css_selectors:
            try:
                el = await self.page.select(sel, timeout=2)
                if el:
                    return el
            except Exception:
                continue

        # Fallback: tìm bằng text
        for label in ("Send message", "Send", "Gửi"):
            try:
                el = await self.page.find(label, best_match=True)
                if el:
                    return el
            except Exception:
                continue
        return None

    # ----------------------------------------------------------
    # Response detection via JS (đáng tin cậy hơn CSS selectors)
    # ----------------------------------------------------------

    _JS_GET_RESPONSE = """
    (() => {
        function extractText(el) {
            if (!el) return null;
            let txt = el.innerText || "";
            if (txt.trim() === "") txt = el.textContent || "";
            return txt.trim();
        }

        // Strategy 1: model-response component (Angular)
        const modelResp = document.querySelectorAll(
            'model-response .model-response-text, model-response message-content'
        );
        if (modelResp.length) return extractText(modelResp[modelResp.length - 1]);

        // Strategy 2: markdown panels
        const md = document.querySelectorAll(
            '.response-container-content .markdown, .markdown-main-panel'
        );
        if (md.length) return extractText(md[md.length - 1]);

        // Strategy 3: generic message content
        const msgs = document.querySelectorAll(
            'message-content, .message-content'
        );
        // Lấy phần tử cuối cùng thuộc model (không phải user)
        for (let i = msgs.length - 1; i >= 0; i--) {
            const parent = msgs[i].closest('model-response, .model-response, [class*="model"]');
            if (parent) return extractText(msgs[i]);
        }
        if (msgs.length >= 2) return extractText(msgs[msgs.length - 1]);

        // Strategy 4: broadest fallback
        const all = document.querySelectorAll('[class*="response-content"], [class*="bot-message"]');
        if (all.length) return extractText(all[all.length - 1]);

        return null;
    })()
    """

    _JS_IS_GENERATING = """
    (() => {
        // [FIX] Sử dụng getBoundingClientRect để kiểm tra hiển thị chính xác 100% trong Headless
        function isVisible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            // Nếu chiều dài hoặc rộng = 0 tức là nó đang tàng hình (bị ẩn)
            if (rect.width === 0 || rect.height === 0) return false;
            
            const style = window.getComputedStyle(el);
            if (style.opacity === '0' || parseFloat(style.opacity) === 0) return false;
            return style.display !== 'none' && style.visibility !== 'hidden';
        }

        const stop = document.querySelector(
            'button[aria-label*="Stop"], button[aria-label*="stop"], '
          + 'button[aria-label*="Dừng"], [mattooltip*="Stop"]'
        );
        if (isVisible(stop)) return true;

        const prog = document.querySelector(
            'mat-progress-bar, [role="progressbar"], .loading-indicator'
        );
        if (isVisible(prog)) return true;

        const cursor = document.querySelector('.blinking-cursor, .cursor-blink');
        if (isVisible(cursor)) return true;

        return false;
    })()
    """

    async def _is_generating(self) -> bool:
        try:
            return bool(await self.page.evaluate(self._JS_IS_GENERATING))
        except Exception:
            return False

    async def _get_latest_response(self) -> str | None:
        try:
            result = await self.page.evaluate(self._JS_GET_RESPONSE)
            return result if result else None
        except Exception:
            return None

    # ----------------------------------------------------------
    # Chat
    # ----------------------------------------------------------

    async def send_message(self, message: str) -> bool:
        """Gửi tin nhắn đến Gemini (giữ nguyên session hội thoại)."""
        input_area = await self._find_input_area()
        if not input_area:
            logger.error("✗ Không tìm thấy ô nhập liệu!")
            return False

        # Focus vào ô nhập
        await input_area.click()
        await self.human.random_delay(0.2, 0.6)

        # Xóa nội dung cũ (nếu có)
        try:
            await self.page.evaluate("""
                (() => {
                    const el = document.querySelector(
                        '.ql-editor, div[contenteditable="true"][role="textbox"], div[contenteditable="true"]'
                    );
                    if (el) {
                        el.innerHTML = '<p><br></p>';
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                })()
            """)
        except Exception:
            pass

        # Dán (Paste) tin nhắn siêu tốc
        await input_area.send_keys(message)
        await asyncio.sleep(1.0)
        
        # Khều nhẹ DOM để Angular mở khoá nút Gửi (Đặc trị cho Headless)
        try:
            await self.page.evaluate("""
                (() => {
                    const el = document.querySelector('.ql-editor, div[contenteditable="true"]');
                    if(el) el.dispatchEvent(new Event('input', {bubbles: true}));
                })()
            """)
        except Exception:
            pass
            
        await asyncio.sleep(0.5)

        # Nhấn gửi
        logger.info("→ Gửi tin nhắn…")
        
        # [FIX] Trong Headless, UI element có thể bị che khuất nên hàm click() vật lý hay xịt.
        # Ép Submit bằng Javascript là cách an toàn nhất!
        js_click = """
        (() => {
            const btns = document.querySelectorAll(
                'button[aria-label*="Send"], button[aria-label*="send"], ' +
                'button[aria-label*="Gửi"], button.send-button, [mattooltip*="Send"]'
            );
            for (let b of btns) {
                if (!b.disabled) {
                    b.click();
                    return true;
                }
            }
            return false;
        })()
        """
        clicked = await self.page.evaluate(js_click)
        
        if not clicked:
            send_btn = await self._find_send_button()
            if send_btn:
                try:
                    await send_btn.click()
                except Exception:
                    await input_area.send_keys("\n")
            else:
                await input_area.send_keys("\r")

        self._msg_count += 1
        return True

    async def wait_response(self, timeout: int | None = None) -> str | None:
        """Chờ Gemini trả lời và trích xuất nội dung."""
        timeout = timeout or self.config.response_timeout
        logger.info("⏳ Đang chờ Gemini phản hồi…")

        # Chờ khởi tạo response dài hơn 1 chút để UI Headless kịp phản ứng
        await asyncio.sleep(3)

        start = time.time()
        prev_text = ""
        stable = 0
        long_stable = 0  # [FIX] Theo dõi text đứng im dù UI vẫn báo generating
        retry_clicked = False # Cờ theo dõi việc bấm Gửi lại

        while time.time() - start < timeout:
            generating = await self._is_generating()
            text = await self._get_latest_response()

            if text:
                # [FIX QUAN TRỌNG] Bỏ qua câu trả lời nếu nó khớp y hệt câu trước đó.
                if text == self.last_bot_response and text != "":
                    if not generating:
                        elapsed = time.time() - start
                        # Cứu hộ: Nút gửi có thể bị tịt trong chế độ Headless
                        if elapsed > 15 and not retry_clicked:
                            logger.warning("⚠ Chờ quá lâu không có phản hồi mới, có thể kẹt nút Gửi. Đang ép gửi lại...")
                            await self.page.evaluate("""
                                const b = document.querySelector('button[aria-label*="Send"], button[aria-label*="Gửi"]');
                                if(b && !b.disabled) b.click();
                            """)
                            retry_clicked = True
                            await asyncio.sleep(3)
                        elif elapsed > 35:
                            logger.error("✗ Đã ép gửi lại nhưng vẫn không nhận được phản hồi.")
                            return None
                            
                    await asyncio.sleep(1)
                    continue

                if text == prev_text:
                    if not generating:
                        stable += 1
                        if stable >= 3:
                            logger.info("✓ Đã nhận phản hồi!")
                            self.last_bot_response = text.strip() # Cập nhật lại câu trả lời cuối cùng
                            return text.strip()
                    else:
                        # [FIX] Fallback: Nếu UI báo 'generating' nhưng text đã ngừng thay đổi suốt 15 giây
                        long_stable += 1
                        if long_stable >= 15:
                            logger.info("✓ Phản hồi đã hoàn tất (bỏ qua cờ load ảo)!")
                            self.last_bot_response = text.strip()
                            return text.strip()
                else:
                    stable = 0
                    long_stable = 0
                    prev_text = text

            await asyncio.sleep(1)

        if prev_text and prev_text != self.last_bot_response:
            logger.warning("⚠ Hết thời gian chờ, trả về phản hồi chưa hoàn chỉnh.")
            self.last_bot_response = prev_text.strip()
            return prev_text.strip()

        logger.error("✗ Không nhận được phản hồi (Hết timeout hoặc lỗi DOM trong Headless).")
        return None

    async def chat(self, message: str) -> str | None:
        """
        Gửi tin nhắn và nhận phản hồi (giữ nguyên session hội thoại).
        Gemini sẽ nhớ toàn bộ ngữ cảnh trong cùng 1 cuộc trò chuyện.
        """
        ok = await self.send_message(message)
        if not ok:
            return None

        response = await self.wait_response()

        try:
            if not self.config.guest_mode:
                current_url = await self.page.evaluate("window.location.href")
                if current_url and "gemini.google.com/app/" in current_url:
                    if current_url != self.config._data.get("last_chat_url", ""):
                        self.config._data["last_chat_url"] = current_url
                        self.config._save()
        except Exception:
            pass

        # Lưu lịch sử nếu bật
        if self.config.save_chat_history and response:
            self._save_history(message, response)

        return response

    # ----------------------------------------------------------
    # Chat history
    # ----------------------------------------------------------

    def _save_history(self, user_msg: str, ai_msg: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user": user_msg,
            "gemini": ai_msg,
        }
        self.chat_history.append(entry)

        # [FIX D5] Append-only JSONL: O(1) ghi thay vì O(n) đọc/ghi toàn bộ file
        hfile = self.config.chat_history_file
        try:
            with open(hfile, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"⚠ Không thể lưu lịch sử chat: {e}")