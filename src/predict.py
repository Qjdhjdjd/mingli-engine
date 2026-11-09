# -*- coding: utf-8 -*-
"""统一预测入口：分析器 -> 规则引擎 -> 结构化报告。

设计原则：所有吉凶结论都必须能回指到「哪本书的哪条规则」，
不做无出处的自由发挥。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import calendar_core as C
from . import tables as T
from .analyzers import bazi as bazi_an
from .analyzers import liuri as liuri_an
from .analyzers import liuyao as liuyao_an
from .analyzers import meihua as meihua_an
from .analyzers import xingming as xm_an
from .analyzers import zeri as zeri_an
from .engine import RuleEngine, load_rules

RULE_DIR = Path(__file__).parent / "rules"

DISCLAIMER = (
    "本工具是对中国传统命理文献中「条件→结论」规则的程序化整理，属文化研究与娱乐用途。"
    "命理典籍的吉凶判断建立在古代阴阳五行宇宙观之上，不具科学预测效力，"
    "不应作为医疗、婚姻、投资、职业等现实决策的依据。"
)

_engine: RuleEngine | None = None


def get_engine() -> RuleEngine:
    global _engine
    if _engine is None:
        rules = (load_rules(RULE_DIR / "bazi.json")
                 + load_rules(RULE_DIR / "other.json")
                 + load_rules(RULE_DIR / "liuri.json"))
        _engine = RuleEngine(rules)
    return _engine


def rule_stats() -> dict:
    eng = get_engine()
    by_book, by_system = {}, {}
    for r in eng.rules:
        by_book[r["book"]] = by_book.get(r["book"], 0) + 1
        by_system[r["system"]] = by_system.get(r["system"], 0) + 1
    return {
        "total_rules": len(eng.rules),
        "total_books": len(by_book),
        "by_book": dict(sorted(by_book.items(), key=lambda kv: -kv[1])),
        "by_system": by_system,
    }


def _pack(kind: str, summary: dict, hits: list[dict], extra: dict | None = None) -> dict:
    eng = get_engine()
    topics = eng.score_by_topic(hits)
    scores = [h["then"].get("score", 0) for h in hits]
    avg = sum(scores) / len(scores) if scores else 0
    if avg >= 1.5:
        level = "大吉"
    elif avg >= 0.5:
        level = "吉"
    elif avg >= -0.5:
        level = "平"
    elif avg > -1.5:
        level = "凶"
    else:
        level = "大凶"

    out = {
        "kind": kind,
        "summary": summary,
        "topics": topics,
        "hits": hits,
        "overall": {
            "avg_score": round(avg, 2),
            "hit_count": len(hits),
            "level": level,
            "confidence": "较高" if len(hits) >= 6 else ("中等" if len(hits) >= 3 else "较低"),
            "note": "综合倾向为命中规则得分的算术平均，仅表示典籍规则的分布，不代表事件概率。命中条数越少，可参考性越低。",
        },
        "disclaimer": DISCLAIMER,
    }
    if extra:
        out.update(extra)
    return out


def bazi_report(birth: datetime, gender: str = "男", name: str = "") -> dict:
    p = C.paipan(birth)
    ctx = bazi_an.analyze(p["pillars"], gender, birth)
    hits = get_engine().match(ctx, "bazi")
    summary = bazi_an.natal_summary(ctx)
    summary.update({
        "birth": p["datetime"].strftime("%Y-%m-%d %H:%M"),
        "gender": gender,
        "name": name,
        "solar_year": p["solar_year"],
        "month_jie": p["month_jie"],
        "jie_time": p["jie_time"].strftime("%Y-%m-%d %H:%M"),
    })
    return _pack("bazi", summary, hits)


def meihua_report(num_a: int, num_b: int, question: str = "") -> dict:
    g = meihua_an.analyze(num_a, num_b)
    hits = get_engine().match(g, "meihua")
    summary = {
        "num_a": num_a, "num_b": num_b, "question": question,
        "ben_gua": g["ben_gua"], "hu_gua": g["hu_gua"], "bian_gua": g["bian_gua"],
        "dong_yao": g["dong"], "ti": g["ti"], "yong": g["yong"],
        "ti_wuxing": g["ti_wx"], "yong_wuxing": g["yong_wx"],
        "tiyong": g["mh_tiyong"],
        "hu_sheng_ti": g["mh_hu_sheng_ti"],
        "bian_sheng_ti": g["mh_bian_sheng_ti"],
        "bian_ke_ti": g["bian_ke_ti"],
        "yao": g["yao"], "bian_yao": g["bian_yao"],
    }
    return _pack("meihua", summary, hits)


def liuyao_report(yao_values: list[int] | None = None, question: str = "综合",
                  gender: str = "男", seed: int | None = None,
                  dt: datetime | None = None) -> dict:
    vals = yao_values or liuyao_an.qigua(seed)
    g = liuyao_an.analyze(vals, question, dt, gender)
    hits = get_engine().match(g["liuyao"], "liuyao")
    summary = {k: v for k, v in g.items() if k != "liuyao"}
    return _pack("liuyao", summary, hits)


def zeri_report(dt: datetime) -> dict:
    g = zeri_an.analyze(dt)
    hits = get_engine().match(g, "zeri")
    return _pack("zeri", g, hits)


def xingming_report(surname: list[int], given: list[int], full_name: str = "") -> dict:
    g = xm_an.analyze(surname, given, full_name)
    hits = get_engine().match(g, "xingming")
    return _pack("xingming", g, hits)


def _level_by_total(total: float) -> str:
    """流日按命中规则的得分总和定级。

    不用算术平均：流日命中条数本身有信息量，一条 +2 与八条平均 +2
    不是同一回事。总和对「多重冲克叠加」更敏感，适合逐日比较。
    """
    if total >= 4:
        return "大吉"
    if total >= 2:
        return "吉"
    if total > -2:
        return "平"
    if total > -4:
        return "凶"
    return "大凶"


def liuri_report(birth: datetime, gender: str = "男",
                 start: datetime | None = None, days: int = 30,
                 name: str = "") -> dict:
    """某人在一段日期内逐日的运势判定。"""
    p = C.paipan(birth)
    natal = bazi_an.analyze(p["pillars"], gender, birth)
    eng = get_engine()

    start_dt = start or datetime.now(C.CST)
    days = max(1, min(int(days), 366))
    ctxs = liuri_an.day_range(natal, start_dt, days)

    out = []
    background: list[dict] = []
    for ctx in ctxs:
        hits = eng.match(ctx, "liuri")
        # 大运、流年整段区间不变，作为背景展示，不参与逐日计分
        scored = [h for h in hits if not h.get("background")]
        if not background:
            background = [
                {"book": h["book"], "title": h["title"],
                 "verdict": h["then"]["verdict"], "score": h["then"]["score"],
                 "text": h["then"]["text"]}
                for h in hits if h.get("background")
            ]
        total = sum(h["then"].get("score", 0) for h in scored)
        out.append({
            "date": ctx["date"],
            "weekday": ctx["weekday"],
            "ganzhi": ctx["day_ganzhi"],
            "ten_god": ctx["lr_ten_god"],
            "jianchu": ctx["lr_jianchu"],
            "zhishen": ctx["lr_zhishen"],
            "huangdao": ctx["lr_huangdao"],
            "shensha": ctx["lr_shensha"],
            "chong": ctx["lr_chong"],
            "he": ctx["lr_he"],
            "kong": ctx["lr_kong"],
            "score": total,
            "hit_count": len(scored),
            "level": _level_by_total(total),
            "hits": scored,
        })

    ranked = sorted(out, key=lambda d: -d["score"])
    first = out[0] if out else {}

    return {
        "kind": "liuri",
        "summary": {
            "name": name,
            "birth": p["datetime"].strftime("%Y-%m-%d %H:%M"),
            "gender": gender,
            "pillars": p["pillars"],
            "day_master": natal["day_master"],
            "day_master_element": natal["day_master_element"],
            "strength": natal["strength"]["level"],
            "pattern": natal["pattern"],
            "kongwang": natal["kongwang"]["branches"],
            "start": first.get("date", ""),
            "days": len(out),
            "dayun": next(
                (d["ganzhi"] for d in natal.get("dayun", [])
                 if d["start_year"] <= start_dt.year < d["start_year"] + 10), ""),
            "liunian": ctxs[0]["lr_liunian"] if ctxs else "",
            "liunian_ten_god": ctxs[0]["lr_liunian_ten_god"] if ctxs else "",
        },
        "days": out,
        "background": background,
        "best": [{"date": d["date"], "ganzhi": d["ganzhi"], "level": d["level"],
                  "score": d["score"], "ten_god": d["ten_god"]} for d in ranked[:3]],
        "worst": [{"date": d["date"], "ganzhi": d["ganzhi"], "level": d["level"],
                   "score": d["score"], "ten_god": d["ten_god"]} for d in ranked[-3:][::-1]],
        "distribution": {
            lv: sum(1 for d in out if d["level"] == lv)
            for lv in ("大吉", "吉", "平", "凶", "大凶")
        },
        "note": (
            "单日评分 = 当日命中的流日规则得分之和。命中的条目与出处均列在当日明细中，"
            "可逐条核对。分值权重为人为设定，非古籍原文；改变权重会改变排序。"
        ),
        "disclaimer": DISCLAIMER,
    }
