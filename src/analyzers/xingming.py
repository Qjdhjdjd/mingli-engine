# -*- coding: utf-8 -*-
"""姓名学：五格剖象法（熊崎氏）。

笔画一律用「康熙字典」口径，由调用方提供——本引擎刻意不内置笔画表，
因为同一字在不同版本字典中笔画有出入，内置表反而会引入静默错误。
"""

from __future__ import annotations

from .. import tables as T


def wuxing_of_num(n: int) -> str:
    """数理五行：1、2 木；3、4 火；5、6 土；7、8 金；9、0 水。"""
    tail = n % 10
    return {1: "木", 2: "木", 3: "火", 4: "火", 5: "土",
            6: "土", 7: "金", 8: "金", 9: "水", 0: "水"}[tail]


def normalize(n: int) -> int:
    """超过 81 的按 81 循环。"""
    if n <= 0:
        return 1
    return (n - 1) % 81 + 1


def jixiong(n: int) -> str:
    n = normalize(n)
    if n in T.SHULI_JI:
        name, verdict = T.SHULI_NAMES.get(n, ("", "吉"))
        return verdict if verdict in ("大吉", "吉") else "吉"
    if n in T.SHULI_BANJI:
        return "半吉"
    return "凶"


def compute_wuge(surname: list[int], given: list[int]) -> dict:
    if not surname or not given:
        raise ValueError("姓与名均不能为空")
    if len(surname) > 2 or len(given) > 2:
        raise ValueError("仅支持单姓/复姓与单名/双名")

    s_sum = sum(surname)
    g_sum = sum(given)

    tian = surname[0] + 1 if len(surname) == 1 else surname[0] + surname[1]
    ren = surname[-1] + given[0]
    di = given[0] + 1 if len(given) == 1 else given[0] + given[1]
    zong = s_sum + g_sum

    if len(surname) == 1 and len(given) == 1:
        wai = 2
    elif len(surname) == 1 and len(given) == 2:
        wai = zong - ren + 1
    elif len(surname) == 2 and len(given) == 1:
        wai = zong - ren + 1
    else:
        wai = zong - ren

    ge = {"天格": tian, "人格": ren, "地格": di, "外格": wai, "总格": zong}
    out = {}
    for k, v in ge.items():
        out[k] = {
            "num": v,
            "normalized": normalize(v),
            "wuxing": wuxing_of_num(v),
            "jixiong": jixiong(v),
            "name": T.SHULI_NAMES.get(normalize(v), ("", ""))[0],
        }
    return out


def sancai_relation(tian: str, ren: str, di: str) -> str:
    """三才配置：相邻两格相生或比和则顺，出现相克则逆。"""
    def rel(a, b):
        if a == b:
            return "同"
        if T.SHENG[a] == b:
            return "生"
        if T.KE[a] == b:
            return "克"
        if T.SHENG[b] == a:
            return "被生"
        return "被克"

    r1, r2 = rel(tian, ren), rel(ren, di)
    if {r1, r2} & {"克", "被克"}:
        return "相克"
    if r1 in ("生", "同") and r2 in ("生", "同"):
        return "相生"
    return "平和"


def analyze(surname: list[int], given: list[int], full_name: str = "") -> dict:
    wuge = compute_wuge(surname, given)
    sc = sancai_relation(
        wuge["天格"]["wuxing"], wuge["人格"]["wuxing"], wuge["地格"]["wuxing"]
    )
    return {
        "name": full_name,
        "strokes": {"surname": sum(surname), "given": sum(given), "total": sum(surname) + sum(given)},
        "wuge": wuge,
        "sancai": sc,
        "sancai_combo": f'{wuge["天格"]["wuxing"]}{wuge["人格"]["wuxing"]}{wuge["地格"]["wuxing"]}',
        "xm_shuli": {k: v["jixiong"] for k, v in wuge.items()},
        "xm_sancai": sc,
    }
