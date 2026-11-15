"""Step `analyse`: RQ1 (type, severity, OWASP category) and RQ2 (findings per KLOC), per tool.

Rules decided 2026-11-02 (docs/beslutningslog.md):
  - CodeQL: security-extended is the main result; the default (code-scanning) suite is
    reported as a subset, by rule id ("codeql_default").
  - CodeQL findings in spec/test/tests/tmp dirs are dropped (owasp.findings).
  - A finding counts once in totals and appears in every OWASP 2025 category its CWEs are
    listed under; findings on no list go to OWASP_UNMAPPED.
  - KLOC = cloc code lines in KLOC_LANGS.
  - "combined" is the project plan's primary count: CodeQL (security-extended) and GitLab,
    deduplicated with match rule MATCH_MAIN; a matched pair counts once, with the union of
    both findings' CWEs and categories and the higher severity of the two.
  - Jaccard J = matched / (codeql + gitlab - matched), per platform (pooled) and per repo,
    for every rule in MATCH_RULES.
Output per finding keeps path and line and stays in /data.
"""

import csv
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .owasp import findings

PLATFORMS = ["lovable", "replit", "boltnew"]
TOOLS = ["combined", "codeql", "codeql_default", "gitlab"]
SEVERITIES = ["Critical", "High", "Medium", "Low", "Info", "None", "Unknown"]


def load_lists(path):
    idx = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            idx[int(r["cwe"])].append(r["category"])
    return dict(idx)


def owasp_categories(cwes, idx):
    cats = sorted({c for cwe in cwes for c in idx.get(cwe, [])})
    return cats or [config.OWASP_UNMAPPED]


def codeql_default_ids(cache):
    """Rule ids (@id) of the queries in the default suites, read from the pinned CodeQL image."""
    if cache.exists():
        return set(json.loads(cache.read_text())["ids"])
    ids = set()
    for suite in config.CODEQL_DEFAULT_SUITES.values():
        script = f"codeql resolve queries {suite} 2>/dev/null | while read f; do grep -m1 '@id' \"$f\"; done"
        out = subprocess.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "sh",
                              config.CODEQL_IMAGE, "-c", script], capture_output=True, text=True, check=True).stdout
        ids |= {l.split("@id", 1)[1].strip() for l in out.splitlines() if "@id" in l}
    cache.write_text(json.dumps({"image": config.CODEQL_IMAGE, "suites": config.CODEQL_DEFAULT_SUITES,
                                 "ids": sorted(ids)}, indent=2))
    return ids


def kloc(cloc_json):
    data = json.loads(cloc_json.read_text())
    return sum(data.get(lang, {}).get("code", 0) for lang in config.KLOC_LANGS) / 1000


def quartiles(xs):
    if len(xs) < 2:
        return (xs[0], xs[0], xs[0]) if xs else (None, None, None)
    q1, q2, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    return q1, q2, q3


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def same_type(a, b, mode):
    wa, wb = set(a["cwes"]), set(b["cwes"])
    if mode == "cwe":
        return bool(wa & wb)
    ca, cb = set(a["categories"]) - {config.OWASP_UNMAPPED}, set(b["categories"]) - {config.OWASP_UNMAPPED}
    return bool(ca & cb) or bool(wa & wb)


def match_pairs(cq, gl, rule):
    """Greedy one-to-one matching of CodeQL and GitLab findings, closest lines first.
    -> [(i, j)] indexes into cq and gl. Ties are broken by index, so the result is deterministic."""
    tol, mode = config.MATCH_RULES[rule]
    cand = []
    for i, a in enumerate(cq):
        for j, b in enumerate(gl):
            if a["path"] != b["path"] or a["line"] is None or b["line"] is None:
                continue
            d = abs(a["line"] - b["line"])
            if (tol is None or d <= tol) and same_type(a, b, mode):
                cand.append((d, i, j))
    used_i, used_j, pairs = set(), set(), []
    for d, i, j in sorted(cand):
        if i not in used_i and j not in used_j:
            used_i.add(i)
            used_j.add(j)
            pairs.append((i, j))
    return pairs


