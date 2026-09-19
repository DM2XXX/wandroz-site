"""
Translate the per-area reasoning, once, and keep the result in the repository.

WHAT THIS TRANSLATES AND WHAT IT DOES NOT
    Only the prose written for one specific area — the paragraph that says what
    was found there and which sources said it. Everything else on a Wandroz
    page (titles, headings, ratings, cards, legend, limitations) is a bounded
    set of strings hand-written per language in i18n.py, where a person can
    read and correct every word. A machine gets the part that is too large for
    that and nothing else.

WHY THE OUTPUT IS COMMITTED
    Same reason the crime counts are: a build has to produce the same bytes
    tomorrow. A translation call inside build_site.py would make the site
    un-reproducible and put a metered API on the critical path of every
    rebuild. This runs by hand, writes data_i18n/<lang>/<city>.json, and the
    build only ever reads that.

WHY IT IS KEYED BY A HASH OF THE SOURCE
    When an area's reasoning is rewritten, its old translation is wrong and its
    neighbours' are still fine. A hash key re-translates exactly the one that
    changed and leaves 1,751 paid-for translations alone.

THE BUDGET IS FINITE AND THE MARGIN IS THIN
    The DeepL Free tier is a ONE-TIME credit of 1,000,000 characters, not a
    monthly allowance. The whole site needs about 926,000 of it. So this script
    refuses to start a run it cannot finish, asks DeepL what is actually left
    rather than trusting an estimate, and writes each city's results to disk as
    soon as they arrive — an interrupted run costs nothing to resume.

USAGE
    python3 pipeline/translate.py --lang it            # count, spend nothing
    python3 pipeline/translate.py --lang it --send     # actually translate
    python3 pipeline/translate.py --lang it --send --city milano
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_site as BS
import i18n

CACHE_DIR = os.path.join(HERE, "data_i18n")
API = "https://api-free.deepl.com/v2"
BATCH = 40          # DeepL accepts 50 texts per request; 40 leaves headroom


def key_of(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cache_path(lang, city_key):
    return os.path.join(CACHE_DIR, lang, "%s.json" % city_key)


def load_cache(lang, city_key):
    p = cache_path(lang, city_key)
    if os.path.isfile(p):
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(lang, city_key, data):
    p = cache_path(lang, city_key)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def cities_for(lang):
    """The cities whose own language is this one — the strategy the owner
    chose: English everywhere, plus the local language where it differs."""
    out = []
    for city_key, url_slug, label, flat in BS.mapped_cities():
        code = BS.city_country_code(label)
        if lang in i18n.languages_for_country_code(code):
            out.append((city_key, url_slug, label))
    return out


def texts_of(city_key):
    path = os.path.join(BS.ZONES_DIR, "%s.json" % city_key)
    if not os.path.isfile(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [(z["slug"], (z.get("text") or "").strip())
            for z in data.get("zones", []) if (z.get("text") or "").strip()]


def api(path, fields):
    key = os.environ.get("DEEPL_API_KEY")
    if not key:
        raise SystemExit("DEEPL_API_KEY is not set. See pipeline/translate.py's header.")
    cmd = ["curl", "-sS", "--max-time", "120",
           "-H", "Authorization: DeepL-Auth-Key %s" % key, "%s%s" % (API, path)]
    for k, v in fields:
        cmd += ["--data-urlencode", "%s=%s" % (k, v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("curl failed: %s" % r.stderr.strip()[:300])
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise SystemExit("DeepL did not return JSON: %s" % r.stdout[:300])


def remaining():
    u = api("/usage", [])
    return u["character_limit"] - u["character_count"], u


def main(lang, send, only_city):
    if lang not in i18n.LANGUAGES or lang == i18n.DEFAULT_LANG:
        raise SystemExit("--lang must be a declared non-English language: %s"
                         % ", ".join(i18n.extra_languages()))

    todo, already, plan = 0, 0, []
    for city_key, url_slug, label in cities_for(lang):
        if only_city and city_key != only_city:
            continue
        cache = load_cache(lang, city_key)
        # Deduplicato per contenuto, non per area: 41 dei 405 testi italiani
        # erano identici fra loro (la stessa frase di "nessun riscontro" su piu'
        # quartieri) e nella prima passata sono stati pagati due volte. La cache
        # e' gia' indicizzata per hash, quindi la seconda copia era denaro
        # buttato senza nemmeno un file in piu' da mostrare.
        seen, missing = set(), []
        for slug, t in texts_of(city_key):
            k = key_of(t)
            if k in cache or k in seen:
                continue
            seen.add(k)
            missing.append((slug, t))
        already += len(texts_of(city_key)) - len(missing)
        chars = sum(len(t) for _s, t in missing)
        todo += chars
        if missing:
            plan.append((city_key, label, missing, chars))

    print("Language: %s" % lang)
    print("Already translated and cached: %d area texts" % already)
    print("To translate now:              %d area texts, %s characters"
          % (sum(len(m) for _k, _l, m, _c in plan), format(todo, ",")))
    for city_key, label, missing, chars in plan:
        print("   %-14s %4d texts  %9s chars" % (city_key, len(missing), format(chars, ",")))

    if not plan:
        print("\nNothing to do — every area text for %s is already cached." % lang)
        return 0

    left, usage = remaining()
    print("\nDeepL credit: %s of %s left."
          % (format(left, ","), format(usage["character_limit"], ",")))

    if not send:
        print("\nDry run. Nothing was sent and nothing was spent.")
        print("Add --send to translate.")
        return 0

    # The one-time credit has no second chance, so a run that cannot finish
    # does not start. Half a city translated is worse than none: it leaves the
    # site mixing languages inside one page set.
    if todo > left:
        print("\nREFUSING: this run needs %s characters and %s are left."
              % (format(todo, ","), format(left, ",")))
        print("Translate one city at a time with --city, or top up the account.")
        return 1

    target = lang.upper()
    for city_key, label, missing, chars in plan:
        cache = load_cache(lang, city_key)
        print("\n%s — %d texts, %s chars" % (label, len(missing), format(chars, ",")))
        for i in range(0, len(missing), BATCH):
            chunk = missing[i:i + BATCH]
            fields = [("target_lang", target), ("source_lang", "EN"),
                      ("preserve_formatting", "1")]
            fields += [("text", t) for _s, t in chunk]
            out = api("/translate", fields)
            got = out.get("translations")
            if not got or len(got) != len(chunk):
                raise SystemExit("DeepL returned %s translations for %d texts: %s"
                                 % (len(got or []), len(chunk), str(out)[:300]))
            for (slug, src), tr in zip(chunk, got):
                cache[key_of(src)] = tr["text"]
            # Written after every batch, not at the end: an interruption must
            # never cost characters that were already paid for.
            save_cache(lang, city_key, cache)
            print("   +%d (%d/%d)" % (len(chunk), min(i + BATCH, len(missing)), len(missing)))

    left_after, _ = remaining()
    print("\nDone. DeepL credit left: %s." % format(left_after, ","))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--city", default=None)
    a = ap.parse_args()
    sys.exit(main(a.lang, a.send, a.city))
