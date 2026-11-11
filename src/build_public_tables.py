"""Build the clean PUBLIC tables (data/public/*.csv) from the dated raw snapshots.

Tables
- dim_merchant.csv            merchant, category, on which platform (Widilo / iGraal), median public rate
- fct_cashback_offer.csv      merchant x platform x snapshot: rate, % or fixed, boosted, usual rate, delays
- dim_app.csv                 Joko and comparable apps: rating, number of ratings, star distribution
- fct_app_rating_history.csv  Joko App Store rating and rating count over time (live + Wayback)
- fct_app_reviews.csv         Joko App Store reviews (no author), deduplicated
- fct_joko_versions.csv       Joko app versions and release dates
- fct_joko_home_claims.csv    numbers Joko's homepage displayed over time (Wayback)
- fct_search_interest.csv     Google Trends, long format
"""
import hashlib
import json
import re
from datetime import datetime

import numpy as np
import pandas as pd

from common import PUBLIC, RAW, ROOT, parse_rate

ROOT_EVAL = ROOT / "eval"
from collect_competitors import norm

CATEGORY_EN = {
    "maison-jardin": "Home & garden", "voyages": "Travel", "beaute": "Beauty & health", "mode": "Fashion",
    "sports": "Sports", "high-tech": "Electronics", "culture-loisirs": "Culture & leisure",
    "services": "Services & finance", "auto-moto": "Auto", "enfants": "Kids", "alimentation": "Food & grocery",
    "entreprises-professionnels": "B2B", "cadeaux-box-fleurs": "Gifts & flowers", "abonnements": "Telecom & subscriptions",
    "marchands-chinois": "Marketplaces (Asia)", "fournisseur-d-energie": "Energy",
}


def latest_json(folder, pattern="2*.json"):
    files = sorted((RAW / folder).glob(pattern))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def to_float(text):
    v, _ = parse_rate(text)
    return v


# ---------------------------------------------------------------------------------------------
def build_merchants_and_offers():
    w = latest_json("competitors/widilo")
    g = latest_json("competitors/igraal")
    wd = pd.DataFrame(w["rows"])
    wd = wd[wd["parent_category"] != "widilo-belgique"].copy()
    wd["merchant_key"] = wd["merchant"].map(norm)
    # a merchant can appear in several category pages: keep its parent category with most rows
    cat = (wd.groupby(["merchant_key", "parent_category"]).size().reset_index(name="n")
             .sort_values(["merchant_key", "n"], ascending=[True, False]).drop_duplicates("merchant_key"))
    wd1 = wd.drop_duplicates("merchant_key")

    # manual review of fuzzy pairs: widilo key -> igraal key
    review_path = PUBLIC / "merchant_match_review.csv"
    alias = {}
    if review_path.exists():
        rv = pd.read_csv(review_path)
        for r in rv[rv["decision"] == "accept"].itertuples():
            alias[r.igraal_key] = norm(r.widilo_name)

    gd = pd.DataFrame(g["rows"])
    gd = gd[gd["status"] == 200].copy()
    gd["merchant_key"] = gd["merchant_key"].map(lambda k: alias.get(k, k))
    gd["match_method"] = np.where(gd.get("matched_widilo_name").notna() if "matched_widilo_name" in gd else False,
                                  "fuzzy_manual", "exact_name")

    # ---- offers (long table)
    offers = []
    for r in wd1.itertuples():
        v, t = parse_rate(r.rate_text)
        offers.append({"merchant_key": r.merchant_key, "platform": "Widilo", "country": "FR",
                       "snapshot_date": w["collected_on"], "rate_value": v, "rate_type": t,
                       "is_boosted": bool(r.is_boosted), "rate_before_boost": to_float(r.rate_before_boost_text),
                       "up_to": None, "validation_days_announced": r.validation_days if r.validation_days else None})
    for r in gd.itertuples():
        v, t = parse_rate(r.rate_text)
        offers.append({"merchant_key": r.merchant_key, "platform": "iGraal", "country": "FR",
                       "snapshot_date": g["collected_on"], "rate_value": v, "rate_type": t,
                       "is_boosted": bool(r.is_boosted), "rate_before_boost": to_float(getattr(r, "rate_before_boost_text", None)),
                       "up_to": bool(r.up_to), "validation_days_announced": None})
    fo = pd.DataFrame(offers)
    fo = fo[fo["rate_value"].notna()]

    # ---- merchant dimension
    dm = wd1[["merchant_key", "merchant"]].merge(cat[["merchant_key", "parent_category"]], on="merchant_key")
    dm["category"] = dm["parent_category"].map(CATEGORY_EN).fillna("Other")
    plat = fo.pivot_table(index="merchant_key", columns="platform", values="rate_value", aggfunc="first")
    dm["on_widilo"] = dm["merchant_key"].isin(plat.index[plat.get("Widilo").notna()] if "Widilo" in plat else [])
    dm["on_igraal"] = dm["merchant_key"].isin(plat.index[plat.get("iGraal").notna()] if "iGraal" in plat else [])
    dm["n_platforms"] = dm["on_widilo"].astype(int) + dm["on_igraal"].astype(int)
    pct = fo[fo["rate_type"] == "percent"].groupby("merchant_key")["rate_value"].median()
    dm["median_public_rate_pct"] = dm["merchant_key"].map(pct)
    meth = gd.drop_duplicates("merchant_key").set_index("merchant_key")["match_method"]
    dm["match_method"] = dm["merchant_key"].map(meth).fillna("not_found_on_igraal")
    dm = dm.sort_values("merchant").reset_index(drop=True)
    dm.insert(0, "merchant_id", np.arange(1, len(dm) + 1))
    dm = dm.drop(columns="parent_category")
    fo = fo.merge(dm[["merchant_key", "merchant_id"]], on="merchant_key", how="inner")
    dm.to_csv(PUBLIC / "dim_merchant.csv", index=False)
    fo.drop(columns="merchant_key").to_csv(PUBLIC / "fct_cashback_offer.csv", index=False)
    rate = dm["on_igraal"].mean()
    print(f"dim_merchant: {len(dm)} merchants, matched on both platforms: {dm['n_platforms'].eq(2).sum()} ({rate:.0%})")
    return dm, fo


