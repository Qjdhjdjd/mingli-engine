# -*- coding: utf-8 -*-
"""干支历法内核。

职责：
1. 公历 <-> 儒略日
2. 太阳视黄经 -> 二十四节气时刻
3. 以「节」为界的年柱 / 月柱，儒略日推日柱，五鼠遁推时柱
4. 五行力量、十神、长生、纳音、空亡、刑冲合害、神煞、大运

精度说明：太阳黄经采用 Meeus《Astronomical Algorithms》第 25 章的低精度公式，
理论误差约 0.01°（约 15 分钟）。因此节气交接前后 15 分钟内出生者，月柱可能存疑，
这是本引擎已知的边界限制，生产使用应换用高精度星历表。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import tables as T

CST = timezone(timedelta(hours=8))

# 二十四节气：(名称, 太阳视黄经, 是否为「节」)
JIEQI = [
    ("小寒", 285, True), ("大寒", 300, False),
    ("立春", 315, True), ("雨水", 330, False),
    ("惊蛰", 345, True), ("春分", 0, False),
    ("清明", 15, True), ("谷雨", 30, False),
    ("立夏", 45, True), ("小满", 60, False),
    ("芒种", 75, True), ("夏至", 90, False),
    ("小暑", 105, True), ("大暑", 120, False),
    ("立秋", 135, True), ("处暑", 150, False),
    ("白露", 165, True), ("秋分", 180, False),
    ("寒露", 195, True), ("霜降", 210, False),
    ("立冬", 225, True), ("小雪", 240, False),
    ("大雪", 255, True), ("冬至", 270, False),
]
# 「节」对应的月支
JIE_ZHI = {
    "立春": "寅", "惊蛰": "卯", "清明": "辰", "立夏": "巳",
    "芒种": "午", "小暑": "未", "立秋": "申", "白露": "酉",
    "寒露": "戌", "立冬": "亥", "大雪": "子", "小寒": "丑",
}


# ------------------------------------------------------------------ 儒略日
def jd_from_datetime(dt: datetime) -> float:
    """datetime（带时区）-> 儒略日。naive 视为 UTC。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    d = dt.day
    frac = (dt.hour + dt.minute / 60 + dt.second / 3600 + dt.microsecond / 3.6e9) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5 + frac


