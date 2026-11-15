"""Search queries and limits from docs/Reposertory-Selection.md (protocol locked 2026-10-31).

Changing anything here changes the protocol: it needs the student's yes and an
entry in docs/beslutningslog.md.
"""

# Lovable and Replit: commit search in random one-minute windows (author-date:<start>..<end>)
COMMIT_QUERIES = {
    "lovable": "author:lovable-dev[bot]",
    "replit": "committer:replit-agent",
}
BLOCKS_PER_DAY = 12       # one random minute in each 2-hour block (UTC)
WINDOW_SECONDS = 60

# Bolt.new: no date windows; first 1,000 results per query in GitHub's ranking
BOLT_REPO_QUERIES = {
    "R1": '"built with Bolt.new"',
    "R2": '"bolt.new"',
    "R3": '"built with bolt"',
    "R4": '"made with bolt"',
    "R5": '"created with bolt"',
    "R6": "topic:bolt-new",
    "R7": "topic:boltnew",
}
BOLT_CODE_QUERIES = {
    "C1": "path:.bolt filename:config.json",
    "C2": 'filename:package.json "vite-react-typescript-starter"',
    "C3": '"Built with Bolt.new" filename:README.md',
}

PER_PAGE = 100            # GitHub search maximum
MAX_RESULTS = 1000        # GitHub search API exposes at most 1,000 results per query
MAX_PAGES = MAX_RESULTS // PER_PAGE

# Minimum seconds between requests (GitHub search limits: 30/min, code search 10/min)
MIN_INTERVAL = {"commits": 2.1, "repositories": 2.1, "code": 6.1}

# Step `prefilter`: repository metadata via GraphQL, many repos per request (aliases)
PREFILTER_BATCH = 50
PREFILTER_MIN_INTERVAL = 1.0

# Step `screen` (protocol item 6-9)
SCREEN_TARGET = 100       # stop when this many repos per platform are included
MIN_BACKEND_NLOC = 50     # Lizard NLOC summed over backend files
CLONE_TIMEOUT = 600       # seconds; a clone that takes longer counts as failed

# Platform trace in git history (matched on email, lower-case regex).
# Lovable: GitHub account id 159125892 = lovable-dev[bot], formerly gpt-engineer-app[bot]
# (measured 2026-11-01: most Lovable commits still carry the old name), plus the
# platform's own address noreply@lovable.dev. Replit: committer "Replit Agent <agent@replit.com>".
PLATFORM_TRACE = {
    "lovable": {"field": "author",
                "email": r"^(159125892\+[^@]+\[bot\]@users\.noreply\.github\.com|noreply@lovable\.dev)$"},
    "replit": {"field": "committer",
               "email": r"^(agent@replit\.com|\d+\+replit-agent@users\.noreply\.github\.com)$"},
}
BOLT_TRACE_DIR = ".bolt"  # in the repo root

# artifacts/api-server added 2026-11-01 after the pilot (Replit Agent monorepo template)
BACKEND_DIRS = ["supabase/functions", "server", "api", "backend", "functions", "netlify/functions",
                "artifacts/api-server"]
BACKEND_EXT = {".ts", ".js", ".mjs", ".cjs", ".py"}
# Server-only files by name, anywhere in the tree (added 2026-11-01 after the validation):
# TanStack Start (Lovable's newer template) puts createServerFn wrappers in *.functions.ts and
# server-only code in *.server.ts (tanstack.com/start/latest/docs/framework/react/guide/server-functions).
BACKEND_SUFFIXES = (".server", ".functions")
SKIP_DIRS = {"node_modules", "dist", "build", ".git"}

# Variables (do not exclude). Matched on path components / basenames anywhere in the tree.
OTHER_AI_TOOL = {          # label -> (kind, value)
    ".claude": ("dir", ".claude"),
    ".cursor": ("dir", ".cursor"),
    ".cursorrules": ("file", ".cursorrules"),
    ".windsurf": ("dir", ".windsurf"),
    ".windsurfrules": ("file", ".windsurfrules"),
    ".clinerules": ("any", ".clinerules"),
    "copilot-instructions": ("path", ".github/copilot-instructions.md"),
    "GEMINI.md": ("file", "GEMINI.md"),
    ".aider*": ("prefix", ".aider"),
}
AMBIGUOUS_INSTRUCTIONS = {"agents.md", "claude.md"}   # compared lower-case


# Step `scan` (added 2026-11-01): the instruments from the project plan, on the main sample.
# Tools run in their own images through the host's Docker; clones and scratch space are in
# the named volume, so both containers see the same paths under /work.
WORK_VOLUME = "msr-paper_msrwork"
TOOL_TIMEOUT = 3600       # seconds per tool and repo; a tool that takes longer counts as failed
# GitLab SAST for JS/TS/Python is the Semgrep-based analyzer (GitLab docs, SAST analyzers, read
# 2026-11-01). Tag 6 as in the SAST.gitlab-ci.yml template; digest pulled 2026-11-01
# (analyzer 6.30.0, Semgrep 1.181.0, multi-arch).
GITLAB_SAST_IMAGE = ("registry.gitlab.com/security-products/semgrep@sha256:"
                     "f24de394b3eb36aa3d7cd1ed73e65555546cc547ec1db39a04ec1ceb34557d83")
