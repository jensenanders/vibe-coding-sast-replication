"""Step `screen`: protocol items 6-9, repo by repo in the shuffled order.

For each repo (in `order_<platform>.csv`):
  1. owner_taken           the owner already has an included repo -> skipped, not cloned
  2. clone_failed          `git clone --filter=blob:none --single-branch` failed or timed out
  3. no_platform_trace     no commit by the platform's identity (Lovable/Replit), no .bolt/ in root (Bolt)
  4. mobile                an app.json with a top-level "expo" key, or an eas.json, anywhere in the tree
  5. backend_nloc_below_min  Lizard NLOC over the backend dirs < MIN_BACKEND_NLOC
The reason is the first rule that fails; rules 3-5 and the variables are recorded for
every cloned repo, also excluded ones (needed for the validation sample).
Screening stops at SCREEN_TARGET included repos or when the order is used up.
Every repo is written to the CSV as soon as it is decided, so an interrupted run resumes.
Clones of included repos are kept (at the analysed commit) for `scan`; others are deleted.
"""

import csv
import datetime as dt
import json
import posixpath
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

import lizard

from . import config
from .prefilter import PLATFORMS

REASONS = ["owner_taken", "clone_failed", "no_platform_trace", "mobile", "backend_nloc_below_min"]
FIELDS = ["rank", "full_name", "included", "reason", "detail", "head_sha", "clone_seconds",
          "n_commits", "n_platform_commits", "platform_share", "platform_trace",
          "mobile", "mobile_file", "backend_nloc", "n_backend_files", "n_lizard_failed",
          "other_ai_tool", "ambiguous_instructions", "other_platform"]


# ---- git -------------------------------------------------------------------------

def git(*args, cwd=None, timeout=120):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, check=True).stdout


def clone(full_name, dest):
    """-> (ok, detail, seconds). No credentials are sent; the repos are public."""
    t0 = time.time()
    try:
        git("clone", "--quiet", "--filter=blob:none", "--single-branch",
            f"https://github.com/{full_name}.git", str(dest), timeout=config.CLONE_TIMEOUT)
        return True, "", round(time.time() - t0, 1)
    except subprocess.TimeoutExpired:
        return False, "timeout", round(time.time() - t0, 1)
    except subprocess.CalledProcessError as e:
        return False, (e.stderr.strip().splitlines() or ["git error"])[-1][:200], round(time.time() - t0, 1)


def has_commits(root):
    """False for an empty repository (it clones fine, but has no HEAD commit)."""
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root,
                          capture_output=True).returncode == 0


def commit_emails(root):
    """(author email, committer email) for every commit reachable from HEAD."""
    out = git("log", "--format=%ae%x00%ce", cwd=root)
    return [tuple(line.lower().split("\x00")) for line in out.splitlines() if line]


def tracked_files(root):
    return [f for f in git("ls-files", "-z", cwd=root).split("\x00") if f]


# ---- rules -----------------------------------------------------------------------

def platform_commits(platform, emails):
    """Number of commits by the platform's identity (Lovable/Replit); None for Bolt."""
    rule = config.PLATFORM_TRACE.get(platform)
    if rule is None:
        return None
    pat = re.compile(rule["email"])
    i = 0 if rule["field"] == "author" else 1
    return sum(1 for e in emails if pat.match(e[i]))


def bolt_trace(files):
    return any(f.startswith(config.BOLT_TRACE_DIR + "/") for f in files)