def datetime_from_jd(jd: float) -> datetime:
    """儒略日 -> UTC datetime。"""
    z = int(jd + 0.5)
    f = jd + 0.5 - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e)
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    total_seconds = f * 86400
    hh = int(total_seconds // 3600)
    mm = int((total_seconds - hh * 3600) // 60)
    ss = int(total_seconds - hh * 3600 - mm * 60)
    return datetime(year, month, day, hh % 24, mm, ss, tzinfo=timezone.utc)


# ------------------------------------------------------------------ 太阳黄经
def sun_apparent_longitude(jd: float) -> float:
    """太阳视黄经（度，0-360）。Meeus 低精度公式。"""
    t = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    mr = math.radians(m % 360)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(mr)
         + (0.019993 - 0.000101 * t) * math.sin(2 * mr)
         + 0.000289 * math.sin(3 * mr))
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    lam = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return lam % 360.0


def _solve_longitude(target: float, lo: float, hi: float) -> float:
    """在 [lo, hi] 儒略日区间内二分求解太阳视黄经 = target。"""
    target %= 360

    def diff(jd: float) -> float:
        d = (sun_apparent_longitude(jd) - target + 180) % 360 - 180
        return d

    flo, fhi = diff(lo), diff(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if flo * fhi > 0:
        # 区间内无符号变化，退化返回中点
        return (lo + hi) / 2
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = diff(mid)
        if abs(fm) < 1e-7 or (hi - lo) < 1e-7:
            return mid
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


@lru_cache(maxsize=512)
def jieqi_of_year(year: int) -> tuple:
    """返回该公历年 24 节气的 (名称, 北京时间 datetime)，按时间排序。"""
    out = []
    # 以该年 1 月 1 日为起点，逐个在 ±8 天窗口内求解
    for name, lon, is_jie in JIEQI:
        # 粗略估算：小寒约 1/6，每节气约 15.2 天
        idx = [q[0] for q in JIEQI].index(name)
        approx = datetime(year, 1, 1, tzinfo=CST) + timedelta(days=idx * 15.2184 + 5)
        center = jd_from_datetime(approx)
        jd = _solve_longitude(lon, center - 8, center + 8)
        out.append((name, datetime_from_jd(jd).astimezone(CST)))
    out.sort(key=lambda x: x[1])
    return tuple(out)


@lru_cache(maxsize=8)
def _jie_pool(year: int) -> tuple:
    """year-1 ~ year+1 的所有「节」，按时间排序：(名称, 月支, datetime)。"""
    items = []
    for y in (year - 1, year, year + 1):
        for name, dt in jieqi_of_year(y):
            if name in JIE_ZHI:
                items.append((name, JIE_ZHI[name], dt))
    items.sort(key=lambda x: x[2])
    return tuple(items)


def current_jie(dt: datetime) -> tuple:
    """返回 dt 时刻所隶属的「节」：(名称, 月支, 交节时刻)。"""
    pool = _jie_pool(dt.year)
    cur = pool[0]
    for item in pool:
        if item[2] <= dt:
            cur = item
        else:
            break
    return cur


def lichun(year: int) -> datetime:
    for name, dt in jieqi_of_year(year):
        if name == "立春":
            return dt
    raise ValueError("立春 not found")


# ------------------------------------------------------------------ 四柱
GAN = T.GAN
ZHI = T.ZHI


def gz(index: int) -> str:
    """0-59 -> 干支。"""
    return GAN[index % 10] + ZHI[index % 12]


def gz_index(name: str) -> int:
    """干支 -> 0-59。"""
    g, z = name[0], name[1]
    for i in range(60):
        if GAN[i % 10] == g and ZHI[i % 12] == z:
            return i
    raise ValueError(f"非法干支: {name}")


def ganzhi_year(year: int) -> str:
    return gz(year - 4)


def day_ganzhi(dt: datetime) -> str:
    """日柱。23:00 之后按次日（晚子时）处理。"""
    local = dt.astimezone(CST)
    d = local.date()
    if local.hour == 23:
        d = d + timedelta(days=1)
    jdn = int(jd_from_datetime(datetime(d.year, d.month, d.day, 12, tzinfo=CST)) + 0.5)
    return gz(jdn + 49)


def hour_zhi(hour: int) -> str:
    return ZHI[((hour + 1) // 2) % 12]


def hour_ganzhi(day_gan: str, hour: int) -> str:
    """五鼠遁：甲己还加甲，乙庚丙作初…"""
    dg = GAN.index(day_gan)
    hz = ((hour + 1) // 2) % 12
    hg = ((dg % 5) * 2 + hz) % 10
    return GAN[hg] + ZHI[hz]


def month_ganzhi(year_gan: str, month_zhi: str) -> str:
    """五虎遁：甲己之年丙作首…"""
    yg = GAN.index(year_gan)
    mz = ZHI.index(month_zhi)
    ord_from_yin = (mz - 2) % 12
    mg = ((yg % 5) * 2 + 2 + ord_from_yin) % 10
    return GAN[mg] + month_zhi


def paipan(dt: datetime) -> dict:
    """四柱排盘。dt 需带时区（无时区按北京时间处理）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CST)
    local = dt.astimezone(CST)

    # 年柱：立春为界
    y = local.year
    if local < lichun(y):
        y -= 1
    year_gz = ganzhi_year(y)

    # 月柱：节为界
    jie_name, month_zhi, jie_dt = current_jie(local)
    month_gz = month_ganzhi(year_gz[0], month_zhi)

    # 日柱
    d_gz = day_ganzhi(local)

    # 时柱
    h_gz = hour_ganzhi(d_gz[0], local.hour)

    return {
        "datetime": local,
        "year": year_gz,
        "month": month_gz,
        "day": d_gz,
        "hour": h_gz,
        "pillars": [year_gz, month_gz, d_gz, h_gz],
        "day_master": d_gz[0],
        "month_jie": jie_name,
        "jie_time": jie_dt,
        "solar_year": y,
    }


# ------------------------------------------------------------------ 五行 / 十神
def shishen(day_gan: str, other_gan: str) -> str:
    me, other = T.GAN_WUXING[day_gan], T.GAN_WUXING[other_gan]
    same = T.GAN_YINYANG[day_gan] == T.GAN_YINYANG[other_gan]
    if me == other:
        rel = "同我"
    elif T.SHENG[me] == other:
        rel = "我生"
    elif T.KE[me] == other:
        rel = "我克"
    elif T.KE[other] == me:
        rel = "克我"
    else:
        rel = "生我"
    return T.SHISHEN_TABLE[(rel, "同" if same else "异")]


def element_scores(pillars: list[str]) -> dict:
    """五行力量估算：天干各 1.0，地支藏干按 0.6/0.3/0.1 加权。"""
    score = {e: 0.0 for e in T.WUXING}
    for i, pg in enumerate(pillars):
        gan, zhi = pg[0], pg[1]
        # 天干：月干略加权（司令之气）
        w = 1.2 if i == 1 else 1.0
        score[T.GAN_WUXING[gan]] += w
        for j, cg in enumerate(T.ZHI_CANGGAN[zhi]):
            score[T.GAN_WUXING[cg]] += T.CANGGAN_WEIGHT[j] * 1.2
    total = sum(score.values()) or 1.0
    return {e: round(v / total * 100, 2) for e, v in score.items()}


def day_master_strength(pillars: list[str]) -> dict:
    """日主强弱：得令 / 得地 / 得生 / 得助 四因素粗判。"""
    dm = pillars[2][0]
    de = T.GAN_WUXING[dm]
    scores = element_scores(pillars)
    month_zhi = pillars[1][1]
    month_elem = T.ZHI_WUXING[month_zhi]

    # 得令：月令生扶日主
    deling = month_elem == de or T.SHENG[month_elem] == de
    # 同类（比劫 + 印）占比
    support = scores[de]
    for e in T.WUXING:
        if T.SHENG[e] == de:
            support += scores[e]
    ratio = support / 100.0

    if ratio >= 0.62:
        level = "偏强"
    elif ratio >= 0.50:
        level = "中和偏强"
    elif ratio >= 0.42:
        level = "中和"
    elif ratio >= 0.32:
        level = "中和偏弱"
    else:
        level = "偏弱"

    return {
        "day_master": dm,
        "element": de,
        "scores": scores,
        "support_ratio": round(ratio, 3),
        "deling": deling,
        "level": level,
        "label": "身强" if ratio >= 0.5 else "身弱",
    }


def changsheng(gan: str, zhi: str) -> str:
    start = T.CHANGSHENG_START[gan]
    si = T.ZHI.index(start)
    zi = T.ZHI.index(zhi)
    forward = T.GAN_YINYANG[gan] == "阳"
    step = (zi - si) % 12 if forward else (si - zi) % 12
    return T.CHANGSHENG_ORDER[step]


def nayin(gz_name: str) -> tuple:
    i = gz_index(gz_name)
    return T.NAYIN_NAMES[i // 2], T.NAYIN_WUXING[i // 2]


def xunkong(gz_name: str) -> tuple:
    i = gz_index(gz_name)
    xun = (i // 10) * 10  # 旬首索引
    head = gz(xun)
    return T.XUNKONG[head]


# ------------------------------------------------------------------ 关系
def branch_relations(zhis: list[str]) -> dict:
    """检测地支之间的冲、合、害、三合、三会、刑。"""
    res = {"冲": [], "六合": [], "害": [], "三合": [], "三会": [], "刑": []}
    n = len(zhis)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = zhis[i], zhis[j]
            if not a or not b:
                continue
            if T.ZHI_CHONG.get(a) == b:
                res["冲"].append(a + b)
            if T.ZHI_HE6.get(a) == b:
                res["六合"].append(a + b)
            if T.ZHI_HAI.get(a) == b:
                res["害"].append(a + b)
    s = set(zhis)
    for trio in T.SANHE:
        if all(x in s for x in trio):
            res["三合"].append("".join(trio))
    for trio in T.SANHUI:
        if all(x in s for x in trio):
            res["三会"].append("".join(trio))
    for item in T.SANXING:
        if len(item) == 3:
            if all(x in s for x in item):
                res["刑"].append("".join(item))
        elif len(item) == 2:
            if item[0] != item[1] and item[0] in s and item[1] in s:
                res["刑"].append("".join(item))
    for x in T.ZIXING:
        if zhis.count(x) >= 2:
            res["刑"].append(x + x)
    for k in res:
        res[k] = sorted(set(res[k]))
    return res


def shensha(pillars: list[str]) -> list[dict]:
    """神煞查法。以日干/年干为主，或以年支/日支三合局为主。"""
    year_gz, month_gz, day_gz, hour_gz = pillars
    yg, yz = year_gz[0], year_gz[1]
    dg, dz = day_gz[0], day_gz[1]
    zhis = [p[1] for p in pillars]
    gans = [p[0] for p in pillars]
    found = []

    def add(name, kind, desc, positions):
        if positions:
            found.append({"name": name, "kind": kind, "desc": desc, "positions": positions})

    # 天乙贵人：日干/年干 -> 地支
    pos = []
    for i, z in enumerate(zhis):
        if z in T.TIANYI.get(dg, []) or z in T.TIANYI.get(yg, []):
            pos.append(i)
    add("天乙贵人", "吉", "遇难呈祥，多得贵人提携", pos)

    # 文昌
    pos = [i for i, z in enumerate(zhis) if z == T.WENCHANG.get(dg)]
    add("文昌贵人", "吉", "聪颖好学，利文书考试", pos)

    # 禄
    pos = [i for i, z in enumerate(zhis) if z == T.LU.get(dg)]
    add("禄神", "吉", "衣食丰足，自立有根", pos)

    # 羊刃
    pos = [i for i, z in enumerate(zhis) if z == T.YANGREN.get(dg)]
    add("羊刃", "凶", "性刚易折，主伤灾争竞", pos)

    # 金舆
    pos = [i for i, z in enumerate(zhis) if z == T.JINYU.get(dg)]
    add("金舆", "吉", "利车马出行，得配偶之助", pos)

    # 三合局系神煞（年支 + 日支为参照）
    for ref, label in ((yz, "年支"), (dz, "日支")):
        group = T.SANHE_GROUP.get(ref)
        if not group:
            continue
        for tbl, nm, kind, desc in (
            (T.YIMA, "驿马", "中性", "主奔波变动、迁徙出行"),
            (T.TAOHUA, "桃花", "中性", "主异性缘、才艺与人缘"),
            (T.HUAGAI, "华盖", "中性", "主聪慧孤高，喜玄学艺术"),
            (T.JIANGXING, "将星", "吉", "主统御组织之能"),
            (T.JIESHA, "劫煞", "凶", "主意外破耗、突发之灾"),
            (T.WANGSHEN, "亡神", "凶", "主口舌是非、官非纠缠"),
        ):
            target = tbl[group]
            pos = [i for i, z in enumerate(zhis) if z == target]
            if pos:
                found.append({"name": nm, "kind": kind, "desc": desc,
                              "positions": pos, "from": label})

    # 天德 / 月德
    tian_de = T.TIANDE.get(month_gz[1])
    if tian_de:
        pos = [i for i, g in enumerate(gans) if g == tian_de] + \
              [i for i, z in enumerate(zhis) if z == tian_de]
        add("天德贵人", "吉", "逢凶化吉，心地仁厚", sorted(set(pos)))
    yue_de = T.YUEDE.get(T.SANHE_GROUP.get(month_gz[1], ""), None)
    if yue_de:
        pos = [i for i, g in enumerate(gans) if g == yue_de]
        add("月德贵人", "吉", "福厚慈祥，灾祸减轻", pos)

    # 魁罡
    if day_gz in T.KUIGANG_DAYS:
        add("魁罡", "中性", "性刚果断，掌权而多起伏", [2])

    # 十恶大败
    if day_gz in T.SHIE_DABAI:
        add("十恶大败", "凶", "主财禄易散，须防破败", [2])

    # 阴阳差错
    if day_gz in T.YINYANG_CHACUO:
        add("阴阳差错", "凶", "主婚姻亲属缘薄、多差错", [2])

    # 孤辰寡宿（年支）
    pos = [i for i, z in enumerate(zhis) if z == T.GUCHEN.get(yz)]
    add("孤辰", "凶", "主孤独，亲缘较淡", pos)
    pos = [i for i, z in enumerate(zhis) if z == T.GUASU.get(yz)]
    add("寡宿", "凶", "主孤寡，情感易疏离", pos)

    # 红鸾天喜
    pos = [i for i, z in enumerate(zhis) if z == T.HONGLUAN.get(yz)]
    add("红鸾", "吉", "主婚喜、人缘和悦", pos)
    pos = [i for i, z in enumerate(zhis) if z == T.TIANXI.get(yz)]
    add("天喜", "吉", "主喜庆、添丁进口", pos)

    return found


# ------------------------------------------------------------------ 大运
def dayun(pillars: list[str], birth: datetime, gender: str, count: int = 8) -> list[dict]:
    """大运排法：阳男阴女顺排，阴男阳女逆排。3 天折 1 年。"""
    year_gan = pillars[0][0]
    yang_year = T.GAN_YINYANG[year_gan] == "阳"
    forward = (yang_year and gender == "男") or ((not yang_year) and gender == "女")

    pool = _jie_pool(birth.year)
    # 出生时刻之后（顺）或之前（逆）的最近一个「节」
    if forward:
        nxt = [x for x in pool if x[2] > birth]
        target = nxt[0] if nxt else pool[-1]
        delta_days = (target[2] - birth).total_seconds() / 86400
    else:
        prev = [x for x in pool if x[2] <= birth]
        target = prev[-1] if prev else pool[0]
        delta_days = (birth - target[2]).total_seconds() / 86400

    start_years = delta_days / 3.0
    years_int = int(start_years)
    months_int = int(round((start_years - years_int) * 12))
    if months_int == 12:
        years_int += 1
        months_int = 0

    base = gz_index(pillars[1])
    out = []
    for i in range(1, count + 1):
        idx = base + i if forward else base - i
        pg = gz(idx)
        age_from = years_int + (i - 1) * 10
        year_from = birth.year + age_from
        out.append({
            "ganzhi": pg,
            "start_age": age_from,
            "start_year": year_from,
            "start_age_detail": f"{years_int}岁{months_int}个月起运" if i == 1 else "",
            "nayin": nayin(pg)[0],
        })
    return out


def liunian(year: int) -> dict:
    g = ganzhi_year(year)
    return {"year": year, "ganzhi": g, "nayin": nayin(g)[0]}
