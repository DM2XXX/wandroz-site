"""
Basel-Stadt's official neighbourhood boundaries, from the canton's own portal.

WHY THESE AREAS
    Basel-Stadt divides itself into 19 Wohnviertel plus the two Landgemeinden,
    Riehen and Bettingen. These are the canton's own statistical units — the
    ones every official table about Basel is published against — and they are
    also what people say out loud: Gundeldingen, Matthäus, Klybeck, St. Johann,
    Bruderholz. Twenty-one areas for a city of 175,000 is the granularity a
    person choosing where to live actually uses. Cutting them finer would add
    rows to a table without adding anything a reader could act on.

WHERE THE DATA COMES FROM
    data.bs.ch dataset 100042, "Statistische Raumeinheiten: Wohnviertel",
    published by Statistisches Amt Basel-Stadt as Open Government Data. The
    geometry is the canton's, not a redraw.

WHAT THIS SCRIPT DOES NOT DO
    It does not assign ratings. Basel publishes its crime statistics by
    Gemeinde only — Basel, Riehen, Bettingen and the canton total (data.bs.ch
    100508) — so there is no official per-Wohnviertel crime figure to rate on,
    and none is invented here. Ratings are researched per area and written in
    separately.

    In particular it does not reach for the per-Wohnviertel figures the canton
    *does* publish — income, nationality shares, social-assistance rates. Those
    are not crime data, and turning them into a safety colour would mean
    colouring neighbourhoods by who lives in them. That is a line this project
    does not cross, and stating it here is cheaper than re-arguing it later.

USAGE
    python3 pipeline/fetch_basel.py > /tmp/basel_geometry.json
"""
import json
import sys
import urllib.request

URL = ("https://data.bs.ch/api/explore/v2.1/catalog/datasets/100042/exports/geojson"
       "?lang=de&timezone=UTC")


def slugify(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -/":
            out.append("-")
        elif ch == "ä":
            out.append("ae")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def rings_of(geom):
    """GeoJSON is [lon, lat]; the site's zone files are [lat, lon]. Outer rings
    only — Basel's Wohnviertel have no holes, and silently dropping a hole that
    did exist would be worse than failing, so this asserts rather than assumes."""
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c
    rings = []
    for poly in polys:
        assert len(poly) == 1, "unexpected hole in a Wohnviertel polygon"
        rings.append([[round(lat, 6), round(lon, 6)] for lon, lat in poly[0]])
    return rings


def main():
    with urllib.request.urlopen(URL, timeout=90) as r:
        fc = json.load(r)
    zones = []
    for f in fc["features"]:
        p = f["properties"]
        zones.append({
            "name": p["wov_name"],
            "slug": slugify(p["wov_name"]),
            "gemeinde": p["gemeinde_name"],
            "wov_id": p["wov_id"],
            "coords": rings_of(f["geometry"]),
        })
    zones.sort(key=lambda z: z["wov_id"])
    json.dump({"source": URL, "zones": zones}, sys.stdout, ensure_ascii=False)
    print("", file=sys.stderr)
    print("%d areas: %s" % (len(zones), ", ".join(z["name"] for z in zones)), file=sys.stderr)


if __name__ == "__main__":
    main()
