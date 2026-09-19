"""
What is this build about to REMOVE from the live site?

WHY THIS EXISTS
    On 19 September 2026 a rebuild of Zurich replaced 34 neighbourhood pages
    with 12, renamed every area, and silently dropped the day/night toggle and
    the whole vocabulary a reader recognised — Langstrasse, Seefeld, Enge
    became "Kreis 4", "Kreis 8", "Kreis 2". It went live. Both gates passed,
    and they were right to: the new site was perfectly consistent with itself.

    That is the hole. qa_full_site asks "is this build internally correct?"
    and verify_reproducible asks "can the source reproduce it?" — neither asks
    "is this build a loss compared with what is already published?" A change
    can be internally flawless and still be a demolition.

WHAT IT COMPARES
    The working dist/ against the dist/ committed at git HEAD, which is what
    production is serving. Not against the live site over HTTP: this has to run
    before a push, offline and deterministically, and check_production_live.py
    already covers the "is production actually serving HEAD" question.

WHAT COUNTS AS A REGRESSION
    - a published page that this build no longer produces
    - a city losing areas
    - a city losing a feature a reader used: the day/night toggle, the
      burglary layer, the sights, the comparison table
    - the site losing pages overall

    Removals are sometimes correct — a city genuinely reshaped, a page
    deliberately retired. So this does not forbid them, it refuses to let them
    happen silently: --accept records that a person looked and meant it.

USAGE
    python3 pipeline/check_regression.py
    python3 pipeline/check_regression.py --accept     # I looked, this is intended

EXIT CODES
    0  nothing is being removed, or removals were accepted
    1  this build removes something
    2  could not run
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(REPO, "dist")

# Things a reader can use, and the marker that proves the page still offers it.
FEATURES = {
    "day/night toggle": "dnSwitch",
    "burglary layer": "burglarySwitch",
    "sights": "poiBar",
    "comparison table": "hubTable",
    "recommendation cards": "hub-card",
}


def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def published_pages():
    """Every .html under dist/ at HEAD — what production is serving."""
    out = git("ls-tree", "-r", "--name-only", "HEAD", "dist/")
    if out is None:
        return None
    return {p[len("dist/"):] for p in out.splitlines() if p.endswith(".html")}


def built_pages():
    found = set()
    for root, _dirs, files in os.walk(DIST):
        for n in files:
            if n.endswith(".html"):
                found.add(os.path.relpath(os.path.join(root, n), DIST))
    return found


def city_of(rel):
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else None


def features_at_head(rel):
    blob = git("show", "HEAD:dist/%s" % rel)
    return {name for name, mark in FEATURES.items() if blob and mark in blob}


def features_now(rel):
    path = os.path.join(DIST, rel)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8", errors="replace") as f:
        blob = f.read()
    return {name for name, mark in FEATURES.items() if mark in blob}


def main(accept):
    if not os.path.isdir(DIST):
        print("FATAL: no dist/ — run build_site.py first.")
        return 2
    was = published_pages()
    if was is None:
        print("FATAL: cannot read dist/ at HEAD (not a git repo, or no commit yet).")
        return 2
    now = built_pages()

    removed = sorted(was - now)
    added = sorted(now - was)

    # Per city, how many area pages each side has.
    def areas(pages):
        out = {}
        for p in pages:
            c = city_of(p)
            if c and not p.endswith(os.sep + "index.html") or (c and p.count(os.sep) == 2):
                out[c] = out.get(c, 0) + 1
        return out

    was_n, now_n = areas(was), areas(now)
    shrunk = {c: (was_n[c], now_n.get(c, 0)) for c in was_n
              if now_n.get(c, 0) < was_n[c]}

    lost = {}
    for rel in sorted(was & now):
        if not rel.endswith("index.html"):
            continue
        gone = features_at_head(rel) - features_now(rel)
        if gone:
            lost[rel] = sorted(gone)

    print("published at HEAD: %d pages" % len(was))
    print("this build:        %d pages  (%+d)" % (len(now), len(now) - len(was)))
    print()

    problems = 0

    if removed:
        problems += 1
        print("REMOVES %d published page(s). Every one of these is a live URL that" % len(removed))
        print("would start returning 404 unless a redirect is added:")
        for p in removed[:12]:
            print("   -", p)
        if len(removed) > 12:
            print("   ... and %d more" % (len(removed) - 12))
        print()

    if shrunk:
        problems += 1
        print("CITIES LOSING AREAS:")
        for c, (a, b) in sorted(shrunk.items()):
            print("   %-22s %d -> %d" % (c, a, b))
        print()

    if lost:
        problems += 1
        print("PAGES LOSING A FEATURE A READER USES:")
        for rel, names in list(lost.items())[:12]:
            print("   %-34s lost: %s" % (rel, ", ".join(names)))
        if len(lost) > 12:
            print("   ... and %d more" % (len(lost) - 12))
        print()

    if added:
        print("(adds %d page(s) — not a problem, listed for context)" % len(added))
        print()

    if not problems:
        print("OK: this build removes nothing.")
        return 0

    if accept:
        print("ACCEPTED: --accept was passed, so the removals above are intended.")
        return 0

    print("REFUSING. Removing pages, areas or features is sometimes right — a city")
    print("genuinely reshaped, a page deliberately retired. It is never right by")
    print("accident. Look at the list; if you meant it, re-run with --accept, and")
    print("add redirects for the removed URLs before publishing.")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.accept))
