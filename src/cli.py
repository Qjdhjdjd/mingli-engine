# -*- coding: utf-8 -*-
"""命令行入口。

用法：
    python -m src.cli bazi  --date 1990-05-15 --time 10:30 --gender 男
    python -m src.cli meihua --a 23 --b 17
    python -m src.cli liuyao --question 求财
    python -m src.cli zeri   --date 2026-11-09
    python -m src.cli xingming --surname 4 --given 11 --name 王伟
    python -m src.cli stats
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import calendar_core as C
from .llm import narrate as llm_narrate
from .llm import provider as llm_provider
from .predict import (bazi_report, liuri_report, liuyao_report, meihua_report,
                      rule_stats, xingming_report, zeri_report)

LINE = "=" * 64


def _fmt_topics(topics: dict) -> str:
    return "  ".join(f"{k}:{v['level']}({v['score']:+d})" for k, v in topics.items()) or "无"


def print_report(r: dict) -> None:
    kind = r["kind"]
    s = r["summary"]
    print(LINE)
    if kind == "bazi":
        print(f"四柱排盘  {s.get('name','')}  {s['birth']}  {s['gender']}")
        print(LINE)
        labels = ["年柱", "月柱", "日柱", "时柱"]
        for i in range(4):
            print(f"  {labels[i]}  {s['pillars'][i]}   十神:{s['ten_gods_stems'][i]:<4} "
                  f"藏干:{''.join(s['canggan'][i]):<4} 纳音:{s['nayin'][i]}  长生:{s['changsheng'][i]}")
        print(f"\n  日主 {s['day_master']}({s['day_master_element']})  "
              f"强弱 {s['strength']['level']}（同类占比 {s['strength']['support_ratio']:.2f}）  "
              f"格局 {s['pattern']}")
        print(f"  月令 {s['month_jie']}（交节 {s['jie_time']}）")
        sc = s["element_scores"]
        print("  五行 " + "  ".join(f"{k}{v:5.1f}%" for k, v in sc.items()))
        t = s["tiaohou"]
        hit = "、".join(f"{h['gan']}(第{h['rank']})" for h in t["hit"]) or "无"
        print(f"  调候（穷通宝鉴）应用 {'/'.join(t['use']) or '—'}  命中 {hit}")
        rel = "；".join(f"{k}{''.join(v)}" for k, v in s["relations"].items() if v) or "无"
        print(f"  刑冲合害 {rel}")
        print(f"  神煞 " + "、".join(x["name"] for x in s["shensha"]))
        print(f"  空亡 {''.join(s['kongwang'])}")
        if s["dayun"]:
            print("\n  大运 " + "  ".join(f"{d['ganzhi']}({d['start_age']})" for d in s["dayun"]))
    elif kind == "meihua":
        print(f"梅花易数  报数 {s['num_a']}/{s['num_b']}")
        print(LINE)
        print(f"  本卦 {s['ben_gua']}  互卦 {s['hu_gua']}  变卦 {s['bian_gua']}")
        print(f"  动爻 第{s['dong_yao']}爻   体卦 {s['ti']}({s['ti_wuxing']})  "
              f"用卦 {s['yong']}({s['yong_wuxing']})")
        print(f"  体用关系 {s['tiyong']}   互卦生体 {s['hu_sheng_ti']}   变卦生体 {s['bian_sheng_ti']}")
    elif kind == "liuyao":
        print(f"六爻纳甲  所问「{s['question']}」")
        print(LINE)
        print(f"  主卦 {s['name']}（{s['gua']}）→ 变卦 {s['bian_name']}")
        print(f"  卦宫 {s['gong']}属{s['gong_wuxing']}  世{s['shi']}爻 应{s['ying']}爻  {s['type']}")
        print(f"  月建 {s['month_zhi']}  日辰 {s['day_ganzhi']}")
        print(f"  用神 {s['yongshen']}  世爻状态 {s['shi_state']}  用神状态 {s['yongshen_state']}")
        print("\n  装卦：")
        for y in reversed(s["yao"]):
            mark = ""
            if y["shi"]:
                mark += " 世"
            if y["ying"]:
                mark += " 应"
            if y["dong"]:
                mark += " ○动"
            bian = f" → {y.get('bian_zhi','')}{y.get('bian_wuxing','')}" if y.get("dong") else ""
            print(f"    {y['pos']}爻 {y['yin_yang']} {y['liuqin']}"
                  f"({y['zhi']}{y['wuxing']}){mark}{bian}")
    elif kind == "zeri":
        print(f"择日  公历 {s['date']}")
        print(LINE)
        print(f"  日干支 {s['day_ganzhi']}  月建 {s['month_zhi']}（{s['month_jie']}）")
        print(f"  建除十二神 {s['jianchu']}（{s['jianchu_jixiong']}）  "
              f"值神 {s['zhishen']}（{'黄道' if s['huangdao'] else '黑道'}）")
        print(f"  宜 {s['yi']}")
    elif kind == "xingming":
        print(f"姓名五格  {s.get('name','')}")
        print(LINE)
        for k, v in s["wuge"].items():
            print(f"  {k} {v['num']:>3}（{v['wuxing']}，{v['jixiong']}，{v['name']}）")
        print(f"  三才 {s['sancai_combo']}  {s['sancai']}")

    print("\n" + "-" * 64)
    o = r["overall"]
    print(f"  规则命中 {o['hit_count']} 条  综合倾向 {o['level']}  "
          f"均分 {o['avg_score']:+.2f}  可参考度 {o['confidence']}")
    print(f"  分主题 {_fmt_topics(r['topics'])}")
    print("\n  命中条目（按典籍）：")
    for h in r["hits"]:
        th = h["then"]
        print(f"    [{th['verdict']}{th['score']:+d}] {h['book']}·{h['title']}：{th['text']}")
    print(LINE)
    print("  " + r["disclaimer"] + "\n")


def print_liuri(r):
    s = r["summary"]
    print(f"流日运势  {s.get('name','')}  {s['birth']}  {s['gender']}")
    print(LINE)
    print(f"  四柱 {' '.join(s['pillars'])}   日主 {s['day_master']}({s['day_master_element']})  "
          f"{s['strength']}  格局 {s['pattern']}")
    print(f"  大运 {s['dayun'] or '未起运'}   流年 {s['liunian']}({s['liunian_ten_god']})")
    for b in r.get("background", []):
        print(f"  背景 [{b['verdict']}] {b['book']}·{b['title']}")
    print(f"\n  {s['start']} 起 {s['days']} 天　分布 "
          + "  ".join(f"{k}{v}" for k, v in r["distribution"].items()))
    print()
    for d in r["days"]:
        tags = "、".join(h["title"] for h in d["hits"]) or "无"
        sc = f"{d['score']:+d}" if d["score"] else "0"
        print(f"  {d['date'][5:]} {d['weekday']} {d['ganzhi']} {d['ten_god']:<3} "
              f"{d['level']:<3} {sc:>4}  {tags}")
    best = r["best"][0] if r["best"] else None
    worst = r["worst"][0] if r["worst"] else None
    if best and worst:
        print(f"\n  最宜 {best['date']}（{best['score']:+d}）　"
              f"最忌 {worst['date']}（{worst['score']:+d}）")
    print("\n  " + r["note"])
    print("  " + r["disclaimer"] + "\n")


def print_narration(out: dict) -> None:
    print(LINE)
    src = (f"{out['provider']} · {out['model']}" if out["online"]
           else "本地模板（未调用大模型）")
    print(f"大模型解读　{src}　模式 {out['mode']}")
    if out.get("fallback_reason"):
        print(f"　回退原因：{out['fallback_reason']}")
    print(LINE)
    print(out["text"])
    print("\n" + "-" * 64)
    print(f"　{out['verification_text']}")
    for p in out["verification"]["problems"]:
        print(f"　· {p}")
    for u in out["verification"]["unsupported"]:
        print(f"　· 未溯源：{u['sentence']}")
    print("　" + out["disclaimer"])
    print(LINE)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mingli", description="传统命理规则引擎（文化研究用途）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bazi", help="四柱八字")
    b.add_argument("--date", required=True, help="YYYY-MM-DD")
    b.add_argument("--time", default="12:00", help="HH:MM")
    b.add_argument("--gender", default="男", choices=["男", "女"])
    b.add_argument("--name", default="")

    m = sub.add_parser("meihua", help="梅花易数报数起卦")
    m.add_argument("--a", type=int, required=True)
    m.add_argument("--b", type=int, required=True)
    m.add_argument("--question", default="")

    l = sub.add_parser("liuyao", help="六爻纳甲")
    l.add_argument("--question", default="综合",
                   choices=["综合", "求财", "事业", "考试", "文书", "婚姻", "子女", "健康", "兄弟", "出行"])
    l.add_argument("--gender", default="男", choices=["男", "女"])

    z = sub.add_parser("zeri", help="择日")
    z.add_argument("--date", required=True)

    x = sub.add_parser("xingming", help="姓名五格")
    x.add_argument("--surname", type=int, required=True, help="姓的康熙笔画（复姓用逗号分隔）")
    x.add_argument("--given", type=int, required=True, help="名的康熙笔画（双名用逗号分隔）")
    x.add_argument("--name", default="")

    lr = sub.add_parser("liuri", help="流日运势：某人某段日子的逐日吉凶")
    lr.add_argument("--date", required=True, help="出生日期 YYYY-MM-DD")
    lr.add_argument("--time", default="12:00", help="出生时间 HH:MM")
    lr.add_argument("--gender", default="男", choices=["男", "女"])
    lr.add_argument("--start", help="起始日期 YYYY-MM-DD，默认今天")
    lr.add_argument("--days", type=int, default=30, help="看多少天，默认 30")
    lr.add_argument("--name", default="")

    sub.add_parser("stats", help="规则库统计")

    n = sub.add_parser("narrate", help="大模型解读（未配置模型时用本地模板）")
    n.add_argument("--kind", choices=["bazi", "liuri"], default="bazi")
    n.add_argument("--date", required=True, help="出生日期 YYYY-MM-DD")
    n.add_argument("--time", default="12:00")
    n.add_argument("--gender", default="男", choices=["男", "女"])
    n.add_argument("--name", default="")
    n.add_argument("--start", help="liuri 起始日期")
    n.add_argument("--days", type=int, default=14)
    n.add_argument("--day", help="liuri 指定某一天（须在区间内）")
    n.add_argument("--mode", choices=["strict", "exploratory"], default="strict")
    n.add_argument("--offline", action="store_true", help="强制使用本地模板")

    a = ap.parse_args(argv)

    if a.cmd == "bazi":
        dt = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M").replace(tzinfo=C.CST)
        print_report(bazi_report(dt, a.gender, a.name))
    elif a.cmd == "meihua":
        print_report(meihua_report(a.a, a.b, a.question))
    elif a.cmd == "liuyao":
        print_report(liuyao_report(question=a.question, gender=a.gender))
    elif a.cmd == "zeri":
        dt = datetime.strptime(a.date, "%Y-%m-%d").replace(hour=12, tzinfo=C.CST)
        print_report(zeri_report(dt))
    elif a.cmd == "xingming":
        sn = [int(v) for v in str(a.surname).split(",")]
        gv = [int(v) for v in str(a.given).split(",")]
        print_report(xingming_report(sn, gv, a.name))
    elif a.cmd == "liuri":
        birth = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M").replace(tzinfo=C.CST)
        start = None
        if a.start:
            start = datetime.strptime(a.start, "%Y-%m-%d").replace(hour=12, tzinfo=C.CST)
        print_liuri(liuri_report(birth, a.gender, start, a.days, a.name))
    elif a.cmd == "narrate":
        birth = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M").replace(tzinfo=C.CST)
        if a.kind == "bazi":
            rep = bazi_report(birth, a.gender, a.name)
            day = None
        else:
            start = None
            if a.start:
                start = datetime.strptime(a.start, "%Y-%m-%d").replace(hour=12, tzinfo=C.CST)
            rep = liuri_report(birth, a.gender, start, a.days, a.name)
            day = None
            if a.day:
                day = next((d for d in rep["days"] if d["date"] == a.day), None)
                if day is None:
                    print(f"日期 {a.day} 不在所选区间内", file=sys.stderr)
                    return
        print_narration(llm_narrate.narrate(
            rep, day=day, mode=a.mode, use_llm=not a.offline))
    elif a.cmd == "stats":
        st = rule_stats()
        print(f"规则总数 {st['total_rules']}  覆盖典籍 {st['total_books']} 部")
        print("按体系:", st["by_system"])
        for k, v in st["by_book"].items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
