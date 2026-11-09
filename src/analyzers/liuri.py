# -*- coding: utf-8 -*-
"""流日运势：把某一天的干支叠到命局上，判当日吉凶。

依据来源：
- 流日天干对日主取十神（《渊海子平》《三命通会》论流年流日之法）
- 流日地支与命局四支论冲、六合、害、伏吟、反吟（《三命通会》《神峰通考》）
- 日课参建除十二神与黄道黑道（《协纪辨方书》）
- 神煞以日干、年支、日支三合局查（《渊海子平》《星平会海》）

判别口径说明：本模块只做「单日对命局」的静态比对，不推演日与日之间的
连锁（如连续三日叠煞、节气交界的气机转换）。此为有意的简化，非遗漏。
"""

from __future__ import annotations

from datetime import datetime

from .. import calendar_core as C
from .. import tables as T

POS = ["年", "月", "日", "时"]


def _dayun_at(dayun: list[dict], year: int) -> dict | None:
    """当天所处的大运。"""
    for d in dayun:
        if d["start_year"] <= year < d["start_year"] + 10:
            return d
    return None


def _shensha_of_day(dm: str, day_zhi: str, branches: list[str]) -> list[str]:
    """当日地支相对于命主是什么神煞日。"""
    out = []
    if day_zhi in T.TIANYI.get(dm, []):
        out.append("天乙贵人")
    if day_zhi == T.WENCHANG.get(dm):
        out.append("文昌")
    if day_zhi == T.LU.get(dm):
        out.append("禄神")
    if day_zhi == T.YANGREN.get(dm):
        out.append("羊刃")
    if day_zhi == T.JINYU.get(dm):
        out.append("金舆")
    # 驿马、桃花、华盖以年支与日支两处三合局分别查
    for base in (branches[0], branches[2]):
        grp = T.SANHE_GROUP.get(base)
        if not grp:
            continue
        if T.YIMA.get(grp) == day_zhi and "驿马" not in out:
            out.append("驿马")
        if T.TAOHUA.get(grp) == day_zhi and "桃花" not in out:
            out.append("桃花")
        if T.HUAGAI.get(grp) == day_zhi and "华盖" not in out:
            out.append("华盖")
    return out


def analyze_day(natal: dict, dt: datetime) -> dict:
    """natal 为 bazi.analyze 的输出；dt 为该日任意时刻（默认正午）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=C.CST)
    local = dt.astimezone(C.CST)

    day_gz = C.day_ganzhi(local)
    dg, dz = day_gz[0], day_gz[1]
    dm = natal["day_master"]
    pillars = natal["pillars"]
    branches = natal["branches"]

    chong, he, hai, fuyin, fanyin, xing = [], [], [], [], [], []
    for i, p in enumerate(pillars):
        pg, pb = p[0], p[1]
        if T.ZHI_CHONG.get(pb) == dz:
            chong.append(POS[i])
            if T.KE[T.GAN_WUXING[pg]] == T.GAN_WUXING[dg]:
                fanyin.append(POS[i])
        if T.ZHI_HE6.get(pb) == dz:
            he.append(POS[i])
        if T.ZHI_HAI.get(pb) == dz:
            hai.append(POS[i])
        if pb == dz and pg != dg:
            xing.append(POS[i])  # 伏吟支同干异，古称「伏吟」之轻者
        if p == day_gz:
            fuyin.append(POS[i])

    # 与命局凑成三合局，且当日支参与
    all_zhi = set(branches) | {dz}
    sanhe = ""
    for trio in T.SANHE:
        if dz in trio and all(x in all_zhi for x in trio):
            sanhe = "".join(trio)
            break

    kong = dz in set(natal["kongwang"]["branches"])

    # 日课：建除十二神与黄道黑道，月建以节为界
    jie_name, month_zhi, _ = C.current_jie(local)
    jc_idx = (T.ZHI.index(dz) - T.ZHI.index(month_zhi)) % 12
    jianchu = T.JIANCHU[jc_idx]
    zhishen = T.ZHISHEN[jc_idx]
    huangdao = zhishen in T.ZHISHEN_HUANGDAO

    # 大运与流年（流年以立春为界）
    dayun = _dayun_at(natal.get("dayun", []), local.year)
    ln_year = local.year if local >= C.lichun(local.year) else local.year - 1
    liunian = C.ganzhi_year(ln_year)

    ctx = {
        # 命主
        "pillars": pillars,
        "branches": branches,
        "day_master": dm,
        "day_master_element": T.GAN_WUXING[dm],
        "strength": natal.get("strength", {}).get("label", ""),
        "gender": natal.get("gender", "男"),
        "kongwang": list(natal["kongwang"]["branches"]),

        # 当日
        "date": local.strftime("%Y-%m-%d"),
        "weekday": "一二三四五六日"[local.weekday()],
        "day_ganzhi": day_gz,
        "day_gan": dg,
        "day_zhi": dz,
        "day_element": T.GAN_WUXING[dg],
        "lr_ten_god": C.shishen(dm, dg),

        # 与命局的关系
        "lr_chong": chong,
        "lr_he": he,
        "lr_hai": hai,
        "lr_fuyin": fuyin,
        "lr_fanyin": fanyin,
        "lr_xing": xing,
        "lr_kong": kong,
        "lr_sanhe": sanhe,
        "lr_shensha": _shensha_of_day(dm, dz, branches),

        # 日课
        "lr_jianchu": jianchu,
        "lr_zhishen": zhishen,
        "lr_huangdao": huangdao,
        "month_zhi": month_zhi,
        "month_jie": jie_name,

        # 大运流年
        "lr_dayun": dayun["ganzhi"] if dayun else "",
        "lr_dayun_ten_god": C.shishen(dm, dayun["ganzhi"][0]) if dayun else "",
        "lr_liunian": liunian,
        "lr_liunian_ten_god": C.shishen(dm, liunian[0]),
    }

    # 流年支冲命局
    ly_chong = [POS[i] for i, b in enumerate(branches) if T.ZHI_CHONG.get(b) == liunian[1]]
    ctx["lr_liunian_chong"] = ly_chong

    return ctx


def day_range(natal: dict, start: datetime, days: int = 30) -> list[dict]:
    """连续若干天的流日上下文。"""
    from datetime import timedelta
    out = []
    base = datetime(start.year, start.month, start.day, 12, tzinfo=C.CST)
    for i in range(days):
        out.append(analyze_day(natal, base + timedelta(days=i)))
    return out
