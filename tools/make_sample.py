# -*- coding: utf-8 -*-
"""生成一份静态示例报告 docs/sample_report.html。"""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.calendar_core import CST  # noqa: E402
from src.predict import bazi_report  # noqa: E402

LEVEL_COLOR = {"大吉": "#2d6a4f", "吉": "#2d6a4f", "平": "#6b7280", "凶": "#a4243b", "大凶": "#a4243b"}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render(r: dict) -> str:
    s = r["summary"]
    labels = ["年柱", "月柱", "日柱", "时柱"]

    cards = ""
    for i in range(4):
        cards += f"""
        <div class="pcard">
          <div class="lab">{labels[i]}</div>
          <div class="gz"><span>{esc(s['pillars'][i][0])}</span><span class="z">{esc(s['pillars'][i][1])}</span></div>
          <div class="ss">{esc(s['ten_gods_stems'][i])}</div>
          <div class="sub">藏干 {esc(' '.join(s['canggan'][i]))}<br>纳音 {esc(s['nayin'][i])}<br>长生 {esc(s['changsheng'][i])}</div>
        </div>"""

    colors = {"木": "#4f7d4a", "火": "#b4472f", "土": "#a8762a", "金": "#8a8f98", "水": "#3b6b8f"}
    bars = ""
    for k, v in s["element_scores"].items():
        bars += f"""<div class="bar"><span>{k}</span>
          <div class="track"><div class="fill" style="width:{min(100, v)}%;background:{colors[k]}"></div></div>
          <span class="val">{v:.1f}%</span></div>"""

    t = s["tiaohou"]
    hit = "、".join(f"{h['gan']}(第{h['rank']}用神)" for h in t["hit"]) or "无"
    rel = "；".join(f"{k}{''.join(v)}" for k, v in s["relations"].items() if v) or "无"

    topics = ""
    for k, v in r["topics"].items():
        col = LEVEL_COLOR.get(v["level"], "#6b7280")
        topics += f'<div class="topic">{esc(k)}<b style="color:{col}">{esc(v["level"])} {v["score"]:+d}</b></div>'

    rules = ""
    for h in r["hits"]:
        th = h["then"]
        vd = "平" if th["verdict"] == "中性" else th["verdict"]
        col = LEVEL_COLOR.get(vd, "#6b7280")
        note = f'　{esc(h["note"])}' if h.get("note") else ""
        rules += f"""
        <div class="rule">
          <div class="tag" style="background:{col}">{esc(vd)}{th['score']:+d}</div>
          <div>
            <div class="src">{esc(h['book'])}{' · ' + esc(h['section']) if h.get('section') else ''}</div>
            <div class="txt">{esc(th['text'])}</div>
            <div class="meta">{esc(h['title'])}　置信度 {esc(h['confidence'])}{note}</div>
          </div>
        </div>"""

    o = r["overall"]
    ocol = LEVEL_COLOR.get(o["level"], "#6b7280")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>命理规则引擎 · 示例报告</title>
