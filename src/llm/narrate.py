# -*- coding: utf-8 -*-
"""解读编排：事实清单 -> 模型 -> 校验 -> （必要时）重写或降级。

两条路径：
- 在线：调用配置好的模型，生成后必过校验。
- 离线：本地模板叙述，同样带编号、同样过校验。

离线路径不是「凑数的兜底」，它是这个功能的基准线：没配模型时也能用，
而且它证明「带出处地讲清结论」这件事不需要大模型也能做到。
"""

from __future__ import annotations

import time

from . import facts, prompts, provider, verify

FALLBACK_NOTE = (
    "本次由本地模板生成（未调用大模型）。模板只重述规则库已有条目，不做语言发挥。"
)


def _cite(hit: dict) -> str:
    return f"[{hit['id']}]" if hit.get("id") else ""


def _one_line(hit: dict, days: int | None = None) -> str:
    book = hit.get("book") or "未详"
    section = f"·{hit['section']}" if hit.get("section") else ""
    freq = f"（区间内出现 {days} 天）" if days else ""
    return f"《{book}》{section}「{hit['title']}」{freq}：{hit['text']} {_cite(hit)}"


def _template_bazi(fact: dict) -> str:
    c = fact["computed"]
    o = fact["overall"]
    js = fact["judgments"]
    pos = [h for h in js if h["score"] > 0]
    neg = [h for h in js if h["score"] < 0]
    neu = [h for h in js if h["score"] == 0]

    month_zhi = c["pillars"][1][1] if len(c.get("pillars", [])) >= 2 else "?"
    elem = "、".join(f"{k}{v:.0f}%" for k, v in
                    sorted((c.get("elements") or {}).items(), key=lambda kv: -kv[1])[:3])

    out = ["## 命局概要"]
    out.append(
        f"{c.get('day_master','?')}{c.get('day_master_element','')}日主，生于{month_zhi}月，"
        f"按同类占比判为{c.get('strength') or '未判'}，格局取「{c.get('pattern') or '未定'}」。"
        f"四柱为{' '.join(c.get('pillars', []))}。五行占比最高的三项是{elem or '—'}。"
    )
    if c.get("shensha"):
        out.append(f"命局所见神煞为{'、'.join(c['shensha'][:8])}，神煞只作参看，不入主判。")
    if c.get("relations"):
        rel = "；".join(f"{k}{''.join(v)}" for k, v in c["relations"].items())
        out.append(f"地支刑冲合害为{rel}，属结构信息，具体吉凶由下列条目分判。")

    out.append("\n## 主要依据")
    if not js:
        out.append("本次没有命中任何规则条目，因此不给出倾向判断。")
    else:
        out.append(f"规则库共命中 {len(js)} 条，其中偏正向 {len(pos)} 条、偏负向 {len(neg)} 条、"
                   f"中性 {len(neu)} 条。以下按原书条目列出。")
        for h in (pos + neu)[:8]:
            out.append(_one_line(h))

    out.append("\n## 需要注意")
    if neg:
        for h in neg[:5]:
            out.append(_one_line(h))
    else:
        out.append("本次未命中偏负向的条目，但这不等于没有风险，只说明规则库在这张盘上没有对应条款。")

    out.append("\n## 一句话")
    out.append(
        f"综合判定为「{o.get('level')}」，命中 {o.get('hit_count')} 条，均分 {o.get('avg_score'):+}。"
        "分值权重由本项目人为设定，改权重就会改结论；它表达的是典籍条目的分布，不是事件概率。"
    )
    return "\n".join(out)


def _template_liuri_day(fact: dict) -> str:
    c = fact["computed"]
    o = fact["overall"]
    js = fact["judgments"]
    neg = [h for h in js if h["score"] < 0]
    rest = [h for h in js if h["score"] >= 0]

    def pos_name(p: str) -> str:
        return f"{p}支" if p in ("年", "月", "日", "时") else p

    out = ["## 命局概要"]
    out.append(
        f"{c.get('date')}（周{c.get('weekday')}）为{c.get('ganzhi')}日，"
        f"对{c.get('day_master')}{c.get('day_master_element')}日主而言，日干所值为「{c.get('ten_god')}」。"
        f"当日建除为「{c.get('jianchu')}」，值神「{c.get('zhishen')}」，"
        f"{'属黄道日' if c.get('huangdao') else '属黑道日'}。"
        f"所处大运为{c.get('dayun') or '未起运'}，流年{c.get('liunian')}。"
    )
    if c.get("shensha"):
        out.append(f"当日神煞见{'、'.join(c['shensha'][:8])}。")
    if c.get("chong"):
        out.append(f"当日地支与命局相冲：{'、'.join(pos_name(x) for x in c['chong'])}。")
    if c.get("he"):
        out.append(f"当日地支与命局相合：{'、'.join(pos_name(x) for x in c['he'])}。")

    out.append("\n## 主要依据")
    if not js:
        out.append("当日没有命中任何流日规则，因此不作倾向判断。")
    else:
        out.append(f"当日共命中 {len(js)} 条规则，合计得分 {o.get('total_score'):+}。")
        for h in rest[:6]:
            out.append(_one_line(h))

    out.append("\n## 需要注意")
    if neg:
        for h in neg[:4]:
            out.append(_one_line(h))
    else:
        out.append("当日没有命中偏负向的条目，但逐日判定只做静态比对，不推演连续影响。")

    out.append("\n## 一句话")
    out.append(
        f"当日判为「{o.get('level')}」。这个等级来自命中条目的代数和，"
        "不是事件发生的可能性；大运与流年整段不变，未计入当日分数。"
    )
    return "\n".join(out)


