# -*- coding: utf-8 -*-
"""回归测试：python -m unittest discover -s tests -v"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import calendar_core as C  # noqa: E402
from src import tables as T  # noqa: E402
from src.analyzers import bazi as B  # noqa: E402
from src.analyzers import liuri as LR  # noqa: E402
from src.analyzers import liuyao as L  # noqa: E402
from src.analyzers import meihua as M  # noqa: E402
from src.analyzers import xingming as X  # noqa: E402
from src.analyzers import zeri as Z  # noqa: E402
from src.engine import RuleEngine, eval_when, load_rules  # noqa: E402
from src.predict import (bazi_report, liuri_report, liuyao_report,  # noqa: E402
                         meihua_report, rule_stats, xingming_report,
                         zeri_report)


class TestCalendar(unittest.TestCase):
    def test_day_pillar_benchmark(self):
        # 2000-01-01 为戊午日（通行万年历）
        self.assertEqual(C.day_ganzhi(datetime(2000, 1, 1, 12, tzinfo=C.CST)), "戊午")
        # 2024-01-01 为甲子日
        self.assertEqual(C.day_ganzhi(datetime(2024, 1, 1, 12, tzinfo=C.CST)), "甲子")

    def test_sizhu_benchmarks(self):
        cases = [
            (datetime(2000, 1, 1, 0, 30, tzinfo=C.CST), ["己卯", "丙子", "戊午", "壬子"]),
            (datetime(2024, 2, 4, 17, 0, tzinfo=C.CST), ["甲辰", "丙寅", "戊戌", "辛酉"]),
            (datetime(2024, 1, 1, 12, 0, tzinfo=C.CST), ["癸卯", "甲子", "甲子", "庚午"]),
        ]
        for dt, expect in cases:
            with self.subTest(dt=dt):
                self.assertEqual(C.paipan(dt)["pillars"], expect)

    def test_lichun_boundary(self):
        # 2024 立春约 2/4 16:27，前后一分钟应换年柱
        before = C.paipan(datetime(2024, 2, 4, 16, 0, tzinfo=C.CST))
        after = C.paipan(datetime(2024, 2, 4, 17, 0, tzinfo=C.CST))
        self.assertEqual(before["year"], "癸卯")
        self.assertEqual(after["year"], "甲辰")

    def test_jieqi_reasonable(self):
        # 节气应落在合理日期区间，且全年严格递增
        table = C.jieqi_of_year(2024)
        self.assertEqual(len(table), 24)
        times = [t for _, t in table]
        self.assertEqual(times, sorted(times))

    def test_wuxing_scores_sum_100(self):
        p = C.paipan(datetime(1990, 5, 15, 10, 30, tzinfo=C.CST))["pillars"]
        s = C.element_scores(p)
        self.assertAlmostEqual(sum(s.values()), 100.0, delta=0.5)


class TestShishen(unittest.TestCase):
    def test_ten_gods(self):
        self.assertEqual(C.shishen("甲", "甲"), "比肩")
        self.assertEqual(C.shishen("甲", "乙"), "劫财")
        self.assertEqual(C.shishen("甲", "丙"), "食神")
        self.assertEqual(C.shishen("甲", "丁"), "伤官")
        self.assertEqual(C.shishen("甲", "戊"), "偏财")
        self.assertEqual(C.shishen("甲", "己"), "正财")
        self.assertEqual(C.shishen("甲", "庚"), "七杀")
        self.assertEqual(C.shishen("甲", "辛"), "正官")
        self.assertEqual(C.shishen("甲", "壬"), "偏印")
        self.assertEqual(C.shishen("甲", "癸"), "正印")

    def test_changsheng(self):
        self.assertEqual(C.changsheng("甲", "亥"), "长生")
        self.assertEqual(C.changsheng("甲", "卯"), "帝旺")
        self.assertEqual(C.changsheng("丙", "午"), "帝旺")
        self.assertEqual(C.changsheng("壬", "申"), "长生")


class TestXingming(unittest.TestCase):
    def test_wuge_single(self):
        # 王(4) 伟(11)：天5 人15 地12 外2 总15
        w = X.compute_wuge([4], [11])
        self.assertEqual(w["天格"]["num"], 5)
        self.assertEqual(w["人格"]["num"], 15)
        self.assertEqual(w["地格"]["num"], 12)
        self.assertEqual(w["外格"]["num"], 2)
        self.assertEqual(w["总格"]["num"], 15)

    def test_wuge_compound(self):
        # 司马(5,10) 懿(22)：天15 人32 地23 外6 总37
        w = X.compute_wuge([5, 10], [22])
        self.assertEqual(w["天格"]["num"], 15)
        self.assertEqual(w["人格"]["num"], 32)
        self.assertEqual(w["地格"]["num"], 23)
        self.assertEqual(w["总格"]["num"], 37)
        self.assertEqual(w["外格"]["num"], 6)

    def test_sancai_ke(self):
        self.assertEqual(X.sancai_relation("土", "土", "木"), "相克")
        self.assertEqual(X.sancai_relation("木", "火", "土"), "相生")

    def test_shuli_normalize(self):
        self.assertEqual(X.normalize(82), 1)
        self.assertEqual(X.normalize(81), 81)


class TestZeri(unittest.TestCase):
    def test_jianchu_cycle(self):
        # 建除索引 = (日支序 - 月支序) mod 12，全月应覆盖 12 个值
        seen = set()
        for day in range(1, 29):
            r = Z.analyze(datetime(2026, 11, day, 12, tzinfo=C.CST))
            seen.add(r["jianchu"])
        self.assertEqual(len(seen), 12)

    def test_huangdao_consistency(self):
        r = Z.analyze(datetime(2026, 11, 9, 12, tzinfo=C.CST))
        self.assertEqual(r["zhishen"] in T.ZHISHEN_HUANGDAO, r["huangdao"])


class TestMeihua(unittest.TestCase):
    def test_qigua(self):
        g = M.qigua(23, 17)
        self.assertEqual(g["upper"], "艮")   # 23 % 8 = 7 -> 艮
        self.assertEqual(g["lower"], "乾")   # 17 % 8 = 1 -> 乾
        self.assertEqual(g["dong"], 4)       # 40 % 6 = 4
        self.assertEqual(g["ti"], "乾")
        self.assertEqual(g["yong"], "艮")
        self.assertEqual(g["mh_tiyong"], "用生体")

    def test_bagua_bits_roundtrip(self):
        for g, bits in T.BAGUA_BITS.items():
            self.assertEqual(T.BITS_BAGUA[bits], g)


class TestLiuyao(unittest.TestCase):
    def test_bagong_coverage(self):
        # 八宫应覆盖全部 64 卦，无重复
        self.assertEqual(len(L.BAGONG), 64)

    def test_shi_ying(self):
        # 八纯卦世6应3
        for g in T.BAGUA:
            bits = T.BAGUA_BITS[g] * 2
            info = L.BAGONG[tuple(bits)]
            self.assertEqual(info["shi"], 6)
            self.assertEqual(info["ying"], 3)

    def test_liuqin(self):
        self.assertEqual(L.liuqin("金", "金"), "兄弟")
        self.assertEqual(L.liuqin("金", "土"), "父母")
        self.assertEqual(L.liuqin("金", "水"), "子孙")
        self.assertEqual(L.liuqin("金", "火"), "官鬼")
        self.assertEqual(L.liuqin("金", "木"), "妻财")

    def test_analyze_runs(self):
        r = L.analyze([7, 8, 9, 7, 6, 8], "求财")
        self.assertIn("name", r)
        self.assertEqual(len(r["yao"]), 6)


class TestEngine(unittest.TestCase):
    def test_all_rule_files_parse(self):
        for f in (ROOT / "src" / "rules").glob("*.json"):
            rules = load_rules(f)
            self.assertGreater(len(rules), 0, f)
            for r in rules:
                for k in ("id", "book", "system", "when", "then"):
                    self.assertIn(k, r, f"{f.name}:{r.get('id')}")

    def test_rule_ids_unique(self):
        ids = []
        for f in (ROOT / "src" / "rules").glob("*.json"):
            ids += [r["id"] for r in load_rules(f)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rule_stats(self):
        st = rule_stats()
        self.assertGreaterEqual(st["total_books"], 20)
        self.assertGreaterEqual(st["total_rules"], 100)

    def test_no_dead_rule(self):
        """每条八字规则至少在 3000 个抽样命盘中命中一次。"""
        import random
        from datetime import timedelta
        rules = load_rules(ROOT / "src" / "rules" / "bazi.json")
        eng = RuleEngine(rules)
        rng = random.Random(11)
        hits = {r["id"]: 0 for r in rules}
        for _ in range(3000):
            d = (datetime(1955, 1, 1) + timedelta(days=rng.randint(0, 20000),
                                                  hours=rng.randint(0, 23))).replace(tzinfo=C.CST)
            ctx = B.analyze(C.paipan(d)["pillars"], rng.choice(["男", "女"]), d)
            for h in eng.match(ctx, "bazi"):
                hits[h["id"]] += 1
        dead = [k for k, v in hits.items() if v == 0]
        self.assertEqual(dead, [], f"死规则: {dead}")

    def test_predicate_not(self):
        ctx = {"day_master": "甲", "day_master_element": "木"}
        self.assertTrue(eval_when({"not": {"day_master": "乙"}}, ctx))
        self.assertFalse(eval_when({"not": {"day_master": "甲"}}, ctx))


class TestLiuri(unittest.TestCase):
    """流日运势：逐日干支、冲合判定与计分口径。"""

    BIRTH = datetime(1990, 5, 15, 10, 30, tzinfo=C.CST)
    BASE = datetime(2026, 11, 10, 12, tzinfo=C.CST)

    def _natal(self):
        return B.analyze(C.paipan(self.BIRTH)["pillars"], "男", self.BIRTH)

    def test_days_continuous(self):
        """日期逐日连续，干支按六十甲子递进。"""
        r = liuri_report(self.BIRTH, "男", self.BASE, 60)
        days = r["days"]
        self.assertEqual(len(days), 60)
        for i in range(1, len(days)):
            self.assertEqual(
                C.gz_index(days[i]["ganzhi"]),
                (C.gz_index(days[i - 1]["ganzhi"]) + 1) % 60,
                days[i]["date"],
            )

    def test_score_is_sum_of_hits(self):
        """单日分数必须等于当日命中规则之和，且不含大运流年背景。"""
        bg = {"LR-31", "LR-32", "LR-33"}
        r = liuri_report(self.BIRTH, "男", self.BASE, 120)
        for d in r["days"]:
            self.assertEqual(d["score"], sum(h["then"]["score"] for h in d["hits"]))
            self.assertEqual(d["hit_count"], len(d["hits"]))
            for h in d["hits"]:
                self.assertNotIn(h["id"], bg, f"{d['date']} 背景规则混入计分")

    def test_level_thresholds(self):
        r = liuri_report(self.BIRTH, "男", self.BASE, 366)
        for d in r["days"]:
            s = d["score"]
            if s >= 4:
                want = "大吉"
            elif s >= 2:
                want = "吉"
            elif s > -2:
                want = "平"
            elif s > -4:
                want = "凶"
            else:
                want = "大凶"
            self.assertEqual(d["level"], want, f"{d['date']} score={s}")

    def test_chong_detected(self):
        """流日支冲日支时须记录该柱：命局庚辰日，戌日冲辰。"""
        natal = self._natal()
        seen = 0
        for i in range(60):
            ctx = LR.analyze_day(natal, self.BASE + timedelta(days=i))
            if ctx["day_zhi"] == "戌":
                self.assertIn("日", ctx["lr_chong"])
                seen += 1
        self.assertGreater(seen, 0)

    def test_kongwang_by_day_branch(self):
        """日柱庚辰属甲戌旬，空亡申酉；逢申酉日须判空。"""
        natal = self._natal()
        self.assertEqual(natal["kongwang"]["branches"], ["申", "酉"])
        for i in range(60):
            ctx = LR.analyze_day(natal, self.BASE + timedelta(days=i))
            self.assertEqual(ctx["lr_kong"], ctx["day_zhi"] in ("申", "酉"),
                             f"{ctx['date']} {ctx['day_ganzhi']}")

    def test_ten_god_of_day(self):
        """流日十神由当日天干对日主决定。"""
        natal = self._natal()
        for i in range(30):
            ctx = LR.analyze_day(natal, self.BASE + timedelta(days=i))
            self.assertEqual(ctx["lr_ten_god"],
                             C.shishen(natal["day_master"], ctx["day_gan"]))

    def test_all_liuri_rules_reachable(self):
        """流日规则无死条目：5 个命主各一年内每条至少命中一次。"""
        rules = load_rules(ROOT / "src" / "rules" / "liuri.json")
        eng = RuleEngine(rules)
        cnt = {r["id"]: 0 for r in rules}
        for b in ((1990, 5, 15, 10, 30), (1985, 3, 2, 8, 0), (1998, 12, 20, 22, 15),
                  (1976, 7, 7, 14, 0), (2003, 1, 30, 6, 45)):
            birth = datetime(*b, tzinfo=C.CST)
            natal = B.analyze(C.paipan(birth)["pillars"], "男", birth)
            for i in range(366):
                ctx = LR.analyze_day(natal, datetime(2026, 1, 1, 12, tzinfo=C.CST)
                                     + timedelta(days=i))
                for h in eng.match(ctx, "liuri"):
                    cnt[h["id"]] += 1
        dead = [k for k, v in cnt.items() if v == 0]
        self.assertEqual(dead, [], f"死规则: {dead}")

    def test_report_shape(self):
        r = liuri_report(self.BIRTH, "男", self.BASE, 7)
        self.assertEqual(r["kind"], "liuri")
        self.assertEqual(len(r["days"]), 7)
        self.assertIn("disclaimer", r)
        self.assertEqual(sum(r["distribution"].values()), 7)
        for d in r["days"]:
            for h in d["hits"]:
                self.assertTrue(h["book"])
                self.assertIn(h["confidence"], ("A", "B", "C"))


class TestReports(unittest.TestCase):
    def test_all_reports_run(self):
        r = bazi_report(datetime(1990, 5, 15, 10, 30, tzinfo=C.CST), "男")
        self.assertIn("overall", r)
        self.assertEqual(len(r["summary"]["pillars"]), 4)
        self.assertIn("disclaimer", r)

        self.assertEqual(meihua_report(23, 17)["kind"], "meihua")
        self.assertEqual(liuyao_report([7, 8, 9, 7, 6, 8], "求财")["kind"], "liuyao")
        self.assertEqual(zeri_report(datetime(2026, 11, 9, 12, tzinfo=C.CST))["kind"], "zeri")
        self.assertEqual(xingming_report([4], [11], "王伟")["kind"], "xingming")

    def test_every_hit_has_source(self):
        r = bazi_report(datetime(1985, 8, 20, 6, 15, tzinfo=C.CST), "女")
        for h in r["hits"]:
            self.assertTrue(h["book"])
            self.assertTrue(h["then"]["text"])
            self.assertIn(h["confidence"], ("A", "B", "C"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
