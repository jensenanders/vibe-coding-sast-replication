import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from msrpipe import screen, shuffle

LOVABLE_OLD = "159125892+gpt-engineer-app[bot]@users.noreply.github.com"
LOVABLE_NEW = "159125892+lovable-dev[bot]@users.noreply.github.com"
REPLIT = "agent@replit.com"
HUMAN = "someone@example.com"

BACKEND_60 = "\n".join(f"export const v{i} = {i};" for i in range(60)) + "\n"


def make_repo(d, files, commits):
    """files: {path: text}; commits: [(author_email, committer_email)]; first commit adds the files."""
    root = Path(d)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    for i, (a, c) in enumerate(commits):
        env = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": a, "GIT_COMMITTER_NAME": "c",
               "GIT_COMMITTER_EMAIL": c, "PATH": "/usr/bin:/bin"}
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", f"c{i}"],
                       check=True, env=env)
    return root


class Shuffle(unittest.TestCase):
    def test_sorted_then_seeded(self):
        names = ["c/z", "a/x", "b/y", "d/w"]
        self.assertEqual(shuffle.order(names, 20261031), shuffle.order(sorted(names), 20261031))
        self.assertEqual(sorted(shuffle.order(names, 1)), sorted(names))
        self.assertNotEqual([shuffle.order(names, s) for s in range(5)],
                            [shuffle.order(names, 20261031)] * 5)


class PlatformTrace(unittest.TestCase):
    def test_lovable_counts_old_and_new_bot_name(self):
        emails = [(LOVABLE_OLD, "x"), (LOVABLE_NEW, "x"), ("noreply@lovable.dev", "x"), (HUMAN, HUMAN)]
        self.assertEqual(screen.platform_commits("lovable", emails), 3)

    def test_lovable_is_author_replit_is_committer(self):
        self.assertEqual(screen.platform_commits("lovable", [(HUMAN, LOVABLE_NEW)]), 0)
        self.assertEqual(screen.platform_commits("replit", [(REPLIT, HUMAN)]), 0)
        self.assertEqual(screen.platform_commits("replit", [(HUMAN, REPLIT)]), 1)

    def test_other_bot_with_similar_name_does_not_match(self):
        self.assertEqual(screen.platform_commits("lovable", [("1+lovable-dev[bot]@users.noreply.github.com", "")]), 0)

    def test_bolt_needs_root_dir(self):
        self.assertTrue(screen.bolt_trace([".bolt/config.json", "src/a.ts"]))
        self.assertFalse(screen.bolt_trace(["web/.bolt/config.json"]))
        self.assertIsNone(screen.platform_commits("boltnew", []))


class Rules(unittest.TestCase):
    def test_backend_files(self):
        files = ["server/a.ts", "server/node_modules/x.js", "api/b.py", "api/c.tsx", "src/api/d.ts",
                 "supabase/functions/f/index.ts", "functions/dist/e.js", "netlify/functions/g.mjs",
                 "artifacts/api-server/src/index.ts", "artifacts/web-app/src/main.ts"]
        self.assertEqual(screen.backend_files(files),
                         ["server/a.ts", "api/b.py", "supabase/functions/f/index.ts", "netlify/functions/g.mjs",
                          "artifacts/api-server/src/index.ts"])

    def test_lizard_crash_counts_as_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "server").mkdir()
            (root / "server/a.ts").write_text(BACKEND_60)
            (root / "server/b.ts").write_text("x")
            orig = screen.lizard.analyze_file

            def flaky(path):
                if path.endswith("b.ts"):
                    raise IndexError("list index out of range")
                return orig(path)

            screen.lizard.analyze_file = flaky
            try:
                self.assertEqual(screen.backend_nloc(root, ["server/a.ts", "server/b.ts"]), (60, 1))
            finally:
                screen.lizard.analyze_file = orig

    def test_server_suffix_files(self):
        files = ["src/lib/pay.functions.ts", "src/integrations/supabase/client.server.ts",
                 "src/lib/util.ts", "src/routes/index.server.tsx", "node_modules/x/a.server.js",
                 "server/a.server.ts"]
        self.assertEqual(screen.backend_files(files),
                         ["src/lib/pay.functions.ts", "src/integrations/supabase/client.server.ts",
                          "server/a.server.ts"])

    def test_mobile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "web").mkdir()
            (root / "app.json").write_text(json.dumps({"name": "not expo"}))
            (root / "web/app.json").write_text("{broken")
            self.assertEqual(screen.mobile_file(root, ["app.json", "web/app.json"]), "")
            (root / "mob").mkdir()
            (root / "mob/app.json").write_text(json.dumps({"expo": {"name": "x"}}))
            self.assertEqual(screen.mobile_file(root, ["app.json", "mob/app.json"]), "mob/app.json")
            self.assertEqual(screen.mobile_file(root, ["deep/eas.json"]), "deep/eas.json")

    def test_markers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "package.json").write_text('{"devDependencies": {"lovable-tagger": "1.0"}}')
            files = [".cursor/rules.md", "x/.aider.conf.yml", ".github/copilot-instructions.md",
                     "AGENTS.md", "docs/Claude.md", ".replit", ".bolt/config.json", "package.json"]
            ai, amb, other = screen.markers(root, files, "replit")
            self.assertEqual(ai, ".aider*;.cursor;copilot-instructions")
            self.assertEqual(amb, "agents.md;claude.md")
            self.assertEqual(other, "boltnew;lovable")         # .replit is Replit's own file


