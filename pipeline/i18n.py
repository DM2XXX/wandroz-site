"""
Wandroz — the translated layer.

WHAT IS IN HERE AND WHAT IS DELIBERATELY NOT
    Roughly 80% of a Wandroz page is generated from templates: the title, the
    headings, the rating wording, the FAQ questions, the legend, the
    limitations. That is a BOUNDED set of strings — about eighty of them — and
    it is what this file holds, written out per language so every word can be
    read and corrected by a person.

    The other 20% is the reasoning written for one specific area: 1,752 unique
    paragraphs, 177,146 words, each carrying safety claims and naming local
    sources. None of that is here. It needs a translation service, its output
    will be cached in the repository like any other build input, and until then
    a translated page shows that paragraph in English and says so. Guessing at
    a translation of "no documented concerns" is the one failure this project
    cannot afford.

WHY A CATALOGUE AND NOT A TRANSLATION CALL AT BUILD TIME
    Same reason the crime counts are committed rather than fetched: a build
    must produce the same bytes tomorrow. A network call in the middle of it
    would make the site un-reproducible and put a paid API on the critical
    path of every rebuild.

HOW TO ADD A LANGUAGE
    Copy the "it" block, translate the values, add the code to LANGUAGES. The
    QA gate fails the build if a declared language is missing a key, so a
    half-finished language cannot reach production by being forgotten.
"""

# Language code -> the name shown in the language switcher, in that language.
LANGUAGES = {
    "en": "English",
    "it": "Italiano",
}

DEFAULT_LANG = "en"

