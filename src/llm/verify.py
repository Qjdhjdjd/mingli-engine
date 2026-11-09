# -*- coding: utf-8 -*-
"""输出校验：判断模型写的东西有没有超出事实清单。

这是「大模型解读」能不能被信任的分界线。提示词可以被忽略，
但生成之后的文本是可检查的：引用了哪些编号、哪些句子下了判断却没有出处、
有没有编造分值、有没有绝对化断言。

校验不通过不等于文本错误，而是说明它超出了「解释已命中规则」的边界。
"""

from __future__ import annotations

import re

SECTION_MARKS = ("【模型推断】", "[模型推断]", "## 模型推断", "### 模型推断")

# 规则编号形如 YHP-001 / WXJ-02 / LR-17
ID_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,6}-\d{1,3})(?![0-9])")

# 归一化后用于判定「这句话在下吉凶结论」
VERDICT_WORDS = ("吉", "凶", "宜", "忌", "利", "妨", "损", "益", "祸", "福")

# 形如「+3 分」「−2分」
SCORE_RE = re.compile(r"([+\-−])\s?(\d{1,2})\s*分")

OVERCLAIM_RE = re.compile(
    r"必然|必定|一定会|注定|百分之[百九]|绝对|铁定|包准"
    r"|\d+\s*%\s*(?:的)?(?:概率|几率|把握|可能)"
)

SENT_SPLIT = re.compile(r"(?<=[。！？；\n])")

# 「大吉 3 天、吉 20 天」这类纯计数复述，是对整体分布的引用，不算新判断
AGGREGATE_RE = re.compile(r"(大吉|吉|平|凶|大凶)\s*\d+\s*天|\d+\s*天[^。]{0,20}(大吉|凶|大凶)")

# 「综合判定为吉」这类复述引擎已算出的总评等级，同样不算新判断
LEVEL_RESTATE_RE = re.compile(
    r"(?:判定为|判为|等级为|评为|总评)[^。！？]{0,6}[「\"]?(大吉|吉|平|凶|大凶)"
)


def _norm_id(token: str) -> str:
    return token.upper().replace(" ", "")


def split_speculation(text: str) -> tuple[str, str]:
    """把正文与「模型推断」段切开。"""
    for mark in SECTION_MARKS:
        if mark in text:
            head, _, tail = text.partition(mark)
            return head, tail.strip()
    return text, ""


def _paragraphs(text: str) -> list[list[str]]:
    """按行切段，段内按句切分。段内的编号视为对前文的引用。"""
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sents = [s.strip() for s in SENT_SPLIT.split(line) if len(s.strip()) >= 3]
        if sents:
            out.append(sents)
    return out


def verify(text: str, allowed_ids: set[str], allowed_scores: set[int] | None = None,
           mode: str = "strict") -> dict:
    """返回校验结果。ok 为 False 时，调用方应重写或降级。"""
    strict_part, speculation = split_speculation(text or "")
    allowed = {_norm_id(i) for i in allowed_ids}
    scores = set(allowed_scores or []) | {0}

    cited_all = [_norm_id(m) for m in ID_RE.findall(strict_part)]
    cited = sorted(set(cited_all))
    unknown = sorted({c for c in cited if c not in allowed}) if allowed else []

    unsupported: list[dict] = []
    supported_count = 0
    for sents in _paragraphs(strict_part):
        buf: list[str] = []
        for sent in sents:
            buf.append(sent)
            if ID_RE.search(sent):
                # 编号置于句末时，视为对该段之前整串句子的引用
                supported_count += len(buf)
                buf = []
        for sent in buf:
            if AGGREGATE_RE.search(sent) or LEVEL_RESTATE_RE.search(sent):
                continue
            # 「吉凶」「宜忌」是中性名词，不构成判断
            scan = sent.replace("吉凶", "").replace("凶吉", "").replace("宜忌", "")
            hit_words = [w for w in VERDICT_WORDS if w in scan]
            if hit_words:
                unsupported.append({"sentence": sent[:120], "reason": "".join(hit_words[:2])})

    invented = []
    for sign, num in SCORE_RE.findall(strict_part):
        val = int(num) * (-1 if sign in "-−" else 1)
        if val not in scores and abs(val) not in {abs(s) for s in scores}:
            invented.append(f"{sign}{num} 分")

    overclaims = sorted(set(OVERCLAIM_RE.findall(strict_part)))

    # 推断段里的编号同样要检查（模型可能借编号伪装出处）
    spec_ids = sorted({_norm_id(m) for m in ID_RE.findall(speculation)})
    spec_unknown = [i for i in spec_ids if i not in allowed]

    total = len(allowed)
    cov = len([c for c in cited if c in allowed])
    ratio = cov / total if total else 1.0
    unsupported_ratio = len(unsupported) / max(1, supported_count + len(unsupported))

    problems: list[str] = []
    if unknown:
        problems.append(f"引用了不存在的规则编号：{'、'.join(unknown)}")
    if spec_unknown:
        problems.append(f"「模型推断」段伪造了编号：{'、'.join(spec_unknown)}")
    if invented:
        problems.append(f"编造了分值与：{'、'.join(sorted(set(invented)))}")
    if overclaims:
        problems.append(f"使用了绝对化措辞：{'、'.join(overclaims)}")
    if unsupported_ratio > 0.2:
        problems.append(
            f"{len(unsupported)} 句下了吉凶判断却没有标注规则编号（占比 {unsupported_ratio:.0%}）"
        )
    if total and cov == 0:
        problems.append("全文没有引用任何一条规则，无法溯源")

    ok = not problems

    return {
        "ok": ok,
        "problems": problems,
        "cited": [c for c in cited if c in allowed],
        "unknown_ids": unknown + spec_unknown,
        "unsupported": unsupported[:8],
        "unsupported_count": len(unsupported),
        "invented_scores": sorted(set(invented)),
        "overclaims": overclaims,
        "coverage": {
            "cited": cov,
            "total": total,
            "ratio": round(ratio, 3),
            "level": ("充分" if ratio >= 0.6 else "部分" if ratio >= 0.3 else "偏低"),
        },
        "speculation": {
            "present": bool(speculation),
            "chars": len(speculation),
            "text": speculation,
            "fake_ids": spec_unknown,
        },
        "mode": mode,
    }


def describe(v: dict) -> str:
    """给界面用的一行中文结论。"""
    if v["ok"]:
        bits = [f"引用规则 {v['coverage']['cited']}/{v['coverage']['total']} 条"]
        if v["speculation"]["present"]:
            bits.append("含独立标注的模型推断")
        return "校验通过 · " + " · ".join(bits)
    return "校验未通过：" + "；".join(v["problems"])
