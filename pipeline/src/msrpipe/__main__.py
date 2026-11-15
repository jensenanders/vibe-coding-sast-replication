"""Entry point: docker compose run --rm pipeline <step> [options]"""

import argparse

from . import analyse, collect, owasp, prefilter, review, scan, screen, sensitivity, shuffle, tables, validate


def main():
    p = argparse.ArgumentParser(prog="msrpipe")
    sub = p.add_subparsers(dest="step", required=True)

    c = sub.add_parser("collect", help="identification searches -> frozen sampling frame")
    c.add_argument("--freeze-date", help="YYYY-MM-DD; default today (UTC). Use it to resume an interrupted run.")
    c.add_argument("--platforms", nargs="+", default=["lovable", "replit", "boltnew"],
                   choices=["lovable", "replit", "boltnew"])
    c.add_argument("--test", action="store_true",
                   help="smoke run (last 2 days, 1 page per window, 2 Bolt queries) into /data/test, not the real frame")
    c.set_defaults(func=collect.run)

    f = sub.add_parser("prefilter", help="multi-platform rule + fork/archived/pushed_at -> eligible list")
    f.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame in /data/frame")
    f.add_argument("--test", action="store_true",
                   help="smoke run (first 100 repos) into /data/test/prefilter")
    f.set_defaults(func=prefilter.run)

    s = sub.add_parser("shuffle", help="eligible repos -> seeded screening order")
    s.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame")
    s.set_defaults(func=shuffle.run)

    r = sub.add_parser("screen", help="clone + platform trace, mobile, backend NLOC, one per owner")
    r.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame")
    r.add_argument("--platforms", nargs="+", default=["lovable", "replit", "boltnew"],
                   choices=["lovable", "replit", "boltnew"])
    r.add_argument("--test", action="store_true",
                   help="smoke run (first 6 repos per platform, target 2) into /data/test/screen")
    r.set_defaults(func=screen.run)

    v = sub.add_parser("validate", help="draw the blind validation sheet, or --score the filled one")
    v.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame")
    v.add_argument("--score", action="store_true", help="compare the filled sheet with the key")
    v.add_argument("--exclude", nargs="*", default=[], metavar="KEY_CSV",
                   help="key files from earlier rounds; their repos are not drawn again")
    v.set_defaults(func=validate.run)

    sc = sub.add_parser("scan", help="cloc + CodeQL + GitLab SAST on the main sample (first 50 included)")
    sc.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame")
    sc.add_argument("--platforms", nargs="+", default=["lovable", "replit", "boltnew"],
                    choices=["lovable", "replit", "boltnew"])
    sc.add_argument("--test", action="store_true",
                    help="smoke run (first 2 repos per platform) into /data/test/scan")
    sc.set_defaults(func=scan.run)

    o = sub.add_parser("owasp", help="OWASP Top 10:2025 CWE lists; findings mapped to 0, 1 or 2+ categories")
    o.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the scanned sample in /data/scan")
    o.set_defaults(func=owasp.run)

    a = sub.add_parser("analyse", help="RQ1 (category, severity, CWE) and RQ2 (per KLOC) per platform and tool")
    a.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the scanned sample in /data/scan")
    a.set_defaults(func=analyse.run)

    se = sub.add_parser("sensitivity", help="backend-NLOC threshold 25/100 vs 50 on the frozen screening results")
    se.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the frozen frame in /data/screen")
    se.set_defaults(func=sensitivity.run)

    tb = sub.add_parser("tables", help="LaTeX tables for the paper from the aggregated analysis output")
    tb.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the analysed sample in /data/analysis")
    tb.set_defaults(func=tables.run)

    rv = sub.add_parser("review", help="draw the manual TP/FP sheets of findings, or --score the filled ones")
    rv.add_argument("--freeze-date", required=True, help="YYYY-MM-DD of the scanned sample in /data/scan")
    rv.add_argument("--score", action="store_true", help="precision per stratum and agreement between coders")
    rv.set_defaults(func=review.run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
