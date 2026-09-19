"""
Wandroz — the translated layer.

WHAT IS IN HERE AND WHAT IS DELIBERATELY NOT
    Roughly 80% of a Wandroz page is generated from templates: the title, the
    headings, the rating wording, the recommendation cards, the legend, the
    limitations. That is a BOUNDED set of strings, and it is what this file
    holds — written out per language so every word can be read and corrected by
    a person rather than trusted to a machine.

    The other 20% is the reasoning written for one specific area: 1,752 unique
    paragraphs, 177,146 words, each carrying safety claims and naming local
    sources. None of that is here. It goes through a translation service whose
    output is cached in the repository like any other build input, and until a
    language has that cache, its pages show the paragraph in English and say
    so. Guessing at a translation of "no documented concerns" is the one
    failure this project cannot afford.

WHY A CATALOGUE AND NOT A TRANSLATION CALL AT BUILD TIME
    The same reason the crime counts are committed rather than fetched: a build
    must produce the same bytes tomorrow. A network call in the middle of one
    would make the site un-reproducible and put a metered API on the critical
    path of every rebuild.

HOW TO ADD A LANGUAGE
    Copy the "it" block, translate the values, add the code to LANGUAGES with
    the country codes it serves. check_i18n() in qa_full_site.py fails the
    build if a declared language is missing a key, so a half-finished language
    cannot reach production by being forgotten about.
"""

DEFAULT_LANG = "en"

# Language code -> (name in that language, the ISO country codes whose cities
# get this language alongside English). The country list is what decides which
# cities are rendered in which language: a reader in Milan searches in Italian,
# a reader going to Milan searches in English, and both should find the page.
LANGUAGES = {
    "en": ("English", ()),
    "it": ("Italiano", ("it",)),
}

