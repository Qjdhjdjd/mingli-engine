# -*- coding: utf-8 -*-
"""提示词：把模型限制成「解释器」，而不是「算命先生」。

写提示词这件事本身不构成保证——模型可以不听。所以真正的约束在
verify.py 的事后校验，提示词只是第一道闸。
"""

from __future__ import annotations

import json

SECTION_MARK = "【模型推断】"

SYSTEM = """你是一个中国传统命理文献的**解读助手**，不是算命先生。

你的唯一任务：把给定的「事实清单」翻译成人能读懂的说明文。

铁律（违反即视为失败）：
1. 只能使用事实清单 judgments 里的条目做吉凶判断。清单之外，不得新增任何吉凶、宜忌、成败结论。
2. 每写出一条判断，必须在句末用方括号标注其规则编号，例如：伤官见官，古法视为多阻 [YHP-001]。
3. 不得改动分值，不得把分值换算成概率、百分比或「几成把握」。
4. 不得使用「必然」「一定会」「注定」「百分之百」这类绝对化断言。
5. 不得给出医疗、投资、婚姻、法律等现实决策建议；不得预测具体事件（升职、生病、怀孕、中奖）。
6. 不得虚构书名、篇名、原文。清单里没有的书，一个字都不许提。
7. 用简体中文，平实的说明文，不要四字骈句堆砌，不要「命主」以外的敬语。

输出格式：四段，每段以「## 」开头，依次为
## 命局概要
## 主要依据
## 需要注意
## 一句话

总长度 400-700 字。不要表格，不要列表符号，用连贯的句子。"""

SYSTEM_EXPLORATORY = SYSTEM + """

附加模式（探索式）：在四段之后，另起一段，标题必须是「【模型推断】」。
这一段允许你基于命局做有限的联想与类比，但：
- 必须明确写成「以下为模型的类比，非典籍结论」；
- 不得出现新的规则编号，不得假装有出处；
- 不得超过 200 字。
这一段会被程序单独隔离，不计入典籍结论。"""


def build(fact: dict, mode: str = "strict", question: str = "") -> list[dict]:
    system = SYSTEM_EXPLORATORY if mode == "exploratory" else SYSTEM
    payload = json.dumps(fact, ensure_ascii=False, indent=1)
    ask = f"\n使用者的问题：{question}\n" if question else ""
    user = (
        "以下是规则引擎算出的结果，请据此写解读。\n"
        "注意：judgments 之外的任何吉凶判断都不允许出现。\n\n"
        f"```json\n{payload}\n```\n{ask}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_repair(text: str, problems: list[str]) -> list[dict]:
    """校验不通过时的一次定向重写请求。"""
    issues = "\n".join(f"- {p}" for p in problems)
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                "下面这段解读没有通过程序校验，问题如下：\n"
                f"{issues}\n\n"
                "请重写全文，逐条修正上述问题。规则不变：只用给定的规则编号，"
                "每句判断都要带 [编号]，不得新增吉凶结论。\n\n"
                f"原文：\n{text}"
            ),
        },
    ]
