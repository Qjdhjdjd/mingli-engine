# -*- coding: utf-8 -*-
"""择日：建除十二神与黄道黑道。

月建以「节」为界，与四柱月柱同源。建日 = 该月内日支与月建相同之日，
其后按十二神顺序轮值，故可直接由 (日支序 - 月支序) mod 12 求得。
"""

from __future__ import annotations

from datetime import datetime

from .. import calendar_core as C
from .. import tables as T


def analyze(dt: datetime) -> dict:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=C.CST)
    local = dt.astimezone(C.CST)

    jie_name, month_zhi, jie_dt = C.current_jie(local)
    day_gz = C.day_ganzhi(local)
    day_zhi = day_gz[1]

    idx = (T.ZHI.index(day_zhi) - T.ZHI.index(month_zhi)) % 12
    jianchu = T.JIANCHU[idx]
    zhishen = T.ZHISHEN[idx]
    huangdao = zhishen in T.ZHISHEN_HUANGDAO

    return {
        "date": local.strftime("%Y-%m-%d"),
        "day_ganzhi": day_gz,
        "day_zhi": day_zhi,
        "month_jie": jie_name,
        "month_zhi": month_zhi,
        "jianchu": jianchu,
        "jianchu_jixiong": T.JIANCHU_JIXIONG[jianchu],
        "zhishen": zhishen,
        "huangdao": huangdao,
        "yi": T.JIANCHU_YI[jianchu],
        "zeri_jianchu_jixiong": T.JIANCHU_JIXIONG[jianchu],
        "zeri_huangdao": huangdao,
        "jie_time": jie_dt.strftime("%Y-%m-%d %H:%M"),
    }
