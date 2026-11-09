# -*- coding: utf-8 -*-
"""六爻纳甲：八宫归属、世应、纳甲装卦、六亲、用神旺衰。

八宫与纳甲由规则程序生成，避免手抄六十四卦大表产生错漏。
旺衰判断为简化口径（月建/日辰生克冲合），不作精细的动变连锁推演。
"""

from __future__ import annotations

import random
from datetime import datetime

from .. import calendar_core as C
from .. import tables as T

# 八宫顺序与卦名（本宫、一世…归魂）
GONG_NAMES = {
    "乾": ["乾为天", "天风姤", "天山遁", "天地否", "风地观", "山地剥", "火地晋", "火天大有"],
    "兑": ["兑为泽", "泽水困", "泽地萃", "泽山咸", "水山蹇", "地山谦", "雷山小过", "雷泽归妹"],
    "离": ["离为火", "火山旅", "火风鼎", "火水未济", "山水蒙", "风水涣", "天水讼", "天火同人"],
    "震": ["震为雷", "雷地豫", "雷水解", "雷风恒", "地风升", "水风井", "泽风大过", "泽雷随"],
    "巽": ["巽为风", "风天小畜", "风火家人", "风雷益", "天雷无妄", "火雷噬嗑", "山雷颐", "山风蛊"],
    "坎": ["坎为水", "水泽节", "水雷屯", "水火既济", "泽火革", "雷火丰", "地火明夷", "地水师"],
    "艮": ["艮为山", "山火贲", "山天大畜", "山泽损", "火泽睽", "天泽履", "风泽中孚", "风山渐"],
    "坤": ["坤为地", "地雷复", "地泽临", "地天泰", "雷天大壮", "泽天夬", "水天需", "水地比"],
}

GONG_WUXING = {"乾": "金", "兑": "金", "离": "火", "震": "木",
               "巽": "木", "坎": "水", "艮": "土", "坤": "土"}

# 世应位置（1-6）
SHI_YING = [(6, 3), (1, 4), (2, 5), (3, 6), (4, 1), (5, 2), (4, 1), (3, 6)]

# 纳甲地支：内卦与外卦各三爻（自下而上）
NAJIA_INNER = {
    "乾": ["子", "寅", "辰"], "坎": ["寅", "辰", "午"], "艮": ["辰", "午", "申"],
    "震": ["子", "寅", "辰"], "巽": ["丑", "亥", "酉"], "离": ["卯", "丑", "亥"],
    "坤": ["未", "巳", "卯"], "兑": ["巳", "卯", "丑"],
}
NAJIA_OUTER = {
    "乾": ["午", "申", "戌"], "坎": ["申", "戌", "子"], "艮": ["戌", "子", "寅"],
    "震": ["午", "申", "戌"], "巽": ["未", "巳", "卯"], "离": ["酉", "未", "巳"],
    "坤": ["丑", "亥", "酉"], "兑": ["亥", "酉", "未"],
}

LIUQIN_ORDER = ["父母", "兄弟", "子孙", "妻财", "官鬼"]

# 六合卦
LIUHE_GUA = {"天地否", "地天泰", "雷地豫", "地雷复", "水泽节", "泽水困", "山火贲", "火山旅"}
# 八纯卦（六冲）
LIUCHONG_GUA = {v[0] for v in GONG_NAMES.values()}


def _ba_gong_table() -> dict:
    """生成 bits(6 位元组) -> (宫, 卦名, 世, 应, 游魂/归魂标记)"""
    table = {}
    for gong, names in GONG_NAMES.items():
        base = T.BAGUA_BITS[gong]
        bits = list(base) + list(base)  # 下卦 + 上卦
        seq = [bits]
        cur = bits.copy()
        # 一世~五世：依次变初爻到五爻
        for i in range(5):
            cur = cur.copy()
            cur[i] = 1 - cur[i]
            seq.append(cur.copy())
        # 游魂：五世基础上变回四爻
        you = cur.copy()
        you[3] = 1 - you[3]
        seq.append(you)
        # 归魂：游魂的内卦三爻全变
        gui = you.copy()
        for i in range(3):
            gui[i] = 1 - gui[i]
        seq.append(gui)
        for i, b in enumerate(seq):
            table[tuple(b)] = {
                "gong": gong, "name": names[i],
                "shi": SHI_YING[i][0], "ying": SHI_YING[i][1],
                "index": i,
                "type": {0: "本宫", 6: "游魂", 7: "归魂"}.get(i, f"{i}世"),
            }
    return table


