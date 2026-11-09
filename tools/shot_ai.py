# -*- coding: utf-8 -*-
"""用假模型跑一遍界面，截图检查渲染。仅开发用。"""

from __future__ import annotations

import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mock_llm import start_in_thread  # noqa: E402

mock, mock_port = start_in_thread(0)
os.environ["MINGLI_LLM_PROVIDER"] = "custom"
os.environ["MINGLI_LLM_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1"
os.environ["MINGLI_LLM_API_KEY"] = "sk-mock-000000"
os.environ["MINGLI_LLM_MODEL"] = "mock-reasoner"

import app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 8795), app.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1280, "height": 1100}, device_scale_factor=2)
        pg.goto("http://127.0.0.1:8795", wait_until="networkidle")
        pg.wait_for_timeout(1200)
        pg.locator("#result .btn.ai").first.click()
        pg.wait_for_selector("#ai-out-liuri .ai-card", timeout=15000)
        pg.wait_for_timeout(400)
        pg.locator("#ai-out-liuri").screenshot(path=str(ROOT / "docs/_ai_liuri.png"))

        pg.click('nav button[data-tab="bazi"]')
        pg.wait_for_timeout(300)
        pg.locator("#p-bazi .btn").first.click()
        pg.wait_for_timeout(900)
        pg.locator("#result .btn.ai").first.click()
        pg.wait_for_selector("#ai-out-bazi .ai-card", timeout=15000)
        pg.wait_for_timeout(400)
        pg.locator("#ai-out-bazi").screenshot(path=str(ROOT / "docs/_ai_bazi.png"))
        b.close()
finally:
    srv.shutdown()
    mock.shutdown()
print("ok")
