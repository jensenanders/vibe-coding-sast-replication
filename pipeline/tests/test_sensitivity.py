import unittest

from msrpipe import sensitivity


def row(rank, fn, reason="", nloc=""):
    included = reason == "" and nloc != "" and int(nloc) >= 50
    return {"rank": str(rank), "full_name": fn, "reason": reason if reason or included
            else "backend_nloc_below_min", "backend_nloc": str(nloc), "included": str(included)}


ROWS = [
    row(1, "a/x", nloc=60),
    row(2, "b/x", nloc=30),                    # in at 25, out at 50
    row(3, "a/y", reason="owner_taken"),       # owner a included at 50 -> not cloned
    row(4, "c/x", reason="mobile", nloc=500),  # threshold-independent
    row(5, "d/x", nloc=120),
    row(6, "e/x", nloc=80),                    # out at 100
]


class Sensitivity(unittest.TestCase):
    def test_reproduces_frozen_threshold(self):
        inc, unknown = sensitivity.simulate(ROWS, 50)
        self.assertEqual(inc, ["a/x", "d/x", "e/x"])
        self.assertEqual(unknown, [])          # owner a is included before rank 3

    def test_lower_threshold_adds_repos(self):
        inc, _ = sensitivity.simulate(ROWS, 25)
        self.assertEqual(inc, ["a/x", "b/x", "d/x", "e/x"])

    def test_higher_threshold_frees_owner_as_unknown(self):
        inc, unknown = sensitivity.simulate(ROWS, 100)
        self.assertEqual(inc, ["d/x"])
        self.assertEqual(unknown, [(3, 0)])    # owner a not included -> a/y never measured

    def test_compare_counts(self):
        r = sensitivity.compare(ROWS, 25, 2, exhausted=True)
        self.assertEqual((r["same_as_main"], r["entering"], r["leaving"]), (1, 1, 1))
        self.assertTrue(r["reached"])
        self.assertEqual(r["last_rank"], 2)
        r = sensitivity.compare(ROWS, 100, 2, exhausted=True)
        self.assertFalse(r["reached"])
        self.assertEqual(r["unknown_owner_taken"], 1)
        self.assertEqual((r["same_as_main"], r["entering"], r["leaving"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
