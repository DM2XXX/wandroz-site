"""
Do the links that leave the site still work?

WHY THIS IS NOT IN THE QA GATE
    qa_full_site.py checks internal links and deliberately skips external ones.
    That is correct: the release gate has to be deterministic and offline, and
    a gate that fails because a government statistics office is having a bad
    morning would block a release for a reason that has nothing to do with the
    release. So outward links are checked here, on a schedule, where a failure
    is news rather than a blockage.

WHAT IS AT STAKE
    The methodology page names its source for all 28 official-data cities and
    links eight of them. Those links are the whole auditability claim: a data
    buyer who clicks one and lands on a 404 has been given a reason to doubt
    everything else on the page. Source links rot — statistics offices
    reorganise their sites yearly — so they need watching.

WHAT IT FIXES BY ITSELF, AND WHAT IT REFUSES TO
    --fix follows one rule and one only: where a URL answers with a PERMANENT
    redirect (301/308) to another URL on the same host, the source is rewritten
    to the destination. That is mechanical and checkable.

    It will not invent a replacement for a dead link. A 404 on a statistics
    table is a question about which table replaced it, and guessing would put a
    plausible wrong source under a safety rating. Those are reported, and the
    safe automatic step offered is to drop the link and keep the source name —
    which is what the 32 research-based cities already do.

USAGE
    python3 pipeline/check_external_links.py
    python3 pipeline/check_external_links.py --fix

EXIT CODES
    0  every external link answered
    1  at least one did not
    2  could not run
"""
import argparse
import collections
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "dist")
BUILD = os.path.join(HERE, "build_site.py")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

HREF_RE = re.compile(r'href="(https?://[^"]+)"')
# Asset hosts and the affiliate network are not editorial links: a font CDN
# being slow is not a Wandroz problem, and the CJ click wrappers deliberately
# bounce through a redirect chain that a HEAD request reads as suspicious.
# Also our own absolute URLs — canonical tags and breadcrumbs point at
# wandroz.com by design, and there are 2,000 of them. Their integrity is
# already two other checks' job: qa_full_site verifies internal links against
# the build, and check_production_live verifies that production is serving that
# build. Re-fetching them here would turn a ten-second check into a ten-minute
# one and tell us nothing new.
SKIP = re.compile(r"(fonts\.googleapis|fonts\.gstatic|cdnjs\.cloudflare|"
                  r"jdoqocy|tkqlhce|dpbolvw|anrdoezrs|kqzyfj|booking\.com|"
                  r"//(www\.)?wandroz\.com)")


def collect():
    """url -> the pages that link to it."""
    found = collections.defaultdict(set)
    for root, dirs, files in os.walk(DIST):
        for name in files:
            if not name.endswith(".html"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, DIST)
            with io.open(full, encoding="utf-8", errors="replace") as f:
                for url in HREF_RE.findall(f.read()):
                    if not SKIP.search(url):
                        found[url].add(rel)
    return found


def probe(url):
    """(status, final url). A real browser user agent, because several
    statistics sites answer 403 to anything that looks automated — and a 403
    that only we see is not a broken link for a reader."""
    r = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "--max-time", "30", "-A", UA,
         "-w", "%{http_code} %{url_effective}", "-L", url],
        capture_output=True, text=True)
    if r.returncode != 0:
        return ("000", url)
    parts = r.stdout.strip().split(" ", 1)
    return (parts[0], parts[1] if len(parts) > 1 else url)


def redirect_target(url):
    """Where a permanent redirect points, or None. Deliberately does NOT follow
    302/307: a temporary redirect is the publisher saying "not yet"."""
    r = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "--max-time", "30", "-A", UA,
         "-w", "%{http_code} %{redirect_url}", url],
        capture_output=True, text=True)
    parts = r.stdout.strip().split(" ", 1)
    if len(parts) == 2 and parts[0] in ("301", "308") and parts[1]:
        return parts[1]
    return None


def main(do_fix):
    if not os.path.isdir(DIST):
        print("FATAL: no dist/ — run build_site.py first.")
        return 2
    links = collect()
    if not links:
        print("No external links found. That is itself worth knowing.")
        return 0

    print("Checking %d distinct external links.\n" % len(links))
    bad, fixed = [], []
    for url in sorted(links):
        status, final = probe(url)
        ok = status.startswith(("2", "3"))
        mark = "ok  " if ok else "FAIL"
        print("%s %-4s %s" % (mark, status, url))
        if ok:
            continue
        bad.append((url, status, sorted(links[url])[:3], len(links[url])))

    if do_fix and bad:
        print("\nLooking for permanent redirects among the failures...")
        src = io.open(BUILD, encoding="utf-8").read()
        for url, status, _, _ in bad:
            target = redirect_target(url)
            if not target:
                continue
            host = re.sub(r"^https?://([^/]+).*", r"\1", url)
            if not target.startswith(("http://%s" % host, "https://%s" % host)):
                print("  skipped %s -> %s (different host, needs a person)" % (url, target))
                continue
            if url in src:
                src = src.replace(url, target)
                fixed.append((url, target))
                print("  rewrote %s -> %s" % (url, target))
        if fixed:
            io.open(BUILD, "w", encoding="utf-8").write(src)
            print("\n%d source URL(s) updated in build_site.py. Rebuild and re-run." % len(fixed))

    print()
    if not bad:
        print("OK: every external link answered.")
        return 0
    print("FAIL: %d link(s) did not answer." % len(bad))
    for url, status, pages, n in bad:
        if any(url == u for u, _ in fixed):
            continue
        print("  %s  HTTP %s  on %d page(s): %s" % (url, status, n, ", ".join(pages)))
    print("\nNothing else was changed automatically. A dead source URL is a question")
    print("about which table replaced it, and a plausible wrong source under a safety")
    print("rating is worse than a named source with no link.")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true",
                    help="rewrite permanent redirects (301/308) to the same host")
    a = ap.parse_args()
    sys.exit(main(a.fix))
