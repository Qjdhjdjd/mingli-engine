# -*- coding: utf-8 -*-
"""本地 Web 服务（零第三方依赖）。

启动：python app.py  ->  http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src import calendar_core as C  # noqa: E402
from src.llm import narrate as llm_narrate  # noqa: E402
from src.llm import provider as llm_provider  # noqa: E402
from src.predict import (bazi_report, liuri_report, liuyao_report,  # noqa: E402
                         meihua_report, rule_stats, xingming_report,
                         zeri_report)

PORT = 8765


def _parse_dt(date_str: str, time_str: str = "12:00") -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=C.CST)


def _report_for(kind: str, body: dict):
    """按体系构造报告。接口与解读共用同一份，避免两套参数解析。"""
    if kind == "bazi":
        return bazi_report(_parse_dt(body.get("date", ""), body.get("time", "12:00")),
                           body.get("gender", "男"), body.get("name", ""))
    if kind == "meihua":
        return meihua_report(int(body["a"]), int(body["b"]), body.get("question", ""))
    if kind == "liuyao":
        return liuyao_report(yao_values=body.get("yao"),
                             question=body.get("question", "综合"),
                             gender=body.get("gender", "男"),
                             seed=body.get("seed"))
    if kind == "zeri":
        return zeri_report(_parse_dt(body.get("date", "")))
    if kind == "liuri":
        start = None
        if body.get("start"):
            start = datetime.strptime(body["start"], "%Y-%m-%d").replace(tzinfo=C.CST)
        return liuri_report(_parse_dt(body.get("date", ""), body.get("time", "12:00")),
                            body.get("gender", "男"), start,
                            int(body.get("days", 30)), body.get("name", ""))
    if kind == "xingming":
        sn = [int(x) for x in str(body["surname"]).replace("，", ",").split(",")]
        gv = [int(x) for x in str(body["given"]).replace("，", ",").split(",")]
        return xingming_report(sn, gv, body.get("name", ""))
    raise ValueError(f"未知体系：{kind}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            f = ROOT / "web" / "index.html"
            if not f.exists():
                self._send(404, b"index.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, f.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/stats":
            self._json(rule_stats())
        elif path == "/api/llm/status":
            self._json(llm_provider.status())
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json({"error": "请求体不是合法 JSON"}, 400)
            return

        try:
            if path == "/api/stats":
                self._json(rule_stats())
            elif path == "/api/narrate":
                kind = body.get("kind", "bazi")
                report = _report_for(kind, body)
                day = None
                if kind == "liuri" and body.get("day"):
                    day = next((d for d in report["days"]
                                if d["date"] == body["day"]), None)
                    if day is None:
                        self._json({"error": "该日期不在所选区间内"}, 400)
                        return
                mode = body.get("mode", "strict")
                self._json(llm_narrate.narrate(
                    report, day=day, mode=mode,
                    use_llm=bool(body.get("use_llm", True)),
                    question=body.get("question", ""),
                ))
            elif path.startswith("/api/") and path[5:] in (
                "bazi", "liuri", "liuyao", "meihua", "zeri", "xingming"
            ):
                self._json(_report_for(path[5:], body))
            else:
                self._json({"error": "未知接口"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"命理规则引擎已启动： http://127.0.0.1:{PORT}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
