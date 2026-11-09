# -*- coding: utf-8 -*-
"""八字分析器：把四柱排盘转换为规则引擎的判定上下文。"""

from __future__ import annotations

from datetime import datetime

from .. import calendar_core as C
from .. import tables as T


def build_pattern(day_master: str, month_zhi: str) -> str:
    """以月令本气藏干对应的十神定格。"""
    benqi = T.ZHI_CANGGAN[month_zhi][0]
    ss = C.shishen(day_master, benqi)
    mapping = {
        "正官": "正官格", "七杀": "七杀格",
        "正财": "财格", "偏财": "财格",
        "正印": "印格", "偏印": "印格",
        "食神": "食神格", "伤官": "伤官格",
    }
    if ss in mapping:
        return mapping[ss]
    # 比劫：月支为日干禄 -> 建禄格，否则月刃格
    if month_zhi == T.LU.get(day_master):
        return "建禄格"
    if month_zhi == T.YANGREN.get(day_master):
        return "月刃格"
    return "比劫格"


def tiaohou_info(day_master: str, month_zhi: str, pillars: list[str]) -> dict:
    """检查《穷通宝鉴》调候用神是否现于命局（天干透出或地支藏干）。"""
    use = T.TIAOHOU.get(day_master, {}).get(month_zhi, [])
    stems = [pillars[0][0], pillars[1][0], pillars[3][0]]  # 不含日干本身
    hidden = []
    for p in pillars:
        hidden.extend(T.ZHI_CANGGAN[p[1]])
    hit = []
    for rank, gan in enumerate(use, start=1):
        where = []
        if gan in stems:
            where.append("天干")
        if gan in hidden:
            where.append("地支")
        if where:
            hit.append({"gan": gan, "rank": rank, "where": where})
    return {"use": use, "hit": hit, "month_branch": month_zhi}


def analyze(pillars: list[str], gender: str = "男",
            birth: datetime | None = None, age: int | None = None,
            dayun_count: int = 8) -> dict:
    year_gz, month_gz, day_gz, hour_gz = pillars
    dm = day_gz[0]
    branches = [p[1] for p in pillars]
    stems = [p[0] for p in pillars]

    # 十神（日干位置标为「日主」，不参与十神计数）
    ten_gods_stems = ["日主" if i == 2 else C.shishen(dm, g) for i, g in enumerate(stems)]
    hidden_gods = []
    for p in pillars:
        for cg in T.ZHI_CANGGAN[p[1]]:
            hidden_gods.append(C.shishen(dm, cg))
    ten_gods_all = [g for g in ten_gods_stems if g != "日主"] + hidden_gods

    counts = {}
    for g in ten_gods_all:
        counts[g] = counts.get(g, 0) + 1

    scores = C.element_scores(pillars)
    strength = C.day_master_strength(pillars)
    relations = C.branch_relations(branches)
    shensha = C.shensha(pillars)
    nayin_pairs = [C.nayin(p) for p in pillars]
    kw = C.xunkong(day_gz)

    ctx = {
        "pillars": pillars,
        "stems": stems,
        "branches": branches,
        "day_master": dm,
        "day_master_element": T.GAN_WUXING[dm],
        "month_branch": branches[1],
        "year_branch": branches[0],
        "hour_branch": branches[3],
        "gender": gender,
        "ten_gods_stems": ten_gods_stems,
        "ten_gods_all": ten_gods_all,
        "ten_god_counts": counts,
        "element_scores": scores,
        "strength": strength,
        "relations": relations,
        "shensha": shensha,
        "nayin": [x[0] for x in nayin_pairs],
        "nayin_wuxing": [x[1] for x in nayin_pairs],
        "kongwang": {"branches": list(kw), "xun": day_gz},
        "tiaohou": tiaohou_info(dm, branches[1], pillars),
        "pattern": build_pattern(dm, branches[1]),
        "age": age,
    }

    if birth is not None:
        ctx["dayun"] = C.dayun(pillars, birth, gender, dayun_count)
    else:
        ctx["dayun"] = []

    return ctx


def natal_summary(ctx: dict) -> dict:
    """整理成便于展示的排盘摘要。"""
    pillars = ctx["pillars"]
    return {
        "pillars": pillars,
        "stems": ctx["stems"],
        "branches": ctx["branches"],
        "ten_gods_stems": ctx["ten_gods_stems"],
        "canggan": [T.ZHI_CANGGAN[b] for b in ctx["branches"]],
        "nayin": ctx["nayin"],
        "day_master": ctx["day_master"],
        "day_master_element": ctx["day_master_element"],
        "strength": ctx["strength"],
        "pattern": ctx["pattern"],
        "element_scores": ctx["element_scores"],
        "relations": ctx["relations"],
        "shensha": ctx["shensha"],
        "kongwang": ctx["kongwang"]["branches"],
        "tiaohou": ctx["tiaohou"],
        "dayun": ctx.get("dayun", []),
        "changsheng": [C.changsheng(ctx["day_master"], b) for b in ctx["branches"]],
    }
