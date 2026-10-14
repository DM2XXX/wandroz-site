"""
Seeds the sitemap's lastmod manifest from the repository's own history.

WHY
    build_site keeps a manifest of {url: (content hash, date that hash first
    appeared)} so the sitemap can carry a lastmod that is true: a page whose
    bytes did not change keeps its old date however many builds run over it.

    On the very first run there is no manifest, so every URL would be stamped
    with today — which would tell Google that all 2,535 pages changed at once
    on the day the feature shipped. That is false, and a sitemap that cries
    wolf gets ignored, which is the opposite of the point.

    The true dates exist already: dist/ is committed, so every published page
    has a last-touched commit date. This reads them once, in a single pass over
    the history, and writes the manifest. After that build_site maintains it.

USAGE
    python3 pipeline/seed_sitemap_lastmod.py        # writes the manifest
    python3 pipeline/seed_sitemap_lastmod.py --dry  # just reports
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(REPO, "dist")
STATE = os.path.join(HERE, "data", "sitemap_lastmod.json")
SITE_URL = "https://www.wandroz.com"


def last_touched():
    """{path relative to dist: YYYY-MM-DD} from one walk of the git history."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "log", "--date=short",
         "--pretty=format:@%ad", "--name-only", "--", "dist/"],
        cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("cannot read git history: %s" % out.stderr.strip())
    dates, day = {}, None
    for line in out.stdout.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line.strip() and day:
            rel = line.strip()
            if rel.startswith("dist/"):
                rel = rel[len("dist/"):]
            # git log walks newest first, so the first date wins.
            dates.setdefault(rel, day)
    return dates


def url_for(rel):
    if rel.endswith("/index.html"):
        return "%s/%s" % (SITE_URL, rel[:-len("index.html")])
    return "%s/%s" % (SITE_URL, rel)


def main(dry):
    dates = last_touched()
    print("git history covers %d files under dist/" % len(dates))
    state, missing = {}, 0
    for root, _dirs, files in os.walk(DIST):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, DIST)
            day = dates.get(rel)
            if day is None:
                missing += 1
                continue
            with open(path, "rb") as f:
                digest = hashlib.sha1(f.read()).hexdigest()[:16]
            state[url_for(rel)] = {"hash": digest, "date": day}
    spread = {}
    for v in state.values():
        spread[v["date"]] = spread.get(v["date"], 0) + 1
    print("dated %d pages across %d distinct days (%d had no history)"
          % (len(state), len(spread), missing))
    for d, n in sorted(spread.items())[:4]:
        print("   %s  %d" % (d, n))
    if len(spread) > 6:
        print("   ...")
    for d, n in sorted(spread.items())[-3:]:
        print("   %s  %d" % (d, n))
    if dry:
        print("\n--dry: nothing written")
        return 0
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0, sort_keys=True)
    print("\nwrote %s" % STATE)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    sys.exit(main(ap.parse_args().dry))
