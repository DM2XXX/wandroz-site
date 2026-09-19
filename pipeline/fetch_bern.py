"""
Bern's official city districts, from the city's own geodata.

WHICH OF BERN'S FOUR DIVISIONS
    Statistik Stadt Bern cuts the city four ways at once, and the choice
    matters more than it looks:

      6   Stadtteile               too coarse — Kirchenfeld and Murifeld are
                                   nothing alike and would share one colour
      32  statistische Bezirke     the names people use: Länggasse, Lorraine,
                                   Breitenrain, Mattenhof, Bümpliz, Bethlehem
      114 gebräuchliche Quartiere  micro-zones; rows without information
      316 Volkszählungsquartiere   census blocks, not places

    So: the 32 statistical districts.

THE OLD TOWN IS THE EXCEPTION
    Five of those 32 are the medieval banner quarters of the Innere Stadt, and
    they are called Schwarzes, Weisses, Grünes, Gelbes and Rotes Quartier. On a
    map that uses red, amber and green to mean danger, an area called "Red
    Quarter" is a trap, and a visitor has no idea where the Yellow Quarter is
    anyway. They are also five slices of one small UNESCO old town that nobody
    experiences as five places.

    They are replaced here by the Stadtteil 1 polygon, "Innere Stadt", which
    the city publishes as the union of exactly those five. No geometry is
    merged by this script — the city had already drawn the shape. 32 districts
    become 28 areas, and the colour names survive in the old town's text, where
    they are history rather than a rating.

SOURCE
    map.bern.ch/ogd/stadteinteilung/stadteinteilung_json.zip, Geoinformation
    Stadt Bern, layers STATISTISCHER_BEZIRK and STADTTEIL, WGS84.

CRIME
    Not fetched, because it is not published at this level. The Kantonspolizei
    Bern's annual PKS has a section 4.1.3, "Strafgesetzbuch: Straftaten nach
    Gemeinde" — by municipality, so the city of Bern gets one figure and its
    32 districts get none. Ratings are researched per area.

USAGE
    python3 pipeline/fetch_bern.py > /tmp/bern_geometry.json
"""
import io
import json
import os
import sys
import urllib.request
import zipfile

URL = "https://map.bern.ch/ogd/stadteinteilung/stadteinteilung_json.zip"
INNER_CITY_STADTTEIL = 1


def slugify(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -":
            out.append("-")
        elif ch == "ä":
            out.append("ae")
        elif ch == "ö":
            out.append("oe")
        elif ch == "ü":
            out.append("ue")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def rings_of(geom):
    """GeoJSON [lon, lat] to the site's [lat, lon]. Outer rings only; a hole
    would be silently dropped, so assert instead of assuming there are none."""
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c
    rings = []
    for poly in polys:
        assert len(poly) == 1, "unexpected hole in a Bern district polygon"
        rings.append([[round(lat, 6), round(lon, 6)] for lon, lat in poly[0]])
    return rings


def main():
    with urllib.request.urlopen(URL, timeout=180) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = [n for n in z.namelist() if n.endswith("wgs84.json")][0]
        layers = json.loads(z.read(name).decode("utf-8"))

    by_layer = {l["name"]: l["features"] for l in layers}
    districts = by_layer["STATISTISCHER_BEZIRK"]
    stadtteile = by_layer["STADTTEIL"]

    inner = [f for f in stadtteile if f["properties"]["nummer"] == INNER_CITY_STADTTEIL]
    if len(inner) != 1:
        raise SystemExit("expected exactly one Stadtteil %d" % INNER_CITY_STADTTEIL)
    inner_fid = inner[0]["properties"].get("id") or inner[0]["properties"].get("fid")

    # The districts carry their Stadtteil as a uuid, and the Stadtteil features
    # do not expose that uuid under a predictable key across releases. The five
    # old-town districts are identifiable without it: they are the only ones
    # whose names end in "Quartier".
    old_town = [f for f in districts if f["properties"]["name"].endswith("Quartier")]
    if len(old_town) != 5:
        raise SystemExit("expected 5 old-town banner quarters, found %d — check the source"
                         % len(old_town))
    old_town_names = sorted(f["properties"]["name"] for f in old_town)

    zones = []
    for f in districts:
        p = f["properties"]
        if p["name"].endswith("Quartier"):
            continue
        zones.append({
            "name": p["name"],
            "slug": slugify(p["name"]),
            "number": p["nummer"],
            "coords": rings_of(f["geometry"]),
        })

    zones.append({
        "name": "Innere Stadt",
        "slug": "innere-stadt",
        "number": 0,
        "replaces": old_town_names,
        "coords": rings_of(inner[0]["geometry"]),
    })
    zones.sort(key=lambda z: z["number"])

    json.dump({"source": URL, "zones": zones}, sys.stdout, ensure_ascii=False)
    print("", file=sys.stderr)
    print("%d areas (27 statistical districts + Innere Stadt, which replaces %s)"
          % (len(zones), ", ".join(old_town_names)), file=sys.stderr)


if __name__ == "__main__":
    main()
