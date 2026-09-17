"""
Official wijk boundaries for Dutch cities, from CBS via PDOK.

WHY NOT OSM, WHICH WORKS EVERYWHERE ELSE
    For Dutch cities OSM's administrative levels do not hold the unit a
    traveller thinks in. Asked for Rotterdam it returns ten areas that include
    Europoort, Maasvlakte, Botlek and Vondelingenplaat — container terminals
    and refineries — with "Rotterdam" listed twice and no sign of the fourteen
    gebieden the city is actually organised into. The Hague returns exactly one
    area. Those are not partial answers, they are the wrong question.

    CBS, the national statistics office, publishes the official wijk- en
    buurtkaart for every municipality: real district names, real boundaries,
    and the resident count alongside. That is the right source for the
    Netherlands, and it is open data.

TWO THINGS THE SERVICE DOES NOT DO
    PDOK ignores CQL_FILTER on this layer, so the whole national set is paged
    through and filtered here. And it serves EPSG:28992 (Dutch RD) unless asked
    otherwise — coordinates in metres, which would land every polygon in the
    Gulf of Guinea if used as latitude and longitude. srsName=EPSG:4326 is not
    optional.

    python3 fetch_nl_zones.py rotterdam Rotterdam "Rotterdam, Netherlands"
"""
import json, os, re, subprocess, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "wandroz-pipeline/1.0 (+https://www.wandroz.com)"
WFS = "https://service.pdok.nl/cbs/wijkenbuurten/2023/wfs/v1_0"
PAGE = 1000


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "wijk"


def fetch_page(start):
    args = ["curl", "-s", "--max-time", "180", "-A", UA, "--get",
            "--data-urlencode", "service=WFS", "--data-urlencode", "version=2.0.0",
            "--data-urlencode", "request=GetFeature",
            "--data-urlencode", "typeName=wijkenbuurten:wijken",
            "--data-urlencode", "outputFormat=application/json",
            "--data-urlencode", "srsName=EPSG:4326",
            "--data-urlencode", "count=%d" % PAGE,
            "--data-urlencode", "startIndex=%d" % start, WFS]
    return json.loads(subprocess.run(args, capture_output=True, text=True).stdout)


def rings_of(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def main(key, gemeente, label):
    found, start = [], 0
    while True:
        doc = fetch_page(start)
        feats = doc.get("features", [])
        found += [f for f in feats if f["properties"].get("gemeentenaam") == gemeente]
        print("  ...%d fetched, %d matching so far" % (start + len(feats), len(found)))
        if len(feats) < PAGE:
            break
        start += PAGE
    if not found:
        raise SystemExit("%s: no wijken for gemeente %r — check the spelling CBS uses" % (key, gemeente))

    zones, lats, lons = [], [], []
    for f in found:
        name = (f["properties"].get("wijknaam") or "").strip()
        # CBS carries two non-places in every municipality's list: "Groot
        # water" for the open water inside its boundary, and a "Buitenland"
        # catch-all. Neither is somewhere anyone sleeps.
        if not name or name.lower() in ("groot water", "buitenland"):
            continue
        rings = []
        for ring in rings_of(f["geometry"]):
            # GeoJSON is (lon, lat); everything downstream here is (lat, lon).
            pts = [(round(p[1], 5), round(p[0], 5)) for p in ring]
            if len(pts) >= 4:
                rings.append(pts)
        if not rings:
            continue
        for r in rings:
            lats += [p[0] for p in r]; lons += [p[1] for p in r]
        pop = f["properties"].get("aantalInwoners")
        zones.append({
            "name": name, "slug": slugify(name),
            "wijkcode": f["properties"].get("wijkcode"),
            "population": pop if isinstance(pop, int) and pop > 0 else None,
            "day": "grey", "night": "grey", "text": "",
            "query": "%s, %s" % (name, label),
            "booking_scope": "area", "coords": rings,
        })
        print("   %-34s %6s inhabitants, %d ring(s)" % (name, pop, len(rings)))

    out = {"label": label,
           "center": [round(sum(lats) / len(lats), 5), round(sum(lons) / len(lons), 5)],
           "zoom": 12, "dataNote": "",
           "source": "CBS wijk- en buurtkaart 2023 via PDOK (open data)",
           "zones": zones}
    path = os.path.join(HERE, "data_zones", "%s_boundaries.json" % key)
    with open(path, "w") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print("   wrote %s (%d wijken, %d KB)" % (path, len(zones), os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