def mobile_file(root, files):
    """First file that makes the repo a mobile app under the Expo rule, else ''."""
    for f in files:
        base = posixpath.basename(f)
        if base == "eas.json":
            return f
        if base == "app.json":
            try:
                data = json.loads((root / f).read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue                    # not valid JSON -> not an Expo config
            if isinstance(data, dict) and "expo" in data:
                return f
    return ""


def backend_files(files):
    """Files in a backend dir in the root, or named *.server.<ext> / *.functions.<ext> anywhere."""
    out = []
    for f in files:
        stem, ext = posixpath.splitext(posixpath.basename(f))
        if ext not in config.BACKEND_EXT or config.SKIP_DIRS & set(f.split("/")[:-1]):
            continue
        in_dir = any(f.startswith(d + "/") for d in config.BACKEND_DIRS)
        if in_dir or stem.endswith(config.BACKEND_SUFFIXES):
            out.append(f)
    return out


def backend_nloc(root, files):
    """-> (sum of Lizard NLOC over the backend files, number of files Lizard could not parse).

    Symlinks are skipped. A file Lizard crashes on counts as 0 NLOC (conservative: it can
    only lower the total) and is counted, so the effect can be reported.
    """
    total = failed = 0
    for f in files:
        p = root / f
        if p.is_symlink() or not p.is_file():
            continue
        try:
            total += lizard.analyze_file(str(p)).nloc
        except Exception:                   # parser bugs in Lizard (seen: IndexError on a .ts file)
            failed += 1
    return total, failed


def markers(root, files, platform):
    """Variables: labels of other-AI-tool files, ambiguous instruction files, other platforms."""
    ai, amb, other = set(), set(), set()
    for f in files:
        parts = f.split("/")
        dirs, base = parts[:-1], parts[-1]
        for label, (kind, v) in config.OTHER_AI_TOOL.items():
            if ((kind == "dir" and v in dirs) or (kind == "file" and base == v)
                    or (kind == "any" and v in parts) or (kind == "path" and (f == v or f.endswith("/" + v)))
                    or (kind == "prefix" and any(p.startswith(v) for p in parts))):
                ai.add(label)
        if base.lower() in config.AMBIGUOUS_INSTRUCTIONS:
            amb.add(base.lower())
        if platform != "replit" and base in (".replit", "replit.md"):
            other.add("replit")
        if platform != "boltnew" and ".bolt" in dirs:
            other.add("boltnew")
        if platform != "lovable" and base == "package.json":
            try:
                if "lovable-tagger" in (root / f).read_text(encoding="utf-8", errors="replace"):
                    other.add("lovable")
            except OSError:
                pass
    return ";".join(sorted(ai)), ";".join(sorted(amb)), ";".join(sorted(other))


def analyse(platform, root):
    """All rule outcomes and variables for one cloned repo, plus the exclusion reason."""
    files = tracked_files(root)
    emails = commit_emails(root)
    n_plat = platform_commits(platform, emails)
    trace = bolt_trace(files) if n_plat is None else n_plat > 0
    mob = mobile_file(root, files)
    bfiles = backend_files(files)
    nloc, lizard_failed = backend_nloc(root, bfiles)
    ai, amb, other = markers(root, files, platform)
    reason = ("no_platform_trace" if not trace else "mobile" if mob
              else "backend_nloc_below_min" if nloc < config.MIN_BACKEND_NLOC else "")
    return reason, {
        "head_sha": git("rev-parse", "HEAD", cwd=root).strip(),
        "n_commits": len(emails), "n_platform_commits": "" if n_plat is None else n_plat,
        "platform_share": "" if n_plat is None or not emails else round(n_plat / len(emails), 4),
        "platform_trace": trace, "mobile": bool(mob), "mobile_file": mob,
        "backend_nloc": nloc, "n_backend_files": len(bfiles), "n_lizard_failed": lizard_failed,
        "other_ai_tool": ai, "ambiguous_instructions": amb, "other_platform": other,
    }


# ---- driver ----------------------------------------------------------------------

def owner(full_name):
    return full_name.split("/", 1)[0].lower()      # GitHub logins are case-insensitive


def read_rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def screen_platform(platform, order, out_csv, clone_root, target):
    done = read_rows(out_csv)
    done_ranks = {int(r["rank"]) for r in done}
    owners = {owner(r["full_name"]) for r in done if r["included"] == "True"}
    n_incl = sum(r["included"] == "True" for r in done)
    new_file = not out_csv.exists()
    with open(out_csv, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for rank, fn in order:
            if n_incl >= target:
                break
            if rank in done_ranks:
                continue
            row = {"rank": rank, "full_name": fn, "included": False, "detail": ""}
            dest = clone_root / platform / f"{rank:05d}"
            shutil.rmtree(dest, ignore_errors=True)          # leftover from an interrupted run
            if owner(fn) in owners:
                row["reason"] = "owner_taken"
            else:
                ok, detail, secs = clone(fn, dest)
                row["clone_seconds"] = secs
                if ok and not has_commits(dest):
                    ok, detail = False, "empty repository"
                if not ok:
                    row.update(reason="clone_failed", detail=detail)
                else:
                    reason, info = analyse(platform, dest)
                    row.update(info, reason=reason, included=not reason)
            if row["included"]:
                owners.add(owner(fn))
                n_incl += 1
            else:
                shutil.rmtree(dest, ignore_errors=True)
            w.writerow(row)
            fh.flush()
            print(f"  {platform} #{rank}: {row['reason'] or 'included'} ({n_incl}/{target} included)")
    return n_incl


def run(args):
    test = args.test
    order_dir = Path("/data/order") / args.freeze_date
    out = Path("/data/test/screen" if test else "/data/screen") / args.freeze_date
    clone_root = Path("/work/test-clones" if test else "/work/clones") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    target = 2 if test else config.SCREEN_TARGET
    manifest_path = out / "screen.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "freeze_date": args.freeze_date, "test": test, "target": target,
        "min_backend_nloc": config.MIN_BACKEND_NLOC, "rules": REASONS,
        "git": git("--version").strip(), "lizard": lizard.version, "platforms": {},
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}

    for p in args.platforms:
        with open(order_dir / f"order_{p}.csv", newline="", encoding="utf-8") as fh:
            order = [(int(r["rank"]), r["full_name"]) for r in csv.DictReader(fh)]
        if test:
            order = order[:6]
        print(f"screen {p}: {len(order)} repos in order, target {target}")
        n_incl = screen_platform(p, order, out / f"screen_{p}.csv", clone_root, target)
        rows = read_rows(out / f"screen_{p}.csv")
        reasons = Counter(r["reason"] for r in rows if r["reason"])
        manifest["platforms"][p] = {"screened": len(rows), **{r: reasons[r] for r in REASONS},
                                    "included": n_incl, "order_exhausted": n_incl < target}
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"  {p}: {manifest['platforms'][p]}")
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"screen: done -> {out}")
