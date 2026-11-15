import json
import tempfile
import unittest
from pathlib import Path

from msrpipe import owasp

PAGE = """# A01:2025 Something

## Description
See [CWE-999 Not in list](https://cwe.mitre.org/data/definitions/999.html).

## List of Mapped CWEs

* [CWE-22 Improper Limitation ('Path Traversal')](https://cwe.mitre.org/data/definitions/22.html)

* [CWE-23 Relative Path Traversal](https://cwe.mitre.org/data/definitions/23.html)
* [CWE-209	Tab after the id](https://cwe.mitre.org/data/definitions/209.html)

## Next section
* [CWE-1000 After the section](https://cwe.mitre.org/data/definitions/1000.html)
"""


class Lists(unittest.TestCase):
    def test_parse_only_the_section(self):
        self.assertEqual(owasp.parse_cwes(PAGE), [22, 23, 209])

    def test_parse_section_at_end_of_file(self):
        self.assertEqual(owasp.parse_cwes("## List of Mapped CWEs\n* [CWE-79 XSS](u)\n"), [79])

    def test_parse_missing_section_fails(self):
        with self.assertRaises(ValueError):
            owasp.parse_cwes("## Description\n* [CWE-79 XSS](u)\n")

    def test_cwe_index_keeps_every_category(self):
        idx = owasp.cwe_index({"A01:2025": [22, 200], "A04:2025": [200]})
        self.assertEqual(idx, {22: ["A01:2025"], 200: ["A01:2025", "A04:2025"]})
        self.assertEqual(owasp.categories([22, 200, 5], idx), ["A01:2025", "A04:2025"])
        self.assertEqual(owasp.categories([], idx), [])


class Findings(unittest.TestCase):
    def test_in_test_dir_any_depth_not_file_name(self):
        self.assertTrue(owasp.in_test_dir("tests/x.ts"))
        self.assertTrue(owasp.in_test_dir("server/spec/a/x.ts"))
        self.assertFalse(owasp.in_test_dir("src/test.ts"))
        self.assertFalse(owasp.in_test_dir("src/testing/x.ts"))

    def test_reports(self):
        sarif = {"runs": [{"tool": {"driver": {"rules": []}, "extensions": [{"rules": [
            {"id": "js/xss", "shortDescription": {"text": "XSS"}, "properties": {"tags": ["security", "external/cwe/cwe-079", "external/cwe/cwe-116"],
                                            "security-severity": "7.8"}},
            {"id": "js/none", "properties": {"tags": ["security"]}}]}]},
            "results": [
                {"ruleId": "js/xss", "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/a.ts"},
                                                                         "region": {"startLine": 3}}}], "message": {"text": "m"}},
                {"ruleId": "js/xss", "locations": [{"physicalLocation": {"artifactLocation": {"uri": "test/a.ts"}}}]},
                {"ruleId": "js/none", "locations": [{"physicalLocation": {"artifactLocation": {"uri": "b.js"}}}]}]}]}
        gl = {"vulnerabilities": [{"location": {"file": "test/x.py", "start_line": 9}, "severity": "High", "name": "SQLi", "description": "d", "identifiers": [
            {"type": "semgrep_id", "value": "r1"}, {"type": "cwe", "value": "89"}, {"type": "owasp", "value": "A03:2021"}]}]}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "codeql-javascript-typescript.sarif").write_text(json.dumps(sarif))
            (d / "gl-sast-report.json").write_text(json.dumps(gl))
            got = list(owasp.findings(d))
        self.assertEqual(got, [
            ("codeql", {"rule": "js/xss", "path": "src/a.ts", "line": 3, "cwes": [79, 116], "severity": "High",
                        "title": "XSS", "message": "m"}),
            ("codeql", {"rule": "js/none", "path": "b.js", "line": None, "cwes": [], "severity": "Unknown",
                        "title": "", "message": ""}),
            ("gitlab", {"rule": "r1", "path": "test/x.py", "line": 9, "cwes": [89], "severity": "High",
                        "title": "SQLi", "message": "d"}),  # not filtered
        ])


    def test_cvss_rating_boundaries(self):
        got = [owasp.cvss_rating(x) for x in ["9.0", "8.9", "7.0", "6.9", "4.0", "3.9", "0.1", "0.0", None]]
        self.assertEqual(got, ["Critical", "High", "High", "Medium", "Medium", "Low", "Low", "None", "Unknown"])


if __name__ == "__main__":
    unittest.main()