BAGONG = _ba_gong_table()


def liuqin(gong_wx: str, yao_wx: str) -> str:
    if gong_wx == yao_wx:
        return "兄弟"
    if T.SHENG[yao_wx] == gong_wx:
        return "父母"
    if T.SHENG[gong_wx] == yao_wx:
        return "子孙"
    if T.KE[yao_wx] == gong_wx:
        return "官鬼"
    return "妻财"


def qigua(seed: int | None = None) -> list[int]:
    """三枚铜钱摇六次。6=老阴 7=少阳 8=少阴 9=老阳。"""
    rng = random.Random(seed)
    out = []
    for _ in range(6):
        coins = [rng.choice([2, 3]) for _ in range(3)]  # 2=背 3=字
        s = sum(coins)
        out.append(s)  # 6,7,8,9
    return out


def yao_state(zhi: str, wuxing: str, month_zhi: str, day_zhi: str) -> str:
    """单爻旺衰（简化口径）：月破 > 旺 > 受克 > 平。"""
    mw, dw = T.ZHI_WUXING[month_zhi], T.ZHI_WUXING[day_zhi]
    if T.ZHI_CHONG.get(month_zhi) == zhi:
        return "月破"
    if zhi == month_zhi or T.SHENG[mw] == wuxing:
        return "旺"
    if zhi == day_zhi or T.SHENG[dw] == wuxing:
        return "旺"
    if T.KE[mw] == wuxing and T.KE[dw] == wuxing:
        return "受克"
    return "平"


