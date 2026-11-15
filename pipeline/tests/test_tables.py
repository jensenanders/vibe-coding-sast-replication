import unittest

from msrpipe import config, tables


class Tables(unittest.TestCase):
    def test_category_name(self):
        self.assertEqual(tables.category_name("A01:2025"), "A01 Broken Access Control")
        self.assertEqual(tables.category_name(config.OWASP_UNMAPPED), "Not in Top 10:2025")

    def test_rq1_category_rows(self):
        cats = list(config.OWASP_2025) + [config.OWASP_UNMAPPED]
        rows = [{"platform": p, "tool": "combined", "category": c, "findings": "1200",
                 "share_of_findings": "0.9999", "repos": "25", "share_of_repos": "0.9999"}
                for p in tables.PLATFORMS for c in cats]
        tex = tables.rq1_category(rows, {"lovable": "4800", "replit": "4800", "boltnew": "4800"},
                                  {p: "50" for p in tables.PLATFORMS})
        # shares come from the counts (1200/4800, 25/50), not from the share columns
        self.assertIn("A05 Injection & 1,200 (25\\,\\%) & 50\\,\\%", tex)
        self.assertIn("Unique findings & 4,800 &  & 4,800 &  & 4,800 &  \\\\", tex)
        self.assertEqual(tex.count("\\\\"), len(cats) + 3)   # two header rows + total

    def test_rq1_severity_omits_empty_levels_and_totals(self):
        rows = []
        for p in tables.PLATFORMS:
            for t in ("combined", "codeql", "gitlab", "codeql_default"):
                for s in tables.SEVERITIES:
                    n = {"High": 3, "Medium": 1}.get(s, 0)
                    rows.append({"platform": p, "tool": t, "severity": s, "findings": str(n),
                                 "share": str(n / 4)})
        tex = tables.rq1_severity(rows)
        self.assertIn("High & 3 (75\\,\\%) & 3 & 3 & 3 (75\\,\\%)", tex)
        self.assertNotIn("Critical &", tex)
        self.assertIn("Total & 4 & 4 & 4 & 4", tex)

    def test_review_precision(self):
        rows = [{"platform": p, "tool": t, "TP": "5", "FP": "15", "uklar": "0", "missing": "0",
                 "precision": "0.25", "ci95_low": "0.112", "ci95_high": "0.469"}
                for p in tables.PLATFORMS for t in ("codeql", "gitlab")]
        tex = tables.review_precision(rows)
        self.assertIn("Bolt.new & 5 & 15 & 0 & 0.25 [0.11--0.47] & 5 & 15 & 0 & 0.25 [0.11--0.47] \\\\", tex)

    def test_markers(self):
        def row(ai="", amb="", other="", share=""):
            return {"other_ai_tool": ai, "ambiguous_instructions": amb, "other_platform": other,
                    "platform_share": share}
        samples = {"lovable": [row(amb="agents.md", share="1.0"), row(share="0.5")],
                   "replit": [row(ai=".cursorrules", share="0.2"), row(share="0.4")],
                   "boltnew": [row(other="lovable"), row()]}
        tex = tables.markers(samples)
        self.assertIn("Other AI coding tool & 0 (0\\,\\%) & 1 (50\\,\\%) & 0 (0\\,\\%) \\\\", tex)
        self.assertIn("Other vibe coding platform & 0 (0\\,\\%) & 0 (0\\,\\%) & 1 (50\\,\\%) \\\\", tex)
        # inclusive quartiles, as in analyse.quartiles: [0.5, 1.0] -> 0.625 / 0.75 / 0.875
        self.assertIn("& 75\\,\\% [63\\,\\%--88\\,\\%] & 30\\,\\% [25\\,\\%--35\\,\\%] & -- \\\\", tex)

    def test_no_double_rounding(self):
        # regression: Replit A04 = 405/3,856 = 10.503 %; the CSV share 0.105 was shown as 10 %
        self.assertEqual(tables.pct(tables.share(405, 3856)), "11\\,\\%")
        self.assertEqual(tables.pct(tables.share(1, 8)), "13\\,\\%")      # 12.5 -> half up
        self.assertEqual(tables.ratio(tables.share(5, 20)), "0.25")
        self.assertEqual(tables.ratio(0.9446), "0.94")
        self.assertEqual(tables.ratio(0.945), "0.94")   # binary 0.945 is just below 0.945

    def test_rq2_density_from_counts(self):
        rows = [{"platform": p, "tool": t, "kloc": "20.0", "repos_zero": "0"}
                for p in tables.PLATFORMS for t, _ in tables.DENSITY_TOOLS]
        repos = [{"platform": p, "kloc": "2.0", "n_combined": str(i), "n_codeql": "0", "n_gitlab": str(i)}
                 for p in tables.PLATFORMS for i in range(1, 6)]
        tex = tables.rq2_density(rows, repos)
        # densities 0.5, 1.0, 1.5, 2.0, 2.5 -> inclusive quartiles 1.0 / 1.5 / 2.0
        self.assertIn("Lovable & 20 & 1.50 [1.00--2.00] & 0 & 0.00 [0.00--0.00] & 0 & 1.50 [1.00--2.00] & 0", tex)

    def test_tukey(self):
        st = tables.tukey([1, 2, 3, 4, 5, 6, 7, 8, 100])
        self.assertEqual((st["q1"], st["median"], st["q3"]), (3, 5, 7))
        self.assertEqual((st["lower"], st["upper"]), (1, 8))
        self.assertEqual(st["outliers"], [100])

    def test_rq2_boxplot_has_no_identifiers(self):
        repos = [{"platform": p, "rank": str(i), "density_combined": str(i / 10)}
                 for p in tables.PLATFORMS for i in range(1, 11)]
        tex = tables.rq2_boxplot(repos)
        self.assertEqual(tex.count("boxplot prepared"), 3)
        self.assertIn("median=0.5500", tex)
        self.assertNotIn("rank", tex)


if __name__ == "__main__":
    unittest.main()