# ---------------------------------------------------------------------------------------------
def build_apps():
    a = latest_json("appstore", "apps_*.json")
    df = pd.DataFrame(a["rows"])
    stars = df["star_counts_5_to_1"].apply(lambda s: s if isinstance(s, list) else [None] * 5)
    for i, k in enumerate([5, 4, 3, 2, 1]):
        df[f"stars_{k}"] = stars.map(lambda s: round(s[i]) if s[i] is not None else None)
    df["share_1_star"] = df["stars_1"] / df["rating_count"]
    df["collected_on"] = a["collected_on"]
    df.drop(columns="star_counts_5_to_1").to_csv(PUBLIC / "dim_app.csv", index=False)
    print(f"dim_app: {len(df)} apps")


def review_key(country, date, title, text):
    raw = f"{country}|{date}|{(title or '').strip()}|{(text or '').strip()[:200]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def parse_version_date(text):
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%a %b %d %Y %H:%M:%S"):
        try:
            return datetime.strptime(text[:24] if "GMT" in text else text[:10], fmt).date()
        except ValueError:
            continue
    return None


# explicit forms: "code parrain: abcdef", "code : abcdef", "code parrainage abcdef"
CODE_PATTERNS = [
    re.compile(r"(?:code\s*(?:de\s*)?parrain(?:age)?|parrain(?:age)?|code)\s*:\s*([a-z]{6})\b", re.I),
    re.compile(r"code\s+parrain(?:age)?\s+([a-z]{6})\b", re.I),
]


def find_codes(texts):
    """Referral codes quoted in reviews. They are account-linked identifiers, so they are masked.

    1. explicit forms (patterns above);
    2. a 6-letter lowercase token in a review that talks about referral codes, used in at most 2 distinct
       reviews (real words are used in many), and either with at most one vowel or written as the last word.
    The resulting list was checked by hand (see DECISIONS, not published since it would publish the codes).
    """
    unique_texts = list(dict.fromkeys(str(t) for t in texts))
    doc_freq = {}
    for t in unique_texts:
        for w in set(re.findall(r"\b[a-z]{6}\b", t)):
            doc_freq[w] = doc_freq.get(w, 0) + 1
    codes = set()
    for t in unique_texts:
        for pat in CODE_PATTERNS:
            for m in pat.finditer(t):
                # the same person often posts the same code several times: allow up to 10 reviews
                if doc_freq.get(m.group(1), 0) <= 10 and m.group(1) not in {"faites", "points", "offert", "valide"}:
                    codes.add(m.group(1))
        if re.search(r"parrain|referral|code", t, re.I):
            words = re.findall(r"\b[a-z]{6}\b", t)
            last = re.findall(r"\b\w+\b", t)[-1:] or [""]
            for w in set(words):
                vowels = sum(ch in "aeiou" for ch in w)
                if doc_freq[w] <= 2 and (vowels <= 1 or w == last[0]):
                    codes.add(w)
    return codes


