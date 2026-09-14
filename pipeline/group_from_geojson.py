"""
Assign zones to the district polygon they fall inside, from the city's own data.

OpenStreetMap's Overpass API was the obvious source and spent the afternoon
timing out, so the districts come from the same place the zone boundaries did:
the city's open-data portal. A zone belongs to the district its centre falls
inside — a plain ray crossing count, no nearest-neighbour guessing. A zone that
lands in no district stays ungrouped and is reported.

    python3 group_from_geojson.py milano /tmp/mi_mun.json MUNICIPIO "Municipio %s"
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rings_of(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def inside(x, y, rings):
    n = 0
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y):
                xx = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if xx > x:
                    n += 1
    return n % 2 == 1


def centroid(coords):
    ring = coords[0]
    return (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring))


def main(city, geojson, prop, fmt):
    src = json.load(open(geojson, encoding="utf-8"))
    districts = []
    for f in src["features"]:
        label = fmt % f["properties"][prop]
        districts.append((label, rings_of(f["geometry"])))
    path = os.path.join(HERE, "data_zones", "%s.json" % city)
    doc = json.load(open(path, encoding="utf-8"))
    hit, missing = 0, []
    for z in doc["zones"]:
        x, y = centroid(z["coords"])
        found = next((name for name, rings in districts if inside(x, y, rings)), None)
        if found:
            z["group"] = found
            hit += 1
        else:
            missing.append(z["name"])
    if hit < len(doc["zones"]) * 0.8:
        print("%s: solo %d/%d assegnate, non scrivo" % (city, hit, len(doc["zones"])))
        return
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    groups = sorted({z.get("group") for z in doc["zones"] if z.get("group")})
    print("%s: %d/%d zone in %d gruppi" % (city, hit, len(doc["zones"]), len(groups)))
    if missing:
        print("  senza gruppo (%d): %s" % (len(missing), ", ".join(missing[:5])))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
