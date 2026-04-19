# 🤖 GeminiBridge

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GeminiBridge                                │
│              Browser Automation → REST API Bridge                   │
└─────────────────────────────────────────────────────────────────────┘
```

Máy chủ proxy nhẹ biến giao diện Google Gemini Web thành REST API tương thích OpenAI và Anthropic. Tận dụng quota miễn phí của Gemini Web cho ứng dụng AI của bạn.

---

## Tổng Quan

```
┌─────────────┐      ┌─────────────┐      ┌─────────────────────┐
│   Claude    │      │  OpenAI SDK │      │   Any OpenAI        │
│    Code     │      │   Client    │      │   Compatible       │
└──────┬──────┘      └──────┬──────┘      └──────────┬────────┘
       │                     │                       │
       └─────────────────────┼───────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Proxy Server   │
                    │  (FastAPI)      │
                    │  :8765          │
                    └────────┬───────┘
                             │
                    ┌────────▼────────┐
                    │  Gemini Web     │
                    │  (Chrome/Edge) │
                    └───────────────┘
```

## Tính Năng Chính

| Tính năng | Mô tả |
|-----------|-------|
| **Hỗ trợ Dual API** | Tương thích OpenAI + Anthropic endpoints |
| **Anti-Detection** | Tự động hóa trình duyệt nodriver |
| **Tự Phục Hồi** | Tự động khởi động lại trình duyệt khi crash |
| **Streaming** | Streaming thời gian thực qua SSE |
| **Guest Mode** | Không cần đăng nhập Google |
| **Model Pool** | Pro / Thinking / Flash / Basic |

---

## Cài Đặt Nhanh

### Cài đặt

```bash
# Clone repository
git clone https://github.com/your-username/GeminiBridge.git
cd GeminiBridge

# Tạo môi trường ảo
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# Cài đặt dependencies
pip install -r requirements.txt
```

**Yêu cầu:** Python 3.10+, Chrome hoặc Microsoft Edge

### Chạy Server

```bash
python start_server.py
```

Server chạy tại `http://127.0.0.1:8765`

---

## Cách Sử Dụng

### Với Claude Code

```powershell
# Windows PowerShell
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8765"
$env:ANTHROPIC_API_KEY="your-api-key-here"
$env:ANTHROPIC_MODEL="gemini-pro"
```

```bash
# Linux/macOS
export ANTHROPIC_BASE_URL="http://127.0.0.1:8765"
export ANTHROPIC_API_KEY="your-api-key-here"
export ANTHROPIC_MODEL="gemini-pro"
```

### Với OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8765/v1",
    api_key="your-api-key-here"
)