def mask_codes(text, codes):
    """Replace referral codes (account-linked identifiers) by [code] before publishing review text."""
    if not isinstance(text, str):
        return text
    return re.sub(r"\b(" + "|".join(map(re.escape, sorted(codes))) + r")\b", "[code]", text, flags=re.I) if codes else text


def refresh_review_text():
    """Put the (unmasked) review text from fct_app_reviews.csv back into the derived files, keeping their labels."""
    full = pd.read_csv(PUBLIC / "fct_app_reviews.csv", keep_default_na=False)
    themed = PUBLIC / "fct_app_reviews_themed.csv"
    if themed.exists():  # labels kept, every other column refreshed from the base table
        labels = pd.read_csv(themed, keep_default_na=False)[["review_key", "primary_theme", "themes", "sentiment", "method", "keyword_theme"]]
        full.merge(labels, on="review_key", how="left").to_csv(themed, index=False)
    base = full[["review_key", "title", "text"]]
    for f in [ROOT_EVAL / "review_validation_sample.csv"]:
        if f.exists():
            df = pd.read_csv(f, keep_default_na=False).drop(columns=["title", "text"])
            cols = list(pd.read_csv(f, nrows=0).columns)
            df.merge(base, on="review_key", how="left")[cols].to_csv(f, index=False)


def mask_review_files():
    """Apply the masking to every published file that contains review text."""
    refresh_review_text()
    files = [PUBLIC / "fct_app_reviews.csv", PUBLIC / "fct_app_reviews_themed.csv",
             ROOT_EVAL / "review_validation_sample.csv"]
    texts = []
    for f in files:
        if f.exists():
            df = pd.read_csv(f, keep_default_na=False)
            texts += list(df.get("title", [])) + list(df.get("text", []))
    codes = find_codes(texts)
    for f in files:
        if f.exists():
            df = pd.read_csv(f, keep_default_na=False)
            for col in ("title", "text"):
                if col in df:
                    df[col] = [mask_codes(t, codes) for t in df[col]]
            df.to_csv(f, index=False)
    print(f"masked {len(codes)} referral codes in {len(files)} files")


