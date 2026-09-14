"""
Give a city's list the districts its own boundary source already carried.

Barcelona's barris arrive with a district code and Madrid's barrios with the
district name spelled out; both were dropped on the way into the zone file
because every city was flattened to the same shape. They are read back here —
no lookup table, no geometry, no guessing which barrio belongs where.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data_raw")
ZONES = os.path.join(HERE, "data_zones")

# Barcelona's source carries the code; the names are the Ajuntament's own.
BCN_DISTRICTS = {
    "01": "Ciutat Vella", "02": "L'Eixample", "03": "Sants-Montjuïc",
    "04": "Les Corts", "05": "Sarrià-Sant Gervasi", "06": "Gràcia",
    "07": "Horta-Guinardó", "08": "Nou Barris", "09": "Sant Andreu",
    "10": "Sant Martí",
}


def apply(city, group_of):
    path = os.path.join(ZONES, "%s.json" % city)
    doc = json.load(open(path, encoding="utf-8"))
    hit, missing = 0, []
    for z in doc["zones"]:
        g = group_of(z)
        if g:
            z["group"] = g
            hit += 1
        else:
            missing.append(z["name"])
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    groups = sorted({z.get("group") for z in doc["zones"] if z.get("group")})
    print("%-10s %3d zone in %2d gruppi" % (city, hit, len(groups)))
    if missing:
        print("           senza gruppo (%d): %s" % (len(missing), ", ".join(missing[:5])))
    return groups


def barcelona():
    raw = json.load(open(os.path.join(RAW, "barcelona_boundaries_2023.json"), encoding="utf-8"))
    by_name = {r["nom"]: BCN_DISTRICTS.get(r["d"]) for r in raw}
    return apply("barcelona", lambda z: by_name.get(z["name"]))


def madrid():
    raw = json.load(open(os.path.join(RAW, "madrid_boundaries_2026.json"), encoding="utf-8"))
    by_name = {r["nom"]: r.get("dist") for r in raw}
    return apply("madrid", lambda z: by_name.get(z["name"]))


if __name__ == "__main__":
    print(barcelona())
    print(madrid())
