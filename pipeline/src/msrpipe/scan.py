"""Step `scan`: the project plan's instruments on the main sample (first MAIN_N included per platform).

Per repo, in rank order:
  1. the kept clone must be at the head_sha `screen` recorded; otherwise the repo fails
  2. the tracked files at that commit are exported (`git archive`) to a scratch dir, so all
     three tools see the same tree and the clone is never written to
  3. cloc --json                      (in this image)
  4. CodeQL: one database per language present (no build), the security-extended suite, SARIF
  5. GitLab SAST: the Semgrep analyzer image with the CI template's settings, offline
  6. reports without code snippets (written in the scratch dir, which the tool containers can see) are moved to
     /data/scan/<date>/raw/<platform>/<rank>/; the scratch dir and databases are deleted
Tools run in their pinned images through the host's Docker, without network. No code snippets
are added to the reports. Each repo is written to scan_<platform>.csv when done, so an
interrupted run resumes.
"""

import csv
import datetime as dt
import json
import posixpath
import shutil
import subprocess
import time
from pathlib import Path

from . import config
from .screen import read_rows
from .validate import pools

FIELDS = ["rank", "full_name", "head_sha", "status", "detail", "n_files", "cloc_code",
          "codeql_langs", "codeql_status", "codeql_seconds", "codeql_findings",
          "gitlab_status", "gitlab_seconds", "gitlab_findings"]
WORK = Path("/work")


def sh(cmd, timeout=None, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def docker(name, image, args, env=None, entrypoint=None):
    """Run a tool container offline with the work volume. -> (status, seconds, stderr tail)."""
    cmd = ["docker", "run", "--rm", "--name", name, "--network", "none",
           "-v", f"{config.WORK_VOLUME}:/work"]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    t0 = time.time()
    try:
        r = sh(cmd + [image, *args], timeout=config.TOOL_TIMEOUT)
        status = "ok" if r.returncode == 0 else f"exit {r.returncode}"
        tail = (r.stderr.strip().splitlines() or [""])[-1][:200]
    except subprocess.TimeoutExpired:
        sh(["docker", "rm", "-f", name])                 # the CLI timed out; stop the container too
        status, tail = "timeout", ""
    return status, round(time.time() - t0, 1), tail


# ---- the tools -------------------------------------------------------------------

def export_tree(clone, sha, src):
    """Tracked files at `sha` -> src. Returns the file list (relative paths)."""
    src.mkdir()
    archive = subprocess.Popen(["git", "-C", str(clone), "archive", "--format=tar", sha], stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(src)], stdin=archive.stdout, check=True)
    if archive.wait() != 0:
        raise RuntimeError("git archive failed")
    return [l for l in sh(["git", "-C", str(clone), "ls-tree", "-r", "--name-only", "-z", sha]).stdout.split("\x00") if l]


def run_cloc(src, out):
    r = sh(["cloc", "--json", "--quiet", "--report-file", str(out / "cloc.json"), str(src)],
           timeout=config.TOOL_TIMEOUT)
    if r.returncode != 0 or not (out / "cloc.json").exists():
        return None
    return json.loads((out / "cloc.json").read_text()).get("SUM", {}).get("code", 0)


def codeql_langs(files):
    exts = {posixpath.splitext(f)[1].lower() for f in files}
    return [lang for lang, c in config.CODEQL_LANGS.items() if exts & c["exts"]]


def run_codeql(tag, src, db, out, langs):
    """-> (status, seconds, findings). One database and one SARIF per language."""
    if not langs:
        return "no language", 0.0, 0
    ram, total, findings = str(config.CODEQL_RAM_MB), 0.0, 0
    db.mkdir(exist_ok=True)
    for lang in langs:
        status, secs, tail = docker(f"{tag}-codeql-db-{lang}", config.CODEQL_IMAGE, [
            "database", "create", str(db / lang), f"--language={lang}", "--build-mode=none",
            f"--source-root={src}", "--threads=0", f"--ram={ram}", "--overwrite"])
        total += secs
        if status != "ok":
            return f"create {lang} {status}: {tail}", round(total, 1), findings
        sarif = out / f"codeql-{lang}.sarif"
        status, secs, tail = docker(f"{tag}-codeql-{lang}", config.CODEQL_IMAGE, [
            "database", "analyze", str(db / lang), config.CODEQL_LANGS[lang]["suite"],
            "--format=sarif-latest", f"--output={sarif}", "--threads=0", f"--ram={ram}", "--no-download"])
        total += secs
        if status != "ok":
            return f"analyze {lang} {status}: {tail}", round(total, 1), findings
        findings += sarif_count(sarif)
    return "ok", round(total, 1), findings


def run_gitlab(tag, src, out):
    """-> (status, seconds, findings). The analyzer writes into the target dir; reports are moved to `out`."""
    status, secs, tail = docker(f"{tag}-gitlab", config.GITLAB_SAST_IMAGE,
                                ["run", "--target-dir", str(src), "--artifact-dir", str(src)],
                                env=config.GITLAB_SAST_ENV, entrypoint="/analyzer")
    # Only GitLab's own report is kept. The analyzer's intermediate semgrep.sarif has code
    # snippets (which could hold secret values) and is left to be deleted with the scratch dir.
    if (src / "gl-sast-report.json").exists():
        shutil.move(str(src / "gl-sast-report.json"), str(out / "gl-sast-report.json"))
    if status != "ok":
        return f"{status}: {tail}", secs, 0
    if not (out / "gl-sast-report.json").exists():
        return "no report", secs, 0
    return "ok", secs, len(json.loads((out / "gl-sast-report.json").read_text()).get("vulnerabilities", []))


