# 🤖 Gemini Web Proxy — Web to OpenAI API Bridge

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![nodriver](https://img.shields.io/badge/nodriver-Anti--Detect-red.svg)](https://github.com/ultrafunkamsterdam/nodriver)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

> **A free, drop-in replacement API for OpenAI, powered directly by Gemini Web.**
> Transforms the Google Gemini Web UI into a fully functional, OpenAI-Compatible REST API. Leverage the abundant free quota of the web version for any app, tool, or SDK that supports the OpenAI ecosystem.

[Vietnamese Version](README.md) | English Version

---

## 💡 Why this project?

Google provides three **completely separate** quotas for using Gemini:

| Channel | Quota Status | Target Audience |
|---------|--------------|-----------------|
| **Antigravity** (IDE Extension) | ⚠️ Dedicated Limit | Developers in IDE |
| **Gemini CLI** (Terminal) | ⚠️ Dedicated Limit | CLI Users |
| **Gemini Web** (Browser) | ✅ **Generous / Independent** | General Users |

**The Problem:** When you code intensely and exhaust your quota on Antigravity or the Gemini CLI, you hit a rate limit. However, **your Web quota remains completely untouched**.
**The Solution:** This project bridges that gap by automating the web interface and exposing it as an OpenAI REST API. This allows you to use your web quota inside any developer tool, script, or SDK that accepts custom OpenAI endpoints.

---

## ✨ Features

- 🚀 **OpenAI-Compatible API** — Drop-in replacement: just change the `base_url`. Works with Python, Node.js, Go SDKs.
- 🛡️ **Ultra Anti-Detection** — Powered by `nodriver` (direct CDP manipulation) to bypass Google's bot detection.
- 🎭 **Human Behaviour Simulator** — Mimics human typing speed and introduces randomized delays to prevent bans.
- 🔄 **Resilience System** — Built-in `BrowserWatchdog` detects crashes and restarts sessions automatically.
- 📡 **SSE Streaming** — Full support for Server-Sent Events (SSE) streaming, just like standard OpenAI APIs.
- 👥 **Guest Mode** — Chat without logging into a Google Account for maximum privacy.
- 🔀 **Auto Model Fallback** — Automatically switches to an available model (Pro, Flash, Thinking) if the requested one is unavailable.
- 🔒 **Session Pool** — Manages multiple browser tabs with auto-cleanup for idle sessions.

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- Google Chrome or Microsoft Edge installed on your machine.

### Setup

```bash
# 1. Clone repository
git clone https://github.com/Nhan-209/Gemini-web-to-api.git
cd Gemini-web-to-api

# 2. Create virtual environment (Recommended)
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Usage

### 1. Start the API Server

```bash
python start_server.py
```
The server will start at `http://127.0.0.1:8765`.

### 2. Integrate with OpenAI SDK

Change your `api_key` in `server_config.json`, then use the standard OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8765/v1",
    api_key="CHANGE_ME"  # Matches server_config.json
)

# Streaming response
stream = client.chat.completions.create(
    model="gemini-flash", # Supported: gemini-flash, gemini-pro, gemini-thinking
    messages=[{"role": "user", "content": "Write a python script for fibonacci."}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## 💖 Donate

If this project helps you in your work or study, and saves you from Google's Quota limits, consider buying me a coffee! ☕

<img src="QRdonate.jpg" width="300" alt="Momo QR Code">

---
*Open-source project for educational and Browser Automation research purposes. Please use responsibly.*