class Analyse(unittest.TestCase):
    def test_included_lovable(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d, {"supabase/functions/f/index.ts": BACKEND_60, "src/App.tsx": "x"},
                             [(LOVABLE_OLD, LOVABLE_OLD), (HUMAN, HUMAN), (LOVABLE_NEW, LOVABLE_NEW)])
            reason, info = screen.analyse("lovable", root)
            self.assertEqual(reason, "")
            self.assertEqual((info["n_commits"], info["n_platform_commits"]), (3, 2))
            self.assertEqual(info["platform_share"], 0.6667)
            self.assertEqual(info["backend_nloc"], 60)
            self.assertEqual(len(info["head_sha"]), 40)

    def test_reasons_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d, {"eas.json": "{}", "server/a.ts": BACKEND_60}, [(HUMAN, HUMAN)])
            self.assertEqual(screen.analyse("replit", root)[0], "no_platform_trace")
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d, {"eas.json": "{}", "server/a.ts": BACKEND_60}, [(HUMAN, REPLIT)])
            self.assertEqual(screen.analyse("replit", root)[0], "mobile")
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d, {".bolt/config.json": "{}", "server/a.ts": "const a = 1;\n"}, [(HUMAN, HUMAN)])
            reason, info = screen.analyse("boltnew", root)
            self.assertEqual(reason, "backend_nloc_below_min")
            self.assertEqual(info["platform_share"], "")


class EmptyRepo(unittest.TestCase):
    def test_has_commits(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertFalse(screen.has_commits(Path(d)))
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(screen.has_commits(make_repo(d, {"a.txt": "x"}, [(HUMAN, HUMAN)])))


class Driver(unittest.TestCase):
    def test_owner_rule_and_resume(self):
        calls = []

        def fake_clone(fn, dest):
            calls.append(fn)
            dest.mkdir(parents=True)
            return True, "", 0.1

        def fake_analyse(platform, root):
            return "", {"head_sha": "0" * 40}

        orig = screen.clone, screen.analyse, screen.has_commits
        screen.clone, screen.analyse, screen.has_commits = fake_clone, fake_analyse, lambda root: True
        try:
            with tempfile.TemporaryDirectory() as d:
                order = [(1, "Alice/a"), (2, "alice/b"), (3, "bob/c"), (4, "carl/d")]
                csv_path = Path(d) / "s.csv"
                self.assertEqual(screen.screen_platform("lovable", order[:2], csv_path, Path(d) / "c", 3), 1)
                n = screen.screen_platform("lovable", order, csv_path, Path(d) / "c", 3)
                rows = screen.read_rows(csv_path)
                self.assertEqual(n, 3)
                self.assertEqual([r["reason"] for r in rows], ["", "owner_taken", "", ""])
                self.assertEqual(calls, ["Alice/a", "bob/c", "carl/d"])   # owner_taken is not cloned
                self.assertTrue((Path(d) / "c/lovable/00001").exists())   # included clone kept
        finally:
            screen.clone, screen.analyse, screen.has_commits = orig


if __name__ == "__main__":
    unittest.main()
