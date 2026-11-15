"""Step `sensitivity`: how the sample depends on the backend-NLOC threshold (B1, item 4).

Decided 2026-11-08 (docs/beslutningslog.md). No new cloning or scanning: the screening
rules are re-applied to the frozen screening results (`screen_<platform>.csv`) with other
thresholds (config.SENSITIVITY_NLOC), walking the same shuffled order.

Per repo, in rank order, with the threshold T:
  - owner already included (under T)          -> skipped (one repo per owner)
  - originally `owner_taken` (never cloned),
    but its owner is not included under T     -> unknown: no backend NLOC was measured;
                                                 counted as excluded and reported
  - clone_failed / no_platform_trace / mobile  -> excluded (independent of T)
  - backend_nloc >= T                          -> included
For each platform, threshold and N in config.SAMPLE_SIZES, the first N included repos are
compared with the sample under the frozen threshold (config.MIN_BACKEND_NLOC).
Repos that enter the sample under another threshold were never scanned; only their number
is reported. Lovable and Replit were screened only until 100 repos were included, so a
sample that needs repos beyond the screened ranks is reported as not reached.
"""

import csv
import json
from pathlib import Path

from . import config
from .analyse import PLATFORMS
from .screen import owner, read_rows

THRESHOLD_INDEPENDENT = {"clone_failed", "no_platform_trace", "mobile"}


def simulate(rows, threshold):
    """Walk the screened rows in rank order -> (included full_names in order, unknown ranks
    as (rank, number of repos included before it))."""
    owners, included, unknown = set(), [], []
    for r in sorted(rows, key=lambda r: int(r["rank"])):
        fn = r["full_name"]
        if owner(fn) in owners:
            continue
        if r["reason"] == "owner_taken":
            unknown.append((int(r["rank"]), len(included)))
            continue
        if r["reason"] in THRESHOLD_INDEPENDENT:
            continue
        if int(r["backend_nloc"]) >= threshold:
            included.append(fn)
            owners.add(owner(fn))
    return included, unknown


def compare(rows, threshold, n, exhausted):
    """One result row: the first n included under `threshold` against the frozen threshold."""
    ref, _ = simulate(rows, config.MIN_BACKEND_NLOC)
    inc, unknown = simulate(rows, threshold)
    sample, main = inc[:n], set(ref[:n])
    rank = {r["full_name"]: int(r["rank"]) for r in rows}
    return {
        "threshold": threshold, "n": n,
        "included_screened": len(inc),
        "reached": len(sample) == n,
        "pool_exhausted": exhausted,
        "last_rank": rank[sample[-1]] if sample else "",
        "same_as_main": len(set(sample) & main),
        "entering": len(set(sample) - main),
        "leaving": len(main - set(sample)),
        "unknown_owner_taken": sum(before < n for _, before in unknown),
    }


def run(args):
    screen_dir = Path("/data/screen") / args.freeze_date
    out = Path("/data/analysis") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((screen_dir / "screen.json").read_text())
    if manifest["min_backend_nloc"] != config.MIN_BACKEND_NLOC:
        raise SystemExit("screen.json was made with another MIN_BACKEND_NLOC")
    thresholds = sorted({config.MIN_BACKEND_NLOC, *config.SENSITIVITY_NLOC})
    results = []
    for p in PLATFORMS:
        rows = read_rows(screen_dir / f"screen_{p}.csv")
        # the simulation under the frozen threshold must reproduce the screening
        ref, _ = simulate(rows, config.MIN_BACKEND_NLOC)
        actual = [r["full_name"] for r in sorted(rows, key=lambda r: int(r["rank"]))
                  if r["included"] == "True"]
        if ref != actual:
            raise SystemExit(f"{p}: simulation does not reproduce screen_{p}.csv")
        exhausted = manifest["platforms"][p]["order_exhausted"]
        for t in thresholds:
            for n in config.SAMPLE_SIZES:
                results.append({"platform": p, **compare(rows, t, n, exhausted)})
    with open(out / "nloc_sensitivity.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    print("sensitivity: backend-NLOC threshold vs the frozen sample "
          f"(T = {config.MIN_BACKEND_NLOC})")
    for r in results:
        print(f"  {r['platform']:8} T={r['threshold']:<4} N={r['n']:<3} reached={r['reached']!s:5} "
              f"included_screened={r['included_screened']:<4} same={r['same_as_main']:<3} "
              f"in={r['entering']:<3} out={r['leaving']:<3} unknown={r['unknown_owner_taken']} "
              f"last_rank={r['last_rank']}")
    print(f"sensitivity: done -> {out / 'nloc_sensitivity.csv'}")
