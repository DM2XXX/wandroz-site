"""Page-level near-duplicate measure: how many pages read as a copy of another.

WHY THIS EXISTS
    Search Console reported 819 URLs discovered and not crawled. Body text is
    not what a crawler compares — the whole rendered page is — so counting
    identical paragraphs understated the problem: 122 pages across ten cities
    were 80% identical to another page in the same city once the shared
    furniture was included.

    This shingles the rendered text of every area page in a city and reports
    the pairs that cross 0.80 Jaccard. Run it against HEAD as well as the
    working build, so a change can be shown to have moved the number rather
    than asserted to have.

USAGE
    python3 pipeline/check_near_duplicates.py

Body text is not what a crawler compares — the whole rendered page is. This
strips the HTML of a sample of area pages, shingles the words, and reports how
many pages are near-identical to another page in the same city.
"""
import html
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")
CITIES = ["firenze", "denhaag", "vilnius", "warsaw", "ghent", "bratislava",
          "zagreb", "geneva", "bern", "torino"]


def text_of(raw):
    raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.findall(r"[a-zà-ÿ0-9']+", t.lower())


def shingles(words, k=6):
    return {" ".join(words[i:i + k]) for i in range(max(len(words) - k + 1, 0))}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def git_show(rel):
    r = subprocess.run(["git", "-c", "core.quotepath=off", "show", "HEAD:%s" % rel],
                       cwd=REPO, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def pages(city):
    d = os.path.join(DIST, city)
    out = []
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if n.endswith(".html") and n != "index.html":
            out.append(("dist/%s/%s" % (city, n), p))
        elif os.path.isdir(p) and os.path.isfile(os.path.join(p, "index.html")):
            out.append(("dist/%s/%s/index.html" % (city, n), os.path.join(p, "index.html")))
    return out


def run(city, use_git):
    sh = []
    for rel, path in pages(city):
        raw = git_show(rel) if use_git else open(path, encoding="utf-8", errors="replace").read()
        if raw is None:
            continue
        sh.append((rel, shingles(text_of(raw))))
    near = 0
    worst = 0.0
    for i in range(len(sh)):
        best = 0.0
        for j in range(len(sh)):
            if i == j:
                continue
            best = max(best, jac(sh[i][1], sh[j][1]))
        if best >= 0.80:
            near += 1
        worst = max(worst, best)
    return len(sh), near, worst


print("%-11s %6s   %-22s %-22s" % ("city", "pages", "near-dup at HEAD", "near-dup now"))
tot_before = tot_after = 0
for c in CITIES:
    n1, b, wb = run(c, True)
    n2, a, wa = run(c, False)
    tot_before += b
    tot_after += a
    print("%-11s %6d   %3d  (max %.2f)        %3d  (max %.2f)"
          % (c, n2, b, wb, a, wa))
print("\n%d pages were near-identical to another in their city; now %d."
      % (tot_before, tot_after))