def merge(a, b):
    """One combined finding from a matched CodeQL (a) and GitLab (b) pair."""
    cats = sorted(set(a["categories"]) | set(b["categories"]))
    if len(cats) > 1:
        cats = [c for c in cats if c != config.OWASP_UNMAPPED]
    sev = min(a["severity"], b["severity"], key=SEVERITIES.index)   # SEVERITIES is highest first
    return {"rule": f'{a["rule"]}|{b["rule"]}', "path": a["path"], "line": a["line"],
            "cwes": sorted(set(a["cwes"]) | set(b["cwes"])), "categories": cats, "severity": sev}


def collect_rows(raw_root, idx, default_ids):
    """-> (finding rows, repo rows, jaccard repo rows). codeql_default is a subset of codeql;
    combined is codeql + gitlab, deduplicated with MATCH_MAIN."""
    frows, rrows, jrows = [], [], []
    for p in PLATFORMS:
        for repo in sorted((raw_root / p).iterdir()):
            rank = int(repo.name)
            per = defaultdict(list)
            for tool, f in findings(repo):
                f = {**f, "categories": owasp_categories(f["cwes"], idx)}
                per[tool].append(f)
                if tool == "codeql" and f["rule"] in default_ids:
                    per["codeql_default"].append(f)
            cq, gl = per["codeql"], per["gitlab"]
            for rule in config.MATCH_RULES:
                m = len(match_pairs(cq, gl, rule))
                union = len(cq) + len(gl) - m
                jrows.append({"platform": p, "rank": rank, "rule": rule, "codeql": len(cq), "gitlab": len(gl),
                              "matched": m, "union": union, "jaccard": round(m / union, 4) if union else ""})
            pairs = match_pairs(cq, gl, config.MATCH_MAIN)
            mi, mj = {i for i, _ in pairs}, {j for _, j in pairs}
            per["combined"] = ([merge(cq[i], gl[j]) for i, j in pairs]
                               + [f for i, f in enumerate(cq) if i not in mi]
                               + [f for j, f in enumerate(gl) if j not in mj])
            for t in TOOLS:
                for f in per[t]:
                    frows.append({"platform": p, "rank": rank, "tool": t, "rule": f["rule"],
                                  "path": f["path"], "line": f["line"],
                                  "cwes": ";".join(map(str, f["cwes"])), "categories": ";".join(f["categories"]),
                                  "severity": f["severity"]})
            k = kloc(repo / "cloc.json")
            rrows.append({"platform": p, "rank": rank, "kloc": round(k, 3),
                          **{f"n_{t}": len(per[t]) for t in TOOLS},
                          **{f"density_{t}": round(len(per[t]) / k, 4) if k else "" for t in TOOLS}})
    return frows, rrows, jrows


def jaccard_summary(jrows):
    out = []
    for p in PLATFORMS:
        for rule in config.MATCH_RULES:
            rows = [r for r in jrows if r["platform"] == p and r["rule"] == rule]
            cq, gl, m = (sum(r[k] for r in rows) for k in ("codeql", "gitlab", "matched"))
            per_repo = sorted(r["jaccard"] for r in rows if r["jaccard"] != "")
            q1, med, q3 = quartiles(per_repo)
            out.append({"platform": p, "rule": rule, "main": rule == config.MATCH_MAIN, "codeql": cq, "gitlab": gl,
                        "matched": m, "union": cq + gl - m, "jaccard_pooled": round(m / (cq + gl - m), 4),
                        "repos": len(per_repo), "jaccard_median": round(med, 4), "q1": round(q1, 4), "q3": round(q3, 4),
                        "repos_jaccard_zero": sum(x == 0 for x in per_repo)})
    return out


