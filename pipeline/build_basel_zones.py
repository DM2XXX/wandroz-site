"""
Builds Basel's 21 areas from the canton's own boundaries and its own figures.

WHAT BASEL PUBLISHES, AND WHAT IT DOES NOT
    Boundaries: yes. data.bs.ch dataset 100042 gives the 19 Wohnviertel plus
    Riehen and Bettingen as the canton draws them. These are the units every
    official table about Basel uses and the names people actually say —
    Gundeldingen, Matthäus, Klybeck, Bruderholz — so they are what this city is
    built on. Twenty-one areas for 210,000 people is the granularity someone
    choosing where to live uses; cutting finer would add rows, not information.

    Crime by area: no. Checked twice, independently. The canton's open data
    (100508, StGB offences) breaks down to Gemeinde only — Basel, Riehen,
    Bettingen — and the Kantonspolizei's own PKS annual report has a section
    headed "Straftaten: Geografische Verteilung" that goes no finer than the
    same three. There is no per-Wohnviertel crime figure to rate on, and none
    is invented here.

    What that leaves is two real things: an official figure for two of the 21
    areas, because Riehen and Bettingen are Gemeinden in their own right, and
    per-area evidence gathered from sourced reporting for the rest.

WHAT IS DELIBERATELY NOT USED
    The canton publishes plenty per Wohnviertel that correlates with crime in
    every city in Europe: social-assistance rates, foreign-national share,
    income, unemployment (dataset 100011). None of it is here. Turning those
    into a safety colour would mean colouring neighbourhoods by who lives in
    them, dressed up as measurement. The line is worth writing down where the
    temptation is one API call away.

THE HEADLINE A READER WILL HAVE SEEN
    Basel-Stadt records more offences per resident than any other Swiss canton,
    and that fact travels. It is also close to meaningless as a comparison:
    Basel-Stadt is the only canton that is just a city, with no countryside to
    dilute it, sitting on a triple border with the foot traffic that brings.
    The same denominator problem this project hit in Zurich's Kreis 1, one
    level up. The city note says so, with the criminologist who said it first.

USAGE
    python3 pipeline/fetch_basel.py > /tmp/basel_geometry.json
    python3 pipeline/build_basel_zones.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEOMETRY = "/tmp/basel_geometry.json"
OUT = os.path.join(HERE, "data_zones", "basel.json")

# Resident population, data.bs.ch 100126, 31 December 2025. Carried so each
# area's size is stated: "quiet" means something different in Bettingen (1,312
# people) than in St. Johann (19,870).
POPULATION = {
    "Riehen": 22885, "St. Johann": 19870, "Gundeldingen": 19511, "Iselin": 18193,
    "Matthäus": 15304, "Bachletten": 13938, "St. Alban": 12765, "Am Ring": 11614,
    "Hirzbrunnen": 10004, "Bruderholz": 9703, "Breite": 9342, "Rosental": 7894,
    "Klybeck": 7297, "Gotthelf": 7256, "Wettstein": 5906, "Vorstädte": 5109,
    "Clara": 4507, "Kleinhüningen": 2892, "Altstadt Grossbasel": 2692,
    "Altstadt Kleinbasel": 2535, "Bettingen": 1312,
}

# (day, night, text, evidence)
#
# "no_findings" is not a softer word for green. It means the area-level search
# returned nothing specific, the rating rests on that absence, and the map
# draws it with a dashed outline so a reader can see which is which.
ZONES = {
    # ---- Lower Kleinbasel: the one part of Basel with current, official,
    # area-specific enforcement reporting.
    "Matthäus": ("yellow", "red", (
        "Basel's most mixed quarter and the centre of the city's open drug scene. "
        "Kantonspolizei Basel-Stadt ran a targeted operation here from 27 May 2026, "
        "naming the area between Claraplatz and the Dreirosenanlage — which is these "
        "streets — and describing organised street dealing; a wider operation in "
        "November 2025 across lower Kleinbasel and the railway station made 175 "
        "arrests and was aimed at violent and property crime as well as drugs. SRF "
        "reported in October 2025 that drugs are prepared and used in the open on "
        "Matthäusplatz from the afternoon onwards, in front of the playground and the "
        "church. The night rating is not about the drug scene itself, which is mostly "
        "a nuisance: it is about what has happened alongside it, including a man "
        "robbed at knifepoint at around 2am near the Matthäus and Klybeck street "
        "junction. By day this is an ordinary, busy, lived-in quarter. Sources: Kanton "
        "Basel-Stadt media release, 29 May 2026; SRF, 1 Oct 2025; BaZ; IG Kleinbasel."),
        "documented"),
    "Altstadt Kleinbasel": ("yellow", "yellow", (
        "The small old quarter on the right bank around Claraplatz, which the canton "
        "named on 29 May 2026 as one end of the corridor its drug-enforcement "
        "operation covers. Busy, central and well used; the documented problem is "
        "street dealing around the square and the Claragraben, reported as a policing "
        "and nuisance issue rather than a risk to passers-by. With 2,535 residents it "
        "is one of the smallest areas on this map, so a single street sets its "
        "character. Sources: Kanton Basel-Stadt media release, 29 May 2026; "
        "IG Kleinbasel."), "documented"),
    "Clara": ("green", "yellow", (
        "A small quarter of 4,507 people behind Claraplatz, next to the area covered "
        "by the canton's May 2026 drug-enforcement operation without being named in it. "
        "The Claragraben, on its edge, appears in residents' accounts of street "
        "dealing. Ordinary and walkable by day; the night rating reflects proximity to "
        "the lower Kleinbasel scene rather than anything reported here. Source: "
        "IG Kleinbasel."), "documented"),
    "Klybeck": ("green", "yellow", (
        "A former industrial quarter on the Rhine, now the city's largest "
        "redevelopment site. It sits inside the lower Kleinbasel area where the "
        "Kantonspolizei has concentrated its drug enforcement, and local politics have "
        "argued through 2025 and 2026 that Klybeck and Kleinhüningen carry more than "
        "their share of the city's asylum accommodation with too little daytime "
        "provision. That is a live civic argument about services, and it is reported "
        "as friction on the street rather than as crime against visitors. Few "
        "travellers stay here. Sources: Bajour; LDP Basel-Stadt position paper."),
        "documented"),
    "Kleinhüningen": ("green", "yellow", (
        "Basel's port quarter at the German and French border, 2,892 residents among "
        "docks, container terminals and the Dreiländereck. Grouped with Klybeck in "
        "the same civic argument about drug dealing and asylum housing in the lower "
        "Kleinbasel. Industrial and empty after working hours, which is the reason for "
        "the night rating: there is very little around. Sources: Bajour; LDP "
        "Basel-Stadt position paper."), "documented"),

    # ---- The station, where the other official operation ran.
    "Gundeldingen": ("green", "yellow", (
        "The dense residential quarter behind Basel SBB, 19,511 people, known locally "
        "as the Gundeli and one of the city's most mixed and liveable areas. The "
        "station itself falls inside it, and the canton has worked on it twice "
        "recently: a November 2025 operation covering the station and lower Kleinbasel "
        "that made 175 arrests, and a focused action from 13 January to 15 February "
        "2026 against violence in and around the station — 206 people checked, 30 "
        "arrested, eight of those for theft. The police reported the situation "
        "noticeably calmer by the end and said they would keep watching it. "
        "Station-area caution after dark; the residential streets south of the tracks "
        "are unremarkable. Source: Kanton Basel-Stadt media releases, November 2025 "
        "and February 2026."), "documented"),

    # ---- The tourist centre.
    "Altstadt Grossbasel": ("green", "yellow", (
        "The old town: Marktplatz, the Rathaus, Barfüsserplatz, and almost everything "
        "a visitor comes to Basel to see, with only 2,692 residents. Busy and heavily "
        "policed by day. The night rating is for Barfüsserplatz, the city's main "
        "going-out square, where alcohol-related incidents are occasionally reported — "
        "a man was arrested there in 2026 after a fight in which another was injured "
        "with a knife. Isolated, and the ordinary caution for a nightlife square "
        "applies rather than avoidance. Source: 20 Minuten, 2026."), "documented"),
    "Vorstädte": ("green", "green", (
        "The belt of townhouses, museums and the theatre immediately outside the old "
        "town, running down to the Steinen cinemas and the Kunstmuseum. 5,109 "
        "residents, quiet, and well used in the evening because of the theatres. "
        "Nothing area-specific was found in the source review."), "no_findings"),

    # ---- The two Landgemeinden, which have their own official figures.
    "Riehen": ("green", "green", (
        "A village that is also Basel-Stadt's second municipality, 22,885 people in "
        "gardens and vineyards on the German border, and the only area on this map "
        "besides Bettingen with a crime figure of its own: the canton publishes "
        "offences by Gemeinde, and Riehen recorded 1,447 criminal-code offences in "
        "2025, about 63 per 1,000 residents against roughly 147 per 1,000 for the city "
        "of Basel. Comfortable, green, well connected by tram, and a standard choice "
        "for families moving to the region. Source: data.bs.ch dataset 100508, 2025."),
        "documented"),
    "Bettingen": ("green", "green", (
        "The smallest municipality in Basel-Stadt, 1,312 people on the Chrischona hill "
        "above Riehen. The canton's own figures record 45 criminal-code offences here "
        "in 2025 — about 34 per 1,000 residents, the lowest in the canton and under a "
        "quarter of the city of Basel's rate. Rural, quiet, and a long way from "
        "anything; that is the point of it. Source: data.bs.ch dataset 100508, 2025."),
        "documented"),

    # ---- Residential Basel. Nothing area-specific found, and the dashed
    # outline says exactly that rather than implying a checked all-clear.
    "St. Johann": ("green", "green", (
        "Basel's largest quarter by population, 19,870 people, running along the Rhine "
        "from the old city wall to the Novartis campus and the French border. Young, "
        "mixed and increasingly expensive; the Voltaplatz end is ordinary residential "
        "city. Nothing area-specific was found in the source review."), "no_findings"),
    "Iselin": ("green", "green", (
        "A large working residential quarter of 18,193 people west of the centre, "
        "built mostly between the wars and rarely visited by anyone who does not live "
        "there. Nothing area-specific was found in the source review."), "no_findings"),
    "Bachletten": ("green", "green", (
        "Comfortable residential streets southwest of the centre, 13,938 residents, "
        "with the zoo at its edge. One of the city's steadiest addresses. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "St. Alban": ("green", "green", (
        "The old paper-mill quarter along the Rhine and the Letten canal, 12,765 "
        "people, running out to the Dreispitz. Historic, green and quiet. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Am Ring": ("green", "green", (
        "The ring of streets on the line of the demolished city wall, 11,614 "
        "residents, wrapping the old town from the Spalentor round to the "
        "Schützenmatte. Central without being the centre. Nothing area-specific was "
        "found in the source review."), "no_findings"),
    "Hirzbrunnen": ("green", "green", (
        "Garden suburb in the northeast, 10,004 people, with the Rheinpark and the "
        "sports grounds. Almost entirely residential. Nothing area-specific was found "
        "in the source review."), "no_findings"),
    "Bruderholz": ("green", "green", (
        "The hill above the city, 9,703 residents, detached houses, allotments and the "
        "water tower — Basel's most expensive address and its quietest. Nothing "
        "area-specific was found in the source review."), "no_findings"),
    "Breite": ("green", "green", (
        "Residential quarter east of St. Alban along the Rhine, 9,342 people, ordinary "
        "and unremarkable in the way most of Basel is. Nothing area-specific was found "
        "in the source review."), "no_findings"),
    "Rosental": ("green", "green", (
        "The trade-fair quarter around Messe Basel and the Rosentalanlage, 7,894 "
        "residents among exhibition halls and pharmaceutical offices. Busy during Art "
        "Basel and Baselworld, quiet the rest of the year. Nothing area-specific was "
        "found in the source review."), "no_findings"),
    "Gotthelf": ("green", "green", (
        "A small, tidy residential quarter of 7,256 people west of the centre, between "
        "Iselin and Bachletten. Nothing area-specific was found in the source review."),
        "no_findings"),
    "Wettstein": ("green", "green", (
        "The right-bank quarter opposite the old town, 5,906 residents, with the "
        "Museum Tinguely and the Solitude park along the Rhine. Well-off and calm, and "
        "named in local politics as the comparison other Kleinbasel quarters would "
        "like to be treated like. Nothing area-specific was found in the source "
        "review."), "no_findings"),
}


def main():
    if not os.path.isfile(GEOMETRY):
        raise SystemExit("run: python3 pipeline/fetch_basel.py > %s" % GEOMETRY)
    geo = json.load(io.open(GEOMETRY, encoding="utf-8"))

    zones = []
    for z in geo["zones"]:
        name = z["name"]
        if name not in ZONES:
            raise SystemExit("no rating written for %s" % name)
        day, night, text, evidence = ZONES[name]
        if name not in POPULATION:
            raise SystemExit("no population for %s" % name)
        zones.append({
            "name": name,
            "slug": z["slug"],
            "day": day,
            "night": night,
            "coords": z["coords"],
            "text": text,
            # Riehen and Bettingen are their own municipalities, so Booking can
            # tell them apart; the 19 Wohnviertel are all inside the city and
            # it cannot, which is why they resolve to Basel.
            "query": ("%s, Basel-Stadt, Switzerland" % name
                      if name in ("Riehen", "Bettingen")
                      else "Basel, Switzerland"),
            "booking_scope": "city",
            "evidence": evidence,
        })

    missing = set(ZONES) - {z["name"] for z in zones}
    if missing:
        raise SystemExit("rated areas absent from the boundary file: %s" % missing)

    out = {
        "label": "Basel, Switzerland",
        "center": [47.5596, 7.5886],
        "zoom": 12,
        "dataNote": (
            "Basel-Stadt records more offences per resident than any other Swiss "
            "canton, and a reader may well have met that headline. Two things are "
            "worth knowing before it does any work. First, it is a poor comparison: "
            "Basel-Stadt is the only canton that is nothing but a city, with no "
            "countryside to average against, on a triple border that brings daily "
            "foot traffic from two other countries. Second, and more useful, it is "
            "almost entirely a theft figure. Of the 27,467 criminal-code offences "
            "recorded in the city of Basel in 2025, 70% were against property and "
            "just 5% were against the person — and most of that 5% was minor assault. "
            "Vehicle theft alone was 20% of all recorded crime, of which 2,840 "
            "bicycles and 2,571 e-bikes. Criminologist Dirk Baier, asked about this "
            "exact ranking in March 2024, said Basel “is still a very safe city” and "
            "that the risk of serious violent attack is essentially zero. So the "
            "practical reading of Basel's rank is: lock the bike, watch the bag, and "
            "do not read it as a reason to avoid parts of the city. Neither the canton "
            "nor the Kantonspolizei publishes crime below municipality level, so the "
            "ratings for the 19 city quarters come from sourced reporting rather than "
            "a per-quarter figure; Riehen and Bettingen are separate municipalities "
            "and do have official figures of their own. Source for the breakdown: "
            "data.bs.ch dataset 100508, 2025."
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
