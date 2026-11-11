"""Shared helpers for the collection scripts.

Rules applied everywhere:
- one request at a time, at least 2 seconds between two requests (polite crawling);
- a neutral User-Agent;
- every raw snapshot is saved with its collection date.
"""
import json
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PUBLIC = ROOT / "data" / "public"
SIMULATED = ROOT / "data" / "simulated"
TODAY = date.today().isoformat()

HEADERS = {"User-Agent": "Mozilla/5.0 (independent case-study research; low-frequency)"}
MIN_DELAY_S = 2.0
_last_call = [0.0]


def polite_get(url, timeout=60, retries=2):
    """GET a public URL, waiting at least MIN_DELAY_S since the previous call."""
    # archive.org asks clients to stay well under ~15 requests per minute
    min_delay = 5.0 if "archive.org" in url else MIN_DELAY_S
    url = url.replace("http://web.archive.org", "https://web.archive.org")
    for attempt in range(retries + 1):
        wait = min_delay - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(20 * (attempt + 1))  # back off when the server asks us to slow down
                continue
            r.encoding = "utf-8"
            return r
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(60 * (attempt + 1))  # connection refused = we were too fast: wait longer


def cached_get_text(url, timeout=180):
    """Fetch an archived page once and keep it on disk (data/raw/cache), so a re-run never re-downloads."""
    import hashlib
    cache = RAW / "cache" / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    r = polite_get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(r.text, encoding="utf-8")
    return r.text


def save_json(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_rate(text):
    """'4,5%' -> (4.5, 'percent'); '12€' -> (12.0, 'fixed'); otherwise (None, None)."""
    if text is None:
        return None, None
    t = str(text).replace(" ", " ").replace("\xa0", " ").replace(",", ".").strip()
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(%|€|\$)", t)
    if not m:
        return None, None
    return float(m.group(1)), ("percent" if m.group(2) == "%" else "fixed")
