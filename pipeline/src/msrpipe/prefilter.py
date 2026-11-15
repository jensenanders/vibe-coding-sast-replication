"""Step `prefilter`: protocol items 3-4 on the frozen frame (no cloning).

Protocol: docs/Reposertory-Selection.md, "Samlet udvælgelsesprotokol".
3. A full_name that is in more than one platform's frame is excluded from all.
4. Metadata: not a fork, not archived, pushed_at on or after the period start.
Metadata comes from GraphQL, one request per PREFILTER_BATCH repos; raw responses are
kept, so a rerun reuses them and gives the same result. A repo the API no longer
returns (deleted, made private, disabled) is excluded as `unavailable`.
Every rule is evaluated for every repo; `reason` is the first rule that fails,
in the order of REASONS, so the counts per reason add up to the excluded total.
"""

import csv
import datetime as dt
import gzip
import json
from collections import Counter
from pathlib import Path

from . import config
from .collect import write_csv
from .github import GitHub

PLATFORMS = ["lovable", "replit", "boltnew"]
REASONS = ["multi_platform", "unavailable", "fork", "archived", "pushed_before_period"]
FIELDS = ["full_name", "resolved_name", "pushed_at", "api_error", *REASONS, "eligible", "reason"]


def read_frame(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [row["full_name"] for row in csv.DictReader(fh)]


def multi_platform(frames):
    """full_names found in more than one platform's frame."""
    count = Counter(fn for names in frames.values() for fn in set(names))
    return {fn for fn, c in count.items() if c > 1}


def batch_query(names):
    """One GraphQL query with an alias r<i> per repo (json.dumps gives a valid GraphQL string)."""
    parts = []
    for i, fn in enumerate(names):
        owner, name = fn.split("/", 1)
        parts.append(f"  r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ ...f }}")
    return ("query {\n" + "\n".join(parts) + "\n}\n"
            "fragment f on Repository { nameWithOwner isFork isArchived pushedAt }")


def parse_batch(names, body):
    """-> {full_name: (metadata or None, api_error)}. Raises if the response is unusable."""
    if not body or "data" not in body or body["data"] is None:
        raise RuntimeError(f"GraphQL response without data: {str(body)[:300]}")
    errors = {}
    for e in body.get("errors", []):
        if not e.get("path"):              # an error about the whole query, not one repo
            raise RuntimeError(f"GraphQL error: {e}")
        errors[e["path"][0]] = e.get("type", "UNKNOWN")
    return {fn: (body["data"].get(f"r{i}"), errors.get(f"r{i}", "")) for i, fn in enumerate(names)}


def fetch_metadata(gh, names, raw_dir):
    raw_dir.mkdir(parents=True, exist_ok=True)
    meta, n_batches = {}, -(-len(names) // config.PREFILTER_BATCH)
    for b in range(n_batches):
        chunk = names[b * config.PREFILTER_BATCH:(b + 1) * config.PREFILTER_BATCH]
        f = raw_dir / f"b{b:05d}.json.gz"
        if f.exists():
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rec = json.load(fh)
            if rec["request"]["names"] != chunk:
                raise SystemExit(f"{f} was fetched for other repos; delete {raw_dir} and rerun.")
            meta.update(parse_batch(chunk, rec["body"]))
        else:
            status, body = gh.graphql(batch_query(chunk), config.PREFILTER_MIN_INTERVAL)
            meta.update(parse_batch(chunk, body))          # validate before caching
            rec = {"request": {"endpoint": "/graphql", "names": chunk},
                   "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "status": status, "body": body}
            with gzip.open(f, "wt", encoding="utf-8") as fh:
                json.dump(rec, fh)
        if (b + 1) % 100 == 0 or b + 1 == n_batches:
            print(f"  metadata: {b + 1}/{n_batches} batches")
    return meta


def decide(fn, m, err, multi, period_start):
    pushed = (m or {}).get("pushedAt") or ""
    flags = {
        "multi_platform": fn in multi,
        "unavailable": m is None,
        "fork": bool(m and m["isFork"]),
        "archived": bool(m and m["isArchived"]),
        "pushed_before_period": m is not None and pushed[:10] < period_start,   # no push at all counts too
    }
    reason = next((r for r in REASONS if flags[r]), "")
    return {"full_name": fn, "resolved_name": (m or {}).get("nameWithOwner", ""), "pushed_at": pushed,
            "api_error": err, **flags, "eligible": not reason, "reason": reason}


def run(args):
    test = args.test
    frame_dir = Path("/data/frame") / args.freeze_date
    frame_manifest = json.loads((frame_dir / "manifest.json").read_text())
    if not frame_manifest.get("finished_at"):
        raise SystemExit(f"Frame {frame_dir} is not finished; run collect first.")
    period_start = frame_manifest["period_start"]
    out = Path("/data/test/prefilter" if test else "/data/prefilter") / args.freeze_date
    raw_dir = Path("/work/test-raw" if test else "/work/raw") / args.freeze_date / "prefilter"
    out.mkdir(parents=True, exist_ok=True)

    frames = {p: read_frame(frame_dir / f"frame_{p}.csv") for p in PLATFORMS}
    multi = multi_platform(frames)                     # on the full frames, also in test mode
    names = sorted(set().union(*frames.values()))
    if test:                                           # smoke run: first 2 batches only
        names = names[:2 * config.PREFILTER_BATCH]
    print(f"prefilter: frame {args.freeze_date}, {len(names)} unique repos, "
          f"{len(multi)} in more than one frame, test={test}")

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    meta = fetch_metadata(GitHub(), names, raw_dir)

    summary = {}
    for p in PLATFORMS:
        rows = [decide(fn, *meta[fn], multi, period_start) for fn in frames[p] if fn in meta]
        write_csv(out / f"prefilter_{p}.csv", rows, FIELDS)
        reasons = Counter(r["reason"] for r in rows if r["reason"])
        summary[p] = {"in_frame": len(rows), **{r: reasons[r] for r in REASONS},
                      "eligible": sum(r["eligible"] for r in rows)}
        print(f"  {p}: {summary[p]}")

    (out / "prefilter.json").write_text(json.dumps({
        "freeze_date": args.freeze_date, "test": test, "period_start": period_start,
        "rules": REASONS, "batch_size": config.PREFILTER_BATCH,
        "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platforms": summary,
    }, indent=2))
    print(f"prefilter: done -> {out}")
