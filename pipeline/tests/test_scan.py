import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from msrpipe import scan
from test_screen import make_repo

HUMAN = "someone@example.com"


class Helpers(unittest.TestCase):
    def test_codeql_langs(self):
        self.assertEqual(scan.codeql_langs(["src/App.tsx", "README.md"]), ["javascript-typescript"])
        self.assertEqual(scan.codeql_langs(["app.py", "web/x.mjs"]), ["javascript-typescript", "python"])
        self.assertEqual(scan.codeql_langs(["index.html", "style.css"]), [])

    def test_sarif_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sarif"
            p.write_text(json.dumps({"runs": [{"results": [{}, {}]}, {"results": [{}]}]}))
            self.assertEqual(scan.sarif_count(p), 3)

    def test_export_only_tracked_files_at_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", {"a.ts": "x\n", "sub/b.py": "y\n"}, [(HUMAN, HUMAN)])
            (root / "untracked.js").write_text("z\n")
            sha = scan.sh(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()
            files = scan.export_tree(root, sha, Path(d) / "src")
            self.assertEqual(sorted(files), ["a.ts", "sub/b.py"])
            self.assertFalse((Path(d) / "src" / "untracked.js").exists())
            self.assertFalse((Path(d) / "src" / ".git").exists())
            self.assertEqual((root / "untracked.js").read_text(), "z\n")     # clone untouched


class ScanRepo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        base = Path(self.d.name)
        self.clones, self.scratch, self.raw = base / "clones", base / "scratch", base / "raw"
        root = make_repo(self.clones / "lovable" / "00007", {"src/a.ts": "let a = 1;\n"}, [(HUMAN, HUMAN)])
        self.sha = scan.sh(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()

    def tearDown(self):
        self.d.cleanup()

    def row(self, sha):
        return {"rank": "7", "full_name": "o/r", "head_sha": sha}

    def test_wrong_sha_fails_without_running_tools(self):
        with mock.patch.object(scan, "docker") as dk:
            row = scan.scan_repo("lovable", self.row("0" * 40), self.clones, self.scratch, self.raw)
        self.assertEqual(row["status"], "failed")
        dk.assert_not_called()

    def test_reports_moved_and_scratch_removed(self):
        def fake_codeql(tag, src, db, reports, langs):
            (reports / "codeql-javascript-typescript.sarif").write_text("{}")
            return "ok", 1.0, 0
        def fake_gitlab(tag, src, reports):
            (reports / "gl-sast-report.json").write_text('{"vulnerabilities": []}')
            return "ok", 1.0, 0
        with mock.patch.object(scan, "run_codeql", fake_codeql), mock.patch.object(scan, "run_gitlab", fake_gitlab), \
             mock.patch.object(scan, "run_cloc", return_value=1):
            row = scan.scan_repo("lovable", self.row(self.sha), self.clones, self.scratch, self.raw)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["codeql_langs"], "javascript-typescript")
        out = self.raw / "lovable" / "00007"
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["codeql-javascript-typescript.sarif", "gl-sast-report.json"])
        self.assertFalse((self.scratch / "lovable" / "00007").exists())

    def test_tool_failure_is_partial(self):
        with mock.patch.object(scan, "run_codeql", return_value=("create timeout: ", 3600.0, 0)), \
             mock.patch.object(scan, "run_gitlab", return_value=("ok", 1.0, 0)), \
             mock.patch.object(scan, "run_cloc", return_value=1):
            row = scan.scan_repo("lovable", self.row(self.sha), self.clones, self.scratch, self.raw)
        self.assertEqual((row["status"], row["detail"]), ("partial", "failed: codeql"))


if __name__ == "__main__":
    unittest.main()
