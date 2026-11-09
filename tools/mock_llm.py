# -*- coding: utf-8 -*-
"""本地假模型：一个 OpenAI 兼容的 /chat/completions 服务。

用途：
1. 开发与演示时验证「在线路径」——不需要任何 API Key。
2. 作为「合规输出」的参考样例：它只引用事实清单里的编号，不新增判断。

启动：
    python tools/mock_llm.py 8799
然后另开一个终端：
    MINGLI_LLM_PROVIDER=custom \
    MINGLI_LLM_BASE_URL=http://127.0.0.1:8799/v1 \
    MINGLI_LLM_API_KEY=sk-mock \
    MINGLI_LLM_MODEL=mock-reasoner \
    python app.py
"""

from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FACT_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def compose(fact: dict, mode: str = "strict") -> str:
    c = fact.get("computed", {})
    o = fact.get("overall", {})
    js = fact.get("judgments", [])
    kind = fact.get("kind", "")

    pos = [h for h in js if h.get("score", 0) > 0]
    neg = [h for h in js if h.get("score", 0) < 0]

    def cite(h):
        return f"[{h['id']}]" if h.get("id") else ""

    def line(h):
        sec = f"·{h['section']}" if h.get("section") else ""
        freq = f"，区间内出现 {h['days']} 天" if h.get("days") else ""
        return f"《{h['book']}》{sec}「{h['title']}」{freq}，原文之意为：{h['text']} {cite(h)}"

    out = ["## 命局概要"]

    if kind == "bazi":
        out.append(
            f"这是一张{c.get('day_master')}{c.get('day_master_element')}日主的盘，"
            f"生于{(c.get('pillars') or ['', '?'])[1][1]}月，"
            f"引擎按同类占比判为{c.get('strength')}，取「{c.get('pattern')}」。"
            f"四柱 {' '.join(c.get('pillars', []))}。"
        )
        if c.get("shensha"):
            out.append(f"神煞见{'、'.join(c['shensha'][:6])}，按古法只作参看，不入主判。")
    elif kind == "liuri_day":
        out.append(
            f"{c.get('date')}是{c.get('ganzhi')}日，日干对{c.get('day_master')}日主为「{c.get('ten_god')}」。"
            f"这一天建除为「{c.get('jianchu')}」，值神「{c.get('zhishen')}」。"
        )
    elif kind == "liuri_range":
        out.append(
            f"这段日子从{c.get('start')}起共 {c.get('days')} 天，"
            f"命主为{c.get('day_master')}{c.get('day_master_element')}日主，"
            f"其间走{c.get('dayun') or '未起运'}运，流年{c.get('liunian')}。"
        )
    else:
        out.append("下面按规则库命中的条目，逐项说明这一局的构成。")

    out.append("\n## 主要依据")
    if not js:
        out.append("这一局没有命中任何条目，因此不下判断。")
    else:
        out.append(f"命中 {len(js)} 条，其中偏正向 {len(pos)} 条、偏负向 {len(neg)} 条。取其中较重的几条来看：")
        for h in (pos or js)[:4]:
            out.append(line(h))

    out.append("\n## 需要注意")
    if neg:
        for h in neg[:3]:
            out.append(line(h))
    else:
        out.append("没有命中偏负向的条目，但这只说明规则库在这张盘上没有对应条款，不等于没有风险。")

    out.append("\n## 一句话")
    level = o.get("level")
    if level:
        tail = f"此局判为「{level}」，均分 {o.get('avg_score', 0):+}"
    elif o.get("total_score") is not None:
        tail = f"当日合计 {o.get('total_score', 0):+} 分"
    else:
        dist = o.get("distribution") or {}
        tail = "区间分布为 " + "、".join(f"{k} {v} 天" for k, v in dist.items() if v)
    out.append(f"按典籍条款，{tail}。这是文本规则的映射结果，不是对现实事件的预测。")

    if mode == "exploratory":
        out.append(
            "\n【模型推断】\n"
            "以下为模型的类比，非典籍结论：此局更像一件已经成形的器物，"
            "接下来的问题不是再造，而是找个合适的地方安置它。"
        )
    return "\n".join(out)


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            self._handle()
        except Exception as exc:  # 假模型自己出错也要回一个合法响应，别把连接掐断
            raw = json.dumps({"error": {"message": f"mock 失败：{exc}"}},
                             ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        user = messages[-1]["content"] if messages else ""
        system = messages[0]["content"] if messages else ""

        fact = {}
        m = FACT_RE.search(user)
        if m:
            try:
                fact = json.loads(m.group(1))
            except json.JSONDecodeError:
                fact = {}

        if not fact:
            # 重写请求里没有清单，返回一段保守文本
            text = ("## 命局概要\n本次未取得可核对的事实清单，因此不作判断。\n"
                    "## 主要依据\n无。\n## 需要注意\n无。\n## 一句话\n请重新生成。")
        else:
            mode = "exploratory" if "【模型推断】" in system else "strict"
            text = compose(fact, mode)

        payload = {
            "model": body.get("model", "mock-reasoner"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(user), "completion_tokens": len(text)},
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def start_in_thread(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    srv = ThreadingHTTPServer(("127.0.0.1", p), MockHandler)
    print(f"假模型已启动： http://127.0.0.1:{p}/v1/chat/completions")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("已停止")