# Settings as in the template's semgrep-sast job and its defaults; metrics off; run offline.
GITLAB_SAST_ENV = {"SEARCH_MAX_DEPTH": "20", "SAST_EXCLUDED_PATHS": "spec, test, tests, tmp",
                   "SAST_SEMGREP_METRICS": "false"}
# CodeQL bundle v2.27.3, built locally from pipeline/codeql/Dockerfile (bundle pinned by sha256)
CODEQL_IMAGE = "msr-codeql:2.27.3"
CODEQL_RAM_MB = 6000
# Languages CodeQL extracts without a build, the files that make us run them, and the suite
CODEQL_LANGS = {
    "javascript-typescript": {"exts": {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"},
                              "suite": "codeql/javascript-queries:codeql-suites/javascript-security-extended.qls"},
    "python": {"exts": {".py"},
               "suite": "codeql/python-queries:codeql-suites/python-security-extended.qls"},
}

# ---- step `owasp` (OWASP Top 10:2025 CWE lists; decided 2026-11-02) --------------
# The category pages' "List of Mapped CWEs", read from OWASP's own markdown source at a
# pinned commit of github.com/OWASP/Top10 (master on 2026-11-02, committed 2026-09-24).
OWASP_TOP10_COMMIT = "3a31f35346c3f4e90f350395124382fa53af2afe"
OWASP_TOP10_RAW = "https://raw.githubusercontent.com/OWASP/Top10/{commit}/2025/docs/en/{file}.md"
OWASP_2025 = {
    "A01:2025": "A01_2025-Broken_Access_Control",
    "A02:2025": "A02_2025-Security_Misconfiguration",
    "A03:2025": "A03_2025-Software_Supply_Chain_Failures",
    "A04:2025": "A04_2025-Cryptographic_Failures",
    "A05:2025": "A05_2025-Injection",
    "A06:2025": "A06_2025-Insecure_Design",
    "A07:2025": "A07_2025-Authentication_Failures",
    "A08:2025": "A08_2025-Software_or_Data_Integrity_Failures",
    "A09:2025": "A09_2025-Security_Logging_and_Alerting_Failures",
    "A10:2025": "A10_2025-Mishandling_of_Exceptional_Conditions",
}
# Decided 2026-11-02: CodeQL findings in these dirs (any depth) are dropped in the analysis,
# as GitLab SAST excludes them by default (SAST_EXCLUDED_PATHS).
TEST_DIRS = {"spec", "test", "tests", "tmp"}
OWASP_UNMAPPED = "Not in OWASP Top 10:2025"   # decided 2026-11-02: findings whose CWEs are on no list

# ---- step `analyse`: nested sample for the sensitivity analysis (Study Design) ----
NESTED_N = 25             # the first 25 included repositories per platform, in screening order

# ---- step `analyse` (RQ1/RQ2 per tool; decided 2026-11-02) ------------------------
# KLOC = cloc code lines in the languages the tools scan (cloc's names; .tsx/.mts are TypeScript).
KLOC_LANGS = {"JavaScript", "TypeScript", "JSX", "Python"}
# CodeQL's security-severity -> CVSS v3.1 qualitative rating (FIRST CVSS v3.1 spec, section 5),
# the scale GitHub code scanning uses for Critical/High/Medium/Low. Highest floor first.
CVSS_RATINGS = [(9.0, "Critical"), (7.0, "High"), (4.0, "Medium"), (0.1, "Low")]
CODEQL_DEFAULT_SUITES = {
    "javascript-typescript": "codeql/javascript-queries:codeql-suites/javascript-code-scanning.qls",
    "python": "codeql/python-queries:codeql-suites/python-code-scanning.qls",
}
# "Same finding" across CodeQL and GitLab (decided 2026-11-02): same file, |line difference| <= tol,
# and a shared OWASP category (not OWASP_UNMAPPED) or a shared CWE ("type"), or a shared CWE only
# ("cwe"). tol None = anywhere in the file. C is the main rule; A and E are the sensitivity bounds.
MATCH_RULES = {"A": (0, "cwe"), "C": (3, "type"), "E": (None, "type")}
MATCH_MAIN = "C"

# ---- step `sensitivity` (backend-NLOC threshold, B1 item 4; decided 2026-11-08) ---
SENSITIVITY_NLOC = (25, 100)  # compared with MIN_BACKEND_NLOC on the frozen screening results
SAMPLE_SIZES = (25, 50)       # nested samples (B6): sensitivity and main analysis

# ---- step `review` (manual check of findings; decided 2026-11-02) -----------------
REVIEW_PER_STRATUM = 20      # per platform x tool (codeql = security-extended, gitlab): 120 findings
REVIEW_CODER2_PER_STRATUM = 5    # of those, coded blind by a second person: 30 findings
REVIEW_LABELS = ("TP", "FP", "uklar")