def _template_liuri_range(fact: dict) -> str:
    c = fact["computed"]
    o = fact["overall"]
    dist = o.get("distribution", {})
    dist_txt = "、".join(f"{k} {dist.get(k, 0)} 天" for k in ("大吉", "吉", "平", "凶", "大凶"))

    out = ["## 命局概要"]
    out.append(
        f"{c.get('day_master','?')}{c.get('day_master_element','')}日主，"
        f"四柱为{' '.join(c.get('pillars', []))}，判为{c.get('strength') or '未判'}，"
        f"格局「{c.get('pattern') or '未定'}」。所查区间自{c.get('start')}起共 {c.get('days')} 天，"
        f"其间大运{c.get('dayun') or '未起运'}，流年{c.get('liunian')}（{c.get('liunian_ten_god')}）。"
    )
    out.append(f"区间等级分布为：{dist_txt}。")

    out.append("\n## 主要依据")
    js = fact.get("judgments", [])
    if js:
        top = js[:5]
        out.append(f"区间内反复出现的规则共 {len(js)} 条，以下按出现天数排列，它们构成这段日子的底色。")
        for h in top:
            out.append(_one_line(h, h.get("days")))
    best, worst = o.get("best", []), o.get("worst", [])
    if best:
        b = best[0]
        out.append(f"单日得分最高的是{b['date']}（{b['ganzhi']}，{b['ten_god']}），合计 {b['score']:+}。")
    if worst:
        w = worst[0]
        out.append(f"单日得分最低的是{w['date']}（{w['ganzhi']}，{w['ten_god']}），合计 {w['score']:+}。")
    out.append("逐日明细与每条规则的出处均列在日历与当日详情中，可逐条核对。")

    out.append("\n## 需要注意")
    out.append(
        "区间内每一天都是独立比对命局，日与日之间的连锁（连续叠煞、交节换气）没有推演，"
        "所以相邻两天的分数不构成趋势线。"
    )

    out.append("\n## 一句话")
    out.append(
        "这张表回答的是「按典籍条款，哪些日子与命局更相合」，"
        "不是「哪些日子会出事」，两者之间没有可验证的等号。"
    )
    return "\n".join(out)


def _template_generic(fact: dict) -> str:
    kind = fact.get("kind", "")
    s = (fact.get("computed") or {}).get("summary") or {}
    o = fact["overall"]
    js = fact["judgments"]

    out = ["## 命局概要"]
    if kind == "liuyao":
        ys = s.get("yongshen_yao") or {}
        out.append(
            f"所问「{s.get('question')}」，主卦「{s.get('name')}」（{s.get('gua')}），"
            f"变卦「{s.get('bian_name')}」，属{s.get('gong')}宫{s.get('gong_wuxing')}。"
            f"世在{s.get('shi')}爻、应在{s.get('ying')}爻，为{s.get('type')}卦。"
            f"用神取{s.get('yongshen')}，落{ys.get('pos', '—')}爻（{ys.get('zhi', '')}{ys.get('wuxing', '')}），"
            f"在{('月建' + str(s.get('month_zhi')))}、{('日辰' + str(s.get('day_ganzhi')))}下判为{s.get('yongshen_state')}，"
            f"世爻状态为{s.get('shi_state')}。"
        )
    elif kind == "meihua":
        out.append(
            f"报数 {s.get('num_a')} 与 {s.get('num_b')} 起卦，得{s.get('ben_gua')}，"
            f"动爻在第 {s.get('dong_yao')} 爻，互卦{s.get('hu_gua')}，变卦{s.get('bian_gua')}。"
            f"体卦{s.get('ti')}（{s.get('ti_wuxing')}），用卦{s.get('yong')}（{s.get('yong_wuxing')}），"
            f"体用关系为「{s.get('tiyong')}」。"
        )
    elif kind == "zeri":
        out.append(
            f"{s.get('date')} 为 {s.get('day_ganzhi')} 日，月建 {s.get('month_zhi')}"
            f"（{s.get('month_jie')} 后），建除为「{s.get('jianchu')}」，"
            f"值神「{s.get('zhishen')}」，{'属黄道日' if s.get('huangdao') else '属黑道日'}。"
            f"通书所载当日行事：{s.get('yi') or '—'}。"
        )
    elif kind == "xingming":
        w = s.get("wuge") or {}
        seg = "、".join(
            f"{k}{v.get('num')}（{v.get('wuxing')}）"
            for k, v in w.items() if isinstance(v, dict)
        )
        out.append(
            f"姓名「{s.get('name')}」，按康熙笔画推五格：{seg}。"
            f"三才配置为{s.get('sancai_combo')}，判为{s.get('sancai')}。"
            "各个数理的具体吉凶见下方命中条目。"
        )
    else:
        pairs = [f"{k}={v}" for k, v in s.items()
                 if isinstance(v, (str, int, float))][:8]
        out.append(f"起局参数为：{'；'.join(pairs) or '—'}。")

    out.append("\n## 主要依据")
    if not js:
        out.append("本次没有命中任何规则条目，因此不给出倾向判断。")
    else:
        out.append(f"共命中 {len(js)} 条，逐条列示如下。")
        for h in js[:10]:
            out.append(_one_line(h))

    out.append("\n## 需要注意")
    caveats = {
        "liuyao": "六爻旺衰只做了月建日辰的生克冲合，未及伏神、旬空、进退神的连锁，实际可靠性低于八字部分。",
        "xingming": "五格所用笔画须按康熙字典口径手填；三才判定目前只分相生与相克两档，未接入 125 种配置表。",
        "meihua": "体用生克只取主卦与变卦两层，未参互卦之外的错综之象。",
        "zeri": "建除与黄道的吉凶倾向在不同通书间有出入，本库择一而从。",
    }
    out.append(caveats.get(kind, "分值权重为人为设定；同一局在不同流派下可能得出相反结论，本库保留分歧、不强行统一。"))

    out.append("\n## 一句话")
    out.append(
        f"综合判定为「{o.get('level')}」，命中 {o.get('hit_count')} 条，均分 {o.get('avg_score'):+}。"
        "这一结论来自上列条目的加权，不是对现实的预测。"
    )
    return "\n".join(out)


