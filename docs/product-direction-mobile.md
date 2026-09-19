# Product direction — Wandroz mobile / live map

> **DO NOT IMPLEMENT NOW — future product decision, recorded on 19 September 2026.**
>
> This is the owner's long-term direction, kept here so it is not lost. Nothing
> in it is a current work item. The only thing it should influence today is a
> negative one, stated in the text itself: do not create new coupling between
> the scoring, the geography, the POIs and the website's presentation that
> would make a second interface expensive later.

## One correction, before the text

The section below headed **KEY FUTURE FEATURE: SEARCH ANY PLACE** is listed as
a bridge to build *after* pilots. **It already exists and is live.**

The homepage carries an address search that geocodes a free-text address,
matches it against the real Wandroz polygons with a point-in-polygon test, and
lands the reader on that neighbourhood's page. Verified end to end on
19 September 2026:

| Query | Result |
|---|---|
| Prinsengracht 263, Amsterdam | Grachtengordel-West |
| Royal Crescent, Bath | Kingsmead |
| Via Garibaldi 3, Genova | Centro storico e caruggi |
| 10 Downing Street, London | Westminster |
| Piazza Duomo, Trento | reported as not covered, after fetching 5 kB and no city file |

All 62 cities are searchable this way; the geocoder's country list is derived
from the flag emoji so it widens by itself. The implementation is in
`pipeline/templates/index.html` (`tryAddressSearch`, `pointInRing`,
`boxesContaining`) and `build_city_boundaries()` in `pipeline/build_site.py`.

What does *not* exist yet from that section is hotel-name lookup — the search
resolves addresses and place names through Nominatim, which finds some hotels
and not others, and there is no hotel index of our own.

So this section is not roadmap. It is something to tell a pilot customer they
can use today.

---

## Owner's text, verbatim

PRODUCT DIRECTION — WANDROZ MOBILE / LIVE MAP

Keep this as a future product decision and architectural direction. DO NOT BUILD THIS NOW.

The long-term consumer vision for Wandroz is NOT simply to package the current website into an iOS/Android app. The useful app concept is: "Wandroz as a live safety + traveller context layer over a familiar map."

IMPORTANT TECHNICAL DISTINCTION

The goal would ideally be to open the normal Google Maps consumer app and enable a Wandroz add-on/layer. However, Google Maps does not currently provide a general third-party plugin system that would allow Wandroz to inject its polygons, POIs and safety data directly into the standard Google Maps consumer app. Therefore the realistic architecture is:

WANDROZ APP → Google Maps / equivalent mapping SDK as base map + Wandroz proprietary layers → Google Maps app for actual navigation when requested.

The user experience should nevertheless feel like: "Google Maps + Wandroz intelligence."

CORE FUTURE EXPERIENCE

A traveller opens Wandroz while physically in a city. The map immediately shows: current GPS position; Wandroz neighbourhood boundaries; safety areas colour-coded according to Wandroz; curated tourist POIs; important sights; neighbourhood names; traveller-relevant area context.

Example:

📍 You are here — St Peter and the Waterfront — Higher caution advised. Central visitor area with elevated recorded incidents. Extra awareness is recommended rather than avoidance. Nearby: Plymouth Hoe, Mayflower Steps, National Marine Aquarium.

The user can tap:

AREA → safety assessment → interpretation → evidence/source → traveller context → places to stay
POI → attraction information → neighbourhood → safety context
HOTEL / ADDRESS → identify automatically which Wandroz area contains it → show area assessment
DIRECTIONS → open Google Maps for actual turn-by-turn navigation.

Wandroz should NOT try to replace Google Maps navigation. Google Maps answers "How do I get there?"; Wandroz answers "What is this area like, and what should I know about it?"

KEY FUTURE FEATURE: SEARCH ANY PLACE

An important bridge between the current product, B2B product and future app is: SEARCH ANY ADDRESS / HOTEL / PLACE.

Example: user searches "Keizersgracht 123" or "Hotel XYZ Amsterdam". Wandroz: 1. geocodes the location; 2. performs point-in-polygon matching against Wandroz geography; 3. identifies the relevant neighbourhood; 4. returns the Wandroz safety assessment; 5. explains important limitations/context; 6. shows nearby relevant POIs.

