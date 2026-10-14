"""
Gives every area page something of its own to say.

THE PROBLEM
    170 published pages carried a body byte-identical to another page's, across
    only 13 distinct texts: 36 Florence areas shared one paragraph, 30 in The
    Hague shared another, 19 in Vilnius a third. Another 200 pages ran under
    300 characters. Search Console reports 819 URLs discovered and not crawled,
    and duplicates are the ones a crawler never comes back for.

    The shared paragraph was not junk — it explained, truthfully, that the city
    publishes no crime data below municipality level and that the area-level
    review found nothing specific. That is worth keeping. The fault was that it
    was the WHOLE page, so forty pages were the same page.

WHAT THIS ADDS, AND WHAT IT REFUSES TO ADD
    An opening sentence built from the geometry the site already publishes:
    where the area sits relative to the city's own centre, how big it is, which
    areas it touches, and which of the mapped sights fall inside it. Every one
    of those is measured from the polygons that draw the map, so it is checkable
    against the map on the same page.

    It invents nothing. No character, no atmosphere, no "leafy" or "up and
    coming", no crime claim of any kind — those would need a source, and the
    reason these pages are thin is precisely that there is no source. The
    rating does not move: this adds description, never evidence.

USAGE
    python3 pipeline/expand_thin_texts.py --dry        # show what would change
    python3 pipeline/expand_thin_texts.py --city firenze
    python3 pipeline/expand_thin_texts.py             # all cities
"""
import argparse
import collections
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as BS
import published

ZONE_DIR = os.path.join(HERE, "data_zones")
POI_DIR = os.path.join(HERE, "data_poi")
THIN = 300

COMPASS = ["north", "north-east", "east", "south-east",
           "south", "south-west", "west", "north-west"]


def _centroid(rings):
    r = max(rings, key=len)
    return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))


