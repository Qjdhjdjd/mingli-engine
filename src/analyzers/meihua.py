# -*- coding: utf-8 -*-
"""梅花易数：数字起卦、体用生克、互卦变卦。

起卦采「报数起卦」正统法：前数除八取上卦，后数除八取下卦，两数之和除六取动爻。
余数 0 分别取 8 与 6。
"""

from __future__ import annotations

from .. import tables as T


def _gua_from_num(n: int) -> str:
    r = n % 8
    return T.BAGUA[(r - 1) % 8] if r else "坤"


def _bits(gua: str) -> tuple:
    return T.BAGUA_BITS[gua]


def _gua_from_bits(bits: tuple) -> str:
    return T.BITS_BAGUA[tuple(bits)]


def qigua(num_a: int, num_b: int) -> dict:
    """报数起卦。num_a -> 上卦，num_b -> 下卦。"""
    upper = _gua_from_num(num_a)
    lower = _gua_from_num(num_b)
    dong = (num_a + num_b) % 6 or 6

    # 六爻自下而上：0-2 为下卦，3-5 为上卦
    yao = list(_bits(lower)) + list(_bits(upper))
    bian_yao = yao.copy()
    bian_yao[dong - 1] = 1 - bian_yao[dong - 1]

    # 互卦：2,3,4 爻为下互；3,4,5 爻为上互
    hu_lower = _gua_from_bits(tuple(yao[1:4]))
    hu_upper = _gua_from_bits(tuple(yao[2:5]))

    bian_lower = _gua_from_bits(tuple(bian_yao[0:3]))
    bian_upper = _gua_from_bits(tuple(bian_yao[3:6]))

    # 体用：动爻所在经卦为用，另一为体
    if dong <= 3:
        ti, yong = upper, lower
        bian_yong = bian_lower
    else:
        ti, yong = lower, upper
        bian_yong = bian_upper

    ti_wx = T.BAGUA_WUXING[ti]
    yong_wx = T.BAGUA_WUXING[yong]

    if ti_wx == yong_wx:
        relation = "比和"
    elif T.SHENG[yong_wx] == ti_wx:
        relation = "用生体"
    elif T.KE[yong_wx] == ti_wx:
        relation = "用克体"
    elif T.SHENG[ti_wx] == yong_wx:
        relation = "体生用"
    else:
        relation = "体克用"

    hu_sheng_ti = any(T.SHENG[T.BAGUA_WUXING[g]] == ti_wx for g in (hu_lower, hu_upper))
    bian_sheng_ti = T.SHENG[T.BAGUA_WUXING[bian_yong]] == ti_wx
    bian_ke_ti = T.KE[T.BAGUA_WUXING[bian_yong]] == ti_wx

    return {
        "upper": upper, "lower": lower, "dong": dong,
        "ben_gua": upper + "上" + lower + "下",
        "hu_gua": hu_upper + "上" + hu_lower + "下",
        "bian_gua": bian_upper + "上" + bian_lower + "下",
        "ti": ti, "yong": yong, "ti_wx": ti_wx, "yong_wx": yong_wx,
        "bian_yong": bian_yong,
        "mh_tiyong": relation,
        "mh_hu_sheng_ti": hu_sheng_ti,
        "mh_bian_sheng_ti": bian_sheng_ti,
        "bian_ke_ti": bian_ke_ti,
        "yao": yao,
        "bian_yao": bian_yao,
    }


def analyze(num_a: int, num_b: int) -> dict:
    return qigua(num_a, num_b)
