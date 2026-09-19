"""
Bern's 28 areas: the city's own districts, rated on what was actually found.

GEOGRAPHY
    27 of Bern's 32 statistische Bezirke plus the Innere Stadt, which stands in
    for the five medieval banner quarters — see fetch_bern.py for why a safety
    map cannot carry an area called "Rotes Quartier".

CRIME DATA
    None at this level. The Kantonspolizei Bern's PKS annual report breaks the
    canton down by Verwaltungskreis and by Gemeinde (sections 4.1.2 and 4.1.3),
    so the city of Bern gets a single figure and its districts get none. Same
    position as Basel: official geography, sourced per-area reporting, nothing
    invented.

WHERE THE FINDINGS ARE
    Bern's documented trouble is concentrated in a few hundred metres either
    side of the station, and the district boundaries there are not where a
    visitor would guess. Both were checked against the city's own polygons and
    independently against OpenStreetMap's district assignment:

      Bahnhofplatz, Bollwerk, Kleine Schanze   Innere Stadt
      Schützenmatte and the Reitschule         Engeried

    Engeried is the surprise. The name belongs to a quiet residential slope
    north-west of the centre, but the district reaches down to the
    Neubrückstrasse beside the station, and that is where the Schützenmatte is.
    The rating covers the whole district, so the text says plainly that one
    square is the reason for it.

BÜMPLIZ AND BETHLEHEM
    Bern West has a reputation, and the reporting that repeats it says so in
    those words — "known in media reports for shootings, vandalism and ugly
    high-rises". A reputation is not a finding, and rating on one is the exact
    mistake this project made in Zurich's Schwamendingen. What there is: youth
    violence reported in the Kleefeld part of Bümpliz, and canton-wide youth
    violence up 5% in 2025 while total offences fell 4%. That is what the texts
    say, and it is all they say.

USAGE
    python3 pipeline/fetch_bern.py > /tmp/bern_geometry.json
    python3 pipeline/build_bern_zones.py
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GEOMETRY = "/tmp/bern_geometry.json"
OUT = os.path.join(HERE, "data_zones", "bern.json")

ZONES = {
    "Innere Stadt": ("green", "yellow", (
        "Bern's UNESCO old town, the federal parliament, the Zytglogge and the main "
        "station, all in one district — this is where a visitor spends almost all of "
        "their time. Busy, heavily policed and safe to walk by day. The night rating "
        "is for the station end: the Kantonspolizei has run targeted controls at the "
        "Bahnhofplatz, the SBB concourse, the Kleine Schanze and the Bollwerk, "
        "reporting 120 offences and 85 people charged across those locations. Nothing "
        "in the old town proper. Sources: Kantonspolizei Bern; plattformJ."),
        "documented"),
    "Engeried": ("green", "yellow", (
        "Mostly a quiet residential slope north-west of the centre — but the district "
        "reaches down to the Neubrückstrasse beside the station, and that is where the "
        "Schützenmatte and the Reitschule are. That one square is the city's most "
        "reported trouble spot: violence, vandalism and open drug dealing, a private "
        "security firm patrolling since 2025, a «social workers' van» for people who "
        "feel unsafe, and the Reitschule itself closing for two weeks over violence. "
        "The city's redesign of the square has slipped to 2032, though parts are being "
        "brought forward. The rest of Engeried is ordinary residential Bern; the "
        "rating is for the square. Sources: SRF; Berner Zeitung; 20 Minuten."),
        "documented"),
    "Bümpliz": ("green", "yellow", (
        "The old village centre of Bern West and the largest district in the city's "
        "sixth Stadtteil, with the postwar estates around it. It carries a reputation "
        "that local reporting itself describes as a media construction — shootings, "
        "vandalism, tower blocks — and a reputation is not something this site rates "
        "on. What is reported: youth violence in the Kleefeld part of the district, "
        "against a canton-wide picture of total offences down 4% in 2025 and youth "
        "violence up 5%, sharpest among 10- to 14-year-olds. Ordinary by day, with the "
        "usual caution for large estates after dark. Sources: Kantonspolizei Bern PKS "
        "2025; Hauptstadt; Kanton Bern."), "documented"),
    "Bethlehem": ("green", "yellow", (
        "The other half of Bern West, built around the Tscharnergut, Switzerland's "
        "first big postwar housing estate and still one of its best known. Grouped "
        "with Bümpliz in every account of the area's reputation; nothing "
        "district-specific was found beyond that. Rated with the usual night-time "
        "caution for large estates, not for anything measured. Source: Kantonspolizei "
        "Bern PKS 2025 (canton level)."), "documented"),

    # Everything below: the area-level search returned nothing specific. The
    # dashed outline on the map says so.
    "Länggasse": ("green", "green", (
        "The university quarter west of the centre, students, bookshops and the "
        "Unitobler. Busy in term time and quiet otherwise. Nothing area-specific was "
        "found in the source review."), "no_findings"),
    "Muesmatt": ("green", "green", (
        "Residential streets between the Länggasse and the Bremgartenwald, close to "
        "the university buildings. Nothing area-specific was found in the source "
        "review."), "no_findings"),
    "Stadtbach": ("green", "green", (
        "Between the Länggasse and Holligen, residential and unremarkable. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Neufeld": ("green", "green", (
        "The northern edge of the university area, with the Neufeld sports ground and "
        "the park-and-ride. Nothing area-specific was found in the source review."),
        "no_findings"),
    "Felsenau": ("green", "green", (
        "A small district on the Aare loop in the north, wooded and residential, with "
        "the Felsenau brewery and the viaduct. Nothing area-specific was found in the "
        "source review."), "no_findings"),
    "Holligen": ("green", "green", (
        "West of the centre, mixed residential with the Steigerhubel and Europaplatz "
        "edges. Nothing area-specific was found in the source review."), "no_findings"),
    "Weissenstein": ("green", "green", (
        "Residential south-west Bern between Holligen and Bümpliz. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Mattenhof": ("green", "green", (
        "Immediately south-west of the station, dense and mixed, with the Eigerplatz "
        "and the Loryspital. Well connected and busy without being a going-out area. "
        "Nothing area-specific was found in the source review."), "no_findings"),
    "Monbijou": ("green", "green", (
        "South of the station across the Monbijoubrücke, offices and apartments with "
        "the Monbijoupark. Central and quiet. Nothing area-specific was found in the "
        "source review."), "no_findings"),
    "Weissenbühl": ("green", "green", (
        "Residential south Bern on the hill above the Aare, with the Weissenbühl "
        "station. Nothing area-specific was found in the source review."), "no_findings"),
    "Sandrain": ("green", "green", (
        "A small, green district in the Aare bend below Weissenbühl, with the Marzili "
        "river swimming close by. Nothing area-specific was found in the source "
        "review."), "no_findings"),
    "Kirchenfeld": ("green", "green", (
        "Bern's embassy quarter across the Kirchenfeldbrücke, wide streets, villas and "
        "the Historical Museum. One of the most comfortable addresses in the city. "
        "Nothing area-specific was found in the source review."), "no_findings"),
    "Gryphenhübeli": ("green", "green", (
        "A small, affluent district between Kirchenfeld and the Aare, containing the "
        "Bear Park at the foot of the Grosser Muristalden — so a visitor crossing the "
        "Nydeggbrücke ends up here without noticing. Nothing area-specific was found "
        "in the source review."), "no_findings"),
    "Brunnadern": ("green", "green", (
        "Residential and green, south-east of Kirchenfeld towards the Elfenau. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Murifeld": ("green", "green", (
        "Residential east Bern around the Thunplatz and the Murifeld estate. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Schosshalde": ("green", "green", (
        "East Bern, holding the Rosengarten viewpoint and the Zentrum Paul Klee — two "
        "of the things visitors come for, in an otherwise residential district. "
        "Nothing area-specific was found in the source review."), "no_findings"),
    "Beundenfeld": ("green", "green", (
        "Between the Schosshalde and the Wankdorf, residential with barracks and "
        "sports grounds. Nothing area-specific was found in the source review."),
        "no_findings"),
    "Altenberg": ("green", "green", (
        "A narrow strip along the right bank of the Aare opposite the old town, one of "
        "the prettiest and quietest addresses in Bern. Nothing area-specific was found "
        "in the source review."), "no_findings"),
    "Spitalacker": ("green", "green", (
        "The heart of the Nordquartier, grid streets of apartment blocks north of the "
        "Lorrainebrücke. Nothing area-specific was found in the source review."),
        "no_findings"),
    "Breitfeld": ("green", "green", (
        "North Bern around the Wankdorf: the stadium, the federal offices and the "
        "retail park. Empty outside event days. Nothing area-specific was found in the "
        "source review."), "no_findings"),
    "Breitenrain": ("green", "green", (
        "The trendiest part of the Nordquartier, cafés along the Breitenrainplatz and "
        "rents rising to match. Local reporting on the district is about gentrification "
        "and pressure on housing, not about crime. Nothing area-specific was found in "
        "the source review."), "no_findings"),
    "Lorraine": ("green", "green", (
        "Bern's alternative quarter, over the bridge from the station, small houses, "
        "co-operatives and the city allotments. Long a byword for left-wing Bern and "
        "now gentrifying like its neighbour. Nothing area-specific was found in the "
        "source review."), "no_findings"),
    "Stöckacker": ("green", "green", (
        "Between Bümpliz and the centre, housing estates and the Stöckacker station. "
        "Nothing area-specific was found in the source review."), "no_findings"),
    "Oberbottigen": ("green", "green", (
        "The city's rural western tip — farms, woodland and a few hamlets, technically "
        "Bern and in practice countryside. Nothing area-specific was found in the "
        "source review."), "no_findings"),
}


def main():
    if not os.path.isfile(GEOMETRY):
        raise SystemExit("run: python3 pipeline/fetch_bern.py > %s" % GEOMETRY)
    geo = json.load(io.open(GEOMETRY, encoding="utf-8"))

    zones = []
    for z in geo["zones"]:
        name = z["name"]
        if name not in ZONES:
            raise SystemExit("no rating written for %s" % name)
        day, night, text, evidence = ZONES[name]
        zones.append({
            "name": name,
            "slug": z["slug"],
            "day": day,
            "night": night,
            "coords": z["coords"],
            "text": text,
            "query": "Bern, Switzerland",
            "booking_scope": "city",
            "evidence": evidence,
        })

    missing = set(ZONES) - {z["name"] for z in zones}
    if missing:
        raise SystemExit("rated areas absent from the boundary file: %s" % missing)

    out = {
        "label": "Bern, Switzerland",
        "center": [46.9480, 7.4474],
        "zoom": 12,
        "dataNote": (
            "Kantonspolizei Bern publishes crime for the canton by administrative "
            "district and by municipality, so the city of Bern has one figure and its "
            "28 districts have none; the ratings here come from sourced reporting "
            "rather than a per-district number. For scale, the canton recorded 82,089 "
            "offences in 2025, 4% fewer than the year before, with criminal-code and "
            "drug offences both falling and youth violence up 5%. Almost everything "
            "specific that is reported in the city happens within a few hundred metres "
            "of the station — the Schützenmatte in particular — and the district "
            "boundaries there do not run where a visitor would guess, so each text "
            "names the place rather than leaving the colour to speak. Source: "
            "Kantonspolizei Bern, Kriminalstatistik 2025."
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
