"""
Do the numbers on the page survive being recalculated?

WHY THIS EXISTS
    Every other check on this site asks whether the site agrees with itself:
    does the map match the page, does the tag match the tier, does the text
    contradict the colour. None of them recomputes anything. A page that says
    "1,763 crimes across 19,485 residents — a rate of 9,048 per 100,000" is
    making three claims and an arithmetic promise, and until now nothing
    checked the promise.

    That matters because the figures reach the page by several routes. Some are
    computed by a scorer and formatted into a sentence. Some were typed into a
    zone text by hand — every figure in Zurich's rewritten area texts was, and
    they will not move when the data is rescored. A hand-typed 6.1 that became
    a 5.8 in the source is invisible to every other gate.

WHAT IT RECOMPUTES
    1. RATE      the published per-100,000 rate against its own published
                 numerator and denominator
    2. RATIO     the published "x times the city average" against the published
                 rate and the city average the same page states
    3. PROSE     figures typed into an area's text against the scored data
                 behind that area, where the two can be tied together
    4. TABLE     the hub comparison table's rating for an area against the
                 rating the map and the area's own page give it
    5. CARDS     a recommendation card's stated rating against that area's
                 actual rating
    6. PERIOD    the data window a city's hub claims against the window its
                 area pages claim

    Tolerances are deliberately loose — published figures are rounded, and the
    point is to catch a wrong number, not a rounding difference.

USAGE
    python3 pipeline/crosscheck.py
    python3 pipeline/crosscheck.py --city amsterdam
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import published

DIST = os.path.join(os.path.dirname(HERE), "dist")

# "recorded 1,763 registered crimes here in 2025 across a population of 19,485
#  residents — a rate of 9,048 crimes per 100,000 residents"
RATE_CLAIM = re.compile(
    r"recorded ([\d,]+) (?:registered )?(?:crimes|incidents|offences)[^.]{0,80}?"
    r"population of ([\d,]+) residents[^.]{0,40}?rate of ([\d,]+) "
    r"(?:crimes|incidents|offences) per 100,000", re.I)
RATIO_CLAIM = re.compile(r"roughly ([\d.]+)× the citywide", re.I)
AVG_IN_TEXT = re.compile(r"city average of ([\d.,]+)", re.I)


def num(s):
    return float(str(s).replace(",", ""))


def check_rates(cities):
    """The published rate against the published count and population."""
    bad, seen = [], 0
    for slug, zones in cities:
        for z in zones:
            m = RATE_CLAIM.search(z.get("text") or "")
            if not m:
                continue
            seen += 1
            n, pop, rate = num(m.group(1)), num(m.group(2)), num(m.group(3))
            if pop <= 0:
                bad.append((slug, z["name"], "population of zero in the text"))
                continue
            calc = n / pop * 100000.0
            # 1.5% covers the provider's own rounding and ours.
            if abs(calc - rate) / max(rate, 1) > 0.015:
                bad.append((slug, z["name"],
                            "says %s per 100,000, but %s ÷ %s × 100,000 = %s"
                            % (m.group(3), m.group(1), m.group(2), "{:,.0f}".format(calc))))
    return seen, bad


def check_ratios(cities):
    """The published multiple against the published rate and the city average.

    The city average is not stated on the area page, so it is derived from the
    city's own set: the mean of its areas' published rates, which is what the
    generator compares against."""
    bad, seen = [], 0
    for slug, zones in cities:
        rates, pairs = [], []
        for z in zones:
            m = RATE_CLAIM.search(z.get("text") or "")
            r = RATIO_CLAIM.search(z.get("text") or "")
            if not m:
                continue
            rates.append(num(m.group(3)))
            if r:
                pairs.append((z["name"], num(m.group(3)), num(r.group(1))))
        if len(rates) < 5 or not pairs:
            continue
        avg = sum(rates) / len(rates)
        for name, rate, claimed in pairs:
            seen += 1
            calc = rate / avg
            # The multiples are printed to one decimal, so 0.15 of a multiple
            # is generous; anything past it is a different number, not rounding.
            if abs(calc - claimed) > 0.15 and abs(calc - claimed) / max(claimed, .1) > 0.12:
                bad.append((slug, name,
                            "says %.1f× the city average; its own rate %s against the "
                            "city's %s gives %.2f×" % (claimed, "{:,.0f}".format(rate),
                                                       "{:,.0f}".format(avg), calc)))
    return seen, bad


def check_zurich_prose():
    """Figures typed by hand into Zurich's area texts against the scored file.

    These were written into the text, not formatted from the data, so a
    rescore moves the data and leaves the sentence behind."""
    bad = []
    path = os.path.join(os.path.dirname(HERE), "data", "scores", "zurich_burglary.json")
    src = os.path.join(HERE, "data_zones", "zurigo.json")
    if not (os.path.isfile(path) and os.path.isfile(src)):
        return 0, []
    scored = json.load(open(path))
    avg = scored.get("city_average_rate_per_1000")
    try:
        import build_site as BS
        q2k = BS.QUARTIER_TO_KREIS
    except Exception:
        return 0, []
    zones = json.load(open(src, encoding="utf-8"))["zones"]
    seen = 0
    for z in zones:
        text = z.get("text") or ""
        k = q2k.get(z["name"])
        rec = scored.get("kreise", {}).get("kreis_%s" % k) or {}
        real = rec.get("rate_avg_per_1000")
        for m in re.finditer(r"(\d+(?:\.\d+)?) break-ins a year per 1,000", text):
            seen += 1
            said = float(m.group(1))
            if real is None or abs(said - real) > 0.15:
                bad.append(("zurigo", z["name"],
                            "text says %s break-ins per 1,000; the scored figure for "
                            "%s is %s" % (said, rec.get("kreis_label", "its district"), real)))
        for m in re.finditer(r"city average of (\d+(?:\.\d+)?)", text):
            seen += 1
            said = float(m.group(1))
            if avg is None or abs(said - avg) > 0.15:
                bad.append(("zurigo", z["name"],
                            "text says a city average of %s; the scored average is %s"
                            % (said, avg)))
    return seen, bad


# The published figure is a MONTHLY AVERAGE per 1,000 residents, while the
# count beside it is the whole window's total. Comparing them directly makes
# every UK ward look wrong by exactly the number of months — which is how this
# check first reported 500 failures that were its own misreading, and how it
# then found that the page never said "a month" either.
UK_CLAIM = re.compile(
    r"recorded ([\d,]+) crimes inside this ward's official boundary over the (\d+) months?"
    r"[^.]{0,60}?— an average of ([\d.]+) per 1,000 residents a month", re.I)


def check_uk_rates(cities):
    """The UK per-1,000 rate against the ward population the boundary file holds.

    500 areas across 20 cities, and the largest block the per-100,000 check
    could not see because it is phrased differently and its denominator lives
    in a separate file rather than in the sentence."""
    bad, seen = [], 0
    for slug, zones in cities:
        bpath = os.path.join(HERE, "data_zones", "%s_boundaries.json" % slug)
        if not os.path.isfile(bpath):
            continue
        raw = json.load(open(bpath, encoding="utf-8"))
        pops = {z["name"]: z.get("population")
                for z in (raw.get("zones") or raw) if isinstance(z, dict)}
        for z in zones:
            m = UK_CLAIM.search(z.get("text") or "")
            pop = pops.get(z["name"])
            if not m or not pop:
                continue
            seen += 1
            n, months, rate = num(m.group(1)), max(num(m.group(2)), 1), num(m.group(3))
            calc = n / months / pop * 1000.0
            # Published to one decimal, so 0.1 is rounding; 0.25 is a wrong number.
            if abs(calc - rate) > 0.25:
                bad.append((slug, z["name"],
                            "says %s per 1,000 a month, but %s crimes over %d months "
                            "÷ %s residents = %.1f"
                            % (m.group(3), m.group(1), months, "{:,}".format(pop), calc)))
    return seen, bad


def check_hub_table(cities):
    """The hub table's badge for an area against the map's rating for it."""
    bad, seen = [], 0
    for slug, zones in cities:
        hub = os.path.join(DIST, slug, "index.html")
        if not os.path.isfile(hub):
            continue
        html = open(hub, encoding="utf-8", errors="replace").read()
        body = html.split("<table", 1)[-1].split("</table>", 1)[0] if "<table" in html else ""
        if not body:
            continue
        by_name = {z["name"]: z for z in zones}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            m = re.search(r">([^<>]{2,60})</a>", row)
            if not m or m.group(1).strip() not in by_name:
                continue
            name = m.group(1).strip()
            tones = re.findall(r'class="badge (green|yellow|red|grey)"', row)
            if not tones:
                continue
            seen += 1
            if tones[0] != by_name[name].get("day"):
                bad.append((slug, name, "table shows %s by day, map shows %s"
                            % (tones[0], by_name[name].get("day"))))
    return seen, bad


def check_cards(cities):
    """A recommendation card names an area and shows two badges. Both must
    match that area's actual rating."""
    bad, seen = [], 0
    for slug, zones in cities:
        hub = os.path.join(DIST, slug, "index.html")
        if not os.path.isfile(hub):
            continue
        html = open(hub, encoding="utf-8", errors="replace").read()
        by_name = {z["name"]: z for z in zones}
        # Cards are <div class="hub-card" data-zone="slug">, not <article>, and
        # the name sits in <span class="nm">. The first version of this matched
        # nothing and reported OK on zero cards, which is worse than failing.
        by_slug = {z.get("slug"): z for z in zones if z.get("slug")}
        for card in re.findall(r'<div class="hub-card"[^>]*>.*?(?=<div class="hub-card"|</div>\s*</div>)',
                               html, re.S):
            ms = re.search(r'data-zone="([^"]+)"', card)
            mn = re.search(r'<span class="nm">(?:<a[^>]*>)?([^<]+)', card)
            z = (by_slug.get(ms.group(1)) if ms else None) or \
                (by_name.get(mn.group(1).strip()) if mn else None)
            if not z:
                continue
            name = z["name"]
            tones = re.findall(r'class="badge (green|yellow|red|grey)"', card)
            if len(tones) < 2:
                continue
            seen += 1
            if tones[0] != z.get("day") or tones[1] != z.get("night"):
                bad.append((slug, name, "card shows %s/%s, the area is %s/%s"
                            % (tones[0], tones[1], z.get("day"), z.get("night"))))
    return seen, bad


