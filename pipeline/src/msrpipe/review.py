"""Step `review`: manual true/false-positive check of a random sample of findings.

Draw (default): per platform x tool (CodeQL security-extended without test dirs, GitLab),
REVIEW_PER_STRATUM findings with random.Random(seed).sample, from the same findings
`analyse` counts. The first REVIEW_CODER2_PER_STRATUM drawn per stratum also go to a second
coder. Each sheet is shuffled, and shows neither platform nor tool; the key holds them.
--score: precision TP / (TP + FP) per stratum with a Wilson 95% interval, labels per rule,
and Cohen's kappa between the two coders on the shared findings.
"""

import csv
import datetime as dt
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .owasp import findings
from .screen import read_rows

PLATFORMS = ["lovable", "replit", "boltnew"]
TOOLS = ["codeql", "gitlab"]
SHEET_FIELDS = ["id", "url", "title", "message", "cwe", "label", "note"]
KEY_FIELDS = ["id", "platform", "tool", "rank", "full_name", "head_sha", "rule", "path", "line", "cwe",
              "severity", "coder2"]


def one_line(text, n=300):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def population(raw_root, scan_rows, platform, tool):
    """All findings of one tool on one platform, in rank order, with the repo's name and sha."""
    out = []
    for r in sorted(scan_rows, key=lambda r: int(r["rank"])):
        repo = raw_root / platform / f"{int(r['rank']):05d}"
        for t, f in findings(repo):
            if t == tool:
                out.append({**f, "platform": platform, "tool": tool, "rank": int(r["rank"]),
                            "full_name": r["full_name"], "head_sha": r["head_sha"]})
    return out


def draw(pops, seed):
    """{(platform, tool): population} -> drawn findings with a coder2 flag, in stratum order."""
    rng = random.Random(seed)
    drawn = []
    for p in PLATFORMS:
        for t in TOOLS:
            sample = rng.sample(pops[(p, t)], min(config.REVIEW_PER_STRATUM, len(pops[(p, t)])))
            drawn += [{**f, "coder2": i < config.REVIEW_CODER2_PER_STRATUM} for i, f in enumerate(sample)]
    return drawn


def url(f):
    u = f"https://github.com/{f['full_name']}/blob/{f['head_sha']}/{f['path']}"
    return u + (f"#L{f['line']}" if f["line"] else "")


def write_csv(path, rows, fields, delimiter=","):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


