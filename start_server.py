"""
start_server.py — Entry point để chạy API Server.

Usage:
    python start_server.py
    python start_server.py --port 9000
    python start_server.py --config my_config.json
"""

import argparse
import asyncio
import logging
import sys
import os

# ============================================================
# Enable ANSI Colors on Windows
# ============================================================
if sys.platform == "win32":
    os.system("")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gemini Web → OpenAI-Compatible API Server"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Port để chạy server (mặc định: 8765, hoặc theo server_config.json)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host bind address (mặc định: 0.0.0.0)",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="server_config.json",
        help="Đường dẫn file cấu hình server",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load config trước để lấy port/host mặc định
    from src.api.server import load_server_config
    config = load_server_config(args.config)

    host = args.host or config.get("host", "0.0.0.0")
    port = args.port or config.get("port", 8765)

    print(f"""
╔══════════════════════════════════════════════════════╗
║    🚀  GEMINI WEB → OpenAI-Compatible API Server    ║
║    Browser Automation · Anti‑Detection · Proxy       ║
╚══════════════════════════════════════════════════════╝

  Endpoint:  http://{host}:{port}/v1/chat/completions
  Models:    http://{host}:{port}/v1/models
  Docs:      http://{host}:{port}/docs
  Health:    http://{host}:{port}/health

  Cách sử dụng với OpenAI SDK:
  ─────────────────────────────────────────────────────
  import openai
  client = openai.OpenAI(
      base_url="http://localhost:{port}/v1",
      api_key="{config.get('api_key', 'nokey')}"
  )
  response = client.chat.completions.create(
      model="gemini-flash",
      messages=[{{"role": "user", "content": "Hello!"}}]
  )
  print(response.choices[0].message.content)
  ─────────────────────────────────────────────────────
""")

    # Chạy uvicorn
    import uvicorn

    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        log_level=config.get("log_level", "info").lower(),
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
