"""Collect public App Store data (PUBLIC DATA).

1. Comparable apps (France and US): average rating, number of ratings, star distribution, from
   Apple's public iTunes Search API and each app's public App Store page.
2. Joko reviews: the reviews shown on Joko's public App Store pages today (several storefronts),
   plus the reviews and rating headers shown on archived copies of those pages in the Wayback
   Machine (max one snapshot per month), 2019-2026.
   Note: Apple's customer-review RSS feed returned empty feeds for every app on 2026-11-11,
   so it could not be used.
3. Joko's recent version history (version number + release date) from the public page.

Privacy: reviewer nicknames are never stored (dropped while parsing, before writing to disk).
"""
import json
import re

from bs4 import BeautifulSoup

from common import RAW, TODAY, cached_get_text, polite_get, save_json

JOKO_ID = 1378996692
APPS = {  # (country, search term) -> keyword that must appear in the app name
    ("fr", "joko"): "joko", ("fr", "igraal"): "igraal", ("fr", "poulpeo"): "poulpeo",
    ("fr", "widilo"): "widilo",
    ("us", "joko"): "joko", ("us", "rakuten cash back"): "rakuten", ("us", "topcashback"): "topcashback",
    ("us", "capital one shopping"): "capital one", ("us", "ibotta"): "ibotta",
    ("us", "fetch rewards"): "fetch", ("us", "paypal honey"): "honey",
}
REVIEW_STOREFRONTS = ["fr", "us", "be", "ch", "lu", "ca", "gb"]


# ---------- parsing helpers -------------------------------------------------------------------
def _num(text):
    """'55,4 k' -> 55400 ; '1.2K' -> 1200 ; '80 270' -> 80270"""
    t = text.replace("\xa0", " ").replace(" ", " ").strip()
    m = re.match(r"([\d\s.,]+)\s*([kKM])?", t)
    if not m:
        return None
    n, mult = m.group(1).replace(" ", ""), m.group(2)
    if mult:
        n = float(n.replace(",", "."))
        return int(round(n * (1000 if mult.lower() == "k" else 1_000_000)))
    return int(n.replace(",", "").replace(".", ""))


