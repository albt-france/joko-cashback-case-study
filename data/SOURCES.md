# Data sources

All public data was collected on **2026-11-11** unless stated otherwise, with polite scripts:
`robots.txt` respected, at least 2 seconds between requests (5 seconds for archive.org), one dated snapshot per run,
no login, no private API, no CAPTCHA circumvention. Raw pages are **not** redistributed (`data/raw/` is git-ignored);
this repository publishes the collection scripts and the derived tables in `data/public/`.

## PUBLIC DATA

| Table (data/public) | Source | URL | Collected | Limits |
|---|---|---|---|---|
| `dim_merchant.csv`, `fct_cashback_offer.csv` | Widilo public category pages: the 10 most visible merchants of each of 93 categories, with rate, boost flag, usual rate and announced validation delay (read from the page's embedded state, i.e. what the page displays) | https://www.widilo.fr/categories/ (via https://www.widilo.fr/category-sitemap.xml) | 2026-11-11 | Top 10 per category only (pagination uses a private API, not used); showcased merchants are more often boosted |
| same | iGraal public merchant pages: headline rate and "au lieu de" (usual) rate | https://fr.igraal.com/marchands/ and https://fr.igraal.com/codes-promo/... | 2026-11-11 | 411 pages; 54 merchants had no active cashback that day; boost detection may miss some layouts (lower bound) |
| `merchant_match_candidates.csv`, `merchant_match_review.csv` | Matching Widilo ↔ iGraal: exact normalised name (407), fuzzy candidates (7) reviewed by hand (4 accepted) | - | 2026-11-11 | Neither site publishes the merchant's domain in a reusable way, so domain matching was not possible |
| `dim_app.csv` | Apple iTunes Search API (rating, rating count, release date) + public App Store pages (star distribution) for Joko and comparable apps (FR: iGraal, Poulpeo, Widilo; US: Rakuten, TopCashback, Capital One Shopping, Ibotta, Fetch, PayPal Honey) | https://itunes.apple.com/search , https://apps.apple.com/ | 2026-11-11 | Rating count is a footprint proxy, not users |
| `fct_app_rating_history.csv` | Joko's App Store page (FR, US): rating and rating count shown in archived copies (Wayback Machine, max 1 per month) and today | https://web.archive.org/ (apps.apple.com/fr/app/joko..., apps.apple.com/us/app/joko...) | 2026-11-11 | Archive coverage is irregular; points from other page variants (tiny counts) are filtered out |
| `fct_app_reviews.csv`, `fct_app_reviews_themed.csv` | Reviews shown on Joko's App Store pages today and in archived copies (2019-2026), and Joko's Firefox add-on reviews from the official addons.mozilla.org API v5 | https://apps.apple.com/ , https://web.archive.org/ , https://addons.mozilla.org/api/v5/ratings/rating/?addon=joko | 2026-11-11 | 123 reviews, not a random sample. **Reviewer names are never collected; referral codes quoted in reviews are masked as [code].** Apple's customer-review RSS feed returned empty feeds for every app on the collection date, so it could not be used. Chrome Web Store review pages are disallowed by its robots.txt |
| `fct_joko_versions.csv` | Joko iOS app version history (number, release date) from the public App Store page and its archived copies | https://apps.apple.com/fr/app/id1378996692 | 2026-11-11 | Only versions displayed on the pages (May 2025 - Nov 2026); 2.x versions of the separate Safari extension listing are excluded |
| `fct_joko_home_claims.csv` | Numbers displayed on Joko's homepage over time (brands, users, App Store rating), archived copies, max 1 per quarter | https://web.archive.org/ (joko.com, home.joko.com) | 2026-11-11 | Wording and definitions change over time |
| `fct_search_interest.csv` | Google Trends, 5 years, weekly, France (Joko, iGraal, Poulpeo, Widilo) and US (Joko, Rakuten, TopCashback, Capital One Shopping, Ibotta), via `pytrends` | https://trends.google.com/ | 2026-11-11 | Relative index (0-100) within one request; "Joko" is also a common word/name (US series = upper bound) |
| `company_timeline.csv` | Company facts, each with its source and date (see the file): Partech press release (2020-10-07/08), PR Newswire US-launch release (2026-09-21), Dealroom profile, Joko homepage, Joko's job posting, iTunes API | URLs in the file | 2026-11-11 | Company-published figures are not audited; the 2026 release gives two different descriptions of the 6M users (Europe vs France + US) |

## Sources checked and NOT used
| Source | Reason |
|---|---|
| Joko's merchant catalogue and rates (app.joko.com, mobile app) | Visible only after login; Joko's terms (art. 7.2) forbid automated extraction from the service |
| Poulpeo | Terms (art. 8.2) protect its database against extraction |
| TopCashback (US) | Terms forbid spidering and reproduction of site data |
| Capital One Shopping | Terms forbid scraping and compiling content into a database |
| Rakuten (US) | Automated access refused (HTTP 403 on the sitemap) |
| BeFrugal | Terms: no reproduction for commercial purposes (excluded by prudence) |
| CashbackMonitor (US aggregator) | Rates are injected by obfuscated JavaScript: reading them would mean working around the page |
| Chrome Web Store reviews | Disallowed by robots.txt |
| Trustpilot, Google Play reviews | Terms restrict automated collection; not needed |
| Wayback Machine, competitor rate history | archive.org answered HTTP 429 (rate limit) after ~100 archived pages: collection stopped, iGraal rate history not collected |
| B Corp directory, LSA article | Refused automated access (HTTP 403); B Corp status is taken from Joko's own job posting |

## SIMULATED data
`data/simulated/` is generated by `src/simulate.py` (seed 42). It uses the real merchant names, categories and median public
rates above; everything else is invented and documented in `data/ASSUMPTIONS.md`. It is **not Joko data** and is labelled
SIMULATED wherever it is used (report pages 7-8, notebook sections 3-4).