def analyze(yao_values: list[int], question: str = "综合",
            dt: datetime | None = None, gender: str = "男") -> dict:
    if dt is None:
        dt = datetime.now(C.CST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=C.CST)
    local = dt.astimezone(C.CST)
    _, month_zhi, _ = C.current_jie(local)
    day_gz = C.day_ganzhi(local)
    day_zhi = day_gz[1]

    main_bits = tuple(1 if v in (7, 9) else 0 for v in yao_values)
    dong_idx = [i for i, v in enumerate(yao_values) if v in (6, 9)]
    bian_bits = list(main_bits)
    for i in dong_idx:
        bian_bits[i] = 1 - bian_bits[i]
    bian_bits = tuple(bian_bits)

    info = BAGONG.get(main_bits)
    if info is None:
        raise ValueError("非法卦象")
    bian_info = BAGONG.get(bian_bits, info)

    lower = T.BITS_BAGUA[main_bits[0:3]]
    upper = T.BITS_BAGUA[main_bits[3:6]]
    gong = info["gong"]
    gong_wx = GONG_WUXING[gong]

    # 装卦
    yao_list = []
    for i in range(6):
        if i < 3:
            zhi = NAJIA_INNER[lower][i]
        else:
            zhi = NAJIA_OUTER[upper][i - 3]
        wx = T.ZHI_WUXING[zhi]
        yao_list.append({
            "pos": i + 1,
            "zhi": zhi,
            "wuxing": wx,
            "liuqin": liuqin(gong_wx, wx),
            "dong": i in dong_idx,
            "yin_yang": "阳" if main_bits[i] else "阴",
            "shi": info["shi"] == i + 1,
            "ying": info["ying"] == i + 1,
        })

    # 变爻地支
    for i, y in enumerate(yao_list):
        if y["dong"]:
            b_lower = T.BITS_BAGUA[bian_bits[0:3]]
            b_upper = T.BITS_BAGUA[bian_bits[3:6]]
            bz = NAJIA_INNER[b_lower][i] if i < 3 else NAJIA_OUTER[b_upper][i - 3]
            y["bian_zhi"] = bz
            y["bian_wuxing"] = T.ZHI_WUXING[bz]

    # 用神
    mapping = {
        "求财": "妻财", "事业": "官鬼", "考试": "父母", "文书": "父母",
        "婚姻": "妻财" if gender == "男" else "官鬼",
        "子女": "子孙", "健康": "子孙", "兄弟": "兄弟",
        "出行": "父母", "综合": "世爻",
    }
    target = mapping.get(question, "世爻")
    if target == "世爻":
        ys = next((y for y in yao_list if y["shi"]), yao_list[0])
    else:
        cands = [y for y in yao_list if y["liuqin"] == target]
        ys = cands[0] if cands else None

    # 旺衰
    shi_yao = next(y for y in yao_list if y["shi"])
    ying_yao = next(y for y in yao_list if y["ying"])
    shi_state = yao_state(shi_yao["zhi"], shi_yao["wuxing"], month_zhi, day_zhi)
    state = "平"
    hidden = ys is None
    ke_shi = False
    huajin = None
    if ys:
        state = yao_state(ys["zhi"], ys["wuxing"], month_zhi, day_zhi)
        ke_shi = T.KE[ys["wuxing"]] == shi_yao["wuxing"]
        if ys.get("dong") and ys.get("bian_zhi"):
            a, b = T.ZHI.index(ys["zhi"]), T.ZHI.index(ys["bian_zhi"])
            d = (b - a) % 12
            if d in (1, 2):
                huajin = "进"
            elif d in (10, 11):
                huajin = "退"

    # 忌神发动：克用神之爻为动
    jishen_dong = False
    if ys:
        jishen_dong = any(
            y["dong"] and T.KE[y["wuxing"]] == ys["wuxing"] for y in yao_list
        )

    if T.SHENG[shi_yao["wuxing"]] == ying_yao["wuxing"] or T.SHENG[ying_yao["wuxing"]] == shi_yao["wuxing"]:
        shi_ying = "相生"
    elif T.KE[shi_yao["wuxing"]] == ying_yao["wuxing"] or T.KE[ying_yao["wuxing"]] == shi_yao["wuxing"]:
        shi_ying = "相克"
    else:
        shi_ying = "比和"

    name = info["name"]
    if name in LIUCHONG_GUA:
        hex_type = "六冲"
    elif name in LIUHE_GUA:
        hex_type = "六合"
    elif info["type"] == "游魂":
        hex_type = "游魂"
    elif info["type"] == "归魂":
        hex_type = "归魂"
    else:
        hex_type = "普通"

    return {
        "question": question,
        "yao_values": yao_values,
        "main_bits": main_bits,
        "bian_bits": bian_bits,
        "gua": f"{upper}上{lower}下",
        "name": name,
        "bian_name": bian_info["name"],
        "gong": gong,
        "gong_wuxing": gong_wx,
        "shi": info["shi"],
        "ying": info["ying"],
        "type": info["type"],
        "yao": yao_list,
        "yongshen": target,
        "yongshen_yao": ys,
        "shi_state": shi_state,
        "yongshen_state": state,
        "month_zhi": month_zhi,
        "day_ganzhi": day_gz,
        "day_zhi": day_zhi,
        "liuyao": {
            "ly_shi_state": "旺" if shi_state == "旺" else "衰",
            "ly_yongshen_state": state,
            "ly_hex_type": hex_type,
            "ly_yongshen_huajin": huajin,
            "ly_jishen_dong": jishen_dong,
            "ly_yongshen_ke_shi": ke_shi,
            "ly_question": question,
            "ly_yongshen_hidden": hidden,
            "ly_shi_ying": shi_ying,
        },
    }