def _find_key(obj, key):
    """Return the first value stored under `key` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        found = _find_key(child, key)
        if found is not None:
            return found
    return None


def parse_new_format(html):
    """Pages served since 2025: data is in a JSON script 'serialized-server-data'."""
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="serialized-server-data")
    if not tag:
        return None
    data = json.loads(tag.string)
    shelves = _find_key(data, "shelfMapping") or {}
    out = {"format": "json", "reviews": [], "versions": []}
    ratings = (shelves.get("productRatings") or {}).get("items") or []
    if ratings:
        r = ratings[0]
        out.update(avg_rating=r.get("ratingAverage"), rating_count=r.get("totalNumberOfRatings"),
                   star_counts_5_to_1=r.get("ratingCounts"))
    seen = set()
    for item in (shelves.get("allProductReviews") or {}).get("items") or []:
        rv = item.get("review") or item
        if rv.get("$kind") != "Review" or rv["id"] in seen:
            continue
        seen.add(rv["id"])
        out["reviews"].append({  # reviewerName deliberately not kept
            "review_id": rv["id"], "date": (rv.get("date") or "")[:10], "rating": int(rv["rating"]),
            "title": rv.get("title"), "text": rv.get("contents"),
            "has_dev_response": bool(rv.get("response")),
        })
    versions_blob = json.dumps((shelves.get("mostRecentVersion") or {}))
    for v, d in re.findall(r'"primarySubtitle": "(?:Version )?([^"]+)", "secondarySubtitle": "([^"]+)"', versions_blob):
        out["versions"].append({"version": v, "date_text": d})
    return out


def parse_old_format(html):
    """Pages served until ~2025: classic HTML with 'we-' CSS classes."""
    soup = BeautifulSoup(html, "lxml")
    out = {"format": "html", "reviews": [], "versions": []}
    head = soup.select_one(".we-rating-count")
    if head:
        txt = head.get_text(" ", strip=True)
        m = re.match(r"([\d][.,]\d)\s*\S\s*(.+?)\s*(?:notes|Ratings|Rating|avis)", txt)
        if m:
            out["avg_rating"] = float(m.group(1).replace(",", "."))
            out["rating_count"] = _num(m.group(2))
    for rv in soup.select(".we-customer-review"):
        star = rv.select_one(".we-star-rating")
        rating = re.search(r"(\d)", star.get("aria-label", "")) if star else None
        title = rv.select_one(".we-customer-review__title")
        body = rv.select_one(".we-customer-review__body")
        date = rv.select_one("time")
        out["reviews"].append({  # the user name element is deliberately not read
            "review_id": None,
            "date": date.get("datetime", "")[:10] if date else None,
            "rating": int(rating.group(1)) if rating else None,
            "title": title.get_text(" ", strip=True) if title else None,
            "text": body.get_text(" ", strip=True) if body else None,
            "has_dev_response": bool(rv.select_one(".we-customer-review__header--response")),
        })
    for item in soup.select(".version-history__item"):
        v = item.select_one(".version-history__item__version-number")
        d = item.select_one("time")
        if v:
            out["versions"].append({"version": v.get_text(strip=True),
                                    "date_text": d.get("datetime", "") if d else ""})
    latest = soup.select_one(".whats-new__latest__version")
    if latest:
        out["latest_version"] = latest.get_text(strip=True).replace("Version", "").strip()
    return out


def parse_page(html):
    return parse_new_format(html) or parse_old_format(html)


# ---------- collection ------------------------------------------------------------------------
def collect_comparables():
    rows = []
    for (country, term), key in APPS.items():
        url = (f"https://itunes.apple.com/search?term={term.replace(' ', '+')}"
               f"&country={country}&entity=software&limit=10")
        results = polite_get(url).json().get("results", [])
        if key == "joko":
            match = next((a for a in results if a.get("trackId") == JOKO_ID), None)
        else:
            match = next((a for a in results if key in a.get("trackName", "").lower()), None)
        if not match:
            print(f"  no match for {term} ({country})")
            continue
        page = parse_page(polite_get(match["trackViewUrl"].split("?")[0]).text) or {}
        rows.append({
            "country": country, "app_id": match["trackId"], "app_name": match["trackName"],
            "seller": match.get("sellerName"),
            "avg_rating": match.get("averageUserRating"), "rating_count": match.get("userRatingCount"),
            "star_counts_5_to_1": page.get("star_counts_5_to_1"),
            "first_release_date": (match.get("releaseDate") or "")[:10],
            "current_version": match.get("version"),
        })
        print(f"  {country} {match['trackName']}: {match.get('averageUserRating'):.2f} ({match.get('userRatingCount')})")
    save_json({"source": "iTunes Search API + public App Store pages", "collected_on": TODAY,
               "rows": rows}, RAW / "appstore" / f"apps_{TODAY}.json")


def collect_current_reviews():
    out = []
    for cc in REVIEW_STOREFRONTS:
        for suffix in ("", "?see-all=reviews"):
            r = polite_get(f"https://apps.apple.com/{cc}/app/id{JOKO_ID}{suffix}")
            if r.status_code != 200:
                continue
            page = parse_page(r.text)
            if not page:
                continue
            out.append({"storefront": cc, "snapshot": TODAY, "source": "live page", **page})
        print(f"  {cc}: done")
    save_json({"collected_on": TODAY, "pages": out}, RAW / "appstore" / f"joko_live_pages_{TODAY}.json")


def collect_wayback_pages():
    pages = []
    for cc, prefix in (("fr", "apps.apple.com/fr/app/joko"), ("us", "apps.apple.com/us/app/joko")):
        cdx = polite_get("http://web.archive.org/cdx/search/cdx?url=" + prefix +
                         "&matchType=prefix&output=json&fl=original,timestamp&filter=statuscode:200",
                         timeout=180).json()[1:]
        # keep the main product page (and the see-all reviews page), max one snapshot per month
        keep, months = [], set()
        for original, ts in sorted(cdx, key=lambda x: x[1]):
            if "joko-jokes" in original or "platform=mac" in original or ".js" in original:
                continue
            if "see-all" in original and "reviews" not in original:
                continue
            key = (ts[:6], "see-all" in original)
            if key in months:
                continue
            months.add(key)
            keep.append((original, ts))
        print(f"  {cc}: {len(keep)} archived snapshots")
        for original, ts in keep:
            try:
                html = cached_get_text(f"https://web.archive.org/web/{ts}id_/{original}")
            except Exception:
                continue
            if not html:
                continue
            page = parse_page(html)
            pages.append({"storefront": cc, "snapshot": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                          "source": "wayback", "url": original, **page})
    save_json({"collected_on": TODAY, "pages": pages}, RAW / "appstore" / f"joko_wayback_pages_{TODAY}.json")


def collect_firefox_reviews():
    """Joko browser extension reviews from the official, documented addons.mozilla.org API (v5).
    Chrome Web Store review pages are disallowed by its robots.txt, so they are not collected."""
    addon = polite_get("https://addons.mozilla.org/api/v5/addons/addon/joko/").json()
    rows, url = [], "https://addons.mozilla.org/api/v5/ratings/rating/?addon=joko&page_size=50"
    while url:
        page = polite_get(url).json()
        for x in page["results"]:
            # x["user"] (name, id, url) is deliberately NOT kept
            rows.append({"review_id": str(x["id"]), "date": x["created"][:10], "rating": x["score"],
                         "version": (x.get("version") or {}).get("version"),
                         "title": None, "text": x.get("body") or None,
                         "has_dev_response": bool(x.get("reply"))})
        url = page.get("next")
    save_json({"source": "addons.mozilla.org API v5", "collected_on": TODAY,
               "addon_ratings": addon.get("ratings"), "average_daily_users": addon.get("average_daily_users"),
               "rows": rows}, RAW / "appstore" / f"joko_firefox_reviews_{TODAY}.json")
    print(f"  firefox: {len(rows)} ratings, {sum(1 for r in rows if r['text'])} with text")


if __name__ == "__main__":
    collect_comparables()
    collect_current_reviews()
    collect_firefox_reviews()
    collect_wayback_pages()
