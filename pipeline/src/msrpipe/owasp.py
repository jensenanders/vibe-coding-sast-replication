"""Step `owasp`: OWASP Top 10:2025 CWE lists, and how often a finding maps to more than one category.

  1. The ten category pages are fetched once from OWASP's markdown source at a pinned commit
     and kept in /data/owasp/2025/ (sha256 in the manifest); later runs read the kept files.
  2. Each page's "## List of Mapped CWEs" section is parsed: one CWE per bullet `* [CWE-<n> ...`.
  3. Every finding in /data/scan/<date>/raw is mapped CWE -> categories (CodeQL: the rule's
     external/cwe tags; GitLab: identifiers of type cwe). CodeQL findings in TEST_DIRS are dropped.
  4. Per platform and tool: findings with 0, 1 and 2+ categories, and the CWEs on 2+ lists.
Deterministic: no judgement, only the lists and the CWE ids the tools report.
"""

import csv
import datetime as dt
import hashlib
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

from . import config

SECTION = re.compile(r"^## List of Mapped CWEs\s*$(.*?)(?=^## |\Z)", re.M | re.S)
BULLET = re.compile(r"^\s*\*\s*\[CWE-(\d+)\b", re.M)
CODEQL_CWE = re.compile(r"^external/cwe/cwe-(\d+)$")


# ---- the lists -------------------------------------------------------------------

def parse_cwes(markdown):
    """CWE ids listed under '## List of Mapped CWEs'."""
    m = SECTION.search(markdown)
    if not m:
        raise ValueError("no 'List of Mapped CWEs' section")
    return sorted({int(n) for n in BULLET.findall(m.group(1))})


def fetch_lists(dest):
    """-> ({category: [cwe]}, {category: sha256}). Downloads only files not yet kept."""
    dest.mkdir(parents=True, exist_ok=True)
    lists, hashes = {}, {}
    for cat, name in config.OWASP_2025.items():
        path = dest / f"{name}.md"
        if not path.exists():
            url = config.OWASP_TOP10_RAW.format(commit=config.OWASP_TOP10_COMMIT, file=name)
            req = urllib.request.Request(url, headers={"User-Agent": "msr-paper-pipeline"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                path.write_bytes(resp.read())
        raw = path.read_bytes()
        hashes[cat] = hashlib.sha256(raw).hexdigest()
        lists[cat] = parse_cwes(raw.decode("utf-8"))
    return lists, hashes


def cwe_index(lists):
    """{cwe: [categories]} over all lists."""
    idx = {}
    for cat, cwes in lists.items():
        for c in cwes:
            idx.setdefault(c, []).append(cat)
    return idx


# ---- the findings ----------------------------------------------------------------

def in_test_dir(path):
    return bool(config.TEST_DIRS & set(path.split("/")[:-1]))


def codeql_findings(sarif):
    for run in json.loads(sarif.read_text()).get("runs", []):
        rules = {r["id"]: r for comp in [run["tool"]["driver"], *run["tool"].get("extensions", [])]
                 for r in comp.get("rules", [])}
        for res in run.get("results", []):
            props = rules.get(res["ruleId"], {}).get("properties", {})
            loc = res["locations"][0]["physicalLocation"]
            yield {"rule": res["ruleId"], "path": loc["artifactLocation"]["uri"],
                   "line": loc.get("region", {}).get("startLine"),
                   "cwes": sorted({int(m.group(1)) for t in props.get("tags", []) if (m := CODEQL_CWE.match(t))}),
                   "severity": cvss_rating(props.get("security-severity")),
                   "title": rules.get(res["ruleId"], {}).get("shortDescription", {}).get("text", ""),
                   "message": res.get("message", {}).get("text", "")}


def cvss_rating(score):
    """CodeQL's security-severity -> CVSS v3.1 qualitative rating, which GitHub code scanning uses."""
    if score is None:
        return "Unknown"
    score = float(score)
    for floor, label in config.CVSS_RATINGS:
        if score >= floor:
            return label
    return "None"


def gitlab_findings(report):
    for v in json.loads(report.read_text()).get("vulnerabilities", []):
        ids = v.get("identifiers", [])
        yield {"rule": next((i["value"] for i in ids if i["type"] == "semgrep_id"), ""),
               "path": v["location"]["file"], "line": v["location"].get("start_line"),
               "cwes": sorted({int(i["value"]) for i in ids if i["type"] == "cwe"}),
               "severity": v.get("severity", "Unknown"),
               "title": v.get("name", ""), "message": v.get("description", "")}


def findings(repo_dir):
    """(tool, finding) for one repo's raw reports; CodeQL findings in TEST_DIRS are dropped."""
    for sarif in sorted(repo_dir.glob("codeql-*.sarif")):
        for f in codeql_findings(sarif):
            if not in_test_dir(f["path"]):
                yield "codeql", f
    report = repo_dir / "gl-sast-report.json"
    if report.exists():
        for f in gitlab_findings(report):
            yield "gitlab", f


def categories(cwes, idx):
    return sorted({cat for c in cwes for cat in idx.get(c, [])})


# ---- driver ----------------------------------------------------------------------

def run(args):
    lists_dir = Path("/data/owasp/2025")
    lists, hashes = fetch_lists(lists_dir)
    idx = cwe_index(lists)
    with open(lists_dir / "owasp2025_cwe.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "cwe"])
        for cat, cwes in lists.items():
            w.writerows([cat, c] for c in cwes)
    multi_cwes = {c: cats for c, cats in idx.items() if len(cats) > 1}
    (lists_dir / "owasp2025.json").write_text(json.dumps({
        "source": config.OWASP_TOP10_RAW, "commit": config.OWASP_TOP10_COMMIT, "sha256": hashes,
        "n_cwes": {cat: len(c) for cat, c in lists.items()}, "n_distinct_cwes": len(idx),
        "cwes_on_several_lists": {str(c): cats for c, cats in sorted(multi_cwes.items())},
        "parsed_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2))
    print(f"owasp: {len(idx)} distinct CWEs on the 10 lists, {len(multi_cwes)} on more than one")

    raw_root = Path("/data/scan") / args.freeze_date / "raw"
    out = Path("/data/analysis") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    rows, hits = [], Counter()
    for p in ["lovable", "replit", "boltnew"]:
        for tool in ["codeql", "gitlab"]:
            n = Counter()
            for repo in sorted((raw_root / p).iterdir()):
                for t, f in findings(repo):
                    if t != tool:
                        continue
                    cats = categories(f["cwes"], idx)
                    n["findings"] += 1
                    n["no_cwe"] += not f["cwes"]
                    n["cat_0"] += len(cats) == 0
                    n["cat_1"] += len(cats) == 1
                    n["cat_2plus"] += len(cats) >= 2
                    if len(cats) >= 2:
                        hits[(tool, ";".join(cats), ";".join(map(str, f["cwes"])))] += 1
            rows.append({"platform": p, "tool": tool, **{k: n[k] for k in
                         ["findings", "no_cwe", "cat_0", "cat_1", "cat_2plus"]}})
    with open(out / "owasp_multi.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(out / "owasp_multi_combos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tool", "categories", "cwes", "findings"])
        w.writerows([*k, v] for k, v in hits.most_common())
    for r in rows:
        print(f"  {r['platform']:8} {r['tool']:6} {r['findings']:5} findings: "
              f"0 cat {r['cat_0']}, 1 cat {r['cat_1']}, 2+ cat {r['cat_2plus']} (no CWE {r['no_cwe']})")
    print(f"owasp: done -> {out}")
