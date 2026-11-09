# -*- coding: utf-8 -*-
"""规则引擎：把典籍规则表达成可判定的条件树，逐条匹配命盘并汇总吉凶。

规则 DSL（JSON）
----------------
{
  "id": "YHP-003",
  "book": "渊海子平",
  "system": "bazi",
  "section": "继善篇",
  "title": "伤官见官",
  "when": {"all": [
      {"ten_god_present": "伤官"},
      {"ten_god_present": "正官"}
  ]},
  "then": {"topic": "事业", "verdict": "凶", "score": -3,
           "text": "伤官见官，为祸百端：易有是非争讼、仕途阻滞。"}
}

when 支持 and/or/not 嵌套：
  {"all": [...]}, {"any": [...]}, {"not": {...}}

可用谓词见 PREDICATES。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import tables as T


# ------------------------------------------------------------------ 谓词
def _cmp(a: float, op: str, b: float) -> bool:
    return {
        ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b,
        "==": a == b, "!=": a != b,
    }.get(op, False)


def _get(ctx, key, default=None):
    return ctx.get(key, default)


PREDICATES = {}


def predicate(name):
    def deco(fn):
        PREDICATES[name] = fn
        return fn
    return deco


@predicate("day_master")
def _(ctx, val):
    return ctx["day_master"] in (val if isinstance(val, list) else [val])


@predicate("day_master_element")
def _(ctx, val):
    return ctx["day_master_element"] in (val if isinstance(val, list) else [val])


@predicate("month_branch")
def _(ctx, val):
    return ctx["month_branch"] in (val if isinstance(val, list) else [val])


@predicate("month_branch_element")
def _(ctx, val):
    return T.ZHI_WUXING[ctx["month_branch"]] in (val if isinstance(val, list) else [val])


@predicate("year_branch")
def _(ctx, val):
    return ctx["year_branch"] in (val if isinstance(val, list) else [val])


@predicate("hour_branch")
def _(ctx, val):
    return ctx["hour_branch"] in (val if isinstance(val, list) else [val])


@predicate("ten_god_present")
def _(ctx, val):
    """天干或地支藏干中出现该十神。"""
    names = val if isinstance(val, list) else [val]
    return any(n in ctx["ten_gods_all"] for n in names)


@predicate("ten_god_in_stems")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return any(n in ctx["ten_gods_stems"] for n in names)


@predicate("ten_god_count")
def _(ctx, spec):
    c = ctx["ten_god_counts"].get(spec["name"], 0)
    return _cmp(c, spec.get("op", ">="), spec["value"])


@predicate("element_score")
def _(ctx, spec):
    return _cmp(ctx["element_scores"].get(spec["element"], 0), spec.get("op", ">="), spec["value"])


@predicate("missing_element")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return all(ctx["element_scores"].get(n, 0) < 1.0 for n in names)


@predicate("strength")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return any(ctx["strength"]["level"] == n or ctx["strength"]["label"] == n for n in names)


@predicate("shensha")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    have = {s["name"] for s in ctx["shensha"]}
    return any(n in have for n in names)


@predicate("shensha_absent")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    have = {s["name"] for s in ctx["shensha"]}
    return all(n not in have for n in names)


@predicate("relation")
def _(ctx, spec):
    """spec: {"type": "冲", "branches": ["子","午"]} 或 {"type":"冲"}"""
    rel = ctx["relations"]
    typ = spec.get("type")
    items = rel.get(typ, [])
    if not items:
        return False
    want = spec.get("branches")
    if not want:
        return True
    return any(all(b in item for b in want) for item in items)


@predicate("has_chong")
def _(ctx, val=True):
    return bool(ctx["relations"].get("冲")) == bool(val)


@predicate("nayin_contains")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return any(n in ctx["nayin"] for n in names)


@predicate("nayin_relation")
def _(ctx, spec):
    """纳音五行关系。spec: {"from": 0, "to": 2, "type": "生"}，柱位 0=年 1=月 2=日 3=时。"""
    ny = ctx["nayin_wuxing"]
    a, b = ny[spec.get("from", 0)], ny[spec.get("to", 2)]
    typ = spec.get("type", "生")
    if typ == "生":
        return T.SHENG[a] == b
    if typ == "克":
        return T.KE[a] == b
    if typ == "同":
        return a == b
    return False


@predicate("nayin_chain_sheng")
def _(ctx, spec):
    """纳音链式相生。spec {"start":0,"end":2} 表示 0→1、1→2 依次相生。"""
    ny = ctx["nayin_wuxing"]
    s, e = spec.get("start", 0), spec.get("end", 3)
    return all(T.SHENG[ny[i]] == ny[i + 1] for i in range(s, e))


@predicate("element_extreme")
def _(ctx, spec):
    """任一五行占比越过阈值。spec {"op": ">", "value": 45}"""
    vals = list(ctx["element_scores"].values())
    op, v = spec.get("op", ">"), spec["value"]
    return any(_cmp(x, op, v) for x in vals)


@predicate("element_balanced")
def _(ctx, spec):
    """五行最大值与最小值之差。"""
    vals = list(ctx["element_scores"].values())
    return _cmp(max(vals) - min(vals), spec.get("op", "<"), spec["value"])


@predicate("pillar_chong")
def _(ctx, pair):
    """指定两柱地支相冲。pair: [0, 2] 表示年柱与日柱。"""
    zhis = ctx["branches"]
    a, b = zhis[pair[0]], zhis[pair[1]]
    return T.ZHI_CHONG.get(a) == b


@predicate("shensha_count")
def _(ctx, spec):
    return _cmp(len(ctx["shensha"]), spec.get("op", ">="), spec["value"])


@predicate("ten_god_group_count")
def _(ctx, spec):
    groups = {
        "财": ["正财", "偏财"],
        "官": ["正官", "七杀"],
        "印": ["正印", "偏印"],
        "食伤": ["食神", "伤官"],
        "比劫": ["比肩", "劫财"],
    }
    names = groups.get(spec["group"], [spec["group"]])
    c = sum(ctx["ten_god_counts"].get(n, 0) for n in names)
    return _cmp(c, spec.get("op", ">="), spec["value"])


@predicate("kongwang")
def _(ctx, val):
    """命局某柱地支是否落空亡。val 可为柱位索引或 True（任一支）。"""
    kw = ctx["kongwang"]["branches"]
    zhis = ctx["branches"]
    if val is True:
        return any(z in kw for z in zhis)
    if isinstance(val, int):
        return zhis[val] in kw
    return False


@predicate("tiaohou_hit")
def _(ctx, spec):
    """调候用神命中。rank=1 指第一用神；rank=2 指第二/第三用神（不含第一）。"""
    rank = spec.get("rank", 1) if isinstance(spec, dict) else 1
    hit = ctx["tiaohou"]["hit"]
    if not hit:
        return False
    if rank == 1:
        return any(h["rank"] == 1 for h in hit)
    if rank == 2:
        return any(h["rank"] >= 2 for h in hit)
    return bool(hit)


@predicate("tiaohou_missing")
def _(ctx, val=True):
    miss = not ctx["tiaohou"]["hit"]
    return miss == bool(val)


@predicate("gender")
def _(ctx, val):
    return ctx["gender"] == val


@predicate("pattern")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return any(ctx["pattern"] == n for n in names)


@predicate("branch_count")
def _(ctx, spec):
    return _cmp(ctx["branches"].count(spec["branch"]), spec.get("op", ">="), spec["value"])


@predicate("dayun_has")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return any(d["ganzhi"] in names for d in ctx.get("dayun", []))


@predicate("age_range")
def _(ctx, spec):
    age = ctx.get("age")
    if age is None:
        return False
    return spec[0] <= age <= spec[1]


# ------------------------------------------------------------------ 其他术数体系谓词
# 这些谓词只读取对应分析器构造的上下文字段，缺字段时一律返回 False。

@predicate("zw_has_main")
def _(ctx, val=True):
    return bool(ctx.get("zw_main_stars")) == bool(val)


@predicate("zw_bright")
def _(ctx, val):
    names = val if isinstance(val, list) else [val]
    return ctx.get("zw_bright") in names


@predicate("zw_ji_count")
def _(ctx, spec):
    return _cmp(ctx.get("zw_ji_count", 0), spec.get("op", ">="), spec["value"])


@predicate("zw_sha_count")
def _(ctx, spec):
    return _cmp(ctx.get("zw_sha_count", 0), spec.get("op", ">="), spec["value"])


@predicate("zw_sihua_in_ming")
def _(ctx, val):
    return ctx.get("zw_sihua_in_ming") == val


@predicate("zw_sanfang_has")
def _(ctx, val):
    """三方四正中至少出现列表中的两颗星。"""
    names = val if isinstance(val, list) else [val]
    pool = set(ctx.get("zw_sanfang", []))
    return sum(1 for n in names if n in pool) >= min(2, len(names))


@predicate("ly_shi_state")
def _(ctx, val):
    return ctx.get("ly_shi_state") == val


@predicate("ly_yongshen_state")
def _(ctx, val):
    return ctx.get("ly_yongshen_state") == val


@predicate("ly_hex_type")
def _(ctx, val):
    return ctx.get("ly_hex_type") == val


@predicate("ly_yongshen_huajin")
def _(ctx, val):
    return ctx.get("ly_yongshen_huajin") == val


@predicate("ly_jishen_dong")
def _(ctx, val=True):
    return bool(ctx.get("ly_jishen_dong")) == bool(val)


@predicate("ly_yongshen_ke_shi")
def _(ctx, val=True):
    return bool(ctx.get("ly_yongshen_ke_shi")) == bool(val)


@predicate("ly_question")
def _(ctx, val):
    return ctx.get("ly_question") == val


@predicate("ly_yongshen_hidden")
def _(ctx, val=True):
    return bool(ctx.get("ly_yongshen_hidden")) == bool(val)


@predicate("ly_shi_ying")
def _(ctx, val):
    return ctx.get("ly_shi_ying") == val


@predicate("mh_tiyong")
def _(ctx, val):
    return ctx.get("mh_tiyong") == val


@predicate("mh_hu_sheng_ti")
def _(ctx, val=True):
    return bool(ctx.get("mh_hu_sheng_ti")) == bool(val)


@predicate("mh_bian_sheng_ti")
def _(ctx, val=True):
    return bool(ctx.get("mh_bian_sheng_ti")) == bool(val)


@predicate("zeri_jianchu_jixiong")
def _(ctx, val):
    return ctx.get("zeri_jianchu_jixiong") == val


@predicate("zeri_huangdao")
def _(ctx, val=True):
    return bool(ctx.get("zeri_huangdao")) == bool(val)


@predicate("zy_dong_count")
def _(ctx, spec):
    return _cmp(ctx.get("zy_dong_count", 0), spec.get("op", ">="), spec["value"])


@predicate("xm_shuli")
def _(ctx, spec):
    ge = spec["ge"]
    want = spec["jixiong"] if isinstance(spec["jixiong"], list) else [spec["jixiong"]]
    return ctx.get("xm_shuli", {}).get(ge) in want


@predicate("xm_sancai")
def _(ctx, val):
    return ctx.get("xm_sancai") == val


# ---------------------------------------------------------------- 流日
@predicate("lr_ten_god")
def _(ctx, val):
    """流日天干对日主的十神。val 可为单值或列表。"""
    want = val if isinstance(val, list) else [val]
    return ctx.get("lr_ten_god") in want


@predicate("lr_in")
def _(ctx, spec):
    """通用：ctx[spec['field']] 列表中是否含任一指定值。"""
    vals = spec["value"] if isinstance(spec["value"], list) else [spec["value"]]
    have = ctx.get(spec["field"], [])
    return any(v in have for v in vals)


@predicate("lr_empty")
def _(ctx, field):
    """通用：ctx[field] 为空（无冲无合之类）。"""
    return not ctx.get(field)


@predicate("lr_not_empty")
def _(ctx, field):
    """通用：ctx[field] 非空（存在冲/合/伏吟之类）。"""
    return bool(ctx.get(field))


@predicate("lr_equal")
def _(ctx, spec):
    """通用：ctx[spec['field']] 等于某值。"""
    return ctx.get(spec["field"]) == spec["value"]


@predicate("lr_jianchu")
def _(ctx, val):
    want = val if isinstance(val, list) else [val]
    return ctx.get("lr_jianchu") in want


@predicate("lr_huangdao")
def _(ctx, val=True):
    return bool(ctx.get("lr_huangdao")) == bool(val)


@predicate("lr_kong")
def _(ctx, val=True):
    return bool(ctx.get("lr_kong")) == bool(val)


@predicate("lr_sanhe")
def _(ctx, val=True):
    return bool(ctx.get("lr_sanhe")) == bool(val)


@predicate("lr_shensha")
def _(ctx, val):
    """当日是否为某神煞日。"""
    want = val if isinstance(val, list) else [val]
    have = ctx.get("lr_shensha", [])
    return any(v in have for v in want)


@predicate("lr_dayun_ten_god")
def _(ctx, val):
    want = val if isinstance(val, list) else [val]
    return ctx.get("lr_dayun_ten_god") in want


@predicate("lr_liunian_ten_god")
def _(ctx, val):
    want = val if isinstance(val, list) else [val]
    return ctx.get("lr_liunian_ten_god") in want


# ------------------------------------------------------------------ 求值
def eval_when(when, ctx) -> bool:
    if when is None:
        return True
    if "all" in when:
        return all(eval_when(w, ctx) for w in when["all"])
    if "any" in when:
        return any(eval_when(w, ctx) for w in when["any"])
    if "not" in when:
        return not eval_when(when["not"], ctx)
    if len(when) != 1:
        raise ValueError(f"无法解析的条件: {when}")
    key, val = next(iter(when.items()))
    fn = PREDICATES.get(key)
    if fn is None:
        raise ValueError(f"未知谓词: {key}")
    return fn(ctx, val)


# ------------------------------------------------------------------ 引擎
class RuleEngine:
    def __init__(self, rules: list[dict]):
        self.rules = rules

    @classmethod
    def from_file(cls, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["rules"])

    def match(self, ctx, system: str = "bazi") -> list[dict]:
        hits = []
        for r in self.rules:
            if r.get("system", "bazi") != system:
                continue
            try:
                if eval_when(r["when"], ctx):
                    hits.append(r)
            except Exception as exc:  # 单条规则异常不应中断整体
                r.setdefault("_errors", []).append(str(exc))
        return hits

    def score_by_topic(self, hits: list[dict]) -> dict:
        out = {}
        for r in hits:
            topic = r["then"].get("topic", "综合")
            out.setdefault(topic, {"score": 0, "items": []})
            out[topic]["score"] += r["then"].get("score", 0)
            out[topic]["items"].append(r)
        for topic, d in out.items():
            s = d["score"]
            if s >= 4:
                d["level"] = "大吉"
            elif s >= 2:
                d["level"] = "吉"
            elif s > -2:
                d["level"] = "平"
            elif s > -4:
                d["level"] = "凶"
            else:
                d["level"] = "大凶"
            d["items"].sort(key=lambda x: -abs(x["then"].get("score", 0)))
        return dict(sorted(out.items(), key=lambda kv: -abs(kv[1]["score"])))


def load_rules(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["rules"]