def build_reviews():
    pages = []
    live = latest_json("appstore", "joko_live_pages_*.json")
    wb = latest_json("appstore", "joko_wayback_pages_*.json")
    for src in (live, wb):
        if src:
            pages += src["pages"]
    # rating history
    hist = [{"storefront": p["storefront"], "snapshot": p["snapshot"], "source": p["source"],
             "avg_rating": p.get("avg_rating"), "rating_count": p.get("rating_count")}
            for p in pages if p.get("rating_count")]
    hist = pd.DataFrame(hist).drop_duplicates(["storefront", "snapshot"]).sort_values(["storefront", "snapshot"])
    # some archived URLs are other variants of the page (Mac app, another listing): their header shows a
    # tiny count. Keep a point only if it is at least half of the highest count seen before it.
    hist["prev_max"] = hist.groupby("storefront")["rating_count"].cummax()
    hist = hist[hist["rating_count"] >= 0.5 * hist["prev_max"]].drop(columns="prev_max")
    hist.to_csv(PUBLIC / "fct_app_rating_history.csv", index=False)
    # versions
    vers = []
    for p in pages:
        for v in p.get("versions", []):
            d = parse_version_date(v["date_text"])
            if d:
                vers.append({"version": v["version"], "release_date": d})
        if p.get("latest_version") and p["source"] == "wayback":
            vers.append({"version": p["latest_version"], "release_date": None, "seen_on": p["snapshot"]})
    vdf = pd.DataFrame(vers)
    vdf = vdf.dropna(subset=["release_date"]).drop_duplicates("version").sort_values("release_date")
    # the archives also contain 2.x versions of Joko's separate Safari/Mac extension listing: keep the iOS app (4.x+)
    vdf = vdf[vdf["version"].str.split(".").str[0].astype(int) >= 4]
    vdf.to_csv(PUBLIC / "fct_joko_versions.csv", index=False)
    # reviews
    rows = []
    for p in pages:
        for r in p.get("reviews", []):
            if not r.get("text") or not r.get("date"):
                continue
            rows.append({"country": p["storefront"], "date": r["date"][:10], "rating": r["rating"],
                         "title": r.get("title"), "text": r["text"], "has_dev_response": r.get("has_dev_response"),
                         "first_seen_snapshot": p["snapshot"], "page_source": p["source"]})
    rv = pd.DataFrame(rows)
    rv["review_key"] = [review_key(*x) for x in zip(rv["country"], rv["date"], rv["title"], rv["text"])]
    rv = rv.sort_values("first_seen_snapshot").drop_duplicates("review_key")
    # version live at the review date (only possible for dates covered by the known version history)
    vdf["release_date"] = pd.to_datetime(vdf["release_date"]).astype("datetime64[ns]")
    rv["date"] = pd.to_datetime(rv["date"]).astype("datetime64[ns]")
    if len(vdf):
        rv = rv.sort_values("date")
        rv = pd.merge_asof(rv, vdf[["release_date", "version"]].sort_values("release_date"),
                           left_on="date", right_on="release_date", direction="backward")
        rv.loc[rv["date"] < vdf["release_date"].min(), "version"] = None
        rv = rv.drop(columns="release_date")
    rv["major_version"] = rv["version"].map(lambda v: str(v).split(".")[0] if isinstance(v, str) else None)
    rv["date"] = rv["date"].dt.date
    rv["store"] = "app_store"
    # Firefox extension reviews (official AMO API); no country is published, version = extension version
    ff = latest_json("appstore", "joko_firefox_reviews_*.json")
    if ff:
        f = pd.DataFrame([r for r in ff["rows"] if r.get("text")])
        f["country"] = "unknown"  # the AMO API publishes no country
        f["store"] = "firefox_extension"
        f["page_source"] = "amo_api"
        f["first_seen_snapshot"] = ff["collected_on"]
        f["major_version"] = None
        f["review_key"] = [review_key("ff", d, None, t) for d, t in zip(f["date"], f["text"])]
        rv = pd.concat([rv, f], ignore_index=True)
    cols = ["review_key", "store", "country", "date", "rating", "version", "major_version", "title", "text",
            "has_dev_response", "page_source", "first_seen_snapshot"]
    rv[cols].to_csv(PUBLIC / "fct_app_reviews.csv", index=False)
    mask_review_files()
    print(f"fct_app_reviews: {len(rv)} reviews ({rv['country'].value_counts().to_dict()}); rating history: {len(hist)} points")


# ---------------------------------------------------------------------------------------------
def build_home_claims():
    h = latest_json("wayback", "joko_home_*.json")
    if not h:
        return
    rows = []
    for p in h["pages"]:
        c = p["claims"]
        def first_num(lst):
            for x in lst:
                s = x if isinstance(x, str) else x[0]
                s = re.sub(r"[\s.,](?=\d{3}\b)", "", s.strip()).replace(",", ".")
                try:
                    return float(s)
                except ValueError:
                    continue
            return None
        lang = "fr" if "/fr" in p["url"] else ("en" if "/en" in p["url"] else "root")
        rows.append({"snapshot": p["snapshot"], "lang": lang, "url": p["url"],
                     "brands_claimed": first_num(c.get("brands", [])),
                     "users_million_claimed": first_num(c.get("users_million", [])),
                     "app_rating_claimed": first_num(c.get("app_rating", [])),
                     "mentions_juno": p.get("mentions_juno", False), "mentions_ai": p.get("mentions_ai", False)})
    pd.DataFrame(rows).sort_values("snapshot").to_csv(PUBLIC / "fct_joko_home_claims.csv", index=False)
    print(f"fct_joko_home_claims: {len(rows)} snapshots")


def build_trends():
    out = []
    for f in sorted((RAW / "trends").glob("trends_*.csv")):
        geo = f.stem.split("_")[1]
        df = pd.read_csv(f, parse_dates=["date"]).drop(columns=["isPartial"], errors="ignore")
        long = df.melt(id_vars="date", var_name="term", value_name="interest")
        long["geo"] = geo
        out.append(long)
    if out:
        pd.concat(out).to_csv(PUBLIC / "fct_search_interest.csv", index=False)
        print("fct_search_interest: done")


if __name__ == "__main__":
    PUBLIC.mkdir(parents=True, exist_ok=True)
    dm, fo = build_merchants_and_offers()
    build_apps()
    build_reviews()  # also masks referral codes in all review files
    build_home_claims()
    build_trends()