<style>
:root{{--bg:#fbf9f5;--card:#fff;--ink:#1f2328;--ink2:#5b6470;--line:#e2ddd4;--accent:#8c2f24;--gold:#a8762a}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.65}}
.wrap{{max-width:960px;margin:0 auto;padding:36px 24px 70px}}
header{{border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}}
h1{{font-family:Georgia,"Songti SC",serif;font-size:25px;margin:0;letter-spacing:.5px}}
h1 small{{display:block;font-size:12px;color:var(--ink2);letter-spacing:2px;font-weight:400;margin-top:6px;font-family:inherit}}
.sec{{font-size:13px;letter-spacing:2px;color:var(--gold);margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line);font-weight:600}}
.pillars{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.pcard{{border:1px solid var(--line);border-radius:10px;padding:14px 12px;text-align:center;background:#fdfcf9}}
.pcard .lab{{font-size:11px;color:var(--ink2);letter-spacing:2px}}
.pcard .gz{{font-family:Georgia,"Songti SC",serif;font-size:32px;letter-spacing:3px;margin:6px 0 4px}}
.pcard .gz .z{{color:var(--accent)}}
.pcard .ss{{font-size:12px;color:var(--gold)}}
.pcard .sub{{font-size:11px;color:var(--ink2);margin-top:6px;line-height:1.7}}
.kv{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:9px 22px;font-size:13.5px}}
.kv div{{display:flex;gap:8px}}
.kv div.wide{{grid-column:1/-1}}
.kv span:first-child{{color:var(--ink2);min-width:66px;flex:none}}
.bars{{display:flex;flex-direction:column;gap:7px}}
.bar{{display:grid;grid-template-columns:26px 1fr 64px;align-items:center;gap:10px;font-size:12px}}
.bar .track{{height:9px;background:#eee9e0;border-radius:5px;overflow:hidden}}
.bar .fill{{height:100%;border-radius:5px}}
.bar .val{{text-align:right;color:var(--ink2);font-variant-numeric:tabular-nums}}
.overall{{display:flex;align-items:center;gap:18px;flex-wrap:wrap;border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:14px 18px;background:#fdfcf9}}
.overall .lv{{font-family:Georgia,serif;font-size:25px;letter-spacing:2px}}
.topics{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
.topic{{border:1px solid var(--line);border-radius:999px;padding:5px 13px;font-size:12.5px;background:#fdfcf9}}
.topic b{{font-weight:600;margin-left:5px}}
.rules{{display:flex;flex-direction:column;gap:9px}}
.rule{{border:1px solid var(--line);border-radius:8px;padding:11px 14px;background:#fff;display:grid;grid-template-columns:64px 1fr;gap:12px}}
.rule .tag{{font-size:12px;font-weight:600;text-align:center;border-radius:5px;height:22px;line-height:22px;color:#fff;white-space:nowrap}}
.rule .src{{font-size:12px;color:var(--gold)}}
.rule .txt{{font-size:13.5px;margin-top:2px}}
.rule .meta{{font-size:11px;color:var(--ink2);margin-top:4px}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--ink2);line-height:1.8}}
@media(max-width:640px){{.pillars{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
<header><h1>命理规则引擎 · 示例报告<small>典籍吉凶规则的程序化整理</small></h1></header>

<div class="sec">四柱排盘</div>
<div class="pillars">{cards}</div>

<div class="sec">命局</div>
<div class="kv">
  <div><span>出生</span><span>{esc(s['birth'])}（{esc(s['gender'])}）</span></div>
  <div><span>月令</span><span>{esc(s['month_jie'])} · 交节 {esc(s['jie_time'][5:])}</span></div>
  <div><span>日主</span><span>{esc(s['day_master'])}（{esc(s['day_master_element'])}）</span></div>
  <div><span>强弱</span><span>{esc(s['strength']['level'])}，同类占比 {s['strength']['support_ratio']}</span></div>
  <div><span>格局</span><span>{esc(s['pattern'])}</span></div>
  <div><span>空亡</span><span>{esc(' '.join(s['kongwang']))}</span></div>
  <div class="wide"><span>调候</span><span>{esc(' / '.join(t['use']) or '—')}　命中 {esc(hit)}</span></div>
  <div><span>刑冲合害</span><span>{esc(rel)}</span></div>
  <div class="wide"><span>神煞</span><span>{esc('、'.join(x['name'] for x in s['shensha']))}</span></div>
  <div class="wide"><span>大运</span><span>{esc(' '.join(d['ganzhi'] + '(' + str(d['start_age']) + ')' for d in s['dayun']))}</span></div>
</div>

<div class="sec">五行力量（藏干加权估算）</div>
<div class="bars">{bars}</div>

<div class="sec">规则判定</div>
<div class="overall">
  <div class="lv" style="color:{ocol}">{esc(o['level'])}</div>
  <div style="font-size:12.5px;color:var(--ink2);line-height:1.7">
    命中 {o['hit_count']} 条规则　均分 {o['avg_score']:+.2f}　可参考度 {esc(o['confidence'])}<br>
    {esc(o['note'])}
  </div>
</div>
<div class="topics">{topics}</div>

<div class="sec">命中条目 · 典籍溯源</div>
<div class="rules">{rules}</div>

<footer><b>性质说明：</b>{esc(r['disclaimer'])}<br>
本报告由 mingli-engine 自动生成，规则库覆盖 29 部典籍、119 条规则。每条结论均可回指所出书名与篇目。</footer>
</div></body></html>"""


def main():
    birth = datetime(1990, 5, 15, 10, 30, tzinfo=CST)
    r = bazi_report(birth, "男", "示例")
    out = ROOT / "docs" / "sample_report.html"
    out.write_text(render(r), encoding="utf-8")
    print(f"已生成 {out}  命中 {r['overall']['hit_count']} 条，总评 {r['overall']['level']}")


if __name__ == "__main__":
    main()
