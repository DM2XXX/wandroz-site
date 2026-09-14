"""
Sights for a city: the well-known ones found by ranking, the rest named by hand.

Two passes, because neither alone is right. Ranking Wikidata by sitelink count
finds the cathedral and the museum and misses every place a resident would send
you after dark — that is how twenty-five cities ended up with a "Nightlife"
filter containing nothing. Naming everything by hand finds those and misses the
obvious. So: a proximity query for what is notable, a curated list for what the
categories promise, and the same two guards on both — nothing beyond 12 km from
the centre, nothing within 60 m of a pin already placed.

    python3 build_city_pois.py birmingham
"""
import json, math, os, subprocess, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
POI_DIR = os.path.join(HERE, "data_poi")
UA = "WandrozPOI/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"
WDQS = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"

CAT_TYPE = {"art": "LANDMARK", "view": "VIEWPOINT", "green": "PARK",
            "square": "AREA", "food": "MARKET", "night": "AREA"}

CITIES = {
    "birmingham": {
        "centre": (-1.8904, 52.4862), "lang": "en",
        "min_sitelinks": 12,
        "curated": [
            ("Bullring, Birmingham", "square", "AREA"),
            ("Selfridges Building, Birmingham", "art", "LANDMARK"),
            ("St Philip's Cathedral, Birmingham", "art", "LANDMARK"),
            ("Symphony Hall, Birmingham", "art", "LANDMARK"),
            ("Thinktank, Birmingham Science Museum", "art", "MUSEUM"),
            ("Cadbury World", "art", "MUSEUM"),
            ("Ikon Gallery", "art", "MUSEUM"),
            ("Barber Institute of Fine Arts", "art", "MUSEUM"),
            ("Soho House, Birmingham", "art", "MUSEUM"),
            ("Sarehole Mill", "art", "MUSEUM"),
            ("Winterbourne House and Garden", "green", "PARK"),
            ("Lickey Hills", "view", "VIEWPOINT"),
            ("Chinese Quarter, Birmingham", "food", "AREA"),
            ("Villa Park", "art", "LANDMARK"),
            ("Jewellery Quarter", "square", "AREA"),
            ("Digbeth", "night", "AREA"),
            ("Broad Street, Birmingham", "night", "AREA"),
            ("Brindleyplace", "square", "AREA"),
            ("Moseley", "night", "AREA"),
            ("Birmingham Museum and Art Gallery", "art", "MUSEUM"),
            ("Library of Birmingham", "art", "LANDMARK"),
            ("Cannon Hill Park", "green", "PARK"),
            ("Sutton Park", "green", "PARK"),
            ("Birmingham Back to Backs", "art", "MUSEUM"),
            ("Aston Hall", "art", "LANDMARK"),
            ("Gas Street Basin", "square", "AREA"),
            ("Edgbaston Cricket Ground", "art", "LANDMARK"),
            ("Custard Factory", "night", "AREA"),
            ("Birmingham Botanical Gardens", "green", "PARK"),
        ],
    },
    "leeds": {
        "centre": (-1.5491, 53.8008), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Leeds Kirkgate Market", "food", "MARKET"),
            ("Leeds Corn Exchange", "square", "AREA"),
            ("Briggate", "square", "AREA"),
            ("Leeds Minster", "art", "LANDMARK"),
            ("Roundhay Park", "green", "PARK"),
            ("Kirkstall Abbey", "art", "LANDMARK"),
            ("Leeds Art Gallery", "art", "MUSEUM"),
            ("Royal Armouries Museum", "art", "MUSEUM"),
            ("Call Lane", "night", "AREA"),
            
            ("Headingley", "night", "AREA"),
            ("Leeds Town Hall", "art", "LANDMARK"),
            ("Victoria Quarter", "square", "AREA"),
            ("Temple Newsam", "green", "PARK"),
            ("Leeds Dock", "square", "AREA"),
        ],
    },
    "bristol": {
        "centre": (-2.5879, 51.4545), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Clifton Suspension Bridge", "view", "VIEWPOINT"),
            ("SS Great Britain", "art", "MUSEUM"),
            ("Bristol Harbour", "square", "AREA"),
            ("St Nicholas Market", "food", "MARKET"),
            ("Clifton, Bristol", "square", "AREA"),
            ("Stokes Croft", "night", "AREA"),
            ("King Street, Bristol", "night", "AREA"),
            ("Ashton Court", "green", "PARK"),
            ("Brandon Hill", "view", "VIEWPOINT"),
            ("M Shed", "art", "MUSEUM"),
            ("Bristol Museum and Art Gallery", "art", "MUSEUM"),
            ("Bristol Cathedral", "art", "LANDMARK"),
            ("Gloucester Road, Bristol", "square", "AREA"),
            ("Queen Square, Bristol", "square", "AREA"),
        ],
    },
}


def http(url, timeout=120):
    res = subprocess.run(["curl", "-sS", "--max-time", str(timeout), "-A", UA, url],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200])
    return json.loads(res.stdout)


