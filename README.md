# 🤖 GeminiBridge

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GeminiBridge                                │
│              Browser Automation → REST API Bridge                    │
└─────────────────────────────────────────────────────────────────────┘
```

A lightweight proxy server that transforms Google Gemini Web interface into OpenAI and Anthropic compatible REST APIs. Leverage free Gemini Web quotas for your AI-powered applications.

---

## Overview

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

## Key Features

| Feature | Description |
|---------|-------------|
| **Dual API Support** | OpenAI + Anthropic compatible endpoints |
| **Anti-Detection** | nodriver-based browser automation |
| **Auto Recovery** | Automatic browser restart on crash |
| **Streaming** | Real-time SSE response streaming |
| **Guest Mode** | No Google login required |
| **Model Pool** | Pro / Thinking / Flash / Basic |

---

## Installation

```bash
git clone https://github.com/RobertNg911/GeminiBridge.git
cd GeminiBridge
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

**Requirements:** Python 3.10+, Chrome or Microsoft Edge

---

## Quick Start

```bash
python start_server.py
```

Server starts at `http://127.0.0.1:8765`

---

## Usage

### With Claude Code

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8765"
export ANTHROPIC_API_KEY="your-api-key-here"
export ANTHROPIC_MODEL="gemini-pro"
```

### With OpenAI SDK

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

## Architecture

```
┌──────────────────────────────────────────────────��──────────────┐
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

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI Chat API |
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | List available models |
| `/health` | GET | Server health check |

---

## Configuration

Edit `server_config.json`:

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

## Available Models

| Model | Description |
|-------|-------------|
| `gemini-pro` | Most capable |
| `gemini-thinking` | Deep thinking |
| `gemini-flash` | Fast |
| `gemini-basic` | Basic |

---

## License

MIT License - See LICENSE file

---

## Disclaimer

This project is for educational purposes. Use responsibly and in accordance with Google's Terms of Service.