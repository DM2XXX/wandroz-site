"""
Is production actually serving what main says it should?

WHY THIS EXISTS
    The release workflow asserts against production after it deploys. That
    covers releases it performed. It covers nothing else — and on 18 September
    that gap cost two hours of a stale site:

      - a commit landed on main at 14:44 and changed the wording on 1,944 pages
      - Vercel created no deployment at all, because the project was over its
        deployment-storage quota on the Hobby plan
      - nothing failed. There was no red build, no alert, no error. Production
        simply went on serving the previous commit
      - it was found by a person opening the site and reading it

    A missing deployment is invisible by construction: the thing that would
    have complained is the thing that never ran.

WHY IT COMPARES A FINGERPRINT AND NOT THE SITEMAP
    The obvious check is "does the live sitemap match the committed one". It
    would have passed happily through the whole incident: that commit changed
    page content and added no URL, so both sitemaps were identical while the
    site was two hours stale. The build publishes a SHA-256 over every file it
    produced (see write_build_fingerprint in build_site.py); comparing that
    answers the real question in one request.

    The sitemap count is still reported, because when the two disagree it is
    useful to know whether pages appeared or vanished or merely changed.

USAGE
    python3 pipeline/check_production_live.py
    python3 pipeline/check_production_live.py --url https://staging.example.com

EXIT CODES
    0  production matches the committed build
    1  production is serving something else — or nothing
    2  the check could not run (no local build, network failure)
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "dist")
SITE = "https://www.wandroz.com"
UA = "Mozilla/5.0 (compatible; wandroz-livecheck/1.0; +https://www.wandroz.com)"


def fetch(url):
    """curl rather than urllib: this has to run identically on a laptop and in
    a GitHub runner, and curl is the one HTTP client both are guaranteed to
    have."""
    r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", UA, url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout


def local(name):
    path = os.path.join(DIST, name)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return f.read()


def main(site):
    want = local("build-fingerprint.txt")
    if want is None:
        print("FATAL: dist/build-fingerprint.txt is missing — run build_site.py first.")
        return 2
    want = want.strip()

    got = fetch("%s/build-fingerprint.txt" % site)
    if got is None:
        print("FATAL: could not reach %s" % site)
        return 2
    got = got.strip()

    # A 404 page is HTML, not a hash. Saying "mismatch" there would be true but
    # unhelpful: the fingerprint has never been deployed, which is a different
    # problem from a stale deployment and has a different fix.
    if not re.fullmatch(r"[0-9a-f]{64}", got):
        print("FAIL: %s/build-fingerprint.txt did not return a fingerprint." % site)
        print("      Production is running a build from before this check existed.")
        print("      Deploy once; from then on this check is meaningful.")
        return 1

    local_map = local("sitemap.xml") or ""
    live_map = fetch("%s/sitemap.xml" % site) or ""
    n_local = len(re.findall(r"<loc>", local_map))
    n_live = len(re.findall(r"<loc>", live_map))

    print("committed build  %s   %d URLs in sitemap" % (want[:16], n_local))
    print("live build       %s   %d URLs in sitemap" % (got[:16], n_live))

    if want == got:
        print("\nOK: production is serving exactly the committed build.")
        return 0

    print("\nFAIL: production is NOT serving the committed build.")
    if n_local == n_live:
        print("      The sitemaps are the same size, so this is changed content, not")
        print("      added or removed pages — exactly the shape of a deployment that")
        print("      never ran. Check the host's deployment list for the newest commit.")
    else:
        print("      %+d URLs live vs committed." % (n_live - n_local))
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=SITE)
    a = ap.parse_args()
    sys.exit(main(a.url.rstrip("/")))