def km(a, b, c, d):
    dy = (a - c) * 111.32
    dx = (b - d) * 111.32 * math.cos(math.radians((a + c) / 2))
    return math.hypot(dx, dy)


def notable(lon, lat, min_sitelinks, radius=6):
    q = """
SELECT ?item ?itemLabel ?sitelinks ?lat ?lon WHERE {
  SERVICE wikibase:around {
    ?item wdt:P625 ?loc .
    bd:serviceParam wikibase:center "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "%d" .
  }
  ?item wikibase:sitelinks ?sitelinks . FILTER(?sitelinks >= %d)
  ?item p:P625/psv:P625 ?c . ?c wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q3957 }      # not a town
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q515 }       # not a city
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q548662 }    # not a civil parish
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q55488 }     # not a railway station
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q1248784 }   # not an airport
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 60""" % (lon, lat, radius, min_sitelinks)
    url = WDQS + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    rows = http(url, timeout=180)["results"]["bindings"]
    out = []
    for b in rows:
        out.append({"qid": b["item"]["value"].rsplit("/", 1)[1],
                    "name": b["itemLabel"]["value"],
                    "sitelinks": int(b["sitelinks"]["value"]),
                    "lat": float(b["lat"]["value"]), "lon": float(b["lon"]["value"])})
    return out


def resolve(name, lang, lon0, lat0):
    u = API + "?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": name,
        "language": lang, "uselang": lang, "format": "json", "limit": 8, "type": "item"})
    ids = [h["id"] for h in http(u, timeout=60).get("search", [])]
    if not ids:
        return None
    u2 = API + "?" + urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids),
        "props": "labels|claims|sitelinks", "languages": "en", "format": "json"})
    ents = http(u2, timeout=60).get("entities", {})
    for qid in ids:
        e = ents.get(qid, {})
        cl = e.get("claims", {}).get("P625")
        if not cl:
            continue
        v = cl[0]["mainsnak"].get("datavalue", {}).get("value", {})
        lat, lon = v.get("latitude"), v.get("longitude")
        if lat is None or km(lat, lon, lat0, lon0) > 12:
            continue
        return {"qid": qid, "lat": lat, "lon": lon,
                "name": (e.get("labels", {}).get("en") or {}).get("value", name),
                "sitelinks": len(e.get("sitelinks", {}))}
    return None


def main(key):
    cfg = CITIES[key]
    lon0, lat0 = cfg["centre"]
    picked = []

    def add(entry, cat, ptype, why):
        d = km(entry["lat"], entry["lon"], lat0, lon0)
        if d > 12:
            print("  scarto %-38s %.1f km fuori" % (entry["name"][:38], d)); return
        for p in picked:
            if km(entry["lat"], entry["lon"], p["lat"], p["lon"]) * 1000 < 60:
                print("  scarto %-38s a 60 m da %s" % (entry["name"][:38], p["name"])); return
            if p["qid"] == entry["qid"]:
                return
        picked.append({"name": entry["name"], "category": cat, "qid": entry["qid"],
                       "lat": round(entry["lat"], 5), "lon": round(entry["lon"], 5),
                       "poi_type": ptype, "status": "OPEN", "map_priority": 3,
                       "sitelinks": entry.get("sitelinks", 0)})
        print("  %-6s %-38s %-11s sl=%-3d %.1f km" % (why, entry["name"][:38], entry["qid"],
                                                      entry.get("sitelinks", 0), d))

    print("== %s: curati" % key)
    for name, cat, ptype in cfg["curated"]:
        e = resolve(name, cfg["lang"], lon0, lat0)
        if not e:
            print("  MANCA  %s" % name); continue
        add(e, cat, ptype, "cur")
        time.sleep(0.3)

    # The proximity ranking stays, but only to suggest. Ranking English
    # Wikipedia by sitelinks around Birmingham returns the county, two
    # universities, a stadium in another borough and the 1998 Eurovision Song
    # Contest before it returns anything a visitor would walk to. It is a good
    # way to notice something missing and a bad way to choose pins, so what it
    # finds is printed for review and nothing is written from it.
    if "--suggest" in sys.argv:
        print("== %s: suggerimenti da Wikidata (non scritti)" % key)
        have = {p["qid"] for p in picked}
        for e in notable(lon0, lat0, cfg["min_sitelinks"]):
            if e["qid"] not in have:
                print("  ? %-40s %-11s sl=%d" % (e["name"][:40], e["qid"], e["sitelinks"]))

    picked.sort(key=lambda p: -p["sitelinks"])
    for i, p in enumerate(picked, 1):
        p["rank"] = i
        p.pop("sitelinks", None)
    dest = os.path.join(POI_DIR, "%s.json" % key)
    json.dump({"city": key, "pois": picked}, open(dest, "w"), ensure_ascii=False, indent=1)
    cats = {}
    for p in picked:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    print("\n%s: %d pin %s -> %s" % (key, len(picked), cats, dest))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "birmingham")