def summarise(frows, rrows):
    by = defaultdict(list)
    for r in frows:
        by[(r["platform"], r["tool"])].append(r)
    n_repos = Counter(r["platform"] for r in rrows)
    cat_rows, sev_rows, cwe_rows, dens_rows = [], [], [], []
    for p in PLATFORMS:
        for t in TOOLS:
            rows = by[(p, t)]
            total = len(rows)
            cats, cat_repos, sev, cwe = Counter(), defaultdict(set), Counter(), Counter()
            for r in rows:
                for c in r["categories"].split(";"):
                    cats[c] += 1
                    cat_repos[c].add(r["rank"])
                sev[r["severity"]] += 1
                cwe[r["cwes"] or "(none)"] += 1
            for c in [*config.OWASP_2025, config.OWASP_UNMAPPED]:
                cat_rows.append({"platform": p, "tool": t, "category": c, "findings": cats[c],
                                 "share_of_findings": round(cats[c] / total, 4) if total else "",
                                 "repos": len(cat_repos[c]), "share_of_repos": round(len(cat_repos[c]) / n_repos[p], 4)})
            for s in SEVERITIES:
                sev_rows.append({"platform": p, "tool": t, "severity": s, "findings": sev[s],
                                 "share": round(sev[s] / total, 4) if total else ""})
            for c, k in sorted(cwe.items(), key=lambda x: (-x[1], x[0])):
                cwe_rows.append({"platform": p, "tool": t, "cwes": c, "findings": k})
            repos = [r for r in rrows if r["platform"] == p]
            d = sorted(r[f"density_{t}"] for r in repos if r[f"density_{t}"] != "")
            q1, med, q3 = quartiles(d)
            total_kloc = sum(r["kloc"] for r in repos)
            dens_rows.append({"platform": p, "tool": t, "repos": len(repos), "findings": total,
                              "kloc": round(total_kloc, 1),
                              "pooled_per_kloc": round(total / total_kloc, 4) if total_kloc else "",
                              "median_per_kloc": round(med, 4), "q1": round(q1, 4), "q3": round(q3, 4),
                              "mean_per_kloc": round(statistics.mean(d), 4),
                              "repos_zero": sum(r[f"n_{t}"] == 0 for r in repos)})
    return cat_rows, sev_rows, cwe_rows, dens_rows


def nested(frows, rrows, n):
    """The rows of the first n repositories per platform, in screening order (lowest rank first)."""
    keep = set()
    for p in PLATFORMS:
        ranks = sorted(r["rank"] for r in rrows if r["platform"] == p)
        keep |= {(p, k) for k in ranks[:n]}
    return ([r for r in frows if (r["platform"], r["rank"]) in keep],
            [r for r in rrows if (r["platform"], r["rank"]) in keep])


def run(args):
    raw_root = Path("/data/scan") / args.freeze_date / "raw"
    out = Path("/data/analysis") / args.freeze_date
    out.mkdir(parents=True, exist_ok=True)
    idx = load_lists(Path("/data/owasp/2025/owasp2025_cwe.csv"))
    default_ids = codeql_default_ids(out / "codeql_default_ids.json")
    frows, rrows, jrows = collect_rows(raw_root, idx, default_ids)
    write_csv(out / "findings.csv", frows)
    write_csv(out / "repos.csv", rrows)
    write_csv(out / "jaccard_repos.csv", jrows)
    jac = jaccard_summary(jrows)
    write_csv(out / "jaccard.csv", jac)
    cat_rows, sev_rows, cwe_rows, dens_rows = summarise(frows, rrows)
    write_csv(out / "rq1_category.csv", cat_rows)
    write_csv(out / "rq1_severity.csv", sev_rows)
    write_csv(out / "rq1_cwe.csv", cwe_rows)
    write_csv(out / "rq2_density.csv", dens_rows)
    nested_dens = summarise(*nested(frows, rrows, config.NESTED_N))[3]
    write_csv(out / f"rq2_density_n{config.NESTED_N}.csv", nested_dens)
    print(f"analyse: {len(default_ids)} default-suite rule ids, {len(frows)} finding rows, {len(rrows)} repos")
    for r in dens_rows:
        print(f"  {r['platform']:8} {r['tool']:14} {r['findings']:5} findings / {r['kloc']:7} KLOC: "
              f"pooled {r['pooled_per_kloc']}, median {r['median_per_kloc']} [{r['q1']}-{r['q3']}], zero {r['repos_zero']}")
    for r in jac:
        print(f"  {r['platform']:8} rule {r['rule']}{'*' if r['main'] else ' '} matched {r['matched']:4} "
              f"J pooled {r['jaccard_pooled']}, median per repo {r['jaccard_median']} (zero in {r['repos_jaccard_zero']}/{r['repos']})")
    for r in nested_dens:
        if r["tool"] == "combined":
            print(f"  {r['platform']:8} first {r['repos']} repos: {r['findings']:5} findings, "
                  f"median {r['median_per_kloc']} [{r['q1']}-{r['q3']}] per KLOC")
    print(f"analyse: done -> {out}")
