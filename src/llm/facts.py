# -*- coding: utf-8 -*-
"""事实清单：把规则引擎的输出压成一份模型可读、可审计的结构。

这一层是整个大模型功能的地基。原则：
1. 模型看到的**只有**这里的字段，没有原始典籍全文，也没有自由发挥的空间。
2. 每条判断都带 id、书名、分值，模型引用时必须原样带回。
3. 条目有上限，超出部分标注 truncated，避免长命盘把上下文撑爆。
"""

from __future__ import annotations

MAX_HITS = 26
MAX_TEXT = 160


def _trim(text: str, n: int = MAX_TEXT) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _hit(h: dict) -> dict:
    then = h.get("then", {})
    return {
        "id": h.get("id", ""),
        "book": h.get("book", ""),
        "section": h.get("section", ""),
        "title": h.get("title", ""),
        "topic": then.get("topic", ""),
        "verdict": then.get("verdict", ""),
        "score": then.get("score", 0),
        "text": _trim(then.get("text", "")),
        "confidence": h.get("confidence", ""),
    }


def _pick_hits(hits: list[dict], limit: int = MAX_HITS) -> tuple[list[dict], int]:
    """按 |分值| 降序取前 N 条；同分时保持原顺序。返回 (保留, 被截断条数)。"""
    if len(hits) <= limit:
        return [_hit(h) for h in hits], 0
    indexed = list(enumerate(hits))
    ordered = sorted(indexed, key=lambda p: (-abs(p[1].get("then", {}).get("score", 0)), p[0]))
    keep = sorted(ordered[:limit], key=lambda p: p[0])
    return [_hit(h) for _, h in keep], len(hits) - limit


def _base(kind: str, report: dict) -> dict:
    s = report.get("summary", {})
    o = report.get("overall", {})
    return {
        "kind": kind,
        "computed": {
            "day_master": s.get("day_master", ""),
            "day_master_element": s.get("day_master_element", ""),
            "strength": (s.get("strength") if isinstance(s.get("strength"), str)
                         else (s.get("strength") or {}).get("level", "")),
            "pattern": s.get("pattern", ""),
            "pillars": s.get("pillars", []),
            "gender": s.get("gender", ""),
            "birth": s.get("birth", ""),
            "kongwang": s.get("kongwang", []),
            "elements": s.get("element_scores", {}),
            "relations": {k: v for k, v in (s.get("relations") or {}).items() if v},
            "shensha": [x.get("name") for x in (s.get("shensha") or []) if isinstance(x, dict)],
            "tiaohou": {
                "use": (s.get("tiaohou") or {}).get("use", []),
                "hit": [x.get("gan") for x in (s.get("tiaohou") or {}).get("hit", [])],
            },
        },
        "overall": {
            "level": o.get("level", ""),
            "avg_score": o.get("avg_score", 0),
            "hit_count": o.get("hit_count", 0),
            "confidence": o.get("confidence", ""),
        },
    }


def build_bazi(report: dict) -> dict:
    fact = _base("bazi", report)
    hits, cut = _pick_hits(report.get("hits", []))
    fact["judgments"] = hits
    fact["truncated"] = cut
    fact["topics"] = {
        k: {"level": v.get("level"), "score": v.get("score")}
        for k, v in (report.get("topics") or {}).items()
    }
    fact["notes"] = [
        "分值为本项目为排序所赋的权重，非古籍原文。",
        "置信度 A/B/C 指出的可靠性，不指预言的准确度。",
    ]
    return fact