def _km(a, b, c, d):
    R = 6371.0
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = (math.sin(dp / 2) ** 2 + math.cos(math.radians(a))
         * math.cos(math.radians(c)) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def _bearing(lat1, lon1, lat2, lon2):
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dl))
    return COMPASS[int(((math.degrees(math.atan2(y, x)) + 360) % 360 + 22.5) % 360 // 45)]


def _touches(a, b, tol=0.0012):
    pa = [p for r in a for p in r][::3]
    pb = [p for r in b for p in r][::3]
    for p in pa:
        for q in pb:
            if abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol:
                return True
    return False


def _inside(lat, lon, rings):
    c = False
    for r in rings:
        n = len(r)
        for i in range(n):
            y1, x1 = r[i]
            y2, x2 = r[(i + 1) % n]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                c = not c
    return c


def _size_words(km2):
    """Always a measurement, never a comparison.

    An earlier version returned "one of the smallest areas on this map", which
    does not fit the slot it was dropped into ("covers one of the smallest
    areas on this map 2.8 km west of the centre") and is also a claim about the
    other areas, which the sentence has no business making.
    """
    if km2 < 1.0:
        return "%.1f km\u00b2" % km2
    if km2 < 10.0:
        return "%.1f km\u00b2" % km2
    return "%.0f km\u00b2" % km2


def _list(names):
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


# "Residential Den Haag." opened a paragraph perfectly well and reads as a
# dropped fragment in the middle of one. The land use is worth keeping, so it
# is folded into the geography sentence instead of left dangling after it.
LEAD_FRAGMENT = re.compile(
    r"^(?:Residential\s+[A-Z][\w'\u00c0-\u024f -]{2,20}?"
    r"|A\s+residential\s+(?:district|quarter|area)\s+of\s+[A-Z][\w'\u00c0-\u024f -]{2,20}?)\.\s+",
    re.U)


def strip_lead_fragment(old):
    """(text without the fragment, True if it said the area is residential)."""
    m = LEAD_FRAGMENT.match(old)
    return (old[m.end():], True) if m else (old, False)


def opening(name, f, residential=False):
    """One sentence about the area, every clause measured from its polygon.

    Five shapes, chosen by what is true of the area rather than at random: one
    template repeated forty times down a city would be the duplicate problem
    again in a different costume. An area holding a famous building leads with
    it; one on the city's edge is described from the edge inwards; a central
    one needs no distance at all.

    Each shape is written out in full rather than assembled from slots. Three
    rounds of slot-filling produced "is covers 3 km2", "lies between
    Borgerhout" for a single neighbour, "covers residential of 1.6 km2" and
    "covers one of the smallest areas on this map 2.8 km west of the centre".
    Whole sentences are harder to get wrong.
    """
    d, b = f["km_from_centre"], f["bearing"]
    nb, sights = f["neighbours"], f["sights"]
    size = _size_words(f["area_km2"])
    land = "%s of residential ground" % size if residential else size
    where = ("in the centre of the city" if f["central"]
             else "%.1f km %s of the centre" % (d, b))

    # 1. It holds something people come for. At most three of them: Ghent's
    #    historic core contains thirteen of the mapped sights, and listing all
    #    of them buried the sentence that followed.
    if sights:
        shown = _list(sights[:3])
        more = " among %d mapped sights" % len(sights) if len(sights) > 3 else ""
        verb = "is" if len(sights[:3]) == 1 else "are"
        tail = ", bordering %s." % _list(nb) if nb else "."
        return "%s %s%s inside this area, which lies %s and covers %s%s" % (
            shown, verb, more, where, size, tail)

    # 2. The outer edge of the city, where an area touches almost nothing.
    if len(nb) <= 2 and d > 3.0:
        edge = "On the %sern edge of the city" % b.split("-")[-1]
        if nb:
            return "%s, %.1f km out, %s covers %s and touches only %s." % (
                edge, d, name, land, _list(nb))
        return "%s, %.1f km out, %s covers %s." % (edge, d, name, land)

    # 3. Central: the distance adds nothing.
    if f["central"]:
        if nb:
            return "%s covers %s in the middle of the city, between %s." % (
                name, land, _list(nb))
        return "%s covers %s in the middle of the city." % (name, land)

    # 4. Everywhere else. Position first, then the area: "covers 0.7 km2 2.2 km
    #    south-east of the centre" puts two measurements against each other
    #    with nothing between them, and the reader has to stop and separate
    #    them. The verb agrees with how many neighbours there are.
    lies = "lies %s" % where
    if len(nb) == 1:
        return "%s %s, its only mapped neighbour %s, and covers %s." % (
            name, lies, nb[0], land)
    if len(nb) == 2:
        return "%s %s, between %s, and covers %s." % (
            name, lies, _list(nb), land)
    if nb:
        return "%s %s, bordering %s, and covers %s." % (
            name, lies, _list(nb), land)

    # 5. No measured neighbour: an exclave, or alone in its corner of the map.
    return "%s %s and covers %s, with no other mapped area touching it." % (
        name, lies, land)


def facts_for_city(slug, zones, pois):
    cents = {z["name"]: _centroid(z["coords"]) for z in zones if z.get("coords")}
    if not cents:
        return {}
    las = sorted(c[0] for c in cents.values())
    los = sorted(c[1] for c in cents.values())
    cla, clo = las[len(las) // 2], los[len(los) // 2]
    out = {}
    for z in zones:
        if not z.get("coords"):
            continue
        c = cents[z["name"]]
        d = _km(cla, clo, c[0], c[1])
        nb = [o["name"] for o in zones
              if o["name"] != z["name"] and o.get("coords")
              and _km(c[0], c[1], *cents[o["name"]]) < 3.0
              and _touches(z["coords"], o["coords"])]
        out[z["name"]] = {
            "km_from_centre": round(d, 1),
            "bearing": _bearing(cla, clo, c[0], c[1]),
            "area_km2": sum(BS.ring_area_m2(r) for r in z["coords"]) / 1e6,
            "neighbours": sorted(nb)[:3],
            "sights": [p["name"] for p in pois if _inside(p["lat"], p["lon"], z["coords"])],
            "central": d < 1.0,
        }
    return out


# A body that is this and nothing else says the same thing twice in 305
# characters, and said it on 36 Florence pages. Where a city's shared paragraph
# is on this list the geography replaces it outright; everywhere else the
# geography is added in front and the existing text is left alone, because
# elsewhere it carries real sourced reporting.
REPLACEABLE = (
    "No specific safety concerns found in local press or official sources",
)


def tail_for(old, city_label):
    """The honest sentence that survives the rewrite.

    One per city, not one per page, and deliberately so: the fact it states —
    that no dataset exists below municipality level and the review found
    nothing for this area — really is the same fact for every area in that
    city. Rewording it forty ways to dodge a duplicate check would be gaming
    the check, not fixing the page. What makes the pages different is that each
    now says something true about itself first.
    """
    if any(old.startswith(x) for x in REPLACEABLE):
        return ("The area-level review found no press or official reporting "
                "specific to it, and %s publishes no crime figures below the "
                "municipality, so there is no number to rate it on. The rating "
                "reflects that absence, not a finding of safety."
                % city_label)
    return old


def source_zones():
    """Every zone, read from data_zones — the files this script edits.

    The first version read the BUILT pages instead, which is wrong in a way
    that hides itself: dist/ is committed, so after reverting the sources the
    built pages were still the fixed ones, the duplicate scan came back empty
    and the script reported success having changed nothing. Decide from the
    same files you write to."""
    out = {}
    for fn in sorted(os.listdir(ZONE_DIR)):
        if not fn.endswith(".json"):
            continue
        doc = json.load(io.open(os.path.join(ZONE_DIR, fn), encoding="utf-8"))
        if doc.get("zones"):
            out[fn[:-5]] = doc["zones"]
    return out


def main(only, dry):
    """Everything here reads and writes data_zones. Nothing consults dist/.

    That separation is the whole correctness story: an earlier version decided
    what was duplicated by reading the BUILT pages while editing the sources,
    so once a build had been run the scan came back empty and the script
    reported success having changed nothing. Twice, in two different places.
    """
    stems = source_zones()
    bodies = collections.Counter(
        " ".join((z.get("text") or "").split())
        for zs in stems.values() for z in zs)
    shared = {t for t, n in bodies.items() if n > 1 and t}

    # data_zones holds 110 files: the rated city files, plus *_boundaries.json
    # geometry dumps and cities that were prepared and never published (Sofia,
    # Helsinki). Only the files behind a published map may be touched — reading
    # the whole directory pulled 1,169 "thin" areas out of pages nobody serves.
    slug_for = {}
    for key, slug, _label, _flat in BS.mapped_cities():
        slug_for[BS.POI_FILE_FOR_KEY.get(key, key)] = slug
    live = set(dict(published.published_cities()))
    stems = {k: v for k, v in stems.items() if slug_for.get(k) in live}
    print("%d of the city files in data_zones are behind a published map"
          % len(stems))

    touched = 0
    for stem, zones in sorted(stems.items()):
        slug = slug_for.get(stem, stem)
        if only and only not in (slug, stem):
            continue
        need = {z["name"] for z in zones
                if " ".join((z.get("text") or "").split()) in shared
                or len(" ".join((z.get("text") or "").split())) < THIN}
        if not need:
            continue
        poi_path = os.path.join(POI_DIR, "%s.json" % stem)
        pois = []
        if os.path.isfile(poi_path):
            pois = json.load(io.open(poi_path, encoding="utf-8")).get("pois", [])
        facts = facts_for_city(stem, zones, pois)
        src = os.path.join(ZONE_DIR, "%s.json" % stem)
        doc = json.load(io.open(src, encoding="utf-8"))
        label = (doc.get("label") or stem).split(",")[0]
        n = 0
        for z in doc["zones"]:
            if z["name"] not in need or z["name"] not in facts:
                continue
            old = " ".join((z.get("text") or "").split())
            rest, residential = strip_lead_fragment(old)
            lead = opening(z["name"], facts[z["name"]], residential)
            if old.startswith(lead[:40]):
                continue
            z["text"] = (lead + " " + tail_for(rest, label)).strip()
            n += 1
        touched += n
        print("%-13s %3d of %3d areas rewritten" % (stem, n, len(zones)))
        if not dry and n:
            io.open(src, "w", encoding="utf-8").write(
                json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print("\n%d pages given an opening of their own%s"
          % (touched, " (dry run, nothing written)" if dry else ""))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.city, a.dry))
