"""
Give Paris and Berlin their own districts as list headings.

Both cities already know the answer and were throwing it away. Every Paris
quartier carries its arrondissement inside its own name; Berlin's boundary
download carries each Bezirksregion's Bezirk and the conversion dropped it.
Nothing is inferred here: the arrondissement is read out of the name, the
Bezirk out of the file the boundaries came from.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data_zones")


def paris():
    p = os.path.join(D, "paris.json")
    doc = json.load(open(p, encoding="utf-8"))
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}
    n = 0
    for z in doc["zones"]:
        m = re.search(r"\((\d+)e arr\.\)", z["name"])
        if not m:
            continue
        i = int(m.group(1))
        z["group"] = "%s arrondissement" % ordinal.get(i, "%dth" % i)
        n += 1
    json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("paris:  %d quartieri in %d arrondissement" % (n, len({z.get("group") for z in doc["zones"]})))


def berlin():
    raw = json.load(open(os.path.join(D, "berlin_raw", "features.json"), encoding="utf-8"))
    by_name = {r["name"]: r.get("bezirk") for r in raw if r.get("name")}
    p = os.path.join(D, "berlin.json")
    doc = json.load(open(p, encoding="utf-8"))
    # Two zones were renamed during the conversion to tell apart the identical
    # "Heerstraße" in two different Bezirke — the disambiguation is the Bezirk,
    # so it is read back out of the name rather than looked up.
    import re
    n, missing = 0, []
    for z in doc["zones"]:
        b = by_name.get(z["name"])
        if not b:
            m = re.match(r"^(.*) \((.+)\)$", z["name"])
            if m and m.group(2) in set(by_name.values()):
                b = m.group(2)
        if b:
            z["group"] = b
            n += 1
        else:
            missing.append(z["name"])
    json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("berlin: %d zone in %d Bezirke" % (n, len({z.get("group") for z in doc["zones"] if z.get("group")})))
    if missing:
        print("  senza Bezirk (%d): %s" % (len(missing), ", ".join(missing[:6])))


paris()
berlin()
