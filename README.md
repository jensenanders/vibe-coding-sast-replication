# Replication package: Static Analysis Security Findings in Vibe-Coded Web Applications

SAST analysis pipeline for public GitHub repositories of applications built with
Lovable, Replit and Bolt.new, together with the results aggregated per platform.

## Contents

| Path | Content |
|---|---|
| `pipeline/` | The pipeline (Python, runs only in Docker): source, tests, Dockerfiles and pinned requirements |
| `docker-compose.yml` | Runs every pipeline step |
| `docs/Reposertory-Selection.md` | The selection protocol: search queries, inclusion and exclusion rules, seed rule (in Danish) |
| `docs/validering_instruktion.md` | Instruction for the manual validation of the screening (in Danish) |
| `docs/review_instruktion.md` | Instruction for the manual TP/FP review of findings (in Danish) |
| `results/` | Results aggregated per platform and tool (six CSV files) |

## What is not included, and why

To protect the repository owners, the package contains **no repository names, no
per-repository results, no file paths and no code excerpts**. The frozen sampling frame
(the raw GitHub API responses), the per-repository analysis output and the mapping
between pseudonyms and repositories are therefore not published.

Consequences:

- The pipeline can be rerun, but a new run will not yield the same sample: GitHub's
  search index changes over time, and the seed is derived from the freeze date.
- The tables in the paper cannot be regenerated from `results/` alone. The `tables`
  step computes medians, quartiles and the box plot from per-repository values, which
  are not published. The files in `results/` document the aggregated numbers.

## Results (`results/`)

All files have one row per platform and tool (or matching rule). `combined` is CodeQL
and GitLab SAST deduplicated with the main matching rule (C). `codeql` is the
`security-extended` suite; `codeql_default` is the subset found by the default
code-scanning suite. Freeze date of the sampling frame: 2026-10-31; 50 repositories per
platform.

| File | Content |
|---|---|
| `rq1_category.csv` | Findings and repositories per OWASP Top 10:2025 category. A finding whose CWEs map to several categories is counted in each |
| `rq1_severity.csv` | Findings per severity |
| `rq2_density.csv` | KLOC, findings, and findings per KLOC per repository (median, quartiles, mean, repositories without findings) |
| `rq2_density_n25.csv` | The same as `rq2_density.csv` for the nested sample of the first 25 included repositories per platform (sensitivity analysis) |
| `jaccard.csv` | Agreement between CodeQL and GitLab SAST for the matching rules A, C (main) and E. Repositories without findings from either tool have no per-repository Jaccard coefficient, hence 47 repositories for Bolt.new |
| `review_precision.csv` | Manual review of a stratified random sample of 20 findings per platform and tool: TP, FP, unclear (`uklar`), precision TP/(TP+FP) with a Wilson 95 % interval |

Shares are rounded to four decimals in the CSV files. The tables in the paper are
computed from the counts and rounded once.

## Requirements

- Docker with Docker Compose.
- A GitHub token exported as `GITHUB_TOKEN` in the host shell (a classic personal access
  token with the `public_repo` scope). The token is passed into the container and is
  never written to disk.
- The CodeQL image is built from the **linux-arm64** bundle (`pipeline/codeql/Dockerfile`).
  On another architecture, the bundle file name and checksum must be changed.
- `mkdir data` before the first run. `data/` and `output/` are git-ignored because they
  contain repository names.

## Steps

Run in this order. `<date>` is the freeze date (`YYYY-MM-DD`) of the frame created by `collect`.

