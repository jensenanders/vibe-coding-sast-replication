import json
import tempfile
import unittest
from pathlib import Path

from msrpipe import analyse, config


def sarif(results):
    return {"runs": [{"tool": {"driver": {"rules": []}, "extensions": [{"rules": [
        {"id": "js/a", "properties": {"tags": ["external/cwe/cwe-079", "external/cwe/cwe-209"], "security-severity": "6.1"}},
        {"id": "js/b", "properties": {"tags": ["external/cwe/cwe-606"], "security-severity": "9.3"}}]}]},
        "results": [{"ruleId": r, "locations": [{"physicalLocation": {"artifactLocation": {"uri": u},
                                                                       "region": {"startLine": 1}}}]} for r, u in results]}]}


class Analyse(unittest.TestCase):
    def test_categories_and_unmapped(self):
        idx = {79: ["A05:2025"], 209: ["A10:2025"]}
        self.assertEqual(analyse.owasp_categories([79, 209], idx), ["A05:2025", "A10:2025"])
        self.assertEqual(analyse.owasp_categories([606], idx), [config.OWASP_UNMAPPED])
        self.assertEqual(analyse.owasp_categories([], idx), [config.OWASP_UNMAPPED])

    def test_kloc_counts_only_scanned_languages(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cloc.json"
            p.write_text(json.dumps({"header": {}, "TypeScript": {"code": 1500}, "JSX": {"code": 200},
                                     "JSON": {"code": 9000}, "CSS": {"code": 700}, "Python": {"code": 300},
                                     "SUM": {"code": 11700}}))
            self.assertAlmostEqual(analyse.kloc(p), 2.0)

    def test_nested_takes_lowest_ranks_per_platform(self):
        rrows = [{"platform": p, "rank": k} for p in analyse.PLATFORMS for k in (7, 2, 9, 4)]
        frows = [{"platform": "lovable", "rank": k} for k in (2, 2, 9)]
        f, r = analyse.nested(frows, rrows, 2)
        self.assertEqual(sorted(x["rank"] for x in r if x["platform"] == "replit"), [2, 4])
        self.assertEqual(len(r), 2 * len(analyse.PLATFORMS))
        self.assertEqual([x["rank"] for x in f], [2, 2])

    def test_end_to_end_counts(self):
        idx = {79: ["A05:2025"], 209: ["A10:2025"]}
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            for p in analyse.PLATFORMS:
                repo = raw / p / "00001"
                repo.mkdir(parents=True)
                (repo / "cloc.json").write_text(json.dumps({"TypeScript": {"code": 2000}}))
                (repo / "codeql-javascript-typescript.sarif").write_text(json.dumps(
                    sarif([("js/a", "src/x.ts"), ("js/b", "src/y.ts"), ("js/a", "tests/z.ts")])))
                (repo / "gl-sast-report.json").write_text(json.dumps({"vulnerabilities": []}))
            frows, rrows, jrows = analyse.collect_rows(raw, idx, default_ids={"js/a"})
            cat, sev, cwe, dens = analyse.summarise(frows, rrows)
        lov = {r["category"]: r for r in cat if r["platform"] == "lovable" and r["tool"] == "codeql"}
        # tests/ is dropped; js/a counts once in totals, in both A05 and A10
        self.assertEqual(rrows[0]["n_codeql"], 2)
        self.assertEqual(rrows[0]["n_codeql_default"], 1)
        self.assertEqual((lov["A05:2025"]["findings"], lov["A10:2025"]["findings"],
                          lov[config.OWASP_UNMAPPED]["findings"]), (1, 1, 1))
        self.assertEqual(lov["A05:2025"]["share_of_findings"], 0.5)
        s = {r["severity"]: r["findings"] for r in sev if r["platform"] == "lovable" and r["tool"] == "codeql"}
        self.assertEqual((s["Medium"], s["Critical"]), (1, 1))
        d = next(r for r in dens if r["platform"] == "lovable" and r["tool"] == "codeql")
        self.assertEqual((d["findings"], d["kloc"], d["pooled_per_kloc"], d["median_per_kloc"]), (2, 2.0, 1.0, 1.0))
        g = next(r for r in dens if r["platform"] == "lovable" and r["tool"] == "gitlab")
        self.assertEqual((g["findings"], g["repos_zero"]), (0, 1))



def f(path, line, cwes, cats, sev="Medium", rule="r"):
    return {"rule": rule, "path": path, "line": line, "cwes": cwes, "categories": cats, "severity": sev}


class Matching(unittest.TestCase):
    U = config.OWASP_UNMAPPED

    def test_rule_c_line_tolerance_and_type(self):
        cq = [f("a.ts", 10, [79], ["A05:2025"])]
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 13, [20], ["A05:2025"])], "C"), [(0, 0)])  # shared category
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 14, [79], ["A05:2025"])], "C"), [])         # 4 lines away
        self.assertEqual(analyse.match_pairs(cq, [f("b.ts", 10, [79], ["A05:2025"])], "C"), [])         # other file
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 10, [338], ["A04:2025"])], "C"), [])        # other type

    def test_unmapped_is_not_a_shared_category(self):
        cq = [f("a.ts", 1, [606], [self.U])]
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 1, [185], [self.U])], "C"), [])
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 1, [606], [self.U])], "C"), [(0, 0)])     # shared CWE

    def test_rules_a_and_e(self):
        cq = [f("a.ts", 10, [79], ["A05:2025"])]
        gl = [f("a.ts", 10, [20], ["A05:2025"])]
        self.assertEqual(analyse.match_pairs(cq, gl, "A"), [])                                          # A needs the CWE
        self.assertEqual(analyse.match_pairs(cq, [f("a.ts", 500, [20], ["A05:2025"])], "E"), [(0, 0)])

    def test_one_to_one_closest_first(self):
        cq = [f("a.ts", 10, [79], ["A05:2025"]), f("a.ts", 12, [79], ["A05:2025"])]
        gl = [f("a.ts", 12, [79], ["A05:2025"])]
        self.assertEqual(analyse.match_pairs(cq, gl, "C"), [(1, 0)])

    def test_merge(self):
        m = analyse.merge(f("a.ts", 10, [79], ["A05:2025"], "Medium", "cq"),
                          f("a.ts", 11, [79, 606], ["A05:2025", self.U], "High", "gl"))
        self.assertEqual((m["rule"], m["line"], m["cwes"], m["categories"], m["severity"]),
                         ("cq|gl", 10, [79, 606], ["A05:2025"], "High"))

    def test_combined_and_jaccard_end_to_end(self):
        idx = {79: ["A05:2025"]}
        cq = {"runs": [{"tool": {"driver": {"rules": [{"id": "js/xss", "properties": {
            "tags": ["external/cwe/cwe-079"], "security-severity": "6.1"}}]}},
            "results": [{"ruleId": "js/xss", "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "src/a.ts"}, "region": {"startLine": l}}}]} for l in (5, 50)]}]}
        gl = {"vulnerabilities": [{"location": {"file": "src/a.ts", "start_line": 7}, "severity": "High",
                                   "identifiers": [{"type": "cwe", "value": "79"}]}]}
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            for p in analyse.PLATFORMS:
                repo = raw / p / "00001"
                repo.mkdir(parents=True)
                (repo / "cloc.json").write_text(json.dumps({"TypeScript": {"code": 1000}}))
                (repo / "codeql-javascript-typescript.sarif").write_text(json.dumps(cq))
                (repo / "gl-sast-report.json").write_text(json.dumps(gl))
            frows, rrows, jrows = analyse.collect_rows(raw, idx, default_ids=set())
        self.assertEqual((rrows[0]["n_codeql"], rrows[0]["n_gitlab"], rrows[0]["n_combined"]), (2, 1, 2))
        jc = analyse.jaccard_summary(jrows)
        c = next(r for r in jc if r["platform"] == "lovable" and r["rule"] == "C")
        self.assertEqual((c["matched"], c["union"], c["jaccard_pooled"]), (1, 2, 0.5))
        sev = sorted(r["severity"] for r in frows if r["platform"] == "lovable" and r["tool"] == "combined")
        self.assertEqual(sev, ["High", "Medium"])


if __name__ == "__main__":
    unittest.main()
