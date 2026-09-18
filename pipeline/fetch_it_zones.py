"""
Official neighbourhood boundaries for Italian cities, from OpenStreetMap.

WHY OSM AND NOT THE CITY'S OWN PORTAL
    For the UK there is one national geography (ONS wards) and one endpoint.
    Italy has none: every comune publishes its quartieri, circoscrizioni,
    municipi or rioni on its own portal, in its own format, when it publishes
    them at all — which is how the first attempt at Florence ended up matching
    a library, a stadium and a charterhouse through a geocoder. OSM already
    holds these as administrative relations at level 9 or 10, tagged by people
    who live there, so one shape of query covers every city.

    This is boundaries only. It says where an area is, never how safe it is:
    the rating is a separate, sourced judgement per area (see the methodology
    page, class B), and this script deliberately writes every zone with no
    tone and no text so nothing can ship rated by accident.

WHY THE OSM API AND NOT OVERPASS FOR THE GEOMETRY
    Overpass answers `out tags` fine and then rate-limits `out geom` with an
    HTML error page — not JSON, not a status code you can branch on. The plain
    OSM API serves one relation at a time and does not, so discovery goes
    through Overpass and geometry through api.openstreetmap.org.

    python3 fetch_it_zones.py bologna "Bologna" "Bologna, Italy"
"""
import json, os, re, subprocess, sys, time, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "wandroz-pipeline/1.0 (+https://www.wandroz.com)"
OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_API = "https://api.openstreetmap.org/api/0.6/relation/%d/full.json"

# curl, not urllib: the same reason the UK fetcher uses it — macOS system
# Python is linked against LibreSSL and cannot complete the handshake with
# some of these hosts.
def curl(args, stdin=None):
    p = subprocess.run(["curl", "-s", "--max-time", "120", "-A", UA] + args,
                       input=stdin, capture_output=True, text=True)
    return p.stdout


# "Quartiere 3", "Municipio VII", "III Circoscrizione" — an administrative
# label, not a place. Florence tags those as `name` and puts the real name in
# `alt_name`; Verona, Genoa, Trieste and Parma do exactly the opposite. So the
# rule cannot be "prefer alt_name" — it has to be "prefer whichever one is not
# just a number", which is what a reader and a Booking query both need.
NUMBERED = re.compile(
    r"^\s*(?:(?:quartiere|circoscrizione|municipio|municipalita|municipalità|zona|distretto|"
    r"unita|unità)\s+)?[IVXLC0-9]+(?:\s*(?:quartiere|circoscrizione|municipio|municipalita|"
    r"municipalità|zona|distretto))?\s*$", re.I)


# OSM wraps the place name in the administrative word for the kind of unit:
# "Gradska četvrt Maksimir", "Senamiesčio seniūnija", "Bratislava – mestská
# časť Staré Mesto". The wrapper is the same on every row, so it carries no
# information and costs width on a map label and precision in a Booking query.
# What a reader recognises is Maksimir, Senamiestis, Staré Mesto.
BOILERPLATE_PREFIX = ("district ", "gradska četvrt ", "gradska cetvrt ", "mestská časť ", "mestska cast ",
                      "stadtteil ", "distrito de ", "quartiere ", "circoscrizione ",
                      "municipio ", "dzielnica ", "rajon ", "kerület ")
BOILERPLATE_SUFFIX = (" seniūnija", " seniunija", " apkaime", " kerület", " kaupunginosa")


def clean_name(name):
    n = (name or "").strip()
    # "Bratislava – mestská časť Staré Mesto": drop the city prefix too.
    for sep in (" – ", " - ", " — "):
        low = n.lower()
        for pre in BOILERPLATE_PREFIX:
            i = low.find(sep + pre)
            if i != -1:
                return n[i + len(sep) + len(pre):].strip()
    low = n.lower()
    for pre in BOILERPLATE_PREFIX:
        if low.startswith(pre):
            return n[len(pre):].strip()
    for suf in BOILERPLATE_SUFFIX:
        if low.endswith(suf):
            return n[: -len(suf)].strip()
    return n


def best_name(tags):
    for key in ("alt_name", "official_name", "name"):
        v = (tags.get(key) or "").strip()
        if v and not NUMBERED.match(v):
            return v
    return (tags.get("name") or "").strip()


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "zona"


def _most_specific_parent(city_osm_name, tries=4):
    """Relation id of the administrative area named `city_osm_name`, most specific first."""
    q = ('[out:json][timeout:120];'
         'rel["name"="%s"]["boundary"="administrative"]["admin_level"];'
         'out tags;' % city_osm_name)
    for _ in range(tries):
        try:
            els = json.loads(curl(["--data-urlencode", "data@-", OVERPASS], stdin=q)).get("elements", [])
        except ValueError:
            time.sleep(20)
            continue
        if not els:
            return None
        # The window is 4 to 8, and both ends were learned the hard way.
        # Above 8 is a province or a region, and asking it for districts
        # returns other towns — that is how Antwerpen first came back as the
        # 148 municipalities of its province. Below 4 there is nothing but
        # countries. And the cap has to be 8, not 9: Antwerp also has a level-9
        # DISTRICT called Antwerpen, and picking that gives 31 areas of the
        # city centre instead of the 9 districts of the city. Bucharest at 4
        # and a Danish kommune at 7 are the legitimate coarse cases.
        cands = [e for e in els if (e["tags"].get("admin_level") or "").isdigit()
                 and 4 <= int(e["tags"]["admin_level"]) <= 8]
        if not cands:
            return None
        best = max(cands, key=lambda e: int(e["tags"]["admin_level"]))
        print("   parent: relation %d at admin_level %s" % (best["id"], best["tags"]["admin_level"]))
        return best["id"]
    raise SystemExit("Overpass kept returning an error page for %s" % city_osm_name)


