import tempfile
import unittest
from pathlib import Path

from msrpipe import config, review


def pop(n, p, t):
    return [{"rule": f"r{i}", "path": "a.ts", "line": i, "cwes": [79], "severity": "High", "title": "t",
             "message": "m", "platform": p, "tool": t, "rank": i, "full_name": "o/r", "head_sha": "abc"}
            for i in range(n)]


class Draw(unittest.TestCase):
    def test_draw_is_stratified_and_reproducible(self):
        pops = {(p, t): pop(50, p, t) for p in review.PLATFORMS for t in review.TOOLS}
        a, b = review.draw(pops, 20261031), review.draw(pops, 20261031)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 6 * config.REVIEW_PER_STRATUM)
        self.assertEqual(sum(f["coder2"] for f in a), 6 * config.REVIEW_CODER2_PER_STRATUM)
        for p in review.PLATFORMS:
            for t in review.TOOLS:
                self.assertEqual(sum(f["platform"] == p and f["tool"] == t for f in a), config.REVIEW_PER_STRATUM)

    def test_small_stratum_takes_all(self):
        pops = {(p, t): pop(50, p, t) for p in review.PLATFORMS for t in review.TOOLS}
        pops[("lovable", "codeql")] = pop(3, "lovable", "codeql")
        self.assertEqual(sum(f["tool"] == "codeql" and f["platform"] == "lovable" for f in review.draw(pops, 1)), 3)

    def test_url_points_at_the_line_and_sha(self):
        f = {"full_name": "o/r", "head_sha": "abc", "path": "src/a.ts", "line": 7}
        self.assertEqual(review.url(f), "https://github.com/o/r/blob/abc/src/a.ts#L7")
        self.assertEqual(review.url({**f, "line": None}), "https://github.com/o/r/blob/abc/src/a.ts")


class Score(unittest.TestCase):
    def test_norm(self):
        self.assertEqual([review.norm(x) for x in ["tp", " FP ", "uklar", "måske", ""]],
                         ["TP", "FP", "uklar", "uklar", "missing"])

    def test_read_sheet_semicolon_and_comma(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.csv"
            p.write_text("﻿id;url;label\nF001;https://x/a,b;TP\n", encoding="utf-8")
            self.assertEqual(review.read_sheet(p)[0]["label"], "TP")
            p.write_text("id,url,label\nF001,u,FP\n", encoding="utf-8")
            self.assertEqual(review.read_sheet(p)[0]["label"], "FP")

    def test_wilson_and_kappa(self):
        self.assertEqual(review.wilson(10, 20), (0.299, 0.701))
        self.assertEqual(review.wilson(0, 0), (None, None))
        self.assertEqual(review.cohen_kappa([("TP", "TP"), ("FP", "FP")]), 1.0)
        self.assertEqual(review.cohen_kappa([("TP", "FP"), ("FP", "TP")]), -1.0)
        # 3 of 4 agree; pe = (2*3 + 2*1) / 16 = 0.5 -> kappa 0.5
        self.assertEqual(review.cohen_kappa([("TP", "TP"), ("TP", "TP"), ("FP", "FP"), ("FP", "TP")]), 0.5)

    def test_precision_rows(self):
        key = [{"id": f"F{i}", "platform": "lovable", "tool": "gitlab"} for i in range(4)]
        labels = {"F0": "TP", "F1": "FP", "F2": "uklar"}
        r = next(r for r in review.precision_rows(labels, key) if r["platform"] == "lovable" and r["tool"] == "gitlab")
        self.assertEqual((r["TP"], r["FP"], r["uklar"], r["missing"], r["precision"]), (1, 1, 1, 1, 0.5))


if __name__ == "__main__":
    unittest.main()
