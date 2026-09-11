"""
Wandroz — source/output reproducibility check

WHAT THIS ASKS
  "Can canonical source reproduce the intended site?"

  qa_full_site.py asks whether a build is internally correct. This asks
  whether the build covers everything it is supposed to cover, and — when
  pointed at the current dist/ — what a clean rebuild would change and why.

WHY IT DOES NOT DIFF BYTES
  Production is a patchwork of several generator vintages: as of 11 Sep 2026
  it carried two different correction addresses, two badge labels and a
  footer string retired weeks earlier. Demanding byte-equality against that
  would enshrine the drift instead of removing it. So this compares
  *structural* expectations — does every source zone have a page, does every
  page have a source zone — and classifies content differences by root cause
  rather than asserting they should be zero.

CLASSES REPORTED
  SOURCE_ONLY        zone in source, no page in the build   (a build bug)
  GENERATED_ONLY     page in the build, no zone in source   (an orphan)
  MISSING_FROM_BUILD city registered but absent from output
  UNEXPECTED_OUTPUT  file in the build no rule accounts for
  COUNT_MISMATCH     zone counts disagree between source, map and pages

USAGE
    python3 pipeline/verify_reproducible.py --dist build_candidate
    python3 pipeline/verify_reproducible.py --dist build_candidate \
        --compare-against dist --report-dir qa_output

EXIT CODES
    0  source and output are structurally consistent
    1  at least one structural inconsistency
    2  the check itself could not run
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)

try:
    import build_site as BS
except Exception as exc:  # pragma: no cover
    print("FATAL: cannot import pipeline/build_site.py (%s)" % exc)
    sys.exit(2)

try:
    from qa_full_site import FALLBACK_REGISTRY, LONDON_SLUG, zone_page_path, walk_html
except Exception as exc:  # pragma: no cover
    print("FATAL: cannot import pipeline/qa_full_site.py (%s)" % exc)
    sys.exit(2)


# Files the build legitimately emits that are not zone or hub pages.
EXPECTED_ROOT_FILES = {
    "index.html", "methodology.html", "robots.txt", "sitemap.xml",
    "search-index.json", "zone-boundaries.json", "style.css",
    "site.webmanifest", "favicon.svg", "favicon-32.png",
    "apple-touch-icon.png", "icon-512.png", "logo-mark.png",
}

# Marker → (why a clean rebuild changes it, expected count in a clean build).
# This is the production-vintage analysis from the 11 Sep crawl, turned into
# an executable assertion so the improvement can be demonstrated rather than
# claimed. "Expected" is what a correct clean build should contain.
VINTAGE_MARKERS = [
    ("dadenuoto@gmail.com",              "email normalisation",              0),
    ("hellowandroz@gmail.com",           "email normalisation (canonical)",  None),
    ("both figures shown are the same",  "FAQ modernisation",                0),
    (">Overall safety level<",           "methodology badge normalisation",  0),
    ("prototype build",                  "footer normalisation",             0),
    ("not a finished product",           "footer normalisation",             0),
    ("areas covered on Wandroz",         "FAQ modernisation",                0),
    ("qualitative first-pass",           "methodology tier scoping",         None),
]

ROOT_CAUSE_RULES = [
    ("email normalisation",                 ("dadenuoto@gmail.com", "hellowandroz@gmail.com")),
    ("FAQ modernisation",                   ("both figures shown are the same",
                                             "areas covered on Wandroz",
                                             "single rating applies at any time of day")),
    ("footer normalisation",                ("prototype build", "not a finished product", "in beta")),
    ("methodology badge normalisation",     ("Overall safety level",
                                             "no day/night split in the source data")),
    ("city switcher normalisation",         ("/krakow/", "<optgroup")),
    ("methodology tier scoping",            ("qualitative first-pass", "general local knowledge",
                                             "public reputation")),
]


def load_zone_source(key):
    path = os.path.join(BASE_DIR, "data_zones", "%s.json" % key)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def get_registry():
    reg = getattr(BS, "CITY_REGISTRY", None)
    if reg:
        return {k: (v["data_key"], v["scheme"]) for k, v in reg.items()}, True
    return dict(FALLBACK_REGISTRY), False


def build_inventories(dist, reg):
    """Return (source_pages, built_pages) as sets of dist-relative paths."""
    source_pages, expected_hubs = set(), set()
    for city, (key, scheme) in reg.items():
        expected_hubs.add(os.path.join(city, "index.html"))
        src = load_zone_source(key)
        if not src:
            continue
        for z in src.get("zones", []):
            rel = os.path.relpath(zone_page_path(dist, city, z["slug"], scheme), dist)
            source_pages.add(rel)
    expected_hubs.add(os.path.join(LONDON_SLUG, "index.html"))

    built_pages = {rel for _p, rel in walk_html(dist)}
    return source_pages, expected_hubs, built_pages


def classify(dist, reg, findings):
    source_pages, expected_hubs, built_pages = build_inventories(dist, reg)

    london_pages = {p for p in built_pages
                    if p.startswith(LONDON_SLUG + os.sep) and not p.endswith("index.html")}
    root_pages = {p for p in built_pages if os.sep not in p}

    for rel in sorted(source_pages - built_pages):
        findings.append(("SOURCE_ONLY", rel, "zone exists in source but the build produced no page"))

    accounted = source_pages | expected_hubs | london_pages | root_pages
    for rel in sorted(built_pages - accounted):
        findings.append(("GENERATED_ONLY", rel, "page exists in the build with no zone in source"))

    for rel in sorted(expected_hubs - built_pages):
        findings.append(("MISSING_FROM_BUILD", rel, "registered city has no hub page in the build"))

    for rel in sorted(root_pages - {f for f in EXPECTED_ROOT_FILES if f.endswith(".html")}):
        findings.append(("UNEXPECTED_OUTPUT", rel, "root-level page no rule accounts for"))

    for root, _dirs, files in os.walk(dist):
        if root != dist:
            continue
        for name in files:
            if not name.endswith(".html") and name not in EXPECTED_ROOT_FILES:
                findings.append(("UNEXPECTED_OUTPUT", name, "root-level asset no rule accounts for"))

    # Count parity across the three places a zone count is expressed.
    counts = {}
    for city, (key, scheme) in sorted(reg.items()):
        src = load_zone_source(key)
        if not src:
            continue
        n_source = len(src.get("zones", []))
        hub = os.path.join(dist, city, "index.html")
        n_map = None
        if os.path.isfile(hub):
            m = re.search(r"var ZONES\s*=\s*(\[.*?\]);\s*$", read(hub), re.M | re.S)
            if m:
                try:
                    n_map = len(json.loads(m.group(1)))
                except ValueError:
                    n_map = -1
        n_pages = sum(1 for z in src.get("zones", [])
                      if os.path.isfile(zone_page_path(dist, city, z["slug"], scheme)))
        counts[city] = {"source": n_source, "map": n_map, "pages": n_pages}
        if n_map is not None and n_map != n_source:
            findings.append(("COUNT_MISMATCH", city,
                             "source has %d zones, hub map has %d" % (n_source, n_map)))
        if n_pages != n_source:
            findings.append(("COUNT_MISMATCH", city,
                             "source has %d zones, build produced %d pages" % (n_source, n_pages)))
    return counts


def marker_counts(directory):
    """How many pages in a directory contain each vintage marker."""
    tally = Counter()
    for path, _rel in walk_html(directory):
        text = read(path)
        for marker, _cause, _expected in VINTAGE_MARKERS:
            if marker in text:
                tally[marker] += 1
    return tally


def root_cause_for(before, after):
    """Attribute a changed page to the fix that explains it."""
    causes = []
    for cause, markers in ROOT_CAUSE_RULES:
        if any((m in before) != (m in after) for m in markers):
            causes.append(cause)
    return causes or ["unexpected difference"]


def compare(candidate, current, report_dir):
    """Classify what a clean rebuild would change, and why."""
    cand = {rel: path for path, rel in walk_html(candidate)}
    curr = {rel: path for path, rel in walk_html(current)}

    added = sorted(set(cand) - set(curr))
    removed = sorted(set(curr) - set(cand))
    common = sorted(set(cand) & set(curr))

    changed, unchanged, by_cause = [], 0, Counter()
    for rel in common:
        before, after = read(curr[rel]), read(cand[rel])
        if before == after:
            unchanged += 1
            continue
        causes = root_cause_for(before, after)
        for c in causes:
            by_cause[c] += 1
        changed.append({"page": rel, "causes": causes})

    for rel in added:
        by_cause["Florence recovery" if rel.startswith("firenze" + os.sep) else "new output"] += 1

    print()
    print("=" * 72)
    print("CANDIDATE vs CURRENT DIST")
    print("=" * 72)
    print("candidate pages %d" % len(cand))
    print("current pages   %d" % len(curr))
    print("unchanged       %d" % unchanged)
    print("changed         %d" % len(changed))
    print("added           %d" % len(added))
    print("removed         %d" % len(removed))
    print()
    print("%-38s %s" % ("ROOT CAUSE", "PAGES"))
    for cause, n in by_cause.most_common():
        print("%-38s %d" % (cause, n))
    if removed:
        print()
        print("REMOVED pages (a clean build no longer emits these — review each):")
        for rel in removed[:40]:
            print("  %s" % rel)
        if len(removed) > 40:
            print("  ... and %d more" % (len(removed) - 40))

    print()
    print("%-38s %10s %10s %10s" % ("VINTAGE MARKER", "CURRENT", "CANDIDATE", "EXPECTED"))
    cur_t, can_t = marker_counts(current), marker_counts(candidate)
    marker_rows, marker_fail = [], False
    for marker, cause, expected in VINTAGE_MARKERS:
        exp = "—" if expected is None else str(expected)
        flag = ""
        if expected is not None and can_t[marker] != expected:
            flag, marker_fail = "  <-- NOT MET", True
        print("%-38s %10d %10d %10s%s" % (marker[:38], cur_t[marker], can_t[marker], exp, flag))
        marker_rows.append({"marker": marker, "root_cause": cause,
                            "current": cur_t[marker], "candidate": can_t[marker],
                            "expected": expected})

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "candidate_diff.json"), "w", encoding="utf-8") as f:
        json.dump({
            "candidate_pages": len(cand), "current_pages": len(curr),
            "unchanged": unchanged, "changed": len(changed),
            "added": added, "removed": removed,
            "by_root_cause": dict(by_cause),
            "markers": marker_rows,
            "changed_pages": changed,
        }, f, indent=2)
        f.write("\n")
    with open(os.path.join(report_dir, "candidate_diff.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "root_causes"])
        for row in changed:
            w.writerow([row["page"], "; ".join(row["causes"])])
        for rel in added:
            w.writerow([rel, "ADDED"])
        for rel in removed:
            w.writerow([rel, "REMOVED"])

    unexplained = sum(1 for c in changed if c["causes"] == ["unexpected difference"])
    if unexplained:
        print()
        print("%d changed page(s) are NOT explained by any known fix — review these first:" % unexplained)
        for row in [c for c in changed if c["causes"] == ["unexpected difference"]][:20]:
            print("  %s" % row["page"])
    return unexplained, marker_fail


def main():
    ap = argparse.ArgumentParser(description="Wandroz source/output reproducibility check")
    ap.add_argument("--dist", default=os.path.join(REPO_DIR, "dist"))
    ap.add_argument("--compare-against", default=None,
                    help="a second directory (normally dist/) to diff the candidate against")
    ap.add_argument("--report-dir", default=os.path.join(REPO_DIR, "qa_output"))
    args = ap.parse_args()

    dist = os.path.abspath(args.dist)
    if not os.path.isdir(dist):
        print("FATAL: %s is not a directory" % dist)
        return 2

    reg, canonical = get_registry()
    findings = []
    counts = classify(dist, reg, findings)

    print("=" * 72)
    print("WANDROZ REPRODUCIBILITY CHECK")
    print("=" * 72)
    print("build audited      %s" % dist)
    print("cities registered  %d%s" % (len(reg) + 1,
          "" if canonical else "   (registry is qa_full_site's fallback, not build_site's)"))
    print("zones in source    %d" % sum(c["source"] for c in counts.values()))
    print()
    if findings:
        tally = Counter(kind for kind, _t, _m in findings)
        print("%-20s %s" % ("CLASS", "COUNT"))
        for kind, n in sorted(tally.items()):
            print("%-20s %d" % (kind, n))
        print()
        for kind, target, message in findings[:60]:
            print("%-20s %-44s %s" % (kind, target[:44], message))
        if len(findings) > 60:
            print("... and %d more (see reproducibility.csv)" % (len(findings) - 60))
    else:
        print("No structural inconsistencies: every source zone has a page, "
              "every page has a source zone.")

    os.makedirs(args.report_dir, exist_ok=True)
    with open(os.path.join(args.report_dir, "reproducibility.json"), "w", encoding="utf-8") as f:
        json.dump({"dist": dist, "counts": counts,
                   "findings": [{"class": k, "target": t, "message": m} for k, t, m in findings]},
                  f, indent=2)
        f.write("\n")
    with open(os.path.join(args.report_dir, "reproducibility.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "target", "message"])
        w.writerows(findings)

    unexplained = 0
    if args.compare_against:
        current = os.path.abspath(args.compare_against)
        if os.path.isdir(current):
            unexplained, _marker_fail = compare(dist, current, args.report_dir)
        else:
            print("WARNING: --compare-against %s is not a directory; skipping diff" % current)

    print()
    print("RESULT: %d structural finding(s), %d unexplained page difference(s)"
          % (len(findings), unexplained))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
