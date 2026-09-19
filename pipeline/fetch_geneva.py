"""
Geneva's areas: the city's eight quarters plus the canton's other communes.

WHY BOTH LAYERS
    Geneva is not a city with suburbs, it is a canton of 45 communes of which
    the city is one. Someone moving there chooses between Carouge, Lancy,
    Meyrin, Vernier and Onex as readily as between parts of the city, and the
    canton's own crime reporting is published per commune. So the communes are
    the natural unit.

    But the cadastral commune layer splits the city of Geneva into its four
    pre-1931 communes — Cité, Eaux-Vives, Plainpalais, Petit-Saconnex — and at
    that grain Pâquis disappears inside Cité. Pâquis is to Geneva what
    Langstrasse is to Zurich: the one area a visitor asks about, by name,
    before they book anything. Losing it to make the layers uniform would be a
    tidy map that fails at its job.

    So: the Ville de Genève's own eight quarters for the city, the cantonal
    commune layer for everywhere else, and the four Genève-* cadastral communes
    dropped because the quarters already cover exactly that ground.

SOURCES
    Ville de Genève quarters   SITG VDG_QUARTIER_VILLE (8 features)
    Cantonal communes          SITG CAD_COMMUNE (48, of which 4 are the city)

CRIME
    Not fetched here, and worth saying why not, because Geneva does publish it
    per commune — "Statistique policière de la criminalité 2025 par commune",
    Corps de police, 23 March 2026. It exists only as a PDF whose text layer
    runs the canton's figure and the commune's figure together: a row reads
    "2291 81 20", which is the canton's 2,291 and 81 followed by the commune's
    2 and 0, and nothing in the extraction distinguishes that from 2,291, 81
    and 20. Publishing crime numbers that might be wrong by a factor of ten is
    worse than publishing none, so the figures are cited as existing and not
    extracted. If the canton ever ships the same table as CSV, this becomes an
    official-data city in an afternoon.

USAGE
    python3 pipeline/fetch_geneva.py > /tmp/geneva_geometry.json
"""
import json
import sys
import urllib.request

QUARTIERS = ("https://vector.sitg.ge.ch/arcgis/rest/services/VDG_QUARTIER_VILLE/"
             "FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson&outSR=4326")
COMMUNES = ("https://vector.sitg.ge.ch/arcgis/rest/services/CAD_COMMUNE/"
            "FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson&outSR=4326")

# The four cadastral communes the eight city quarters already cover.
CITY_COMMUNES = {"Genève-Cité", "Genève-Eaux-Vives",
                 "Genève-Petit-Saconnex", "Genève-Plainpalais"}


def slugify(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -'’":
            out.append("-")
        elif ch in "éèê":
            out.append("e")
        elif ch == "à":
            out.append("a")
        elif ch == "ô":
            out.append("o")
        elif ch == "û":
            out.append("u")
        elif ch == "ç":
            out.append("c")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wandroz/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def rings_of(geom):
    """[lon, lat] to [lat, lon]. Communes on the Rhône and the lake do have
    multiple parts, so MultiPolygon is expected; interior holes are not, and
    dropping one silently would put a village inside a lake."""
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c
    rings = []
    for poly in polys:
        if len(poly) != 1:
            raise SystemExit("unexpected hole in a Geneva polygon")
        rings.append([[round(lat, 6), round(lon, 6)] for lon, lat in poly[0]])
    return rings


def main():
    zones = []

    for f in get(QUARTIERS)["features"]:
        name = f["properties"]["NOM_QUARTIER"]
        zones.append({"name": name, "slug": slugify(name), "kind": "quarter",
                      "coords": rings_of(f["geometry"])})

    for f in get(COMMUNES)["features"]:
        name = f["properties"]["COMMUNE"]
        if name in CITY_COMMUNES:
            continue
        zones.append({"name": name, "slug": slugify(name), "kind": "commune",
                      "coords": rings_of(f["geometry"])})

    seen = set()
    for z in zones:
        if z["slug"] in seen:
            raise SystemExit("duplicate slug: %s" % z["slug"])
        seen.add(z["slug"])

    zones.sort(key=lambda z: (z["kind"] != "quarter", z["name"]))
    json.dump({"sources": [QUARTIERS, COMMUNES], "zones": zones},
              sys.stdout, ensure_ascii=False)
    q = sum(1 for z in zones if z["kind"] == "quarter")
    print("", file=sys.stderr)
    print("%d areas: %d city quarters + %d communes"
          % (len(zones), q, len(zones) - q), file=sys.stderr)


if __name__ == "__main__":
    main()