def sarif_count(path):
    return sum(len(r.get("results", [])) for r in json.loads(path.read_text()).get("runs", []))


# ---- driver ----------------------------------------------------------------------

def scan_repo(platform, r, clone_root, scratch_root, raw_root):
    rank = int(r["rank"])
    row = {"rank": rank, "full_name": r["full_name"], "head_sha": r["head_sha"], "status": "ok", "detail": ""}
    clone = clone_root / platform / f"{rank:05d}"
    head = sh(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.strip()
    if head != r["head_sha"]:
        return {**row, "status": "failed", "detail": f"clone not at recorded sha ({head[:12] or 'missing'})"}
    scratch = scratch_root / platform / f"{rank:05d}"
    out = raw_root / platform / f"{rank:05d}"
    shutil.rmtree(scratch, ignore_errors=True)        # leftover from an interrupted run
    shutil.rmtree(out, ignore_errors=True)
    src, db, reports = scratch / "src", scratch / "db", scratch / "reports"
    reports.mkdir(parents=True)
    try:
        files = export_tree(clone, r["head_sha"], src)
        row["n_files"] = len(files)
        row["cloc_code"] = run_cloc(src, reports)
        langs = codeql_langs(files)
        tag = f"msr-scan-{platform}-{rank:05d}"
        row["codeql_langs"] = ";".join(langs)
        row["codeql_status"], row["codeql_seconds"], row["codeql_findings"] = run_codeql(tag, src, db, reports, langs)
        row["gitlab_status"], row["gitlab_seconds"], row["gitlab_findings"] = run_gitlab(tag, src, reports)
        shutil.copytree(reports, out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    bad = [t for t in ("codeql", "gitlab") if row[f"{t}_status"] not in ("ok", "no language")]
    if row["cloc_code"] is None:
        bad.append("cloc")
    if bad:
        row["status"], row["detail"] = "partial", "failed: " + ",".join(bad)
    return row


def tool_versions():
    def v(cmd):
        r = sh(cmd)
        return (r.stdout + r.stderr).strip().splitlines() or [""]
    clean = lambda s: "".join(ch for ch in s if ch.isprintable())
    gitlab = [l for l in v(["docker", "run", "--rm", "--network", "none", "--entrypoint", "/analyzer",
                            config.GITLAB_SAST_IMAGE, "--version"]) if "version" in l]
    semgrep = v(["docker", "run", "--rm", "--network", "none", "--entrypoint", "semgrep",
                 config.GITLAB_SAST_IMAGE, "--version"])
    return {
        "cloc": v(["cloc", "--version"])[0],
        "codeql": v(["docker", "run", "--rm", "--network", "none", config.CODEQL_IMAGE, "version", "--format=terse"])[0],
        "codeql_image_id": sh(["docker", "image", "inspect", "--format", "{{.Id}}", config.CODEQL_IMAGE]).stdout.strip(),
        "gitlab_analyzer": clean(gitlab[-1]) if gitlab else "",
        "semgrep": next((l for l in semgrep if l[:1].isdigit()), ""),
        "gitlab_image": config.GITLAB_SAST_IMAGE,
        "docker_server": sh(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip(),
    }


def run(args):
    test = args.test
    screen_dir = Path("/data/screen") / args.freeze_date
    out = Path("/data/test/scan" if test else "/data/scan") / args.freeze_date
    raw_root = out / "raw"
    clone_root = WORK / "clones" / args.freeze_date
    scratch_root = WORK / ("test-scan" if test else "scan") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "scan.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "freeze_date": args.freeze_date, "test": test, "tools": tool_versions(),
        "gitlab_env": config.GITLAB_SAST_ENV,
        "codeql": {"langs": {k: {"exts": sorted(c["exts"]), "suite": c["suite"]} for k, c in config.CODEQL_LANGS.items()},
                   "ram_mb": config.CODEQL_RAM_MB, "build_mode": "none"},
        "tool_timeout": config.TOOL_TIMEOUT, "platforms": {},
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    manifest_path.write_text(json.dumps(manifest, indent=2))

    for p in args.platforms:
        sample, _ = pools(read_rows(screen_dir / f"screen_{p}.csv"))
        if test:
            sample = sample[:2]
        out_csv = out / f"scan_{p}.csv"
        done = {int(r["rank"]) for r in read_rows(out_csv)}
        new_file = not out_csv.exists()
        print(f"scan {p}: {len(sample)} repos, {len(done)} already done")
        with open(out_csv, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                w.writeheader()
            for i, r in enumerate(sample, 1):
                if int(r["rank"]) in done:
                    continue
                row = scan_repo(p, r, clone_root, scratch_root, raw_root)
                w.writerow(row)
                fh.flush()
                print(f"  {p} {i}/{len(sample)} #{r['rank']}: {row['status']} {row['detail']} "
                      f"cloc {row.get('cloc_code')} codeql {row.get('codeql_findings')} ({row.get('codeql_seconds')} s) "
                      f"gitlab {row.get('gitlab_findings')} ({row.get('gitlab_seconds')} s)")
        rows = read_rows(out_csv)
        manifest["platforms"][p] = {"scanned": len(rows), "ok": sum(r["status"] == "ok" for r in rows),
                                    "partial": sum(r["status"] == "partial" for r in rows),
                                    "failed": sum(r["status"] == "failed" for r in rows)}
        manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"scan: done -> {out}")
