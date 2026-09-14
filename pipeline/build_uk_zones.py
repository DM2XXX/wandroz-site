"""
Official ward boundaries for an English or Welsh city, from the ONS.

The London pipeline was never really about London: it takes a polygon, asks
data.police.uk what happened inside it, and splits the answer into a day and a
night score. The ONS publishes every ward boundary in the country, so a new
city starts here.

    python3 build_uk_zones.py birmingham Birmingham "Birmingham, United Kingdom"
"""
import json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = None
# Two ward vintages, because a city that re-warded after the 2021 census has
# boundaries the census cannot populate: Liverpool's 2024 wards return nothing
# from NOMIS, since the population was counted against the 2021 ones. Where
# that happens the city is built on the 2021 vintage instead, so the boundary
# and its denominator come from the same year — a real official boundary and a
# real official count, rather than two that do not line up.
ONS_BY_VINTAGE = {
    "2024": ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
             "Wards_December_2024_Boundaries_UK_BGC/FeatureServer/0/query", "WD24CD", "WD24NM", "LAD24NM"),
    "2021": ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
             "Wards_(December_2021)_UK_BGC/FeatureServer/0/query", "WD21CD", "WD21NM", "LAD21NM"),
}
VINTAGE = os.environ.get("WARD_VINTAGE", "2024")
ONS, CODE_F, NAME_F, LAD_F = ONS_BY_VINTAGE[VINTAGE]
UA = "WandrozBoundaries/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"
KEY, LAD, LABEL = "birmingham", "Birmingham", "Birmingham, United Kingdom"
if len(sys.argv) > 3:
    KEY, LAD, LABEL = sys.argv[1], sys.argv[2], sys.argv[3]


def slugify(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -&'/":
            out.append("-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def fetch():
    params = {
        "where": "%s='%s'" % (LAD_F, LAD),
        "outFields": "%s,%s,%s" % (CODE_F, NAME_F, LAD_F),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    url = ONS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["features"]


def rings_to_coords(geom):
    """ArcGIS rings are [lon, lat]; Leaflet wants [lat, lon]. Only the outer
    rings are kept — holes would draw as filled shapes on a Leaflet polygon
    unless nested, and no Manchester ward has one that matters at city zoom."""
    out = []
    for ring in geom.get("rings", []):
        pts = [[round(lat, 5), round(lon, 5)] for lon, lat in ring]
        if len(pts) > 3:
            out.append(pts)
    out.sort(key=len, reverse=True)
    return out[:1] if out else []


def main():
    global OUT
    OUT = os.path.join(HERE, "data_zones", "%s_boundaries.json" % KEY)
    feats = fetch()
    zones = []
    for f in feats:
        name = f["attributes"][NAME_F]
        coords = rings_to_coords(f.get("geometry") or {})
        if not coords:
            print("SKIP (nessuna geometria):", name)
            continue
        zones.append({
            "name": name,
            "slug": slugify(name),
            "code": f["attributes"][CODE_F],
            "day": "grey", "night": "grey",
            "text": "",
            "query": "%s, %s, United Kingdom" % (name, LAD),
            "booking_scope": "area",
            "coords": coords,
        })
    zones.sort(key=lambda z: z["name"])
    lat = sum(p[0] for z in zones for p in z["coords"][0]) / sum(len(z["coords"][0]) for z in zones)
    lon = sum(p[1] for z in zones for p in z["coords"][0]) / sum(len(z["coords"][0]) for z in zones)
    doc = {
        "label": LABEL,
        "ward_vintage": VINTAGE,
        "center": [round(lat, 4), round(lon, 4)],
        "zoom": 11,
        "dataNote": "",
        "zones": zones,
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, ensure_ascii=False)
    pts = sum(len(z["coords"][0]) for z in zones)
    print("%d ward, %d punti di confine, centro %s" % (len(zones), pts, doc["center"]))
    print("scritto", OUT, "(%.0f KB)" % (os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
