"""Step `shuffle`: protocol item 5, the screening order.

The eligible repos from `prefilter` are sorted alphabetically on full_name and then
shuffled with random.Random(seed), one fresh generator per platform. The seed is the
one in the frame's manifest (freeze date as YYYYMMDD). Sorting first makes the result
independent of the order rows happen to have in the input file.
"""

import csv
import datetime as dt
import json
import platform as pyplatform
import random
from pathlib import Path

from .collect import write_csv
from .prefilter import PLATFORMS


def order(names, seed):
    names = sorted(names)
    random.Random(seed).shuffle(names)
    return names


def eligible(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [r["full_name"] for r in csv.DictReader(fh) if r["eligible"] == "True"]


def run(args):
    seed = json.loads((Path("/data/frame") / args.freeze_date / "manifest.json").read_text())["seed"]
    src = Path("/data/prefilter") / args.freeze_date
    out = Path("/data/order") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for p in PLATFORMS:
        names = order(eligible(src / f"prefilter_{p}.csv"), seed)
        write_csv(out / f"order_{p}.csv", [{"rank": i, "full_name": fn} for i, fn in enumerate(names, 1)],
                  ["rank", "full_name"])
        counts[p] = len(names)
        print(f"  {p}: {len(names)} repos in order")
    (out / "order.json").write_text(json.dumps({
        "freeze_date": args.freeze_date, "seed": seed, "python": pyplatform.python_version(),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "n": counts}, indent=2))
    print(f"shuffle: seed {seed} -> {out}")
