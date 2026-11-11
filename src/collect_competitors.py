"""Collect a dated snapshot of public cashback rates from two French cashback sites.

PUBLIC DATA. Sources and limits are documented in data/SOURCES.md.

- Widilo: each public category page lists its 10 most visible merchants with the rate,
  whether the rate is boosted ("cashbackIsIncrease") and the usual rate before the boost,
  plus the validation delay Widilo announces. We read the JSON state embedded in the page
  (the same data the page displays). We do NOT call Widilo's API.
- iGraal: for each merchant found on Widilo (and iGraal's own "popular brands" menu) we open
  the public merchant page and read the headline cashback rate and, when boosted, the
  "instead of" (au lieu de) rate.

Politeness: robots.txt respected, >= 2 s between requests, one snapshot per run.
Output: data/raw/competitors/<platform>/<date>.json
"""
import json
import re
import sys

from bs4 import BeautifulSoup

from common import RAW, TODAY, parse_rate, polite_get, save_json

WIDILO = "https://www.widilo.fr"
IGRAAL = "https://fr.igraal.com"
# Widilo time units, as used in its page state (0=hours, 1=days, 2=weeks, 3=months)
UNIT_TO_DAYS = {0: 1 / 24, 1: 1, 2: 7, 3: 30.4}


def norm(name):
    """Normalise a merchant name for matching: lowercase, no accents, no punctuation."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\.(com|fr|net)\b", "", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def widilo_state(html):
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="ng-state")
    if not tag:
        return {}
    state = json.loads(tag.string)
    out = {}
    for key, value in state.items():
        if isinstance(value, dict) and isinstance(value.get("b"), str):
            try:
                out[key] = json.loads(value["b"])
            except json.JSONDecodeError:
                pass
    return out


def collect_widilo():
    sitemap = polite_get(f"{WIDILO}/category-sitemap.xml").text
    category_urls = sorted(set(re.findall(r"<loc>\s*(.*?)\s*</loc>", sitemap)))
    print(f"Widilo: {len(category_urls)} category pages")
    tree, rows = {}, []
    for i, url in enumerate(category_urls, 1):
        r = polite_get(url)
        if r.status_code != 200:
            continue
        state = widilo_state(r.text)
        for obj in state.values():
            # the category tree (parent -> sub-categories) is in one of the state entries
            if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "subCategories" in obj[0]:
                for parent in obj:
                    tree[parent["routeName"]] = parent["routeName"]
                    for sub in parent.get("subCategories") or []:
                        tree[sub["routeName"]] = parent["routeName"]
            if isinstance(obj, dict) and "lines" in obj:
                slug = url.rstrip("/").split("/")[-1]
                for rank, line in enumerate(obj["lines"], 1):
                    rows.append({
                        "category_page": slug,
                        "rank_in_page": rank,
                        "merchant": line.get("name"),
                        "merchant_slug": line.get("routeName"),
                        "rate_text": line.get("cashbackValue"),
                        "rate_before_boost_text": line.get("cashbackBeforeIncreaseValue"),
                        "is_boosted": line.get("cashbackIsIncrease"),
                        "rate_value": line.get("cashbackRate"),
                        "rate_type_code": line.get("cashbackType"),
                        "has_validation_delay": line.get("hasCashbackDelay"),
                        "validation_time": line.get("cashbackValidationTime"),
                        "validation_unit": line.get("cashbackValidationTimeUnit"),
                        "appearance_time": line.get("cashbackAppearanceTime"),
                        "appearance_unit": line.get("cashbackAppearanceTimeUnit"),
                    })
        if i % 10 == 0:
            print(f"  {i}/{len(category_urls)} pages, {len(rows)} rows")
    for row in rows:
        row["parent_category"] = tree.get(row["category_page"], row["category_page"])
        for k in ("validation", "appearance"):
            t, u = row[f"{k}_time"], row[f"{k}_unit"]
            row[f"{k}_days"] = round(t * UNIT_TO_DAYS[u], 1) if t is not None and u in UNIT_TO_DAYS else None
    snapshot = {"source": "widilo.fr public category pages", "collected_on": TODAY,
                "category_tree": tree, "rows": rows}
    save_json(snapshot, RAW / "competitors" / "widilo" / f"{TODAY}.json")
    return rows


def igraal_merchant_index():
    html = polite_get(f"{IGRAAL}/marchands/").text
    soup = BeautifulSoup(html, "lxml")
    index = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if "/codes-promo/" in href and name:
            href = href if href.startswith("http") else IGRAAL + href
            index.setdefault(norm(name), (name, href))
    return index


def parse_igraal_page(html):
    """Return the headline cashback rate of an iGraal merchant page."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True).replace("\xa0", " ") if soup.title else ""
    text = soup.get_text(" | ", strip=True).replace("⁣", "").replace("\xa0", " ").replace(" ", " ")
    out = {"title": title}
    m = re.search(r"\+\s*(jusqu'à\s*)?([\d,]+\s*(?:%|€))\s*(?:de\s*)?cashback", title, re.I)
    out["rate_text"] = m.group(2) if m else None
    out["up_to"] = bool(m and m.group(1))
    # main offer block: "3 % de cashback | Au lieu de 1,5 %"
    m2 = re.search(r"Bons plans \(\d+\) \| (?:Jusqu'à )?([\d,]+ ?(?:%|€)) ?de cashback(?: \| Au lieu de ([\d,]+ ?(?:%|€)))?", text)
    if m2:
        out["rate_text_block"] = m2.group(1)
        out["rate_before_boost_text"] = m2.group(2)
    out["is_boosted"] = bool(m2 and m2.group(2))
    return out


def collect_igraal(widilo_rows, limit=None):
    index = igraal_merchant_index()
    print(f"iGraal: {len(index)} merchants listed")
    wanted = []
    for row in widilo_rows:
        key = norm(row["merchant"] or "")
        if key in index and key not in [w[0] for w in wanted]:
            wanted.append((key, row["merchant"]))
    if limit:
        wanted = wanted[:limit]
    print(f"iGraal: {len(wanted)} merchants matched by name with Widilo, fetching their pages")
    rows = []
    for i, (key, _) in enumerate(wanted, 1):
        name, url = index[key]
        r = polite_get(url)
        rec = {"merchant": name, "merchant_key": key, "url": url, "status": r.status_code}
        if r.status_code == 200:
            rec.update(parse_igraal_page(r.text))
        rows.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(wanted)}")
    snapshot = {"source": "fr.igraal.com public merchant pages", "collected_on": TODAY,
                "merchants_listed": len(index), "rows": rows}
    save_json(snapshot, RAW / "competitors" / "igraal" / f"{TODAY}.json")
    return rows


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    w = collect_widilo()
    print(f"Widilo rows: {len(w)}")
    g = collect_igraal(w, limit)
    print(f"iGraal rows: {len(g)}")