STRINGS = {
    "en": {
        # --- chrome -------------------------------------------------------
        "tagline": "Neighbourhood safety for travellers",
        "nav_home": "Home",
        "nav_methodology": "Methodology",
        "methodology_arrow": "Methodology &rarr;",
        "city_label": "City",
        "other_languages": "Language",
        "footer_note": "in beta — coverage is expanding",
        "footer_about": "About",
        "footer_privacy": "Privacy",
        "footer_disclosure": "Affiliate disclosure",
        "footer_contact": "Contact",

        # --- map ----------------------------------------------------------
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
        "poi_art": "Art & history",
        "poi_view": "Views",
        "poi_green": "Green space",
        "poi_square": "Squares & walks",
        "poi_food": "Food markets",
        "poi_night": "Nightlife",
        "poi_all": "All",
        "unit_generic": "neighbourhoods",
        "sights_hidden": "Sights hidden",
        "burglary_toggle": "🔎 Real burglary data (by district)",
        "all_zones": "All neighbourhoods",
        "booking_cta": "Search accommodation here on Booking.com →",
        "see_full_page": "See the full page →",
        "not_covered": "Not covered by this dataset.",
        "click_hint": "Click an area on the map to see its level and the reasoning behind it.",

        # --- ratings ------------------------------------------------------
        "tone_green": "Relatively safer",
        "tone_yellow": "Average",
        "tone_red": "Higher caution advised",
        "tone_grey": "Not covered",

        # --- hub ----------------------------------------------------------
        "hub_title": "Where to stay in %(city)s: safest neighbourhoods compared | Wandroz",
        "hub_description": ("Every neighbourhood of %(city)s rated for daytime and night "
                            "safety on real administrative boundaries, with the reasoning "
                            "and the sources behind each rating."),
        "hub_h1": "Where to stay in %(city)s",
        "hub_lead": ("Every area rated for day and night, with the reasoning and the "
                     "sources behind each rating."),
        "hub_answer_head": "For a short stay in %(city)s: %(areas)s.",
        "hub_answer_more": ("One area for each kind of trip, each shown with its own day and "
                            "night rating — including where that rating says be careful."),
        "hub_answer_tail": "None of them is here because someone paid for it.",
        "list_and": "and",
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

        # --- recommendation cards ----------------------------------------
        "card_first_visit": "For a first visit",
        "card_family": "With family",
        "card_going_out": "For going out",
        "card_best": "Best rated overall",
        "find_a_place": "Find a place in %(area)s →",
        "why_first_visit": "%(n)d of the city's main sights are close enough to walk between",
        "why_first_visit_one": "one of the city's main sights is inside it",
        "why_family_one": "1 park within reach, and nothing here turns into a nightlife strip after dark",
        "why_family": "%(n)d parks within reach, and nothing here turns into a nightlife strip after dark",
        "why_going_out": "this is where the city's evening venues are concentrated",
        "why_best": "nowhere in the city is rated better, by day or after dark",

        # --- why a recommended area can be rated red ----------------------
        "caution_open_first_visit": "Still a practical base for a first visit",
        "caution_open_family": "Still a workable choice with family",
        "caution_open_going_out": "Still where the evening happens",
        "caution_open_best": "Still the best-rated area in the city",
        "caution_open_generic": "Still a practical choice",
        "caution_core_both": "the rating is driven by %(day)s during the day and %(night)s after dark",
        "caution_core_day": "the daytime rating is driven by %(day)s",
        "caution_core_night": "the night rating is driven by %(night)s",
        "caution_denominator": (", counted as a rate against the %(pop)s people registered as "
                                "living here rather than the far larger number who pass through"),
        "caution_closer": ("Take extra care, particularly after dark — that is what the rating "
                           "is for, not a reason to stay out of the area."),
        "caution_sights_here": "%(n)d of the city's main sights are inside it. ",
        "caution_snapshot": ("%(open)s. %(where)sThe city's published rate is counted per "
                             "registered resident, so a district that hosts many more people "
                             "than it houses reads higher. %(closer)s"),
        "caution_neutral": ("%(open)s, for its location and what is within walking distance of "
                            "it. The safety evidence points the other way, and the rating is a "
                            "reason to take extra care — particularly after dark — not by "
                            "itself a reason to avoid the area."),

        # --- crime categories, in plain words -----------------------------
        "cat_shoplifting": "shoplifting",
        "cat_burglary": "burglary",
        "cat_vehicle-crime": "vehicle crime",
        "cat_bicycle-theft": "bicycle theft",
        "cat_drugs": "drug offences",
        "cat_violent-crime": "violence",
        "cat_robbery": "robbery",
        "cat_theft-from-the-person": "pickpocketing",
        "cat_public-order": "public-order offences",
        "cat_anti-social-behaviour": "anti-social behaviour",

        # --- honesty about what is not translated -------------------------

        # --- FAQ dell'area -------------------------------------------------
        "desc_green": "relatively safer than most other neighbourhoods in %(city)s",
        "desc_yellow": "roughly average compared to other neighbourhoods in %(city)s",
        "desc_red": "an area where the data suggests extra caution relative to other neighbourhoods in %(city)s",
        "desc_grey": "not covered by this dataset",

        "faq_q_safe": "Is %(name)s safe?",
        "faq_q_night": "Is %(name)s safe at night?",
        "faq_q_daynight": "Does %(name)s's rating differ between day and night?",
        "faq_q_tourist": "Is %(name)s a good area to stay in as a tourist?",
        "faq_q_checked": "What was checked for %(name)s?",
        "faq_q_official": "Is there official crime data for %(name)s?",

        "basis_official": ("This rating is derived from %(source)s — an official statistic, not an "
                           "assessment. High-footfall tourist, transit or shopping areas can read "
                           "higher on this kind of measure without that meaning elevated risk per "
                           "visit, since these statistics are normalised against registered "
                           "residents rather than footfall — see the note on this page and the "
                           "methodology page for the full caveats."),
        "basis_research": ("This comes from a structured local-source assessment: an area-level "
                           "review of credible local sources — local and national news, municipal "
                           "and police-published material, and official surveys where they exist — "
                           "consolidated across sources rather than taken from a single report. "
                           "%(city)s publishes no comparable neighbourhood-level crime dataset; "
                           "where a city does, Wandroz uses it instead."),
        "basis_limited": ("This is a limited-data assessment: %(city)s publishes no "
                          "neighbourhood-level crime dataset and this area has not yet had a full "
                          "source review, so the rating is indicative and labelled as such rather "
                          "than presented as evidenced."),

        "faq_a_rating_same": ("Wandroz currently rates %(name)s in %(city)s as %(day)s, both by day "
                              "and after dark. %(basis)s"),
        "faq_a_rating_diff": ("Wandroz currently rates %(name)s in %(city)s as %(day)s during the "
                              "day and %(night)s at night. %(basis)s"),
        "faq_a_rating_notime": ("Wandroz currently rates %(name)s in %(city)s as %(day)s. %(basis)s "
                                "The source data has no day/night breakdown, so this single rating "
                                "applies at any time of day rather than being a distinct "
                                "night-specific figure."),
        "faq_a_night": ("At night, %(name)s is rated as %(night)s. If you're unsure, it's worth "
                        "checking recent local reviews for your specific street or block, since a "
                        "neighbourhood-wide rating can't capture block-by-block variation."),
        "faq_a_daynight": ("No — %(name)s's source data has no time-of-day breakdown, so the same "
                           "rating (%(day)s) is shown for both day and night rather than Wandroz "
                           "inventing a separate night figure it doesn't actually have."),
        "faq_a_tourist": ("%(name)s's day rating (%(day)s) is the more relevant one for typical "
                          "daytime tourist activity; check the night rating too if you'll be out "
                          "late. You can search accommodation already filtered to this specific "
                          "area using the Booking.com link on this page."),

        "faq_a_nofind_safe": ("Wandroz rates %(name)s in %(city)s as %(day)s. That rating rests on "
                              "an area-level review that reached no traveller-relevant reporting "
                              "specific to %(name)s — no incidents, no recurring problems, nothing "
                              "documented either way — read together with the character of the "
                              "area. It is not a positive finding of safety: an absence of "
                              "reporting is weaker evidence than the sourced ratings elsewhere on "
                              "this map, and it is marked as such wherever it appears."),
        "faq_a_nofind_checked": ("The same area-level review every other neighbourhood on the "
                                 "%(city)s map gets: local and national news, municipal and "
                                 "police-published material, and official surveys where they exist, "
                                 "searched for this specific area. %(name)s returned nothing "
                                 "traveller-relevant, which is common for smaller administrative "
                                 "areas without a press profile of their own. Where a review does "
                                 "return something, the sources are named on the area's page."),
        "faq_a_nofind_tourist": ("Nothing documented argues against it. For a stay, weigh that "
                                 "against the areas on the %(city)s map whose ratings are backed by "
                                 "named sources, and check recent reviews for the specific street. "
                                 "You can search accommodation already scoped to this area using "
                                 "the Booking.com link on this page."),

        "faq_a_official_yes": ("Yes. %(name)s's rating is derived from %(source)s, not an "
                               "assessment — see the note on this page for the exact figure and the "
                               "methodology page for full sourcing."),
        "faq_a_official_research": ("Not an official government crime feed — %(name)s's rating "
                                    "comes from Wandroz's own current local/national press and "
                                    "survey research for this specific area instead (see the note "
                                    "on this page for what was checked and the sources used). An "
                                    "absence of recent negative coverage is treated as "
                                    "inconclusive, not as proof the area is safe. If you live in or "
                                    "know %(name)s well, you can suggest a correction using the "
                                    "link below."),
        "faq_a_official_none": ("Not yet at neighbourhood level. Unlike London, this city does not "
                                "currently publish an open, geolocated crime dataset at this level "
                                "of detail (checked against the relevant local and national "
                                "open-data portals — see the methodology page for what was "
                                "checked). If you live in or know %(name)s well, you can suggest a "
                                "correction to its rating using the link below."),
        "source_generic": "a real official crime statistic",
        "untranslated_notice": ("The assessment text for this area has not been translated yet "
                                "and is shown in English."),
    },

    "it": {
        "tagline": "Sicurezza dei quartieri per chi viaggia",
        "nav_home": "Home",
        "nav_methodology": "Metodologia",
        "methodology_arrow": "Metodologia &rarr;",
        "city_label": "Città",
        "other_languages": "Lingua",
        "footer_note": "in beta — la copertura è in crescita",
        "footer_about": "Chi siamo",
        "footer_privacy": "Privacy",
        "footer_disclosure": "Informativa affiliazione",
        "footer_contact": "Contatti",

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
        "poi_art": "Arte e storia",
        "poi_view": "Panorami",
        "poi_green": "Verde",
        "poi_square": "Piazze e passeggiate",
        "poi_food": "Mercati e cibo",
        "poi_night": "Vita notturna",
        "poi_all": "Tutti",
        "unit_generic": "quartieri",
        "sights_hidden": "Luoghi nascosti",
        "burglary_toggle": "🔎 Dati reali sui furti in abitazione (per distretto)",
        "all_zones": "Tutti i quartieri",
        "booking_cta": "Cerca un alloggio qui su Booking.com →",
        "see_full_page": "Vedi la pagina completa →",
        "not_covered": "Non coperta da questi dati.",
        "click_hint": "Clicca un'area sulla mappa per vedere il suo livello e il ragionamento dietro.",

        "tone_green": "Relativamente più sicura",
        "tone_yellow": "Nella media",
        "tone_red": "Consigliata maggiore prudenza",
        "tone_grey": "Non coperta",

        "hub_title": "Dove dormire a %(city)s: i quartieri più sicuri a confronto | Wandroz",
        "hub_description": ("Ogni quartiere di %(city)s valutato per la sicurezza di giorno e "
                            "di notte sui confini amministrativi reali, con il ragionamento e "
                            "le fonti dietro a ogni valutazione."),
        "hub_h1": "Dove dormire a %(city)s: i quartieri più sicuri",
        "hub_lead": ("Ogni zona valutata di giorno e di notte, con il ragionamento e le fonti "
                     "dietro a ciascuna valutazione."),
        "hub_answer_head": "Per un soggiorno breve a %(city)s: %(areas)s.",
        "hub_answer_more": ("Una zona per ogni tipo di viaggio, ciascuna con la sua valutazione "
                            "di giorno e di notte — compreso dove quella valutazione dice di "
                            "stare attenti."),
        "hub_answer_tail": "Nessuna è qui perché qualcuno ha pagato.",
        "list_and": "e",
        "compare_all": "Confronta %(unit)s (%(n)d)",
        "table_note": ("Ordinate per quanto ciascuna zona si discosta dal resto della città, "
                       "non per valutazione: prima quelle fuori dalla norma. Clicca una colonna "
                       "per ordinarla come preferisci."),
        "col_area": "Zona",
        "col_day": "Giorno",
        "col_night": "Notte",
        "col_evidence": "Evidenza",
        "col_sights": "Luoghi",
        "col_book": "Prenota",
        "book_arrow": "Prenota →",
        "evidence_sourced": "con fonti",
        "evidence_none": "nessun riscontro specifico",

        "card_first_visit": "Per una prima visita",
        "card_family": "In famiglia",
        "card_going_out": "Per uscire la sera",
        "card_best": "Valutazione migliore",
        "find_a_place": "Cerca un alloggio a %(area)s →",
        "why_first_visit": "%(n)d dei luoghi principali della città sono abbastanza vicini da farli a piedi",
        "why_first_visit_one": "uno dei luoghi principali della città si trova qui dentro",
        "why_family_one": "un parco a portata di mano, e qui niente diventa una zona di locali dopo il tramonto",
        "why_family": "%(n)d parchi a portata di mano, e qui niente diventa una zona di locali dopo il tramonto",
        "why_going_out": "è qui che si concentrano i locali serali della città",
        "why_best": "nessuna zona della città è valutata meglio, né di giorno né dopo il tramonto",

        "caution_open_first_visit": "Resta una base pratica per una prima visita",
        "caution_open_family": "Resta una scelta praticabile in famiglia",
        "caution_open_going_out": "Resta il posto dove si passa la sera",
        "caution_open_best": "Resta la zona meglio valutata della città",
        "caution_open_generic": "Resta una scelta pratica",
        "caution_core_both": "la valutazione è trainata da %(day)s di giorno e da %(night)s dopo il tramonto",
        "caution_core_day": "la valutazione diurna è trainata da %(day)s",
        "caution_core_night": "la valutazione notturna è trainata da %(night)s",
        "caution_denominator": (", contata come tasso sui %(pop)s residenti registrati qui e non "
                                "sul numero ben più alto di persone che ci passano"),
        "caution_closer": ("Serve prudenza in più, soprattutto dopo il tramonto — è a questo che "
                           "serve la valutazione, non a stare alla larga dalla zona."),
        "caution_sights_here": "%(n)d dei luoghi principali della città si trovano qui dentro. ",
        "caution_snapshot": ("%(open)s. %(where)sIl tasso pubblicato dalla città è contato per "
                             "residente registrato, quindi un distretto che ospita molte più "
                             "persone di quante ne abiti risulta più alto. %(closer)s"),
        "caution_neutral": ("%(open)s, per la posizione e per quello che ha a portata di piedi. "
                            "L'evidenza sulla sicurezza dice il contrario, e la valutazione è un "
                            "motivo per fare più attenzione — soprattutto dopo il tramonto — non "
                            "di per sé un motivo per evitare la zona."),

        "cat_shoplifting": "taccheggio",
        "cat_burglary": "furti in abitazione",
        "cat_vehicle-crime": "reati contro i veicoli",
        "cat_bicycle-theft": "furti di biciclette",
        "cat_drugs": "reati di droga",
        "cat_violent-crime": "violenza",
        "cat_robbery": "rapine",
        "cat_theft-from-the-person": "borseggio",
        "cat_public-order": "reati contro l'ordine pubblico",
        "cat_anti-social-behaviour": "comportamenti antisociali",


        # --- FAQ dell'area -------------------------------------------------
        "desc_green": "relativamente più sicura della maggior parte degli altri quartieri di %(city)s",
        "desc_yellow": "nella media rispetto agli altri quartieri di %(city)s",
        "desc_red": "una zona in cui i dati suggeriscono maggiore prudenza rispetto agli altri quartieri di %(city)s",
        "desc_grey": "non coperta da questi dati",

        "faq_q_safe": "%(name)s è una zona sicura?",
        "faq_q_night": "%(name)s è sicura di notte?",
        "faq_q_daynight": "La valutazione di %(name)s cambia fra giorno e notte?",
        "faq_q_tourist": "%(name)s è una buona zona dove alloggiare da turista?",
        "faq_q_checked": "Che cosa è stato verificato per %(name)s?",
        "faq_q_official": "Esistono dati ufficiali sulla criminalità per %(name)s?",

        "basis_official": ("Questa valutazione deriva da %(source)s — una statistica ufficiale, non "
                           "una stima. Le zone con molto passaggio — turismo, trasporti, negozi — "
                           "possono risultare più alte su una misura di questo tipo senza che questo "
                           "significhi un rischio maggiore per il singolo visitatore, perché queste "
                           "statistiche sono rapportate ai residenti registrati e non alle persone "
                           "che ci passano: vedi la nota su questa pagina e la pagina della "
                           "metodologia per i limiti completi."),
        "basis_research": ("Deriva da una valutazione strutturata su fonti locali: una revisione "
                           "area per area di fonti credibili — stampa locale e nazionale, materiale "
                           "pubblicato da comune e forze dell'ordine, e indagini ufficiali dove "
                           "esistono — messe a confronto fra loro invece che prese da un singolo "
                           "articolo. %(city)s non pubblica un dataset comparabile sulla criminalità "
                           "a livello di quartiere; dove una città lo fa, Wandroz usa quello."),
        "basis_limited": ("Questa è una valutazione con dati limitati: %(city)s non pubblica un "
                          "dataset sulla criminalità a livello di quartiere e per quest'area non è "
                          "ancora stata completata una revisione delle fonti, quindi la valutazione "
                          "è indicativa ed è dichiarata come tale invece di essere presentata come "
                          "documentata."),

        "faq_a_rating_same": ("Wandroz valuta attualmente %(name)s a %(city)s come %(day)s, sia di "
                              "giorno sia dopo il tramonto. %(basis)s"),
        "faq_a_rating_diff": ("Wandroz valuta attualmente %(name)s a %(city)s come %(day)s di giorno "
                              "e %(night)s di notte. %(basis)s"),
        "faq_a_rating_notime": ("Wandroz valuta attualmente %(name)s a %(city)s come %(day)s. "
                                "%(basis)s I dati di partenza non distinguono fra giorno e notte, "
                                "quindi questa singola valutazione vale a qualunque ora invece di "
                                "essere un dato notturno a sé."),
        "faq_a_night": ("Di notte %(name)s è valutata come %(night)s. Se hai dubbi, vale la pena "
                        "leggere recensioni recenti sulla tua strada o sul tuo isolato: una "
                        "valutazione che copre tutto il quartiere non può cogliere le differenze da "
                        "un isolato all'altro."),
        "faq_a_daynight": ("No — i dati di partenza di %(name)s non distinguono le ore del giorno, "
                           "quindi la stessa valutazione (%(day)s) vale sia di giorno sia di notte, "
                           "invece che Wandroz si inventi un dato notturno che non ha."),
        "faq_a_tourist": ("La valutazione diurna di %(name)s (%(day)s) è quella più utile per una "
                          "giornata da turista; se pensi di stare fuori fino a tardi guarda anche "
                          "quella notturna. Puoi cercare un alloggio già circoscritto a questa zona "
                          "con il link Booking.com su questa pagina."),

        "faq_a_nofind_safe": ("Wandroz valuta %(name)s a %(city)s come %(day)s. Quella valutazione "
                              "poggia su una revisione area per area che non ha trovato alcuna "
                              "segnalazione rilevante per chi viaggia specifica di %(name)s — nessun "
                              "episodio, nessun problema ricorrente, niente di documentato né in un "
                              "senso né nell'altro — letta insieme al carattere della zona. Non è un "
                              "riscontro positivo di sicurezza: un'assenza di segnalazioni è "
                              "un'evidenza più debole delle valutazioni con fonti che trovi altrove "
                              "su questa mappa, ed è indicata come tale ovunque compaia."),
        "faq_a_nofind_checked": ("La stessa revisione area per area che riceve ogni altro quartiere "
                                 "sulla mappa di %(city)s: stampa locale e nazionale, materiale "
                                 "pubblicato da comune e forze dell'ordine, e indagini ufficiali "
                                 "dove esistono, cercati per questa specifica zona. Per %(name)s non "
                                 "è emerso nulla di rilevante per chi viaggia, cosa comune per le "
                                 "suddivisioni amministrative più piccole che non hanno una propria "
                                 "presenza sulla stampa. Dove una revisione trova qualcosa, le fonti "
                                 "sono indicate sulla pagina dell'area."),
        "faq_a_nofind_tourist": ("Niente di documentato dice il contrario. Per un soggiorno, mettilo "
                                 "a confronto con le zone della mappa di %(city)s le cui valutazioni "
                                 "sono sostenute da fonti citate, e leggi recensioni recenti sulla "
                                 "strada specifica. Puoi cercare un alloggio già circoscritto a "
                                 "questa zona con il link Booking.com su questa pagina."),

        "faq_a_official_yes": ("Sì. La valutazione di %(name)s deriva da %(source)s, non da una "
                               "stima — vedi la nota su questa pagina per la cifra esatta e la "
                               "pagina della metodologia per le fonti complete."),
        "faq_a_official_research": ("Non da un flusso ufficiale di dati governativi — la valutazione "
                                    "di %(name)s viene invece dalla ricerca di Wandroz su stampa "
                                    "locale e nazionale e su indagini, condotta per questa specifica "
                                    "zona (vedi la nota su questa pagina per cosa è stato verificato "
                                    "e con quali fonti). L'assenza di notizie negative recenti è "
                                    "trattata come non conclusiva, non come prova che la zona sia "
                                    "sicura. Se abiti a %(name)s o la conosci bene, puoi segnalare "
                                    "una correzione con il link qui sotto."),
        "faq_a_official_none": ("Non ancora a livello di quartiere. A differenza di Londra, questa "
                                "città non pubblica al momento un dataset aperto e geolocalizzato "
                                "sulla criminalità a questo livello di dettaglio (verificato sui "
                                "portali open data locali e nazionali competenti — vedi la pagina "
                                "della metodologia per cosa è stato controllato). Se abiti a "
                                "%(name)s o la conosci bene, puoi segnalare una correzione con il "
                                "link qui sotto."),
        "source_generic": "una vera statistica ufficiale sulla criminalità",
        "untranslated_notice": ("Il testo di valutazione di quest'area non è ancora tradotto ed è "
                                "mostrato in inglese."),
    },
}


