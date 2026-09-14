"""
Point a city's zones at the district Booking actually indexes.

A neighbourhood name is only useful in a Booking search if Booking has a
destination by that name. Opened and read: "Amstel III/Bullewijk, Amsterdam"
and "Giardini Pubblici Indro Montanelli, Milan" both redirect to Booking's
homepage; "Praha 1, Prague" resolves to a single apartment whose title contains
"Praha 1". Berlin's Bezirksregionen are the same kind of micro-unit.

The district above them is not: all twelve Berlin Bezirke were opened and each
returns its own Booking district inside Berlin, from Reinickendorf's 37
properties to Mitte's 460. So where a zone carries a verified parent, the link
searches the parent and the page says that is what it does — narrower than the
city, wider than the neighbourhood, and real.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
Z = os.path.join(HERE, "data_zones")
LEDGER = os.path.join(Z, "booking_destinations.json")

# city -> (suffix for the query, {district: "what Booking returned"})
VERIFIED = {
    "berlin": (", Berlin, Germany", {
        "Mitte": "460 properties", "Friedrichshain-Kreuzberg": "334 properties",
        "Charlottenburg-Wilmersdorf": "333 properties", "Pankow": "337 properties",
        "Treptow-Köpenick": "125 properties", "Neukölln": "112 properties",
        "Tempelhof-Schöneberg": "128 properties", "Steglitz-Zehlendorf": "49 properties",
        "Spandau": "52 properties", "Reinickendorf": "37 properties",
        "Marzahn-Hellersdorf": "43 properties", "Lichtenberg": "56 properties",
    }),
    "madrid": (", Madrid, Spain", {
        "Centro": "2,956 properties, as Madrid City Center",
        "Salamanca": "385 properties", "Tetuán": "361 properties",
        "Arganzuela": "307 properties", "Chamberí": "290 properties",
        "Ciudad Lineal": "205 properties", "Chamartín": "203 properties",
        "Carabanchel": "169 properties", "Puente de Vallecas": "167 properties",
        "Retiro": "161 properties", "Moncloa - Aravaca": "155 properties",
        "Usera": "122 properties", "Hortaleza": "114 properties",
        "Fuencarral - El Pardo": "80 properties", "Villa de Vallecas": "48 properties",
        "Moratalaz": "20 properties",
        # Five distritos are deliberately absent. "Latina" resolves to La
        # Latina, the barrio in Centro five kilometres away; "San Blas -
        # Canillejas" to a single property; "Villaverde" to nothing at all;
        # "Barajas" to the airport's 6,566-property radius. Their barrios keep
        # their own queries, unverified and reported as such.
    }),
    "barcelona": (", Barcelona, Spain", {
        "L'Eixample": "1,530 properties (queried as Eixample: the article makes "
                      "Booking match an apartment listing instead)",
        "Ciutat Vella": "553 properties", "Sants-Montjuïc": "417 properties",
        "Gràcia": "338 properties", "Sant Martí": "331 properties",
        "Les Corts": "99 properties", "Horta-Guinardó": "82 properties",
        # Sarrià-Sant Gervasi returns one property; Nou Barris and Sant Andreu
        # are untested. Their barris keep their own queries.
    }),
}

# Where Booking's own spelling differs from the city's.
QUERY_SPELLING = {"L'Eixample": "Eixample"}


def apply(city):
    suffix, districts = VERIFIED[city]
    path = os.path.join(Z, "%s.json" % city)
    doc = json.load(open(path, encoding="utf-8"))
    ledger = json.load(open(LEDGER, encoding="utf-8")) if os.path.exists(LEDGER) else {}
    done, skipped = 0, []
    for zone in doc["zones"]:
        g = zone.get("group")
        if not g or g not in districts:
            skipped.append(zone["name"])
            continue
        zone["query"] = QUERY_SPELLING.get(g, g) + suffix
        zone["booking_scope"] = "parent"
        ledger["%s/%s" % (city, zone["slug"])] = {
            "class": "TRAVELLER_ALIAS", "checked": "2026-09-14",
            "note": ("searches %s, the district this area sits in: Booking returns %s there. "
                     "The area's own name is a statistical micro-unit, not a Booking "
                     "destination." % (g, districts[g])),
        }
        done += 1
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(sorted(ledger.items())), open(LEDGER, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("%s: %d zone verso %d distretti verificati" % (city, done, len(districts)))
    if skipped:
        print("  invariate (%d): %s" % (len(skipped), ", ".join(skipped[:4])))


if __name__ == "__main__":
    apply(sys.argv[1] if len(sys.argv) > 1 else "berlin")
