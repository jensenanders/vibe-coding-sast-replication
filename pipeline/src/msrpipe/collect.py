"""Step `collect`: identification searches and the frozen sampling frame.

Protocol: docs/Reposertory-Selection.md, items 1-2 of "Samlet udvælgelsesprotokol".
- Period: 12 months back from the freeze date (the freeze day itself is excluded).
- Lovable/Replit: commit search in one random minute per 2-hour block (UTC) per day,
  drawn with the seed; every window is fetched in full, capped windows are logged.
- Bolt.new: repository and code searches, first 1,000 results each, no date windows.
- Duplicates are removed on full_name; raw responses are kept with a timestamp.
"""

import csv
import datetime as dt
import gzip
import hashlib
import json
import platform as pyplatform
import random
from pathlib import Path

from . import config
from .github import GitHub

PROTOCOL = Path("/docs/Reposertory-Selection.md")


def period(freeze):
    """Days in the 12 months before the freeze date: [freeze - 1 year, freeze)."""
    try:
        start = freeze.replace(year=freeze.year - 1)
    except ValueError:                      # freeze date is 29 February
        start = freeze.replace(year=freeze.year - 1, day=28)
    return [start + dt.timedelta(days=i) for i in range((freeze - start).days)]


def seed_for(freeze):
    return int(freeze.strftime("%Y%m%d"))