# Nomi di luogo, dove la lingua li cambia. Solo le eccezioni: "Bologna" o
# "Parma" non hanno bisogno di una riga, e una tabella piena di identita' e'
# una tabella che nessuno rilegge. Una pagina italiana che si intitola "Dove
# dormire a Milan" si autodenuncia come traduzione automatica al primo sguardo.
PLACE_NAMES = {
    "it": {
        "Milan": "Milano", "Rome": "Roma", "Turin": "Torino", "Naples": "Napoli",
        "Venice": "Venezia", "Florence": "Firenze", "Genoa": "Genova",
        "Italy": "Italia",
    },
}


def place(lang, name):
    return PLACE_NAMES.get(lang, {}).get(name, name)


def local_label(lang, label):
    """"Milan, Italy" -> "Milano, Italia". Tradotto pezzo per pezzo perche' la
    seconda meta' e' il paese e cambia anch'essa."""
    return ", ".join(place(lang, part.strip()) for part in label.split(","))


def strings(lang):
    """The catalogue for a language, with English filling any gap.

    The fallback keeps a build from dying on a missing key, but it is not a
    licence to ship gaps: check_i18n() turns one into a failed build.
    """
    base = dict(STRINGS[DEFAULT_LANG])
    base.update(STRINGS.get(lang, {}))
    return base


def missing_keys(lang):
    """Keys a declared language has not translated. Empty is the only shippable
    state, and the QA gate enforces that."""
    return sorted(set(STRINGS[DEFAULT_LANG]) - set(STRINGS.get(lang, {})))


def extra_languages():
    return [c for c in LANGUAGES if c != DEFAULT_LANG]


def languages_for_country_code(code):
    """Which non-English languages a city in this country should also exist in."""
    return [c for c, (_, codes) in LANGUAGES.items() if code in codes]


def url_for(lang, path):
    """English keeps the bare paths it has always had. Moving them under /en/
    would throw away every URL Google has indexed, for no gain."""
    path = "/" + path.lstrip("/")
    return path if lang == DEFAULT_LANG else "/%s%s" % (lang, path)