def check_periods():
    """A city's hub and its area pages must name the same data window."""
    bad, seen = [], 0
    win = re.compile(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
                     r"\s*[–-]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4})")
    for slug in sorted(os.listdir(DIST)):
        hub = os.path.join(DIST, slug, "index.html")
        if not os.path.isfile(hub):
            continue
        hw = set(win.findall(open(hub, encoding="utf-8", errors="replace").read()))
        if not hw:
            continue
        pages = [f for f in os.listdir(os.path.join(DIST, slug))
                 if f.endswith(".html") and f != "index.html"][:40]
        for f in pages:
            pw = set(win.findall(open(os.path.join(DIST, slug, f),
                                      encoding="utf-8", errors="replace").read()))
            if not pw:
                continue
            seen += 1
            if not (hw & pw):
                bad.append((slug, f, "hub says %s, page says %s"
                            % (", ".join(sorted(hw)), ", ".join(sorted(pw)))))
                break
    return seen, bad


def main(only):
    cities = [(s, z) for s, z in published.published_cities()
              if not only or s == only]
    blocks = [
        ("RATE — published rate vs its own count and population", check_rates(cities)),
        ("RATIO — published multiple vs the city's own average", check_ratios(cities)),
        ("UK RATE — per-1,000 rate vs the ward's population", check_uk_rates(cities)),
        ("PROSE — hand-typed Zurich figures vs the scored data",
         check_zurich_prose() if not only or only == "zurigo" else (0, [])),
        ("TABLE — hub table rating vs map rating", check_hub_table(cities)),
        ("CARDS — recommendation badges vs the area's rating", check_cards(cities)),
        ("PERIOD — hub window vs area-page window", check_periods() if not only else (0, [])),
    ]
    total = 0
    for title, (seen, bad) in blocks:
        print("%-56s %5d checked  %s" % (title, seen, "OK" if not bad else "%d WRONG" % len(bad)))
        for slug, name, why in bad[:6]:
            print("      %-12s %-28s %s" % (slug, name[:28], why))
        if len(bad) > 6:
            print("      ... and %d more" % (len(bad) - 6))
        total += len(bad)
    print()
    print("recomputed claims that do not survive: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    a = ap.parse_args()
    sys.exit(main(a.city))