def discover(city_osm_name, tries=4, want_level=None):
    """Relation ids of the city's administrative subdivisions.

    The parent is matched by name at ANY admin level, not at 8. A comune is 8
    in Italy, a kommune is 7 in Denmark and Bucharest is 4, so pinning the
    level made this answer "no subdivisions" for cities that plainly have
    districts. What identifies the parent is its name, not the number a
    national convention gives it.
    """
    # Two steps, because one was wrong. Matching the parent by name alone also
    # matches anything else with that name — and a province is very often named
    # after its capital. Asked for Antwerpen in one query, this returned the
    # 148 municipalities of the PROVINCE of Antwerp as if they were districts
    # of the city. So: find the candidates, keep the most specific one (the
    # highest admin_level, which is the city rather than the province or the
    # arrondissement above it), and only then look inside that.
    parent = _most_specific_parent(city_osm_name, tries)
    if parent is None:
        return []
    q = ('[out:json][timeout:180];'
         'rel(id:%d);map_to_area->.a;'
         'relation(area.a)["boundary"="administrative"]["admin_level"~"^(9|10|11)$"];'
         'out tags;' % parent)
    for attempt in range(tries):
        body = curl(["--data-urlencode", "data@-", OVERPASS], stdin=q)
        try:
            els = json.loads(body).get("elements", [])
        except ValueError:
            time.sleep(20)      # an HTML error page: rate limited, wait it out
            continue
        if not els:
            return []
        by_level = {}
        for e in els:
            by_level.setdefault(e["tags"].get("admin_level"), []).append(e)
        if want_level:
            return by_level.get(want_level, [])
        # Otherwise prefer the coarser level when it is a real subdivision.
        # Helsinki is why the caller can override: it has 8 areas at level 9,
        # 59 at 10 and 118 at 11, and the 8 are so broad that one of them is
        # "the southern district" covering the entire centre.
        level = "9" if len(by_level.get("9", [])) >= 6 else max(by_level, key=lambda k: len(by_level[k]))
        return by_level[level]
    raise SystemExit("Overpass kept returning an error page for %s" % city_osm_name)


def rings_from_relation(doc, rel_id):
    """Stitch the relation's outer ways into closed rings."""
    nodes, ways, rel = {}, {}, None
    for e in doc["elements"]:
        if e["type"] == "node":
            nodes[e["id"]] = (round(e["lat"], 5), round(e["lon"], 5))
        elif e["type"] == "way":
            ways[e["id"]] = e["nodes"]
        elif e["type"] == "relation" and e["id"] == rel_id:
            rel = e
    if rel is None:
        return [], {}
    segs = [list(ways[m["ref"]]) for m in rel["members"]
            if m["type"] == "way" and m.get("role") in ("outer", "") and m["ref"] in ways]
    rings, current = [], []
    while segs:
        if not current:
            current = segs.pop(0)
            continue
        joined = False
        for i, s in enumerate(segs):
            if s[0] == current[-1]:
                current += s[1:]; segs.pop(i); joined = True; break
            if s[-1] == current[-1]:
                current += list(reversed(s))[1:]; segs.pop(i); joined = True; break
            if s[-1] == current[0]:
                current = s[:-1] + current; segs.pop(i); joined = True; break
            if s[0] == current[0]:
                current = list(reversed(s))[:-1] + current; segs.pop(i); joined = True; break
        if not joined or current[0] == current[-1]:
            rings.append(current); current = []
    if current:
        rings.append(current)
    out = []
    for r in rings:
        pts = [nodes[n] for n in r if n in nodes]
        # Three points is a sliver, not an area — a relation whose ways did not
        # stitch produces these, and they must not reach a map as a polygon.
        if len(pts) >= 4:
            out.append(pts)
    return out, rel["tags"]


def main(key, city_osm_name, label, want_level=None):
    found = discover(city_osm_name, want_level=want_level)
    if not found:
        raise SystemExit("%s: no administrative subdivisions in OSM — needs another source" % key)
    print("%s: %d areas at admin_level %s" % (key, len(found), found[0]["tags"].get("admin_level")))

    zones, lats, lons = [], [], []
    for e in found:
        doc = json.loads(curl([OSM_API % e["id"]]))
        rings, tags = rings_from_relation(doc, e["id"])
        if not rings:
            print("   SKIP %s (relation %d did not close)" % (tags.get("name"), e["id"]))
            continue
        name = clean_name(best_name(tags))
        if NUMBERED.match(name):
            print("   NOTE %s has only a numbered label in OSM" % name)
        for r in rings:
            lats += [p[0] for p in r]; lons += [p[1] for p in r]
        zones.append({
            "name": name,
            "slug": slugify(name),
            "osm_relation": e["id"],
            "day": "grey", "night": "grey",     # unrated on purpose — see docstring
            "text": "",
            "query": "%s, %s" % (name, label),
            "booking_scope": "area",
            "coords": rings,
        })
        print("   %-46s %d ring(s), %d pts" % (name, len(rings), sum(len(r) for r in rings)))
        time.sleep(1)

    if not zones:
        raise SystemExit("%s: nothing usable" % key)
    out = {
        "label": label,
        "center": [round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5)],
        "zoom": 12,
        "dataNote": "",
        "source": "OpenStreetMap administrative relations (ODbL)",
        "zones": zones,
    }
    path = os.path.join(HERE, "data_zones", "%s_boundaries.json" % key)
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print("   wrote %s (%d zones, %d KB)" % (path, len(zones), os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         sys.argv[4] if len(sys.argv) > 4 else None)