| Step | Command | Output |
|---|---|---|
| `collect` | `docker compose run --rm pipeline collect` | `data/frame/<date>/`: the sampling frame per platform, the search windows and a manifest (seed, period, protocol hash). Raw API responses in the Docker volume |
| `prefilter` | `docker compose run --rm pipeline prefilter --freeze-date <date>` | `data/prefilter/<date>/`: metadata rules per repository (multi-platform, fork, archived, `pushed_at`) |
| `shuffle` | `docker compose run --rm pipeline shuffle --freeze-date <date>` | `data/order/<date>/`: the seeded screening order |
| `screen` | `docker compose run --rm pipeline screen --freeze-date <date>` | `data/screen/<date>/`: one row per screened repository (reason, commit SHA, backend NLOC, variables). Clones in the Docker volume |
| `validate` | `docker compose run --rm pipeline validate --freeze-date <date>`, then `... --score` | `data/validate/<date>/`: a blind validation sheet, the key, and after scoring the agreement |
| `scan` | `docker build -t msr-codeql:2.27.3 pipeline/codeql` (once), then `docker compose run --rm pipeline scan --freeze-date <date>` | `data/scan/<date>/`: cloc, CodeQL and GitLab SAST reports per repository, without code excerpts. The tools run in their own images without network access |
| `owasp` | `docker compose run --rm pipeline owasp --freeze-date <date>` | `data/owasp/2025/`: the OWASP Top 10:2025 lists of mapped CWEs from OWASP's own source at a pinned commit |
| `analyse` | `docker compose run --rm pipeline analyse --freeze-date <date>` | `data/analysis/<date>/`: findings, per-repository density, and the aggregated files published in `results/` |
| `sensitivity` | `docker compose run --rm pipeline sensitivity --freeze-date <date>` | `data/analysis/<date>/nloc_sensitivity.csv`: the selection recomputed with other backend-NLOC thresholds |
| `review` | `docker compose run --rm pipeline review --freeze-date <date>`, then `... --score` | `data/review/<date>/`: the review sheets and, after scoring, precision and inter-rater agreement |
| `tables` | `docker compose run --rm pipeline tables --freeze-date <date>` | `output/tables/` and `output/figures/`: the LaTeX tables and the box plot |

Smoke runs that do not touch the real frame: `collect --test`, `prefilter --test`,
`screen --test` and `scan --test`. An interrupted `collect`, `prefilter`, `screen` or
`scan` resumes when the same command is run again.

Expected running time of `collect`: about 4,380 searches per commit-based platform with
at least 2.1 s between requests, that is, about 2.5 to 3 hours each.

## Tests

```
docker compose run --rm --entrypoint python pipeline -m unittest discover -s /app/tests
```

## Pinned versions

| Component | Version |
|---|---|
| Base image | `python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159` (Python 3.12.16, Debian 13.7) |
| Python packages | lizard 1.24.3, pathspec 1.1.1, Pygments 2.21.0 (`pipeline/requirements.txt`) |
| Debian packages | git `1:2.47.3-0+deb13u1`, cloc `2.04-1`, docker-cli `26.1.5+dfsg1-9+deb13u1` (`pipeline/Dockerfile`) |
| GitLab SAST | `registry.gitlab.com/security-products/semgrep@sha256:f24de394b3eb36aa3d7cd1ed73e65555546cc547ec1db39a04ec1ceb34557d83` (analyzer 6.30.0, Semgrep 1.181.0). Settings from GitLab's `SAST.gitlab-ci.yml` template: `SEARCH_MAX_DEPTH=20`, `SAST_EXCLUDED_PATHS=spec, test, tests, tmp`; metrics off |
| CodeQL | CLI bundle v2.27.3 (`codeql-bundle-linux-arm64.tar.gz`, sha256 `0c9e32e9fcf65be4ab8df0cf0a7bb83e64aff4099fffc5f4930e84c12a454c8b`), Node.js `20.19.2+dfsg-1+deb13u3`. Suite `security-extended` for `javascript-typescript` and `python`, `--build-mode=none` |
| OWASP Top 10:2025 | `github.com/OWASP/Top10` at commit `3a31f35346c3f4e90f350395124382fa53af2afe` |

The seed is the freeze date written as the integer `YYYYMMDD` (20261031 for the
published results).

## Security notes

- The `scan` step starts the tool containers through the host's Docker socket, which is
  mounted into the pipeline container. Access to the Docker socket is equivalent to root
  access on the host, so run the pipeline only on a machine where that is acceptable.
- The pipeline clones and analyses code from public repositories that it does not
  control. The code is never executed: the repositories are cloned without credentials,
  exported with `git archive`, and analysed statically by tools that run without network
  access.
- `GITHUB_TOKEN` is sent only to `api.github.com`. A token with the `public_repo` scope
  is sufficient; do not use a token with wider scopes.
- Findings in other people's repositories are never tested against live systems, and
  the reports are stored without code excerpts.

## Notes on the protocol file

`docs/Reposertory-Selection.md` is the version of 2026-11-01, when the backend rule was
extended after the pilot and the first validation round and then frozen. The sampling
frame was collected on 2026-10-31, so the protocol hash in the frame's manifest refers
to an earlier version of the file. Comments in the source code refer to
a decision log (`docs/beslutningslog.md`) that is not part of this package.

## License

MIT, see `LICENSE`.