# The strings the city hub and its template need. English is the reference:
# every other language must define exactly these keys.
STRINGS = {
    "en": {
        "tagline": "Neighbourhood safety for travellers",
        "nav_home": "Home",
        "nav_methodology": "Methodology",
        "methodology_link": "Methodology &rarr;",
        "label_day": "day",
        "label_night": "night",
        "legend_green": "Calm — no particular concern",
        "legend_yellow": "Caution — fine by day, be more careful in the evening/night",
        "legend_red": "Not recommended for a tourist — known, recurring issues",
        "legend_grey": "Not covered by this dataset",
        "legend_dashed": "Dashed outline: no area-specific findings",
        "sights_heading": "Sights on this map",
        "reset_view": "Reset view",
        "hide_sights": "Hide sights",
        "burglary_toggle": "🔎 Real burglary data (by district)",
        "city_label": "City",
        "compare_all": "Compare all %(n)d %(unit)s",
        "table_note": ("Ordered by how much each area differs from the rest of the city, "
                       "not by rating — the unusual ones first. Click a column to sort it "
                       "your way."),
        "col_area": "Area",
        "col_day": "Day",
        "col_night": "Night",
        "col_evidence": "Evidence",
        "col_sights": "Sights",
        "col_book": "Book",
        "book_arrow": "Book →",
        "evidence_sourced": "sourced",
        "evidence_none": "no area-specific findings",
        "all_zones": "All neighbourhoods",
        "booking_cta": "Search accommodation here on Booking.com →",
        "see_full_page": "See the full page →",
        "card_first_visit": "For a first visit",
        "card_family": "With family",
        "card_going_out": "For going out",
        "card_best": "Best rated overall",
        "tone_green": "Relatively safer",
        "tone_yellow": "Average",
        "tone_red": "Higher caution advised",
        "tone_grey": "Not covered",
        "hub_h1": "Where to stay in %(city)s",
        "hub_lead": ("Every area rated for day and night, with the reasoning and the "
                     "sources behind each rating."),
        "hub_answer": ("For a short stay in %(city)s: %(areas)s. One area for each kind of "
                       "trip, each shown with its own day and night rating — including "
                       "where that rating says be careful. None of them is here because "
                       "someone paid for it."),
        "hub_title": "Where to stay in %(city)s: safest neighbourhoods compared | Wandroz",
        "hub_description": ("Every neighbourhood of %(city)s rated for daytime and night "
                            "safety on real administrative boundaries, with the reasoning "
                            "and the sources behind each rating."),
        "footer_about": "About",
        "footer_privacy": "Privacy",
        "footer_disclosure": "Affiliate disclosure",
        "footer_contact": "Contact",
        "footer_note": "in beta — coverage is expanding",
        "other_languages": "Other languages",
        # Shown where a page is translated but the per-area reasoning is not.
        "untranslated_notice": ("The assessment text for this area has not been translated "
                                "yet and is shown in English."),
    },

    "it": {
        "tagline": "Sicurezza dei quartieri per chi viaggia",
        "nav_home": "Home",
        "nav_methodology": "Metodologia",
        "methodology_link": "Metodologia &rarr;",
        "label_day": "giorno",
        "label_night": "notte",
        "legend_green": "Tranquillo — nessun problema segnalato",
        "legend_yellow": "Attenzione — di giorno va bene, la sera serve più prudenza",
        "legend_red": "Sconsigliato a chi visita — problemi noti e ricorrenti",
        "legend_grey": "Non coperto da questi dati",
        "legend_dashed": "Contorno tratteggiato: nessun riscontro specifico per l'area",
        "sights_heading": "Cosa vedere su questa mappa",
        "reset_view": "Ripristina vista",
        "hide_sights": "Nascondi i luoghi",
        "burglary_toggle": "🔎 Dati reali sui furti in abitazione (per distretto)",
        "city_label": "Città",
        "compare_all": "Confronta %(unit)s (%(n)d)",
        "table_note": ("Ordinati per quanto ciascuna zona si discosta dal resto della "
                       "città, non per valutazione: prima quelle fuori dalla norma. "
                       "Clicca una colonna per ordinarla come preferisci."),
        "col_area": "Zona",
        "col_day": "Giorno",
        "col_night": "Notte",
        "col_evidence": "Evidenza",
        "col_sights": "Luoghi",
        "col_book": "Prenota",
        "book_arrow": "Prenota →",
        "evidence_sourced": "con fonti",
        "evidence_none": "nessun riscontro specifico",
        "all_zones": "Tutti i quartieri",
        "booking_cta": "Cerca un alloggio qui su Booking.com →",
        "see_full_page": "Vedi la pagina completa →",
        "card_first_visit": "Per una prima visita",
        "card_family": "In famiglia",
        "card_going_out": "Per uscire la sera",
        "card_best": "Valutazione migliore",
        "tone_green": "Relativamente più sicura",
        "tone_yellow": "Nella media",
        "tone_red": "Consigliata maggiore prudenza",
        "tone_grey": "Non coperta",
        "hub_h1": "Dove dormire a %(city)s: i quartieri più sicuri",
        "hub_lead": ("Ogni zona valutata di giorno e di notte, con il ragionamento e le "
                     "fonti dietro a ciascuna valutazione."),
        "hub_answer": ("Per un soggiorno breve a %(city)s: %(areas)s. Una zona per ogni "
                       "tipo di viaggio, ciascuna con la sua valutazione di giorno e di "
                       "notte — compreso dove quella valutazione dice di stare attenti. "
                       "Nessuna è qui perché qualcuno ha pagato."),
        "hub_title": "Dove dormire a %(city)s: quartieri più sicuri a confronto | Wandroz",
        "hub_description": ("Ogni quartiere di %(city)s valutato per la sicurezza di giorno "
                            "e di notte sui confini amministrativi reali, con il "
                            "ragionamento e le fonti dietro a ogni valutazione."),
        "footer_about": "Chi siamo",
        "footer_privacy": "Privacy",
        "footer_disclosure": "Informativa affiliazione",
        "footer_contact": "Contatti",
        "footer_note": "in beta — la copertura è in crescita",
        "other_languages": "Altre lingue",
        "untranslated_notice": ("Il testo di valutazione di quest'area non è ancora "
                                "tradotto ed è mostrato in inglese."),
    },
}


def strings(lang):
    """The catalogue for a language, falling back to English per key.

    The fallback exists so a missing key renders readable English rather than a
    KeyError mid-build — but it is not a licence to ship gaps: check_i18n() in
    qa_full_site.py fails the build when a declared language is missing one.
    """
    base = dict(STRINGS[DEFAULT_LANG])
    base.update(STRINGS.get(lang, {}))
    return base


def missing_keys(lang):
    """Keys a language has not translated yet. Empty is the only shippable state."""
    ref = set(STRINGS[DEFAULT_LANG])
    return sorted(ref - set(STRINGS.get(lang, {})))


def url_for(lang, path):
    """English keeps the bare paths it has always had — moving them to /en/
    would throw away every URL Google has indexed. Other languages live under
    their own prefix."""
    path = path.lstrip("/")
    return "/%s" % path if lang == DEFAULT_LANG else "/%s/%s" % (lang, path)