This avoids requiring users to know administrative neighbourhood names. Valuable for BOTH consumers ("Is the area around my hotel/Airbnb a good place to stay?") and B2B relocation ("What is the neighbourhood around this apartment we're proposing to a client?"). Therefore this functionality may be worth building BEFORE a native app if customer/pilot feedback supports it.

WHY AN APP COULD EVENTUALLY MAKE SENSE

The current website is primarily BEFORE THE TRIP: city → neighbourhood → safety. The future mobile product could become DURING THE TRIP: my location → neighbourhood → safety context → nearby sights → navigation. This creates a genuine reason to install Wandroz.

Do NOT build a native app merely to reproduce existing website pages. An app becomes justified when location awareness and repeated in-city usage materially improve the product.

RELATIONSHIP WITH B2B

The same core infrastructure should ideally support: consumer website, consumer mobile app, relocation dashboard, client-facing reports, embeddable widget, API/data licensing. The valuable underlying asset is the WANDROZ NEIGHBOURHOOD INTELLIGENCE LAYER, not any single interface.

Therefore avoid future architectural decisions that unnecessarily couple scoring, geography, POIs, interpretation and source metadata to the current website presentation. Where reasonable, these should remain structured reusable data that could later be consumed by multiple interfaces.

Do NOT refactor the whole project now purely for this future possibility. Just avoid creating obvious new technical debt that would prevent reuse later.

WHEN TO BUILD

CURRENT PHASE: do NOT build native app. Priorities remain: 1. stabilise and improve current Wandroz product; 2. continue B2B outreach; 3. get conversations with relocation companies; 4. validate actual use cases; 5. obtain pilot(s); 6. observe how users/customers actually use Wandroz.

AFTER INITIAL VALIDATION: if pilots show demand for address/property-level neighbourhood lookup, build search address/place → point-in-polygon → Wandroz neighbourhood intelligence, potentially as a web/B2B feature first.

NEXT: test a mobile-first "Explore Map" experience on the web/PWA: current location + safety polygons + POIs + area context.

Only after usage demonstrates that people benefit from accessing this repeatedly while physically moving around cities should we consider a native iOS/Android Wandroz app.

DECISION GATES

Do not start native app development simply because it is technically possible. Revisit the app when at least one of these signals appears:

A. Consumer users repeatedly access Wandroz from mobile while travelling.
B. Users frequently search hotels/addresses/POIs rather than neighbourhood names.
C. B2B clients explicitly request location/address lookup or live map functionality.
D. A pilot demonstrates that the map layer materially improves relocation decisions.
E. Wandroz develops enough recurring consumer usage that installation/retention has a credible benefit.

Until then: WEB FIRST. DATA LAYER FIRST. VALIDATION FIRST. APP LATER.

STRATEGIC PRINCIPLE

Do not try to build another Google Maps. Google owns navigation and exhaustive place discovery. Wandroz should own the interpretation layer: WHERE AM I? WHAT AREA IS THIS? WHAT DOES THE SAFETY DATA ACTUALLY MEAN? IS THIS A PRACTICAL AREA FOR MY TRIP / HOME SEARCH? WHAT IMPORTANT PLACES ARE AROUND ME?

That is the long-term product direction. Record this as a future product/architecture decision only. Do not implement it as part of the current work.

---

## Where today's code already meets this direction, and where it does not

Recorded so a future reader does not have to re-derive it.

**Already reusable, as the text asks:** the boundary geometry is published per
city as `/<city>/boundaries.json` with a `city-boxes.json` index — a second
interface can consume those without touching the website. The per-area ratings,
evidence class, sources and POIs all live in `pipeline/data_zones/*.json` and
`pipeline/data_poi/*.json`, which are structured data the site renders rather
than data the site owns.

**Not reusable yet, and the debt to avoid deepening:** the interpretation —
the sentence that explains what a rating means, the caution note, the FAQ — is
generated inside `build_site.py` at render time and exists only as HTML. A
second interface would have to re-implement it. If an API or an app is ever
built, that logic wants to move behind a function that returns structured
interpretation, with the templates as one consumer among several.
