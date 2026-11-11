"""Google Trends search interest, 5 years, France and US (PUBLIC DATA).

Uses the unofficial `pytrends` client. Google Trends values are relative (0-100) inside one request:
compare terms within the same request only. If Google answers 429 (too many requests), we wait
and retry a few times, then skip (the report says so).

Note: "Joko" is also a common word/name in some languages; in the US the series mixes the app with
unrelated searches, so it is read as an upper bound.
"""
import time

from pytrends.request import TrendReq

from common import RAW, TODAY

QUERIES = {
    "FR": ["Joko", "iGraal", "Poulpeo", "Widilo"],
    "US": ["Joko", "Rakuten", "TopCashback", "Capital One Shopping", "Ibotta"],
}


def fetch(geo, terms, tries=4):
    for attempt in range(tries):
        try:
            client = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
            client.build_payload(terms, timeframe="today 5-y", geo=geo)
            return client.interest_over_time()
        except Exception as exc:  # pytrends raises its own error classes for 429
            print(f"  {geo}: attempt {attempt + 1} failed ({type(exc).__name__}), waiting")
            time.sleep(60 * (attempt + 1))
    return None


if __name__ == "__main__":
    out = RAW / "trends"
    out.mkdir(parents=True, exist_ok=True)
    for geo, terms in QUERIES.items():
        path = out / f"trends_{geo}_{TODAY}.csv"
        if path.exists():
            print(f"{geo}: already collected today")
            continue
        df = fetch(geo, terms)
        if df is None:
            print(f"{geo}: skipped (Google Trends refused the request)")
            continue
        df.to_csv(path)
        print(f"{geo}: {len(df)} weeks saved")
        time.sleep(20)
