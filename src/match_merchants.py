"""Match merchants across platforms (PUBLIC DATA).

The same shop can be written differently on two sites ("Booking.com" / "Booking", "LEGO®" / "Lego").
Method, in order:
1. exact match on a normalised name (lowercase, accents and punctuation removed, ".com/.fr" dropped);
2. fuzzy match (rapidfuzz token_sort_ratio >= 88) for the remaining names, written to
   data/public/merchant_match_candidates.csv for MANUAL review;
3. manual decisions are stored in data/public/merchant_match_review.csv (accept / reject + note) and
   applied here. Doubtful pairs (e.g. "Fnac" vs "Fnac Spectacles") are rejected.
(No merchant domain is published by both sites, so domain matching was not possible; see SOURCES.md.)

The match rate (share of Widilo merchants found on iGraal) is printed and saved.
"""
import json

import pandas as pd
from rapidfuzz import fuzz, process

from collect_competitors import igraal_merchant_index, norm, parse_igraal_page
from common import PUBLIC, RAW, TODAY, polite_get, save_json

FUZZY_THRESHOLD = 88


def latest(platform):
    files = sorted((RAW / "competitors" / platform).glob("2*.json"))  # dated snapshots only
    return json.loads(files[-1].read_text(encoding="utf-8"))


def build_candidates():
    """Save the iGraal index and list fuzzy candidates for names without an exact match."""
    index = igraal_merchant_index()
    save_json({"collected_on": TODAY, "index": {k: v for k, v in index.items()}},
              RAW / "competitors" / "igraal" / f"index_{TODAY}.json")
    widilo = pd.DataFrame(latest("widilo")["rows"])
    names = widilo["merchant"].dropna().unique()
    exact = {n for n in names if norm(n) in index}
    igraal_names = {v[0]: k for k, v in index.items()}
    rows = []
    for n in names:
        if n in exact:
            continue
        best = process.extractOne(n, list(igraal_names), scorer=fuzz.token_sort_ratio)
        if best and best[1] >= FUZZY_THRESHOLD:
            rows.append({"widilo_name": n, "igraal_name": best[0], "score": round(best[1], 1),
                         "igraal_key": igraal_names[best[0]]})
    cand = pd.DataFrame(rows).sort_values("score", ascending=False)
    cand.to_csv(PUBLIC / "merchant_match_candidates.csv", index=False)
    print(f"{len(names)} Widilo merchants, {len(exact)} exact matches, {len(cand)} fuzzy candidates to review")
    return cand


def fetch_accepted():
    """Fetch iGraal pages for manually accepted fuzzy pairs (added to the iGraal snapshot)."""
    review = pd.read_csv(PUBLIC / "merchant_match_review.csv")
    accepted = review[review["decision"] == "accept"]
    index = json.loads(sorted((RAW / "competitors" / "igraal").glob("index_*.json"))[-1].read_text(encoding="utf-8"))["index"]
    snap = latest("igraal")
    done = {r["merchant_key"] for r in snap["rows"]}
    for r in accepted.itertuples():
        if r.igraal_key in done:
            continue
        name, url = index[r.igraal_key]
        page = polite_get(url)
        rec = {"merchant": name, "merchant_key": r.igraal_key, "url": url, "status": page.status_code,
               "matched_widilo_name": r.widilo_name}
        if page.status_code == 200:
            rec.update(parse_igraal_page(page.text))
        snap["rows"].append(rec)
    files = sorted((RAW / "competitors" / "igraal").glob("2*.json"))
    save_json(snap, files[-1])
    print(f"fetched {len(accepted)} accepted fuzzy matches")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch_accepted()
    else:
        build_candidates()