def make_sheets(args):
    seed = json.loads((Path("/data/frame") / args.freeze_date / "manifest.json").read_text())["seed"]
    scan_dir = Path("/data/scan") / args.freeze_date
    out = Path("/data/review") / args.freeze_date
    if (out / "review_sheet.csv").exists():
        raise SystemExit(f"{out / 'review_sheet.csv'} exists (it may hold your answers); refusing to overwrite.")
    out.mkdir(parents=True, exist_ok=True)
    pops = {(p, t): population(scan_dir / "raw", read_rows(scan_dir / f"scan_{p}.csv"), p, t)
            for p in PLATFORMS for t in TOOLS}
    drawn = draw(pops, seed)
    rng = random.Random(seed)
    rng.shuffle(drawn)                                   # sheet order hides the strata
    key, sheet = [], []
    for i, f in enumerate(drawn, 1):
        fid = f"F{i:03d}"
        cwe = ";".join(map(str, f["cwes"]))
        key.append({"id": fid, **{k: f[k] for k in ["platform", "tool", "rank", "full_name", "head_sha",
                                                     "rule", "path", "line", "severity", "coder2"]}, "cwe": cwe})
        sheet.append({"id": fid, "url": url(f), "title": one_line(f["title"], 120),
                      "message": one_line(f["message"]), "cwe": cwe, "label": "", "note": ""})
    coder2 = [s for s, k in zip(sheet, key) if k["coder2"]]
    rng.shuffle(coder2)
    write_csv(out / "review_sheet.csv", sheet, SHEET_FIELDS)
    write_csv(out / "review_sheet_coder2.csv", coder2, SHEET_FIELDS)
    write_csv(out / "review_key.csv", key, KEY_FIELDS)
    (out / "review.json").write_text(json.dumps({
        "seed": seed, "per_stratum": config.REVIEW_PER_STRATUM, "coder2_per_stratum": config.REVIEW_CODER2_PER_STRATUM,
        "population": {f"{p}/{t}": len(v) for (p, t), v in pops.items()}, "drawn": len(sheet),
        "coder2": len(coder2), "labels": config.REVIEW_LABELS,
        "drawn_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2))
    print(f"review: seed {seed}, {len(sheet)} findings -> review_sheet.csv, {len(coder2)} -> review_sheet_coder2.csv "
          f"(key: review_key.csv, do not open)")


# ---- scoring ---------------------------------------------------------------------

def read_sheet(path):
    """A filled sheet; Numbers exports with ';' in a Danish locale."""
    text = path.read_text(encoding="utf-8-sig")
    delim = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delim))


def norm(v):
    v = (v or "").strip()
    if not v:
        return "missing"
    return v.upper() if v.upper() in ("TP", "FP") else "uklar"


def wilson(k, n, z=1.96, places=3):
    """Wilson score interval; places=None returns the unrounded bounds."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    if places is None:
        return c - h, c + h
    return round(c - h, places), round(c + h, places)


def cohen_kappa(pairs):
    """Cohen's kappa over (label1, label2) pairs, all categories as given."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    c1, c2 = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(c1[c] * c2[c] for c in set(c1) | set(c2)) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def precision_rows(labels, key):
    cells = defaultdict(Counter)
    for k in key:
        cells[(k["platform"], k["tool"])][labels.get(k["id"], "missing")] += 1
    rows = []
    for p in PLATFORMS:
        for t in TOOLS:
            c = cells[(p, t)]
            lo, hi = wilson(c["TP"], c["TP"] + c["FP"])
            rows.append({"platform": p, "tool": t, "TP": c["TP"], "FP": c["FP"], "uklar": c["uklar"],
                         "missing": c["missing"],
                         "precision": round(c["TP"] / (c["TP"] + c["FP"]), 3) if c["TP"] + c["FP"] else "",
                         "ci95_low": lo, "ci95_high": hi})
    return rows


def score(args):
    out = Path("/data/review") / args.freeze_date
    key = read_rows(out / "review_key.csv")
    mine = {r["id"]: norm(r["label"]) for r in read_sheet(out / "review_sheet.csv")}
    rows = precision_rows(mine, key)
    write_csv(out / "review_precision.csv", rows, list(rows[0]))
    by_rule = defaultdict(Counter)
    for k in key:
        by_rule[(k["tool"], k["rule"])][mine.get(k["id"], "missing")] += 1
    write_csv(out / "review_by_rule.csv",
              [{"tool": t, "rule": r, **{l: c[l] for l in ["TP", "FP", "uklar", "missing"]}}
               for (t, r), c in sorted(by_rule.items(), key=lambda x: -sum(x[1].values()))],
              ["tool", "rule", "TP", "FP", "uklar", "missing"])
    for r in rows:
        print(f"  {r['platform']:8} {r['tool']:6} TP {r['TP']:2} FP {r['FP']:2} uklar {r['uklar']:2} "
              f"missing {r['missing']:2} precision {r['precision']} [{r['ci95_low']}-{r['ci95_high']}]")
    c2_path = out / "review_sheet_coder2.csv"
    other = {r["id"]: norm(r["label"]) for r in read_sheet(c2_path)} if c2_path.exists() else {}
    pairs = [(mine[i], other[i]) for i in other if "missing" not in (mine.get(i, "missing"), other[i])]
    if pairs:
        agree = {"n": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3),
                 "kappa": cohen_kappa(pairs), "pairs": Counter(f"{a}/{b}" for a, b in pairs)}
        (out / "review_agreement.json").write_text(json.dumps(agree, indent=2))
        print(f"  coder agreement: n {agree['n']}, {agree['agreement']}, Cohen's kappa {agree['kappa']}")
    print(f"review --score -> {out}")


def run(args):
    (score if args.score else make_sheets)(args)
