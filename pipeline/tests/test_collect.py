import datetime as dt
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from msrpipe import collect, config


class Period(unittest.TestCase):
    def test_twelve_months_excluding_freeze_day(self):
        days = collect.period(dt.date(2026, 11, 3))
        self.assertEqual(days[0], dt.date(2025, 11, 3))
        self.assertEqual(days[-1], dt.date(2026, 11, 2))
        self.assertEqual(len(days), 365)

    def test_leap_year(self):
        self.assertEqual(len(collect.period(dt.date(2028, 3, 1))), 366)
        self.assertEqual(collect.period(dt.date(2028, 2, 29))[0], dt.date(2027, 2, 28))

    def test_seed_is_freeze_date(self):
        self.assertEqual(collect.seed_for(dt.date(2026, 11, 3)), 20261103)


class MinuteWindows(unittest.TestCase):
    def setUp(self):
        self.days = collect.period(dt.date(2026, 11, 3))
        self.w = collect.minute_windows(self.days, 20261103)

    def test_one_minute_per_two_hour_block(self):
        self.assertEqual(len(self.w), 365 * 12)
        for i, (day, start, end) in enumerate(self.w[:24]):
            block = i % 12
            self.assertEqual(start.date(), day)
            self.assertEqual(start.hour // 2, block)
            self.assertEqual((end - start).total_seconds(), 59)

    def test_reproducible_with_seed(self):
        self.assertEqual(self.w, collect.minute_windows(self.days, 20261103))
        self.assertNotEqual(self.w, collect.minute_windows(self.days, 20261104))

    def test_query_format(self):
        _, start, end = self.w[0]
        self.assertRegex(f"{collect.iso(start)}..{collect.iso(end)}",
                         r"^\d{4}-\d\d-\d\dT\d\d:\d\d:00Z\.\.\d{4}-\d\d-\d\dT\d\d:\d\d:59Z$")


class FakeGitHub:
    """Serves pages of a search with a given total_count; records requests."""

    def __init__(self, total):
        self.total, self.calls = total, []

    def search(self, kind, q, page, per_page, min_interval):
        self.calls.append(page)
        start = (page - 1) * per_page
        if start >= min(self.total, config.MAX_RESULTS):
            return 422, None
        n = min(per_page, self.total - start)
        items = [{"repository": {"full_name": f"o{(start + i) % 7}/r"}} for i in range(n)]
        return 200, {"total_count": self.total, "incomplete_results": False, "items": items}


class FetchAll(unittest.TestCase):
    def test_stops_at_last_page(self):
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub(total=250)
            items, info = collect.fetch_all(gh, "commits", "q", Path(d), config.MAX_PAGES)
            self.assertEqual(len(items), 250)
            self.assertEqual(gh.calls, [1, 2, 3])
            self.assertFalse(info["capped"])

    def test_cap_at_1000(self):
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub(total=5000)
            items, info = collect.fetch_all(gh, "commits", "q", Path(d), config.MAX_PAGES)
            self.assertEqual(len(items), 1000)
            self.assertEqual(len(gh.calls), 10)
            self.assertTrue(info["capped"])

    def test_resume_reuses_raw_pages(self):
        with tempfile.TemporaryDirectory() as d:
            collect.fetch_all(FakeGitHub(total=150), "commits", "q", Path(d), config.MAX_PAGES)
            gh = FakeGitHub(total=150)
            items, _ = collect.fetch_all(gh, "commits", "q", Path(d), config.MAX_PAGES)
            self.assertEqual(gh.calls, [])
            self.assertEqual(len(items), 150)
            with gzip.open(Path(d) / "p01.json.gz", "rt") as fh:
                self.assertIn("fetched_at", json.load(fh))


class Dedupe(unittest.TestCase):
    def test_unique_repos_per_platform(self):
        with tempfile.TemporaryDirectory() as d:
            days = [dt.date(2026, 1, 1), dt.date(2026, 1, 2)]
            windows = collect.minute_windows(days, 1)
            repos, rows = collect.collect_commits(FakeGitHub(total=20), "lovable", windows, Path(d), 10)
            self.assertEqual(len(repos), 7)                       # o0..o6
            self.assertEqual(sum(r["n_commits_seen"] for r in repos.values()), 20 * 24)
            self.assertEqual(len(rows), 24)
            self.assertEqual(rows[0]["day"], "2026-01-01")


if __name__ == "__main__":
    unittest.main()
