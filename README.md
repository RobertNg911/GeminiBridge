# 🤖 Gemini Web Proxy — Web to OpenAI API Bridge

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![nodriver](https://img.shields.io/badge/nodriver-Anti--Detect-red.svg)](https://github.com/ultrafunkamsterdam/nodriver)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

> **Drop-in replacement API cho OpenAI, được cấp nguồn hoàn toàn miễn phí từ Gemini Web.**
> Biến giao diện web của Google Gemini thành một REST API chuẩn OpenAI. Tận dụng hạn ngạch (quota) miễn phí dồi dào của bản Web cho bất kỳ ứng dụng, tool hay SDK nào hỗ trợ hệ sinh thái OpenAI.

[English Version](README-en.md) | Phiên bản Tiếng Việt

---

## 💡 Tại Sao Cần Dự Án Này?

Nếu bạn là lập trình viên thường xuyên sử dụng AI, bạn sẽ biết Google cung cấp 3 hạn ngạch sử dụng Gemini **hoàn toàn tách biệt**:

| Kênh | Hạn Ngạch | Đặc điểm |
|------|-----------|-----------|
| **Antigravity** (IDE Extension) | ⚠️ Giới hạn riêng | Dành cho code trong IDE |
| **Gemini CLI** (Terminal) | ⚠️ Giới hạn riêng | Dành cho thao tác dòng lệnh |
| **Gemini Web** (Trình duyệt) | ✅ **Rất lớn / Độc lập** | Chat qua web thông thường |

**Vấn đề:** Khi bạn code quá "cháy" và hết sạch quota trên Antigravity hoặc Gemini CLI, bạn sẽ bị chặn. Tuy nhiên, **bản Web lúc đó vẫn còn nguyên hạn ngạch**. 
**Giải pháp:** Dự án này giúp bạn khai thác hạn ngạch dồi dào của bản Web đó bằng cách biến nó thành API chuẩn OpenAI — dùng được với mọi tool, SDK, và ứng dụng (thậm chí có thể config lại cho các IDE extension hỗ trợ custom OpenAI endpoint).

---

## ✨ Tính Năng Nổi Bật

- 🚀 **OpenAI-Compatible API** — Drop-in replacement: chỉ cần đổi `base_url`, tương thích 100% mọi OpenAI SDK (Python, Node.js, Go...)
- 🛡️ **Ultra Anti-Detection** — Sử dụng `nodriver` (Chrome CDP trực tiếp), qua mặt mọi cơ chế chống bot của Google.
- 🎭 **Human Behaviour Simulator** — Giả lập tốc độ gõ, delay ngẫu nhiên, mô phỏng hành vi người thật để tránh bị khóa tài khoản.
- 🔄 **Resilience System** — `BrowserWatchdog` theo dõi 24/7, tự động phát hiện crash và khởi động lại browser.
- 📡 **SSE Streaming** — Hỗ trợ response streaming theo chuẩn Server-Sent Events, realtime giống hệt OpenAI.
- 👥 **Guest Mode** — Chat không cần đăng nhập tài khoản Google (An toàn tối đa).
- 🔀 **Auto Model Fallback** — Tự động chuyển sang model khả dụng (Pro, Flash, Thinking) nếu model yêu cầu bị quá tải.
- 🔒 **Session Pool** — Quản lý multi-session (nhiều tab/browser), tự động dọn dẹp idle, chống quá tải.

---

## 📦 Cài Đặt

### Yêu cầu hệ thống
- Python 3.10+
- Google Chrome hoặc Microsoft Edge đã cài đặt.

### Các bước cài đặt

```bash
# 1. Clone repository
git clone https://github.com/yourusername/gemini-web-proxy.git
cd gemini-web-proxy

# 2. Tạo môi trường ảo (Khuyến nghị)
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 3. Cài đặt dependencies
pip install -r requirements.txt
```

---

## 🚀 Sử Dụng

### 1. Khởi chạy Server

Chạy server FastAPI để biến Gemini Web thành REST API:

```bash
python start_server.py
```

Server mặc định chạy tại `http://127.0.0.1:8765`.

### 2. Tích hợp vào Code (Ví dụ với OpenAI Python SDK)

Mở file `server_config.json`, đặt lại `api_key` của bạn, sau đó sử dụng như sau:

```python
from openai import OpenAI

# Khởi tạo client OpenAI nhưng trỏ về proxy của chúng ta
client = OpenAI(
    base_url="http://127.0.0.1:8765/v1",
    api_key="CHANGE_ME"  # Khớp với api_key trong server_config.json
)

# Chế độ Streaming (Realtime)
print("Response: ", end="")
stream = client.chat.completions.create(
    model="gemini-flash", # Hỗ trợ: gemini-flash, gemini-pro, gemini-thinking
    messages=[{"role": "user", "content": "Viết một đoạn code Python tính số Fibonacci"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

**API Endpoints hỗ trợ:**
- `POST /v1/chat/completions`: Chat completion (hỗ trợ cả streaming `stream=true`).
- `GET /v1/models`: Liệt kê các models hỗ trợ.
- `GET /v1/sessions`: Xem trạng thái session pool hiện tại.
- `GET /health`: Kiểm tra trạng thái server.

---

## ⚙️ Cấu Hình (`server_config.json`)

```jsonc
{
    "host": "127.0.0.1",
    "port": 8765,
    "api_key": "CHANGE_ME",        // Đổi key này để bảo mật API
    "max_sessions": 3,             // Số lượng browser tab chạy ngầm tối đa
    "idle_timeout_seconds": 300,   // Đóng tab nếu không dùng sau 5 phút
    "default_model": "gemini-flash",
    "headless": true,              // Chạy ngầm không hiện cửa sổ Chrome
    "guest_mode": true             // Không cần login Google
}
```

---

## ⚠️ Lưu Ý Kỹ Thuật
- **Cơ chế ẩn danh (Pseudo-Headless):** Khi bật `headless=true`, trình duyệt thực tế vẫn chạy nhưng bị đẩy ra ngoài tọa độ màn hình (`-32000,-32000`). Điều này đảm bảo giao diện DOM của Google render chính xác 100% thay vì bị chặn do phát hiện headless mode thật.
- **Tài khoản:** Khuyến khích luôn bật `guest_mode: true` để sử dụng ẩn danh. Nếu muốn dùng model cao cấp yêu cầu đăng nhập, hãy dùng một tài khoản phụ.

---

## 💖 Ủng Hộ (Donate)

Nếu dự án này giúp ích cho bạn trong công việc và học tập, giúp bạn vượt qua giới hạn Quota của Google, bạn có thể mời mình một ly cà phê nhé! ☕

<img src="QRdonate.jpg" width="300" alt="Momo QR Code">

---
*Mã nguồn mở phục vụ mục đích học tập và nghiên cứu Browser Automation. Vui lòng sử dụng có trách nhiệm.*