def build_liuri_day(report: dict, day: dict) -> dict:
    s = report.get("summary", {})
    hits, cut = _pick_hits(day.get("hits", []))
    return {
        "kind": "liuri_day",
        "computed": {
            "pillars": s.get("pillars", []),
            "day_master": s.get("day_master", ""),
            "day_master_element": s.get("day_master_element", ""),
            "strength": s.get("strength", ""),
            "pattern": s.get("pattern", ""),
            "date": day.get("date", ""),
            "weekday": day.get("weekday", ""),
            "ganzhi": day.get("ganzhi", ""),
            "ten_god": day.get("ten_god", ""),
            "jianchu": day.get("jianchu", ""),
            "zhishen": day.get("zhishen", ""),
            "huangdao": day.get("huangdao", False),
            "shensha": day.get("shensha", []),
            "chong": day.get("chong", []),
            "he": day.get("he", []),
            "kong": day.get("kong", []),
            "dayun": s.get("dayun", ""),
            "liunian": s.get("liunian", ""),
        },
        "overall": {
            "level": day.get("level", ""),
            "total_score": day.get("score", 0),
            "hit_count": day.get("hit_count", 0),
        },
        "judgments": hits,
        "truncated": cut,
        "background": [
            {"book": b.get("book"), "title": b.get("title"),
             "verdict": b.get("verdict"), "text": _trim(b.get("text", ""), 100)}
            for b in (report.get("background") or [])
        ],
        "range": {
            "start": s.get("start", ""),
            "days": s.get("days", 0),
            "distribution": report.get("distribution", {}),
        },
        "notes": [
            "单日分数是命中规则得分之和，不是概率。",
            "大运、流年整段不变，只作背景，不计入当日分数。",
        ],
    }


def build_liuri_range(report: dict) -> dict:
    s = report.get("summary", {})
    days = report.get("days", [])

    # 区间内哪几条规则反复出现，才是「这段日子的底色」，比逐日罗列更有信息量
    counter: dict[str, dict] = {}
    for d in days:
        for h in d.get("hits", []):
            rid = h.get("id")
            if not rid:
                continue
            rec = counter.get(rid)
            if rec is None:
                rec = {"hit": h, "days": 0}
                counter[rid] = rec
            rec["days"] += 1
    ordered = sorted(
        counter.values(),
        key=lambda r: (-r["days"], -abs(r["hit"].get("then", {}).get("score", 0))),
    )[:12]
    judgments = []
    for rec in ordered:
        item = _hit(rec["hit"])
        item["days"] = rec["days"]
        judgments.append(item)

    return {
        "kind": "liuri_range",
        "computed": {
            "pillars": s.get("pillars", []),
            "day_master": s.get("day_master", ""),
            "day_master_element": s.get("day_master_element", ""),
            "strength": s.get("strength", ""),
            "pattern": s.get("pattern", ""),
            "dayun": s.get("dayun", ""),
            "liunian": s.get("liunian", ""),
            "liunian_ten_god": s.get("liunian_ten_god", ""),
            "start": s.get("start", ""),
            "days": s.get("days", 0),
        },
        "overall": {
            "distribution": report.get("distribution", {}),
            "best": report.get("best", []),
            "worst": report.get("worst", []),
        },
        "judgments": judgments,
        "truncated": max(0, len(counter) - len(judgments)),
        "sample_days": [
            {"date": d["date"], "ganzhi": d["ganzhi"], "level": d["level"],
             "score": d["score"], "ten_god": d["ten_god"],
             "titles": [h["title"] for h in d.get("hits", [])][:4]}
            for d in list(report.get("best", [])) + list(report.get("worst", []))
        ],
        "notes": [
            "等级阈值由实测分布确定，非古籍规定。",
            "区间内逐日互不影响，未推演连续叠加。",
        ],
    }


def build_generic(report: dict) -> dict:
    """六爻、梅花、择日、姓名：结构各异，只取通用字段。"""
    kind = report.get("kind", "")
    fact = _base(kind, report)
    nested = {"wuge", "yongshen_yao", "strokes", "sancai_combo"}
    summary = {
        k: v for k, v in (report.get("summary") or {}).items()
        if isinstance(v, (str, int, float, bool))
        or (isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v))
        or (k in nested and isinstance(v, dict))
    }
    fact["computed"]["summary"] = summary
    hits, cut = _pick_hits(report.get("hits", []))
    fact["judgments"] = hits
    fact["truncated"] = cut
    fact["topics"] = {
        k: {"level": v.get("level"), "score": v.get("score")}
        for k, v in (report.get("topics") or {}).items()
    }
    return fact


def build(report: dict, day: dict | None = None) -> dict:
    kind = report.get("kind", "")
    if kind == "bazi":
        return build_bazi(report)
    if kind == "liuri":
        return build_liuri_day(report, day) if day else build_liuri_range(report)
    return build_generic(report)


def allowed_ids(fact: dict) -> set[str]:
    return {j["id"] for j in fact.get("judgments", []) if j.get("id")}
