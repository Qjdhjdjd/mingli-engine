# -*- coding: utf-8 -*-
"""开发用：本地起服务并截图，检查界面渲染。"""

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import Handler  # noqa: E402

PORT = 8791
srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1280, "height": 1000}, device_scale_factor=1.5)
        pg.goto(f"http://127.0.0.1:{PORT}", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(ROOT / "docs" / "shot_bazi.png"), full_page=True)

        pg.click('nav button[data-tab="liuyao"]')
        pg.wait_for_timeout(200)
        pg.click("#p-liuyao .btn")
        pg.wait_for_timeout(900)
        pg.screenshot(path=str(ROOT / "docs" / "shot_liuyao.png"), full_page=True)

        pg.click('nav button[data-tab="zeri"]')
        pg.wait_for_timeout(200)
        pg.click("#p-zeri .btn")
        pg.wait_for_timeout(900)
        pg.screenshot(path=str(ROOT / "docs" / "shot_zeri.png"), full_page=True)
        b.close()
    print("screenshot ok")
finally:
    srv.shutdown()