response = client.chat.completions.create(
    model="gemini-pro",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

---

## Kiến Trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Architecture               │
└─────────────────────────────────────────────────────────────────┘

                            ┌──────────────────────┐
                            │                     │
                      ┌─────▼─────┐      ┌──────▼──────┐
                      │  OpenAI   │      │ Anthropic  │
                      │ Endpoint │      │  Endpoint │
                      └─────┬─────┘      └──────┬──────┘
                           │                    │
                           └────────┬───────────┘
                                    │
                           ┌────────▼──────────┐
                           │    Request Router│
                           │  (Model Mapping,  │
                           │   Auth Check,    │
                           │   Throttling)    │
                           └──────────┬──────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                   │
              ┌─────▼─────┐     ┌──────▼──────┐     ┌──────▼──────┐
              │ Session 1 │     │ Session 2   │     │ Session N   │
              │  (Edge)   │     │  (Chrome)  │     │  (Edge)    │
              └─────┬─────┘     └──────┬──────┘     └──────┬──────┘
                   │                  │                   │
                   └──────────────────┼───────────────────┘
                                      │
                             ┌────────▼────────┐
                             │   Gemini Web     │
                             │    UI (AI)      │
                             └─────────────────┘
```

## Luồng Xử Lý Request

```
┌─────────────────────────────────────────────────────────────────┐
│                    Request Flow                      │
└─────────────────────────────────────────────────────────────────┘

1. Client Request (Yêu cầu từ Client)
       │
       ▼
2. Auth Validation (Kiểm tra API Key)
       │
       ▼
3. Route to Session Pool (Định tuyến đến Session Pool)
       │
       ▼
4. Get/Create Browser Session (Lấy/Tạo Session trình duyệt)
       │
       ▼
5. Send Prompt to Gemini Web (Gửi prompt đến Gemini Web)
       │
       ��
6. Poll Response (0.5s interval) (Kiểm tra phản hồi mỗi 0.5s)
       │
       ▼
7. Stream Back to Client (Stream về cho Client)
       │
       ▼
8. Return SSE/JSON Response (Trả về SSE/JSON)
```

---

## Tham Khảo API

### Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI Chat API |
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | Liệt kê models khả dụng |
| `/v1/sessions` | GET | Liệt kê sessions đang hoạt động |
| `/health` | GET | Kiểm tra sức khỏe server |

### Định dạng OpenAI

```bash
curl -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{
    "model": "gemini-pro",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

### Định dạng Anthropic

```bash
curl -X POST http://127.0.0.1:8765/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{
    "model": "gemini-pro",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

---

## Cấu Hình

Chỉnh sửa `server_config.json`:

```json
{
    "host": "127.0.0.1",
    "port": 8765,
    "api_key": "your-api-key-here",
    "max_sessions": 1,
    "idle_timeout_seconds": 600,
    "default_model": "gemini-pro",
    "headless": true,
    "guest_mode": true
}
```

| Tham số | Kiểu | Mặc định | Mô tả |
|---------|------|---------|-------|
| `host` | string | 127.0.0.1 | Địa chỉ bind server |
| `port` | int | 8765 | Cổng server |
| `api_key` | string | - | API key của bạn |
| `max_sessions` | int | 1 | Số tabs tối đa |
| `idle_timeout_seconds` | int | 600 | Timeout khi không hoạt động |
| `default_model` | string | gemini-pro | Model mặc định |
| `headless` | boolean | true | Chạy ẩn trình duyệt |
| `guest_mode` | boolean | true | Chế độ khách |

---

## Models Khả Dụng

| Model | Mô tả | Khả năng |
|-------|------|---------|
| `gemini-pro` | Mạnh nhất | Lập luận phức tạp, viết code |
| `gemini-thinking` | Tư duy sâu | Phân tích từng bước |
| `gemini-flash` | Nhanh | Phản hồi nhanh |
| `gemini-basic` | Cơ bản | Tác vụ đơn giản |

---

## Cấu Trúc Dự Án

```
GeminiBridge/
├── src/
│   ├── api/
│   │   ├── server.py       # FastAPI server
│   │   └── router.py       # Định tuyến model
│   ├── core/
│   │   ├── client.py       # Trình duyệt Gemini
│   │   ├── adapter.py     # Chuyển đổi định dạng API
│   │   └── session.py     # Quản lý session
│   └── schemas/
│       └── models.py       # Pydantic models
├── start_server.py        # Entry point
├── server_config.json     # Cấu hình server
├── config.json          # Cấu hình client
├── requirements.txt    # Python dependencies
└── README.md           # File này
```

---

## Ghi Chú Kỹ Thuật

### Cách Hoạt Động

1. **Tự động hóa trình duyệt**: Sử dụng `nodriver` (Chrome DevTools Protocol) để điều khiển trình duyệt
2. **Session Pool**: Quản lý nhiều browser sessions cho request song song
3. **Tự phục hồi**: BrowserWatchdog theo dõi và khởi động lại trình duyệt khi crash
4. **Streaming**: Kiểm tra Gemini DOM mỗi 500ms để phản hồi thời gian thực

### Chế độ Headless

Khi `headless: true`, trình duyệt chạy "pseudo-headless" - đặt tại vị trí `-32000, -32000` trên màn hình. Điều này đảm bảo:
- Render DOM chính xác
- Bỏ qua phát hiện headless
- Ẩn với người dùng nhưng đầy đủ chức năng

### Chế độ Guest

Với `guest_mode: true`:
- Sử dụng hồ sơ trình duyệt ẩn danh
- Không cần đăng nhập Google
- An toàn cho triển khai công khai
- Hoạt động với Gemini free tier

---

## Xử Lý Sự Cố

### Issue: 401 Unauthorized

**Giải pháp:** Kiểm tra `api_key` trong `server_config.json` khớp với request header

### Issue: Trình duyệt không khởi động

**Giải pháp:** Đảm bảo Chrome/Edge đã cài đặt. Kiểm tra `headless: false` để debug

### Issue: Phản hồi chậm

**Giải pháp:** Đây là bình thường do overhead tự động hóa trình duyệt. Cân nhắc:
- Dùng `gemini-flash` để phản hồi nhanh hơn
- Giảm `max_sessions` xuống 1
- Tăng throttle delays

---

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Tuyên Bố Từ Chối

Dự án này cho mục đích giáo dục và nghiên cứu. Sử dụng có trách nhiệm và tuân thủ Điều Khoản Dịch Vụ của Google. Các tác giả không chịu trách nhiệm cho bất kỳ việc sử dụng sai hoặc hạn chế tài khoản nào.