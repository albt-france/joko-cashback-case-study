"""Historical public data from the Internet Archive's Wayback Machine (PUBLIC DATA).

Uses the CDX API (https://web.archive.org/cdx/search/cdx) and archived copies of public pages.
At most ONE snapshot per page and per month (per quarter for the homepage), >= 5 s between requests,
archived pages cached on disk so a re-run never downloads them twice.
Note (2026-11-11): archive.org answered HTTP 429 after ~100 archived pages, so collection was stopped there;
a planned history of competitor rates (iGraal pages) was not collected.

1. Joko homepage claims over time (number of brands, users, savings, App Store rating),
   French and English homepages, 2019-2026.
2. Joko App Store product pages (France, US): rating header and visible reviews over time
   (see collect_appstore.collect_wayback_pages).

Output: data/raw/wayback/*.json
"""
import json
import re
import sys

from bs4 import BeautifulSoup

from common import RAW, TODAY, cached_get_text, polite_get, save_json

CDX = "https://web.archive.org/cdx/search/cdx"


def monthly_snapshots(url, match_type="exact", since="2019", every_months=1, keep=None):
    """One successful snapshot per period (default: per month; every_months=3 -> per quarter)."""
    q = (f"{CDX}?url={url}&matchType={match_type}&output=json&fl=original,timestamp"
         f"&filter=statuscode:200&from={since}&collapse=timestamp:6")
    r = polite_get(q, timeout=180)
    rows = r.json()[1:] if r.status_code == 200 and r.text.strip() else []
    seen, out = set(), []
    for original, ts in sorted(rows, key=lambda x: x[1]):
        if keep and not keep(original):
            continue
        period = (ts[:4], (int(ts[4:6]) - 1) // every_months)
        if period in seen:
            continue
        seen.add(period)
        out.append((original, ts))
    return out


def archived(original, ts):
    try:
        return cached_get_text(f"https://web.archive.org/web/{ts}id_/{original}")
    except Exception as exc:  # archive.org sometimes drops connections: skip that snapshot
        print(f"    skipped {ts} {original}: {type(exc).__name__}")
        return None


# ---------- 1. Joko homepage claims -----------------------------------------------------------
CLAIM_PATTERNS = {
    "brands": r"(\d[\d\s.,]*\d|\d)\s*\+?\s*(?:marques|enseignes|marchands|brands|stores|merchants|partner)",
    "users_million": r"(\d+(?:[.,]\d+)?)\s*(?:millions?|M)\s*(?:d['’]\s*)?(?:utilisateurs|membres|users|people|members|de membres)",
    "users_thousand": r"(\d[\d\s.,]*)\s*(?:utilisateurs|membres|users|members)",
    "app_rating": r"(\d[.,]\d)\s*/\s*5",
    "savings": r"(\d[\d\s.,]*)\s*(?:M|millions?)?\s*(?:€|\$|euros?)\s*(?:économisés|d['’]économies|saved|in savings|de cashback|cash back)",
}


def extract_claims(text):
    t = text.replace("\xa0", " ").replace(" ", " ")
    out = {}
    for key, pat in CLAIM_PATTERNS.items():
        m = re.findall(pat, t, flags=re.I)
        out[key] = m[:5]
    return out


def collect_joko_home():
    pages = []
    # the CDX index already merges www.joko.com and joko.com, so each path is queried once
    for url in ["joko.com/fr", "joko.com/en", "home.joko.com/fr"]:
        for original, ts in monthly_snapshots(url, every_months=3):
            html = archived(original, ts)
            if not html:
                continue
            text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            pages.append({"url": original, "snapshot": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                          "claims": extract_claims(text), "mentions_juno": "juno" in text.lower(),
                          "mentions_ai": bool(re.search(r"\bIA\b|\bAI\b", text)),
                          "text_excerpt": text[:6000]})
        print(f"  {url}: total {len(pages)} pages")
        save_json({"collected_on": TODAY, "pages": pages}, RAW / "wayback" / f"joko_home_{TODAY}.json")
    save_json({"collected_on": TODAY, "pages": pages}, RAW / "wayback" / f"joko_home_{TODAY}.json")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "home"):
        collect_joko_home()
    if what in ("all", "appstore"):
        import collect_appstore
        collect_appstore.collect_wayback_pages()
