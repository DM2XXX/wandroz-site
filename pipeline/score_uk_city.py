"""
Turn a city's raw data.police.uk months into the zone file the site renders.

London has its own borough pages, written before the rest of the site existed.
Every new English city instead produces a standard zone file — the same shape
as Rome's or Berlin's — so it inherits the map, the sights, the evidence line,
the FAQ and the accommodation link without a second renderer to keep in sync.

The scoring is London's, imported rather than restated so the two cannot
drift: the same category weights, the same day/night split, the same
"rate against this city's own average" rule. What differs is the denominator.
London corrects resident population towards a workday estimate; a new city has
no such release, so the rate is per resident and every page says so.

    python3 score_uk_city.py manchester
"""
import collections, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from score_london import (CATEGORY_WEIGHT, DEFAULT_WEIGHT, DAY_CATEGORIES,
                          NIGHT_CATEGORIES, RED_THRESHOLD, GREEN_THRESHOLD)

MONTH_NAME = ["", "January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]


def pretty_month(m):
    y, mo = m.split("-")
    return "%s %s" % (MONTH_NAME[int(mo)], y)


def weighted(counts, categories):
    return sum(n * CATEGORY_WEIGHT.get(c, DEFAULT_WEIGHT)
               for c, n in counts.items() if c in categories)


def load_counts(key):
    """Per-ward, per-month category counts, written by fetch_uk_city.py.

    The scorer reads the aggregate rather than the raw records: it needs a
    count per category, and carrying every incident's street name in the
    repository to recompute one is how a repo ends up 100 MB heavier per city.
    """
    path = os.path.join(REPO, "data", "counts_%s.json" % key)
    with open(path) as f:
        return json.load(f)["counts"]


def load_zone(counts, slug):
    per = counts.get(slug) or {}
    months = sorted(per, reverse=True)
    return months, [collections.Counter(per[m]) for m in months]


def tone(rate, avg):
    if not avg:
        return "grey"
    if rate >= RED_THRESHOLD * avg:
        return "red"
    if rate <= GREEN_THRESHOLD * avg:
        return "green"
    return "yellow"


def describe(z, rank, total, force, window, top_day, top_night, city):
    cats = lambda pairs: ", ".join("%s (%d)" % (c.replace("-", " "), n) for c, n in pairs)
    return (
        "%s recorded %s crimes inside this ward's official boundary over %s — %s per 1,000 "
        "residents, the %s highest rate of %s's %d wards. The daytime score here is "
        "driven by %s; the evening/night score by %s. Rated against the average of the city's "
        "own wards, never against another city."
        % (force, "{:,}".format(z["total"]), window, z["rate_all"],
           ordinal(rank), city, total, cats(top_day) or "no recorded incidents in those categories",
           cats(top_night) or "no recorded incidents in those categories")
    )


def ordinal(n):
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def main(key, label, force, centre_zoom=11):
    src = os.path.join(HERE, "data_zones", "%s_boundaries.json" % key)
    doc = json.load(open(src))
    counts = load_counts(key)

    rows = []
    all_months = set()
    for z in doc["zones"]:
        months, per_month = load_zone(counts, z["slug"])
        if not months:
            print("SALTATA (nessun dato):", z["name"]); continue
        all_months.update(months)
        avg = collections.Counter()
        for month_counts in per_month:          # not `counts`: that name holds
            for c, n in month_counts.items():   # the whole city's table above
                avg[c] += n / len(per_month)
        pop = z.get("population") or 0
        if not pop:
            print("SALTATA (nessuna popolazione):", z["name"]); continue
        rows.append({
            "zone": z, "months": months, "avg": avg,
            "day_rate": round(weighted(avg, DAY_CATEGORIES) / pop * 1000, 4),
            "night_rate": round(weighted(avg, NIGHT_CATEGORIES) / pop * 1000, 4),
            "rate_all": round(sum(avg.values()) / pop * 1000, 1),
            "total": int(round(sum(avg.values()) * len(per_month))),
        })

    day_avg = sum(r["day_rate"] for r in rows) / len(rows)
    night_avg = sum(r["night_rate"] for r in rows) / len(rows)
    window = "the %d months to %s" % (len(sorted(all_months)), pretty_month(max(all_months)))
    by_rate = sorted(rows, key=lambda r: -r["rate_all"])
    rank_of = {id(r): i + 1 for i, r in enumerate(by_rate)}

    zones = []
    for r in rows:
        z = r["zone"]
        top_day = [(c, int(round(n))) for c, n in r["avg"].most_common() if c in DAY_CATEGORIES][:3]
        top_night = [(c, int(round(n))) for c, n in r["avg"].most_common() if c in NIGHT_CATEGORIES][:3]
        zones.append({
            "name": z["name"], "slug": z["slug"],
            "day": tone(r["day_rate"], day_avg), "night": tone(r["night_rate"], night_avg),
            "text": describe({"total": r["total"], "rate_all": r["rate_all"]},
                             rank_of[id(r)], len(rows), force, window, top_day, top_night,
                             label.split(",")[0]),
            # Ward names are not Booking destinations. Three were opened to
            # check: "Ladywood, Birmingham" redirected to Booking's homepage,
            # "Headingley, Leeds" resolved to a single hotel called Roomzzz
            # Leeds Headingley, and only "Clifton Down, Bristol" landed
            # somewhere real (a station radius). London's boroughs work because
            # they are places Booking indexes; a ward is not. So these cities
            # search the city, and the page says that is what the link does.
            "query": "%s, United Kingdom" % label.split(",")[0],
            "booking_scope": "city",
            "evidence": "documented",
            "coords": z["coords"],
        })
    zones.sort(key=lambda z: z["name"])
    out = {"label": label, "center": doc["center"], "zoom": doc.get("zoom", centre_zoom),
           "dataNote": "", "zones": zones}
    dest = os.path.join(HERE, "data_zones", "%s.json" % key)
    json.dump(out, open(dest, "w"), ensure_ascii=False)
    tones = collections.Counter((z["day"], z["night"]) for z in zones)
    print("%s: %d ward, finestra %s" % (key, len(zones), window))
    print("  toni giorno/notte:", dict(tones))
    print("  scritto", dest, "(%.0f KB)" % (os.path.getsize(dest) / 1024))


# key -> (label, the force that recorded the data)
CITIES = {
    "birmingham": ("Birmingham, United Kingdom", "West Midlands Police"),
    "leeds": ("Leeds, United Kingdom", "West Yorkshire Police"),
    "liverpool": ("Liverpool, United Kingdom", "Merseyside Police"),
    "bristol": ("Bristol, United Kingdom", "Avon and Somerset Constabulary"),
    "newcastle": ("Newcastle upon Tyne, United Kingdom", "Northumbria Police"),
    "sheffield": ("Sheffield, United Kingdom", "South Yorkshire Police"),
    "nottingham": ("Nottingham, United Kingdom", "Nottinghamshire Police"),
    "cardiff": ("Cardiff, United Kingdom", "South Wales Police"),
    "leicester": ("Leicester, United Kingdom", "Leicestershire Police"),
    "liverpool": ("Liverpool, United Kingdom", "Merseyside Police"),
    "brighton": ("Brighton and Hove, United Kingdom", "Sussex Police"),
    "york": ("York, United Kingdom", "North Yorkshire Police"),
    "oxford": ("Oxford, United Kingdom", "Thames Valley Police"),
    "cambridge": ("Cambridge, United Kingdom", "Cambridgeshire Constabulary"),
    "bath": ("Bath, United Kingdom", "Avon and Somerset Constabulary"),
    "coventry": ("Coventry, United Kingdom", "West Midlands Police"),
    "southampton": ("Southampton, United Kingdom", "Hampshire Constabulary"),
    "portsmouth": ("Portsmouth, United Kingdom", "Hampshire Constabulary"),
    "plymouth": ("Plymouth, United Kingdom", "Devon & Cornwall Police"),
    "derby": ("Derby, United Kingdom", "Derbyshire Constabulary"),
    "norwich": ("Norwich, United Kingdom", "Norfolk Constabulary"),
}

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "birmingham"
    label, force = CITIES[key]
    main(key, label, force)