def template_text(fact: dict) -> str:
    kind = fact.get("kind", "")
    if kind == "bazi":
        return _template_bazi(fact)
    if kind == "liuri_day":
        return _template_liuri_day(fact)
    if kind == "liuri_range":
        return _template_liuri_range(fact)
    return _template_generic(fact)


def _scores(fact: dict) -> set[int]:
    vals = {int(h.get("score", 0)) for h in fact.get("judgments", [])}
    overall = fact.get("overall", {})
    for key in ("avg_score", "total_score"):
        v = overall.get(key)
        if isinstance(v, (int, float)):
            vals.add(int(round(v)))
    return vals


def narrate(report: dict, day: dict | None = None, mode: str = "strict",
            use_llm: bool = True, question: str = "",
            repair: bool = True, cfg: provider.LLMConfig | None = None) -> dict:
    """生成解读。永远返回可展示的结果，不因模型故障抛异常。"""
    started = time.time()
    fact = facts.build(report, day)
    allowed = facts.allowed_ids(fact)
    scores = _scores(fact)
    fallback_reason = None
    online = False
    text = ""
    model = "local-template"
    prov = "template"
    usage: dict = {}

    if use_llm:
        try:
            cfg = cfg or provider.resolve_config()
            res = provider.chat(prompts.build(fact, mode, question), cfg)
            text, model, prov, online = res["text"], res["model"], res["provider"], True
            usage = res.get("usage", {})
        except provider.LLMNotConfigured as exc:
            fallback_reason = str(exc)
        except provider.LLMError as exc:
            fallback_reason = f"调用模型失败：{exc}"

    if online:
        v = verify.verify(text, allowed, scores, mode)
        # 只对「编造出处/分值」这类硬伤重写；措辞问题保留并如实展示
        if not v["ok"] and repair and (v["unknown_ids"] or v["invented_scores"]):
            try:
                cfg = cfg or provider.resolve_config()
                res = provider.chat(prompts.build_repair(text, v["problems"]), cfg)
                text = res["text"]
                v = verify.verify(text, allowed, scores, mode)
            except provider.LLMError as exc:
                fallback_reason = f"重写失败：{exc}"

        if v["unknown_ids"] or v["invented_scores"]:
            # 编造出处是不可接受的，直接降级
            fallback_reason = (fallback_reason or "") + "模型输出了不存在的出处，已降级为本地模板。"
            text, online, model, prov = template_text(fact), False, "local-template", "template"
            v = verify.verify(text, allowed, scores, mode)
    else:
        text = template_text(fact)
        v = verify.verify(text, allowed, scores, mode)

    return {
        "text": text,
        "mode": mode,
        "online": online,
        "provider": prov,
        "model": model,
        "fallback_reason": fallback_reason,
        "verification": v,
        "verification_text": verify.describe(v),
        "fact_count": len(fact.get("judgments", [])),
        "truncated": fact.get("truncated", 0),
        "elapsed_ms": int((time.time() - started) * 1000),
        "usage": usage,
        "disclaimer": (
            "解读由语言模型对规则库输出进行改写，事实与出处以命中条目为准。"
            "校验通过仅表示未超出给定规则，不代表命理结论成立。"
        ),
    }
