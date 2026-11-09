# -*- coding: utf-8 -*-
"""大模型解读层测试。

在线路径用一个本地假服务模拟 OpenAI 兼容接口，不需要真实 API Key，
但走的是完整的 HTTP 序列化、请求构造、响应解析、校验、降级链路。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.calendar_core import CST  # noqa: E402
from src.llm import facts, narrate, provider, verify  # noqa: E402
from src.predict import (bazi_report, liuri_report, liuyao_report,  # noqa: E402
                         meihua_report, xingming_report, zeri_report)

BIRTH = datetime(1990, 5, 15, 10, 30, tzinfo=CST)


class _FakeLLM(BaseHTTPRequestHandler):
    reply = ""
    calls: list[dict] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).calls.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "model": body.get("model"),
            "messages": body.get("messages", []),
        })
        payload = {
            "model": body.get("model", "fake"),
            "choices": [{"message": {"role": "assistant", "content": type(self).reply}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class TestVerifier(unittest.TestCase):
    ALLOWED = {"YHP-001", "SMT-002"}
    SCORES = {0, -2, 3}

    def test_clean_text_passes(self):
        text = (
            "## 主要依据\n"
            "伤官见官，古法以为多阻 [YHP-001]。\n"
            "时柱见财官，主晚运得力 [SMT-002]。\n"
            "## 一句话\n综合判定为「平」。"
        )
        v = verify.verify(text, self.ALLOWED, self.SCORES)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["coverage"]["cited"], 2)

    def test_fabricated_id_is_fatal(self):
        v = verify.verify("此说见于某书 [ZZZ-999]。", self.ALLOWED, self.SCORES)
        self.assertFalse(v["ok"])
        self.assertEqual(v["unknown_ids"], ["ZZZ-999"])
        self.assertTrue(any("不存在的规则编号" in p for p in v["problems"]))

    def test_invented_score_flagged(self):
        v = verify.verify("此条计 +9 分，颇为不利 [YHP-001]。", self.ALLOWED, self.SCORES)
        self.assertFalse(v["ok"])
        self.assertIn("+9 分", v["invented_scores"])

    def test_real_score_accepted(self):
        v = verify.verify("此条计 -2 分 [YHP-001]。", self.ALLOWED, self.SCORES)
        self.assertTrue(v["ok"], v["problems"])

    def test_overclaim_flagged(self):
        v = verify.verify("此人必然富贵 [YHP-001]。", self.ALLOWED, self.SCORES)
        self.assertFalse(v["ok"])
        self.assertTrue(v["overclaims"])

    def test_unsourced_verdict_flagged(self):
        v = verify.verify("此日大凶，诸事不宜。", self.ALLOWED, self.SCORES)
        self.assertFalse(v["ok"])
        self.assertEqual(v["unsupported_count"], 1)

    def test_no_citation_at_all_flagged(self):
        v = verify.verify("## 命局概要\n日主庚金，生于巳月，气偏旺。", self.ALLOWED, self.SCORES)
        self.assertFalse(v["ok"])
        self.assertIn("全文没有引用任何一条规则", "；".join(v["problems"]))

    def test_aggregate_and_level_restate_allowed(self):
        text = (
            "区间内大吉 3 天、吉 20 天。\n"
            "综合判定为「平」，命中 6 条 [YHP-001]。"
        )
        v = verify.verify(text, self.ALLOWED, self.SCORES)
        self.assertTrue(v["ok"], v["problems"])

    def test_speculation_section_isolated(self):
        text = (
            "此条主晚运得力 [SMT-002]。\n"
            "【模型推断】\n"
            "以下为模型的类比，非典籍结论：此局近似于秋日锻铁，需火候得当。"
        )
        v = verify.verify(text, self.ALLOWED, self.SCORES, mode="exploratory")
        self.assertTrue(v["ok"], v["problems"])
        self.assertTrue(v["speculation"]["present"])

    def test_speculation_cannot_fake_ids(self):
        text = "此条主晚运得力 [SMT-002]。\n【模型推断】\n另有一说 [ABC-123]，模型私拟。"
        v = verify.verify(text, self.ALLOWED, self.SCORES, mode="exploratory")
        self.assertFalse(v["ok"])
        self.assertIn("ABC-123", v["unknown_ids"])


class TestFactSheet(unittest.TestCase):
    def test_bazi_fact_contains_only_engine_ids(self):
        rep = bazi_report(BIRTH, "男")
        fact = facts.build(rep)
        engine_ids = {h["id"] for h in rep["hits"]}
        self.assertTrue(facts.allowed_ids(fact) <= engine_ids)
        self.assertEqual(fact["kind"], "bazi")
        self.assertNotIn("days", fact)          # 八字没有逐日字段
        self.assertIn("overall", fact)

    def test_liuri_range_aggregates_frequency(self):
        rep = liuri_report(BIRTH, "男", datetime(2026, 11, 10, tzinfo=CST), 30)
        fact = facts.build(rep)
        self.assertEqual(fact["kind"], "liuri_range")
        self.assertTrue(fact["judgments"])
        days = [j["days"] for j in fact["judgments"]]
        self.assertEqual(days, sorted(days, reverse=True))

    def test_liuri_day_scope(self):
        rep = liuri_report(BIRTH, "男", datetime(2026, 11, 10, tzinfo=CST), 7)
        day = rep["days"][2]
        fact = facts.build(rep, day)
        self.assertEqual(fact["kind"], "liuri_day")
        self.assertEqual(fact["computed"]["date"], day["date"])


class TestProvider(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLLM)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _FakeLLM.calls = []
        _FakeLLM.reply = "## 命局概要\n测试。\n"
        self.cfg = provider.LLMConfig(
            provider="custom",
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="sk-test-1234567890",
            model="fake-model",
        )

    def test_chat_roundtrip(self):
        res = provider.chat([{"role": "user", "content": "hi"}], self.cfg)
        self.assertEqual(res["text"], "## 命局概要\n测试。")
        self.assertEqual(res["provider"], "custom")
        self.assertEqual(_FakeLLM.calls[0]["path"], "/v1/chat/completions")
        self.assertEqual(_FakeLLM.calls[0]["auth"], "Bearer sk-test-1234567890")
        self.assertEqual(_FakeLLM.calls[0]["model"], "fake-model")

    def test_public_masks_key(self):
        pub = self.cfg.public()
        self.assertNotIn("1234567890", json.dumps(pub))
        self.assertTrue(pub["masked_key"].startswith("sk-t"))

    def test_missing_key_raises_not_configured(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("MINGLI_", "OPENAI_"))}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(provider.LLMNotConfigured):
                provider.resolve_config({"provider": "deepseek",
                                         "base_url": "https://api.deepseek.com/v1",
                                         "model": "deepseek-chat"})

    def test_connection_error_becomes_llm_error(self):
        cfg = provider.LLMConfig(provider="custom", base_url="http://127.0.0.1:1/v1",
                                 api_key="sk-x", model="m", timeout=2)
        with self.assertRaises(provider.LLMError):
            provider.chat([{"role": "user", "content": "hi"}], cfg, retries=0)


class TestNarrate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLLM)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _FakeLLM.calls = []
        self.rep = bazi_report(BIRTH, "男")
        self.cfg = provider.LLMConfig(
            provider="custom",
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="sk-test-1234567890",
            model="fake-model",
        )

    def _clean_reply(self, n=3):
        ids = [h["id"] for h in self.rep["hits"][:n]]
        body = "\n".join(f"古法于此有说，按条列示 [{i}]。" for i in ids)
        return ("## 命局概要\n日主庚金，生于巳月，判为偏强，格局七杀格。\n"
                f"## 主要依据\n{body}\n"
                "## 需要注意\n分值权重为人所设，非古籍原文。\n"
                "## 一句话\n综合判定为「平」。")

    def test_offline_template_always_available(self):
        out = narrate.narrate(self.rep, use_llm=False)
        self.assertFalse(out["online"])
        self.assertTrue(out["verification"]["ok"], out["verification"]["problems"])
        self.assertIn("## 主要依据", out["text"])

    def test_online_clean_reply_kept(self):
        _FakeLLM.reply = self._clean_reply()
        out = narrate.narrate(self.rep, cfg=self.cfg)
        self.assertTrue(out["online"])
        self.assertEqual(out["provider"], "custom")
        self.assertTrue(out["verification"]["ok"], out["verification"]["problems"])
        # 发给模型的必须是事实清单，不能夹带原始报告里的无关字段
        system = _FakeLLM.calls[0]["messages"][0]["content"]
        self.assertIn("不得新增任何吉凶", system.replace("\n", ""))

    def test_online_fabrication_degrades_to_template(self):
        _FakeLLM.reply = ("## 命局概要\n日主庚金。\n"
                          "## 主要依据\n此说见于秘本 [ZZZ-777]。\n"
                          "## 一句话\n综合判定为「平」。")
        out = narrate.narrate(self.rep, cfg=self.cfg)
        self.assertFalse(out["online"])
        self.assertIn("降级", out["fallback_reason"] or "")
        self.assertTrue(out["verification"]["ok"])
        self.assertIn("《", out["text"])

    def test_online_failure_degrades_with_reason(self):
        cfg = provider.LLMConfig(provider="custom", base_url="http://127.0.0.1:1/v1",
                                 api_key="sk-x", model="m", timeout=2)
        out = narrate.narrate(self.rep, cfg=cfg)
        self.assertFalse(out["online"])
        self.assertIn("调用模型失败", out["fallback_reason"] or "")
        self.assertTrue(out["verification"]["ok"])

    def test_liuri_day_narrative(self):
        rep = liuri_report(BIRTH, "男", datetime(2026, 11, 10, tzinfo=CST), 7)
        out = narrate.narrate(rep, day=rep["days"][0], use_llm=False)
        self.assertIn("当日", out["text"])
        self.assertTrue(out["verification"]["ok"], out["verification"]["problems"])

    def test_prompt_carries_no_api_key(self):
        _FakeLLM.reply = self._clean_reply()
        narrate.narrate(self.rep, cfg=self.cfg)
        blob = json.dumps(_FakeLLM.calls[0]["messages"], ensure_ascii=False)
        self.assertNotIn("sk-test-1234567890", blob)

    def test_templates_contain_no_python_repr(self):
        """模板是给人读的，不能把 list/dict 的 repr 直接漏出来。"""
        lr = liuri_report(BIRTH, "男", datetime(2026, 11, 10, tzinfo=CST), 7)
        cases = [
            bazi_report(BIRTH, "男"),
            liuri_report(BIRTH, "男", datetime(2026, 11, 10, tzinfo=CST), 7),
            liuyao_report([7, 8, 9, 7, 6, 8], "求财", seed=42),
            meihua_report(23, 17, "问事"),
            zeri_report(datetime(2026, 11, 9, 10, 0, tzinfo=CST)),
            xingming_report([4], [11], "王伟"),
        ]
        texts = [narrate.narrate(c, use_llm=False)["text"] for c in cases]
        texts.append(narrate.narrate(lr, day=lr["days"][0], use_llm=False)["text"])
        for t in texts:
            self.assertNotIn("['", t)
            self.assertNotIn('{"', t)
            self.assertNotIn("None", t)


if __name__ == "__main__":
    unittest.main()
