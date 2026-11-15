import unittest

from msrpipe import validate


def row(rank, included, reason="", trace=True, mobile=False, nloc=100):
    return {"rank": str(rank), "full_name": f"o{rank}/r", "head_sha": "a" * 40,
            "included": str(included), "reason": reason, "platform_trace": str(trace),
            "mobile": str(mobile), "backend_nloc": str(nloc)}


ROWS = ([row(i, True) for i in range(1, 61)]
        + [row(100 + i, False, "backend_nloc_below_min", nloc=3) for i in range(8)]
        + [row(200, False, "owner_taken"), row(201, False, "clone_failed")])


class Draw(unittest.TestCase):
    def test_pools(self):
        inc, exc = validate.pools(ROWS)
        self.assertEqual(len(inc), 50)                       # only the main sample
        self.assertEqual(max(int(r["rank"]) for r in inc), 50)
        self.assertEqual({r["reason"] for r in exc}, {"backend_nloc_below_min"})

    def test_five_and_five_reproducible(self):
        d = validate.draw(ROWS, 20261031)
        self.assertEqual(sum(r["included"] == "True" for r in d), 5)
        self.assertEqual(sum(r["included"] == "False" for r in d), 5)
        self.assertEqual(d, validate.draw(list(reversed(ROWS)), 20261031))
        self.assertNotEqual(d, validate.draw(ROWS, 1))

    def test_exclude_earlier_round(self):
        first = validate.draw(ROWS, 20261031)
        seen = {r["full_name"] for r in first}
        second = validate.draw(ROWS, 20261031, seen)
        self.assertFalse(seen & {r["full_name"] for r in second})
        self.assertEqual(len(second), 8)                     # 8 excluded in the pool, 5 already seen
        inc, _ = validate.pools(ROWS, seen)
        self.assertTrue(all(int(r["rank"]) <= 50 for r in inc))   # the main sample is not refilled

    def test_small_pool(self):
        self.assertEqual(len(validate.draw([row(1, True), row(2, False, "mobile", mobile=True)], 1)), 2)


class Score(unittest.TestCase):
    def test_agreement(self):
        key = [{"id": "V-L01", "code_platform_ok": "ja", "code_web_not_mobile": "ja", "code_backend_ok": "nej"}]
        sheet = [{"id": "V-L01", "platform": "lovable", "platform_ok": "Ja ",
                  "web_not_mobile": "?", "backend_ok": "ja", "note": ""}]
        table, diffs = validate.agreement(sheet, key)
        self.assertEqual(table[("lovable", "platform_ok")], {"agree": 1, "disagree": 0, "unclear": 0})
        self.assertEqual(table[("lovable", "web_not_mobile")]["unclear"], 1)
        self.assertEqual(diffs, [("V-L01", "backend_ok", "ja", "nej")])

    def test_code_answers(self):
        self.assertEqual(validate.code_answers(row(1, False, trace=False, mobile=True, nloc=49)),
                         {"code_platform_ok": "nej", "code_web_not_mobile": "nej", "code_backend_ok": "nej"})


if __name__ == "__main__":
    unittest.main()
