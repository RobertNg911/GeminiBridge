# 🤖 GeminiBridge

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GeminiBridge                                │
│              Browser Automation → REST API Bridge                    │
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
                    │  Proxy Server │
                    │  (FastAPI)  │
                    │  :8765      │
                    └─────────────┘
                             │
                    ┌────────▼────────┐
                    │  Gemini Web  │
                    │(Chrome/Edge)│
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

## Cài Đặt

```bash
git clone https://github.com/RobertNg911/GeminiBridge.git
cd GeminiBridge
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

**Yêu cầu:** Python 3.10+, Chrome hoặc Microsoft Edge

---

## Sử Dụng Nhanh

```bash
python start_server.py
```

Server chạy tại `http://127.0.0.1:8765`

---

## Cách Sử Dụng

### Với Claude Code

```bash
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
│                  System Architecture                        │
└─────────────────────────────────────────────────────────────────┘

                      ┌───────────────────┐
                 ┌────▼────┐     ┌──────▼──────┐
                 │ OpenAI  │     │ Anthropic  │
                 │Endpoint│     │  Endpoint │
                 └────┬────┘     └──────┬──────┘
                      │                │
                      └───────┬────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Request Router  │
                    └─────────┬──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                   │                      │
  ┌─────▼─────┐     ┌──────▼──────┐     ┌──────▼──────┐
  │Session 1  │     │Session 2   │     │Session N   │
  │ (Edge)   │     │ (Chrome)  │     │  (Edge)   │
  └──────────┘     └───────────┘     └───────────┘
        │                   │                      │
        └───────────────────┼──────────────────────┘
                         │
                ┌────────▼────────┐
                │ Gemini Web  │
                └────────────┘
```

---

## Tham Khảo API

| Endpoint | Method | Mô tả |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI Chat API |
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | Liệt kê models khả dụng |
| `/health` | GET | Kiểm tra sức khỏe server |

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

---

## Models Khả Dụng

| Model | Mô tả |
|-------|-------------|
| `gemini-pro` | Mạnh nhất |
| `gemini-thinking` | Tư duy sâu |
| `gemini-flash` | Nhanh |
| `gemini-basic` | Cơ bản |

---

## License

MIT License - Xem file LICENSE

---

## Tuyên Bố Từ Chối

Dự án này cho mục đích giáo dục. Sử dụng có trách nhiệm và tuân thủ Điều Khoản Dịch Vụ của Google.