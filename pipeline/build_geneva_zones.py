"""
Geneva: 8 city quarters and 44 communes, rated on what was found.

See fetch_geneva.py for why the map mixes two official layers, and for why the
canton's per-commune crime table is cited but not extracted.

WHAT THE CANTON PUBLISHES ABOUT ITSELF
    50,020 criminal-code offences in 2025, down 4% from 52,146 in 2024. Of
    those, 36,844 were against property and 2,291 against life and bodily
    integrity. Burglaries have fallen from 5,747 in 2015 to 3,410. One officer
    per 350 residents, 90,220 police interventions in 2025, and 29,326 hours
    of coordinated work against street dealing. (Police cantonale genevoise,
    14 August 2026.)

    Same shape as Basel: three quarters of Geneva's recorded crime is theft.

WHAT IS RATED AMBER, AND WHY ONLY THAT
    Four areas. Pâquis and the station, where the reporting is specific and
    sustained; Plainpalais, where it is thinner; and Vernier, for Le Lignon.
    Everywhere else the area-level search returned nothing, and the dashed
    outline says so rather than implying a checked all-clear.

    Six communes — Genève, Carouge, Lancy, Meyrin, Plan-les-Ouates, Vernier —
    hold "contrats locaux de sécurité" with the canton. That is a fact about
    how they are policed, not a finding about crime, and it is not treated as
    one: Carouge and Meyrin are rated green, because being in the programme
    says nothing about what happens on their streets.

USAGE
    python3 pipeline/fetch_geneva.py > /tmp/geneva_geometry.json
    python3 pipeline/build_geneva_zones.py
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GEOMETRY = "/tmp/geneva_geometry.json"
OUT = os.path.join(HERE, "data_zones", "geneva.json")

FOUND = {
    "Pâquis Sécheron": ("yellow", "yellow", (
        "The quarter between the station and the lake, and the one a visitor asks "
        "about by name. By day it is one of the most enjoyable parts of Geneva — "
        "dense, multilingual, full of small restaurants, with the Bains des Pâquis on "
        "the water. After dark the rue de Berne and the streets around it are where "
        "the city's street prostitution and a large share of its street drug dealing "
        "concentrate; residents' complaints are about noise, fights and persistent "
        "soliciting rather than attacks on passers-by. There is a police station in "
        "the quarter, the cantonal police logged 29,326 hours against street dealing "
        "across the region in 2025, and when cameras went up on the rue de Berne the "
        "reported effect was that the dealers moved a street over. Rated amber in both "
        "halves because the quarter is busy and worth knowing about, not because it is "
        "somewhere to avoid. The lakefront and the Sécheron end, with the UN and the "
        "Palais des Nations, are a different world from the rue de Berne. Sources: "
        "Police cantonale genevoise, 14 Aug 2026; Tribune de Genève."), "documented"),
    "Grottes Saint-Gervais": ("green", "yellow", (
        "The quarter immediately behind Cornavin station, including the Grottes with "
        "its famous Schtroumpfs buildings. Central and well used. The night rating is "
        "for the station forecourt and the streets between it and the Pâquis, where "
        "the same dealing that the canton targets in Pâquis reaches; the Grottes "
        "itself, a few streets further in, is residential and quiet. Source: Police "
        "cantonale genevoise, 14 Aug 2026."), "documented"),
    "Plainpalais Jonction": ("green", "yellow", (
        "The university quarter, the plaine de Plainpalais with its flea market, and "
        "the Jonction where the Rhône and the Arve meet. Lively, student-heavy and one "
        "of the better places to be in Geneva. The plaine is a large open space that "
        "empties at night, which is the whole of the night rating; nothing "
        "area-specific beyond that was found."), "documented"),
    "Carouge": ("green", "yellow", (
        "The Sardinian-built town across the Arve: low ochre houses, arcades, "
        "workshops, and the liveliest evening streets outside the city centre. The "
        "canton's Diagnostic local de sécurité, which asks residents how safe they "
        "feel walking alone in their own streets after 10pm, puts Carouge second of "
        "the communes surveyed, behind Vernier. That is a measure of how people feel "
        "rather than of what is recorded, and Carouge's evening crowd is a large part "
        "of why it ranks where it does — the night rating reflects a busy going-out "
        "town, not a dangerous one. Source: Diagnostic local de sécurité, canton de "
        "Genève, 2023."), "documented"),
    "Vernier": ("green", "yellow", (
        "The canton's second-largest commune, an industrial and residential belt west "
        "of the city that includes Le Lignon — a kilometre-long 1960s housing complex, "
        "one of the largest in Europe. Le Lignon has had a run of fires and vandalism "
        "reported over months, with complaints filed weekly, and the canton and the "
        "commune have put police and social workers into it together; a local party "
        "has petitioned for the municipal police post to be reinstated. That is "
        "property damage and disorder rather than crime against passers-by, and it "
        "concerns one estate rather than the commune. Vernier also comes first among "
        "the communes the canton surveys for how safe residents feel walking alone "
        "after 10pm — again a measure of feeling, not of recorded crime. Sources: "
        "Tribune de Genève; Diagnostic local de sécurité, canton de Genève, 2023."),
        "documented"),
}

# name -> one line of what the place actually is. Everything here was searched
# and returned nothing area-specific; the dashed outline on the map says so.
PLAIN = {
    "Acacias Bâtie": "The industrial and office strip south of the Arve, now filling with towers and the new Pont-Rouge district, with the Bois de la Bâtie park above it.",
    "Champel": "Geneva's most comfortable address: villas, clinics, the Bois de la Bâtie slopes and the university hospital.",
    "Eaux-Vives Cité": "The old town, the cathedral, the banking streets and the lakefront out to the Eaux-Vives — most of what a visitor comes to Geneva for.",
    "Saint-Jean Charmilles": "Residential quarters along the right bank of the Rhône, between the city and Vernier, ordinary and well connected.",
    "Servette Petit-Saconnex": "Dense residential Geneva north of the station, with the Servette football ground and the international organisations on the hill above.",
    "Aire-la-Ville": "A village on the Rhône in the rural west of the canton.",
    "Anières": "A lakeside village on the right bank towards the French border.",
    "Avully": "A farming village in the canton's south-western corner.",
    "Avusy": "A rural commune of hamlets and vineyards near the French border.",
    "Bardonnex": "A rural commune on the southern border, best known for its motorway customs post.",
    "Bellevue": "A lakeside commune north of the city, villas and the Port-Gitana marina.",
    "Bernex": "A large residential commune west of the city, growing fast around its new tram line.",
    "Cartigny": "A village of farms and vineyards above the Rhône.",
    "Chancy": "The westernmost commune in Switzerland, on the Rhône at the French border.",
    "Choulex": "A small rural commune in the canton's eastern countryside.",
    "Chêne-Bougeries": "An affluent residential commune east of the city, villas and parkland along the Chêne road.",
    "Chêne-Bourg": "A dense small commune on the French border, rebuilt around the Léman Express station.",
    "Collex-Bossy": "A rural commune north of the city, close to the airport approach.",
    "Collonge-Bellerive": "A lakeside commune on the right bank, villas and the Vésenaz shops.",
    "Cologny": "The hill above the lake: the most expensive addresses in the canton, with the Fondation Bodmer.",
    "Confignon": "A residential commune south-west of the city, half village and half new housing.",
    "Corsier": "A small lakeside commune on the right bank.",
    "Céligny": "A Genevan exclave surrounded by the canton of Vaud, in two separate pieces, with a few hundred residents.",
    "Dardagny": "Vineyard country in the far west, with a castle and three hamlets.",
    "Genthod": "A small, wealthy lakeside commune of eighteenth-century houses.",
    "Grand-Saconnex": "North of the city by the airport and the international organisations, offices and apartment blocks.",
    "Gy": "One of the smallest communes in the canton, farmland on the French border.",
    "Hermance": "A medieval lakeside village at the eastern end of the canton.",
    "Jussy": "Farmland and woodland in the canton's eastern countryside.",
    "Laconnex": "A small farming village in the south-west.",
    "Lancy": "A large commune between the city and the airport, from the Pont-Rouge towers to older estates and the Parc Navazza. In the canton's Diagnostic local de sécurité, which asks residents how safe they feel walking alone in their own streets after 10pm, Lancy ranks fourth of the communes surveyed — a measure of how people feel rather than of recorded crime, and one the canton publishes precisely because the two differ.",
    "Meinier": "A rural commune of hamlets east of the city.",
    "Meyrin": "A satellite town built for CERN, with the laboratory on its edge and a large international population. In the canton's Diagnostic local de sécurité, which asks residents how safe they feel walking alone in their own streets after 10pm, Meyrin ranks fifth of the communes surveyed — a measure of how people feel rather than of recorded crime, and one the canton publishes precisely because the two differ.",
    "Onex": "A hillside commune west of the city, mostly postwar housing estates around the Cité Nouvelle, with its own municipal police.",
    "Perly-Certoux": "A small commune on the southern border, with its own customs crossing.",
    "Plan-les-Ouates": "South of the city, the canton's watchmaking and biotech estate with residential districts around it. In the canton's Diagnostic local de sécurité, which asks residents how safe they feel walking alone in their own streets after 10pm, Plan-les-Ouates ranks third of the communes surveyed — a measure of how people feel rather than of recorded crime, and one the canton publishes precisely because the two differ.",
    "Pregny-Chambésy": "A wealthy commune above the lake, with the Rothschild estate and the botanical gardens.",
    "Presinge": "A farming village near the French border in the east.",
    "Puplinge": "A small commune on the eastern border, half village and half suburb.",
    "Russin": "The smallest commune in the canton, a vineyard village on the Rhône.",
    "Satigny": "The largest commune by area and the biggest wine-growing commune in Switzerland, with an industrial zone at Meyrin's edge.",
    "Soral": "A small farming commune on the French border.",
    "Thônex": "A residential commune on the eastern edge of the city, continuous with Chêne-Bourg and the French border.",
    "Troinex": "A quiet residential commune at the foot of the Salève.",
    "Vandoeuvres": "Countryside and large properties east of the city, one of the wealthiest communes in Switzerland.",
    "Versoix": "A small town on the lake towards Vaud, with its own centre, a chocolate factory and a long shoreline.",
    "Veyrier": "A residential commune under the Salève, running up to the French border crossing.",
}


def main():
    if not os.path.isfile(GEOMETRY):
        raise SystemExit("run: python3 pipeline/fetch_geneva.py > %s" % GEOMETRY)
    geo = json.load(io.open(GEOMETRY, encoding="utf-8"))

    tail = ("Nothing area-specific was found in the source review; the dashed outline "
            "on the map records that absence rather than a checked all-clear.")

    zones = []
    for z in geo["zones"]:
        name = z["name"]
        if name in FOUND:
            day, night, text, evidence = FOUND[name]
        elif name in PLAIN:
            day, night = "green", "green"
            text = "%s %s" % (PLAIN[name], tail)
            evidence = "no_findings"
        else:
            raise SystemExit("no text written for %s" % name)
        zones.append({
            "name": name,
            "slug": z["slug"],
            "day": day,
            "night": night,
            "coords": z["coords"],
            "text": text,
            # The communes are separate municipalities Booking can resolve; the
            # eight city quarters all sit inside Geneva and it cannot.
            "query": ("Geneva, Switzerland" if z["kind"] == "quarter"
                      else "%s, Geneva, Switzerland" % name),
            "booking_scope": "city",
            "evidence": evidence,
        })

    unused = (set(FOUND) | set(PLAIN)) - {z["name"] for z in zones}
    if unused:
        raise SystemExit("texts written for areas not in the boundary file: %s" % unused)

    out = {
        "label": "Geneva, Switzerland",
        # Zoom 11 fitted the whole canton and made the city unreadable: Céligny
        # sits 15 km north as an exclave, so framing everything pushes Geneva
        # itself down to a smudge among French villages. 12 frames the city and
        # its ring of communes, which is where 48 of the 52 areas are; the rest
        # is one drag away and "Reset view" comes back.
        "center": [46.2100, 6.1350],
        "zoom": 12,
        "scopeNote": (
            "Geneva is a canton of 45 communes of which the city is one, so this map "
            "covers all of it: the Ville de Genève's eight quarters, and every other "
            "commune from Carouge to the vineyard villages on the French border. The "
            "canton also runs a Diagnostic local de sécurité — a survey of residents "
            "on how safe they feel — and its 2023 edition found 28.9% saying they feel "
            "unsafe walking alone in their own neighbourhood after 10pm, down from "
            "32.8% in 2020 and from a peak of 49.9% in 2013. Where a commune's text "
            "cites that ranking it is describing what people report feeling, which is "
            "not the same thing as what is recorded, and the canton publishes both "
            "because they diverge. The "
            "canton recorded 50,020 criminal-code offences in 2025, 4% fewer than in "
            "2024, of which 36,844 were against property and 2,291 against life and "
            "bodily integrity — three quarters of it theft. Burglaries have fallen by "
            "40% since 2015. The canton does publish those figures per commune, but "
            "only as a PDF whose text layer runs the cantonal and communal columns "
            "together, so a row cannot be read back reliably; rather than risk "
            "publishing a commune's crime count wrong by a factor of ten, the ratings "
            "here come from sourced reporting and the per-commune table is left cited "
            "and unextracted. Source: Police cantonale genevoise, 14 August 2026."
        ),
        "zones": zones,
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print("Wrote %s — %d areas, %d with sourced findings, %d recorded as no findings"
          % (OUT, len(zones),
             sum(1 for z in zones if z["evidence"] == "documented"),
             sum(1 for z in zones if z["evidence"] == "no_findings")))


if __name__ == "__main__":
    main()
