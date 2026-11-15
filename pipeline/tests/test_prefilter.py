import tempfile
import unittest
from pathlib import Path

from msrpipe import config, prefilter

START = "2025-10-31"


def meta(fork=False, archived=False, pushed="2026-05-01T10:00:00Z", name="o/r"):
    return {"nameWithOwner": name, "isFork": fork, "isArchived": archived, "pushedAt": pushed}


class MultiPlatform(unittest.TestCase):
    def test_only_names_in_two_or_more_frames(self):
        frames = {"lovable": ["a/x", "b/y"], "replit": ["b/y", "c/z"], "boltnew": ["c/z", "c/z", "d/w"]}
        self.assertEqual(prefilter.multi_platform(frames), {"b/y", "c/z"})


class Decide(unittest.TestCase):
    def test_eligible(self):
        r = prefilter.decide("o/r", meta(), "", set(), START)
        self.assertTrue(r["eligible"])
        self.assertEqual(r["reason"], "")

    def test_each_rule(self):
        cases = {
            "multi_platform": ("o/r", meta(), {"o/r"}),
            "unavailable": ("o/r", None, set()),
            "fork": ("o/r", meta(fork=True), set()),
            "archived": ("o/r", meta(archived=True), set()),
            "pushed_before_period": ("o/r", meta(pushed="2025-10-30T23:59:59Z"), set()),
        }
        for reason, (fn, m, multi) in cases.items():
            r = prefilter.decide(fn, m, "", multi, START)
            self.assertEqual(r["reason"], reason)
            self.assertFalse(r["eligible"])

    def test_period_start_day_is_inside(self):
        self.assertTrue(prefilter.decide("o/r", meta(pushed="2025-10-31T00:00:00Z"), "", set(), START)["eligible"])

    def test_never_pushed_is_excluded(self):
        self.assertEqual(prefilter.decide("o/r", meta(pushed=None), "", set(), START)["reason"],
                         "pushed_before_period")

    def test_first_failing_rule_wins_but_all_flags_kept(self):
        r = prefilter.decide("o/r", meta(fork=True, archived=True), "", {"o/r"}, START)
        self.assertEqual(r["reason"], "multi_platform")
        self.assertTrue(r["fork"] and r["archived"])


class ParseBatch(unittest.TestCase):
    def test_not_found_is_unavailable(self):
        body = {"data": {"r0": meta(), "r1": None},
                "errors": [{"type": "NOT_FOUND", "path": ["r1"]}]}
        out = prefilter.parse_batch(["o/a", "o/b"], body)
        self.assertEqual(out["o/a"][1], "")
        self.assertEqual(out["o/b"], (None, "NOT_FOUND"))

    def test_query_level_error_raises(self):
        with self.assertRaises(RuntimeError):
            prefilter.parse_batch(["o/a"], {"data": None, "errors": [{"message": "boom"}]})
        with self.assertRaises(RuntimeError):
            prefilter.parse_batch(["o/a"], {"data": {"r0": meta()}, "errors": [{"message": "boom"}]})

    def test_query_escapes_names(self):
        q = prefilter.batch_query(["my-org/app.v2", "x/y_z"])
        self.assertIn('r0: repository(owner: "my-org", name: "app.v2")', q)
        self.assertIn('r1: repository(owner: "x", name: "y_z")', q)


class FakeGitHub:
    def __init__(self):
        self.calls = 0

    def graphql(self, query, min_interval):
        self.calls += 1
        n = query.count("repository(")
        return 200, {"data": {f"r{i}": meta() for i in range(n)}}


class FetchMetadata(unittest.TestCase):
    def test_batches_and_resume(self):
        names = [f"o{i}/r" for i in range(config.PREFILTER_BATCH * 2 + 3)]
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub()
            m = prefilter.fetch_metadata(gh, names, Path(d))
            self.assertEqual(len(m), len(names))
            self.assertEqual(gh.calls, 3)
            gh2 = FakeGitHub()
            self.assertEqual(prefilter.fetch_metadata(gh2, names, Path(d)), m)
            self.assertEqual(gh2.calls, 0)

    def test_cached_batch_for_other_names_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            prefilter.fetch_metadata(FakeGitHub(), ["a/x"], Path(d))
            with self.assertRaises(SystemExit):
                prefilter.fetch_metadata(FakeGitHub(), ["b/y"], Path(d))


if __name__ == "__main__":
    unittest.main()
