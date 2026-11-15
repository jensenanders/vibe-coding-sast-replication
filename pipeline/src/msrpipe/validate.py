"""Step `validate`: protocol item 10, the student's manual check of the automated screening.

Draw (default): per platform, with a fresh random.Random(seed),
  - 5 repos from the main sample (the first MAIN_N included in the order), and
  - 5 repos from those excluded on a criterion (no_platform_trace, mobile,
    backend_nloc_below_min). owner_taken and clone_failed are left out: the code
    judged no criterion for them.
Both pools are sorted by rank before sampling. Repos named in earlier key files
(--exclude) are removed from both pools first, so a new round is independent of the
repos the student has already seen. The sheet the student fills in is blind:
it has the GitHub link at the analysed commit, but not the code's decision. The code's
answers go in a separate key file.

--score: compares the filled sheet with the key, per criterion and platform.
"""

import csv
import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from .collect import write_csv
from .prefilter import PLATFORMS
from .screen import read_rows
from . import config

MAIN_N = 50
PER_GROUP = 5
CRITERION_REASONS = {"no_platform_trace", "mobile", "backend_nloc_below_min"}
PREFIX = {"lovable": "L", "replit": "R", "boltnew": "B"}
QUESTIONS = ["platform_ok", "web_not_mobile", "backend_ok"]      # answered ja / nej / uklar
SHEET_FIELDS = ["id", "platform", "url", *QUESTIONS, "note"]
KEY_FIELDS = ["id", "full_name", "rank", "head_sha", "included", "reason",
              "code_platform_ok", "code_web_not_mobile", "code_backend_ok", "backend_nloc"]


def pools(rows, exclude=frozenset()):
    """The main sample is fixed first (first MAIN_N included); `exclude` then only removes from the pools."""
    rows = sorted(rows, key=lambda r: int(r["rank"]))
    included = [r for r in rows if r["included"] == "True"][:MAIN_N]
    excluded = [r for r in rows if r["reason"] in CRITERION_REASONS]
    keep = lambda rs: [r for r in rs if r["full_name"] not in exclude]
    return keep(included), keep(excluded)


def draw(rows, seed, exclude=frozenset()):
    """-> drawn rows in sheet order (included and excluded mixed, so the sheet is blind)."""
    rng = random.Random(seed)
    included, excluded = pools(rows, exclude)
    by_rank = lambda rs: sorted(rs, key=lambda r: int(r["rank"]))
    picked = (rng.sample(by_rank(included), min(PER_GROUP, len(included)))
              + rng.sample(by_rank(excluded), min(PER_GROUP, len(excluded))))
    rng.shuffle(picked)
    return picked


def code_answers(r):
    yn = lambda b: "ja" if b else "nej"
    return {"code_platform_ok": yn(r["platform_trace"] == "True"),
            "code_web_not_mobile": yn(r["mobile"] != "True"),
            "code_backend_ok": yn(int(r["backend_nloc"] or 0) >= config.MIN_BACKEND_NLOC)}


def make_sheet(args):
    seed = json.loads((Path("/data/frame") / args.freeze_date / "manifest.json").read_text())["seed"]
    screen_dir = Path("/data/screen") / args.freeze_date
    out = Path("/data/validate") / args.freeze_date
    sheet_path = out / "validation_sheet.csv"
    if sheet_path.exists():
        raise SystemExit(f"{sheet_path} exists (it may hold your answers); refusing to overwrite.")
    exclude = set()
    for k in args.exclude:
        with open(k, newline="", encoding="utf-8") as fh:
            exclude |= {r["full_name"] for r in csv.DictReader(fh)}
    out.mkdir(parents=True, exist_ok=True)
    sheet, key = [], []
    for p in PLATFORMS:
        for i, r in enumerate(draw(read_rows(screen_dir / f"screen_{p}.csv"), seed, exclude), 1):
            vid = f"V-{PREFIX[p]}{i:02d}"
            sheet.append({"id": vid, "platform": p,
                          "url": f"https://github.com/{r['full_name']}/tree/{r['head_sha']}"})
            key.append({"id": vid, "full_name": r["full_name"], "rank": r["rank"], "head_sha": r["head_sha"],
                        "included": r["included"], "reason": r["reason"], **code_answers(r),
                        "backend_nloc": r["backend_nloc"]})
    write_csv(sheet_path, sheet, SHEET_FIELDS)
    write_csv(out / "validation_key.csv", key, KEY_FIELDS)
    (out / "validate.json").write_text(json.dumps({
        "seed": seed, "main_n": MAIN_N, "per_group": PER_GROUP, "drawn": len(sheet),
        "excluded_from_keys": list(args.exclude), "n_excluded_repos": len(exclude),
        "drawn_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2))
    print(f"validate: seed {seed}, {len(exclude)} repos excluded, {len(sheet)} repos -> {sheet_path} "
          f"(key: validation_key.csv, do not open)")


def norm(v):
    v = (v or "").strip().lower()
    return v if v in ("ja", "nej") else "uklar"


def agreement(sheet, key):
    """-> {(platform, question): {"agree", "disagree", "unclear"}} and the disagreeing ids."""
    k = {r["id"]: r for r in key}
    out, diffs = defaultdict(lambda: {"agree": 0, "disagree": 0, "unclear": 0}), []
    for s in sheet:
        for q in QUESTIONS:
            mine, code = norm(s[q]), k[s["id"]][f"code_{q}"]
            cell = out[(s["platform"], q)]
            if mine == "uklar":
                cell["unclear"] += 1
            elif mine == code:
                cell["agree"] += 1
            else:
                cell["disagree"] += 1
                diffs.append((s["id"], q, mine, code))
    return dict(out), diffs


def score(args):
    out = Path("/data/validate") / args.freeze_date
    with open(out / "validation_sheet.csv", newline="", encoding="utf-8") as fh:
        sheet = list(csv.DictReader(fh))
    with open(out / "validation_key.csv", newline="", encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    table, diffs = agreement(sheet, key)
    rows = [{"platform": p, "question": q, **c} for (p, q), c in sorted(table.items())]
    write_csv(out / "validation_agreement.csv", rows, ["platform", "question", "agree", "disagree", "unclear"])
    write_csv(out / "validation_disagreements.csv",
              [{"id": i, "question": q, "student": m, "code": c} for i, q, m, c in diffs],
              ["id", "question", "student", "code"])
    for r in rows:
        print(f"  {r['platform']:8} {r['question']:15} agree {r['agree']}  disagree {r['disagree']}  unclear {r['unclear']}")
    print(f"validate --score: {len(diffs)} disagreements -> {out}")


def run(args):
    (score if args.score else make_sheet)(args)
