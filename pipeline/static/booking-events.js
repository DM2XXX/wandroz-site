/* Outbound Booking clicks, reported to GA4.
 *
 * WHY THIS EXISTS
 *   The site had analytics and no idea whether anyone ever clicked the thing it
 *   is monetised by. Every number about conversion was therefore an estimate of
 *   an estimate. This records the one event that matters — someone leaving for
 *   Booking — with enough detail to answer the two questions that keep coming
 *   up: which cities produce clicks, and what share of those clicks are on a
 *   link that can actually earn (only seven cities are inside an approved
 *   programme today).
 *
 * WHY A DELEGATED LISTENER
 *   The CTA is rendered in several places — a neighbourhood page, a London
 *   borough page, the recommendation cards on a city hub, the row of the
 *   comparison table. Binding at click time on the document catches all of
 *   them with one listener and cannot miss one that is added later.
 *
 *   It used to also catch a CTA built in JavaScript inside the map's detail
 *   card. That card is gone: clicking a zone now darkens it and opens the
 *   area's own page. So the old "map-card" surface no longer exists, and a
 *   report that still expects it is reading a value nothing emits.
 *
 * It never blocks or delays the navigation: the event is sent and the browser
 * follows the link as it normally would. A click that GA4 misses is a lost
 * data point, not a lost booking.
 */
(function () {
  var CJ_HOST = /(^|\.)(jdoqocy|tkqlhce|dpbolvw|anrdoezrs|kqzyfj)\.(com|net)$/;

  function bookingLink(el) {
    while (el && el !== document) {
      if (el.tagName === "A" && el.href) {
        var host;
        try { host = new URL(el.href).hostname; } catch (e) { return null; }
        if (host === "www.booking.com" || host === "booking.com") return { a: el, attributed: false };
        if (CJ_HOST.test(host)) return { a: el, attributed: true };
      }
      el = el.parentNode;
    }
    return null;
  }

  // The city is in the path (/bologna/navile.html), which is more reliable than
  // anything we could stamp on the link and survives the map's dynamic cards.
  function pathParts() {
    var p = location.pathname.replace(/^\/|\.html$/g, "").split("/");
    return { city: p[0] || "home", area: p.length > 1 && p[1] ? p[1] : "(city hub)" };
  }

  document.addEventListener("click", function (ev) {
    var hit = bookingLink(ev.target);
    if (!hit || typeof window.gtag !== "function") return;
    var where = pathParts();
    window.gtag("event", "booking_click", {
      city: where.city,
      area: where.area,
      attributed: hit.attributed ? "yes" : "no",
      // Present so a report can separate the three intents: someone acting on
      // a recommendation card, someone picking a row out of the comparison
      // table, and someone who already read a whole area page.
      surface: (hit.a.classList && hit.a.classList.contains("bk")) ? "hub-card"
               : (where.area === "(city hub)" ? "hub-table" : "area-page"),
      transport_type: "beacon"
    });
  }, true);
})();