def minute_windows(days, seed):
    """One random minute in each 2-hour block of each day (UTC), same for all platforms."""
    rng = random.Random(seed)
    block = 24 * 60 // config.BLOCKS_PER_DAY
    out = []
    for day in days:
        midnight = dt.datetime.combine(day, dt.time(), tzinfo=dt.timezone.utc)
        for b in range(config.BLOCKS_PER_DAY):
            start = midnight + dt.timedelta(minutes=b * block + rng.randrange(block))
            out.append((day, start, start + dt.timedelta(seconds=config.WINDOW_SECONDS - 1)))
    return out


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_all(gh, kind, q, raw_dir, max_pages):
    """Fetch up to max_pages pages of one search; reuse raw pages already on disk."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    items, total, incomplete, pages = [], 0, False, 0
    for page in range(1, max_pages + 1):
        f = raw_dir / f"p{page:02d}.json.gz"
        if f.exists():
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rec = json.load(fh)
        else:
            status, body = gh.search(kind, q, page, config.PER_PAGE, config.MIN_INTERVAL[kind])
            rec = {"request": {"endpoint": f"/search/{kind}", "q": q, "page": page,
                               "per_page": config.PER_PAGE},
                   "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "status": status, "body": body}
            with gzip.open(f, "wt", encoding="utf-8") as fh:
                json.dump(rec, fh)
        body = rec["body"]
        if body is None:
            break
        pages += 1
        total = body.get("total_count", 0)
        incomplete = incomplete or bool(body.get("incomplete_results"))
        page_items = body.get("items", [])
        items.extend(page_items)
        if len(page_items) < config.PER_PAGE or page * config.PER_PAGE >= min(total, config.MAX_RESULTS):
            break
    return items, {"total_count": total, "n_items": len(items), "pages": pages,
                   "capped": total > config.MAX_RESULTS, "incomplete": incomplete}


def collect_commits(gh, name, windows, raw_root, max_pages):
    repos, rows = {}, []
    for i, (day, start, end) in enumerate(windows, 1):
        q = f"{config.COMMIT_QUERIES[name]} author-date:{iso(start)}..{iso(end)}"
        raw_dir = raw_root / name / day.isoformat() / start.strftime("%H%M")
        items, info = fetch_all(gh, "commits", q, raw_dir, max_pages)
        for it in items:
            fn = it["repository"]["full_name"]
            r = repos.setdefault(fn, {"full_name": fn, "n_commits_seen": 0,
                                      "first_day": day.isoformat(), "last_day": day.isoformat()})
            r["n_commits_seen"] += 1
            r["last_day"] = day.isoformat()
        rows.append({"day": day.isoformat(), "window_start": iso(start), "window_end": iso(end), **info})
        if i % (30 * config.BLOCKS_PER_DAY) == 0 or i == len(windows):
            print(f"  {name}: {i}/{len(windows)} windows, {len(repos)} unique repos")
    return repos, rows


def collect_bolt(gh, raw_root, max_pages, query_ids=None):
    repos, query_rows = {}, []
    queries = [("repositories", k, q) for k, q in config.BOLT_REPO_QUERIES.items()]
    queries += [("code", k, q) for k, q in config.BOLT_CODE_QUERIES.items()]
    for kind, qid, q in queries:
        if query_ids and qid not in query_ids:
            continue
        items, info = fetch_all(gh, kind, q, raw_root / "boltnew" / qid, max_pages)
        for it in items:
            fn = it["full_name"] if kind == "repositories" else it["repository"]["full_name"]
            r = repos.setdefault(fn, {"full_name": fn, "n_hits": 0, "queries": set()})
            r["n_hits"] += 1
            r["queries"].add(qid)
        query_rows.append({"id": qid, "endpoint": f"/search/{kind}", "q": q, **info})
        print(f"  boltnew {qid}: {info['n_items']} items (total_count {info['total_count']})")
    for r in repos.values():
        r["queries"] = ";".join(sorted(r["queries"]))
    return repos, query_rows


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run(args):
    test = args.test
    freeze = dt.date.fromisoformat(args.freeze_date) if args.freeze_date \
        else dt.datetime.now(dt.timezone.utc).date()
    out = Path("/data/test" if test else "/data/frame") / freeze.isoformat()
    raw_root = Path("/work/test-raw" if test else "/work/raw") / freeze.isoformat()
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()).get("finished_at"):
        raise SystemExit(f"Frame for {freeze} is already frozen ({manifest_path}); refusing to overwrite.")
    out.mkdir(parents=True, exist_ok=True)

    days = period(freeze)
    max_pages = config.MAX_PAGES
    platforms = args.platforms
    bolt_ids = None
    windows = minute_windows(days, seed_for(freeze))   # drawn over the full period, then trimmed in test
    if test:                                 # tiny smoke run: last 2 days, 1 page, 1 query per Bolt endpoint
        days, max_pages, bolt_ids = days[-2:], 1, {"R1", "C1"}
        windows = [w for w in windows if w[0] in days]

    manifest = {
        "freeze_date": freeze.isoformat(), "seed": seed_for(freeze), "test": test,
        "period_start": days[0].isoformat(), "period_end": days[-1].isoformat(),
        "n_days": len(days), "n_windows": len(windows),
        "blocks_per_day": config.BLOCKS_PER_DAY, "window_seconds": config.WINDOW_SECONDS,
        "max_pages": max_pages,
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() if PROTOCOL.exists() else None,
        "python": pyplatform.python_version(),
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "platforms": {},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"collect: freeze {freeze} (seed {manifest['seed']}), {len(days)} days, test={test}")

    gh = GitHub()
    for name in platforms:
        if name in config.COMMIT_QUERIES:
            repos, rows = collect_commits(gh, name, windows, raw_root, max_pages)
            write_csv(out / f"windows_{name}.csv", rows,
                      ["day", "window_start", "window_end", "total_count", "n_items", "pages",
                       "capped", "incomplete"])
            fields = ["full_name", "n_commits_seen", "first_day", "last_day"]
            summary = {"unique_repos": len(repos),
                       "commits_seen": sum(r["n_items"] for r in rows),
                       "capped_windows": sum(r["capped"] for r in rows),
                       "incomplete_windows": sum(r["incomplete"] for r in rows)}
        else:
            repos, query_rows = collect_bolt(gh, raw_root, max_pages, bolt_ids)
            write_csv(out / "queries_boltnew.csv", query_rows,
                      ["id", "endpoint", "q", "total_count", "n_items", "pages", "capped", "incomplete"])
            fields = ["full_name", "n_hits", "queries"]
            summary = {"unique_repos": len(repos),
                       "capped_queries": sum(r["capped"] for r in query_rows)}
        write_csv(out / f"frame_{name}.csv", sorted(repos.values(), key=lambda r: r["full_name"]), fields)
        manifest["platforms"][name] = summary
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"  {name}: {summary}")

    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"collect: done -> {out}")
