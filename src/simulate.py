"""SIMULATED internal data for a cashback app (NOT Joko data).

Generates 18 months of users, events, purchases and payouts, using:
- REAL merchant names, categories and median public cashback rates (from the public snapshot of
  iGraal/Widilo built by build_public_tables.py) so that the simulated basket looks credible;
- documented, made-up behavioural assumptions (data/ASSUMPTIONS.md).

Built-in mechanisms (the "ground truth" the analysis should recover):
1. Activation (first purchase tracked in the first 14 days) strongly lowers churn.
2. A long wait for the first cashback validation (> 45 days) raises churn.
3. Seasonality: sales (January, July), Black Friday / Christmas.
4. Users who adopt the AI assistant buy more often, BUT adoption is more likely for already
   engaged users (selection bias). The true causal uplift is +10% purchase frequency; a naive
   comparison shows much more.

Fixed seed 42. Output: data/simulated/*.csv
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from common import PUBLIC, SIMULATED

RNG = np.random.default_rng(42)
START, END = pd.Timestamp("2025-05-01"), pd.Timestamp("2026-10-31")
N_USERS = 30_000
END_PY = END.to_pydatetime()
TRUE_ASSISTANT_UPLIFT = 1.10

CHANNELS = {"organic": 0.30, "referral": 0.25, "paid_social": 0.20, "app_store_search": 0.15, "influencer": 0.10}
CHANNEL_ENGAGEMENT = {"organic": 1.0, "referral": 1.25, "paid_social": 0.75, "app_store_search": 0.95, "influencer": 0.85}
PLATFORMS = {"ios": 0.55, "android": 0.35, "extension": 0.10}
MONTH_SEASONALITY = {1: 1.25, 2: 0.9, 3: 0.95, 4: 0.95, 5: 1.0, 6: 1.0, 7: 1.2, 8: 0.85,
                     9: 0.95, 10: 1.0, 11: 1.7, 12: 1.4}
# validation delay (days) by category: (mean, sd) - travel is validated after the stay
VALIDATION_DAYS = {"travel": (75, 25), "default": (38, 14)}


def load_merchants():
    """Real merchants with their median public rate (PUBLIC snapshot). Fallback list if absent."""
    path = PUBLIC / "dim_merchant.csv"
    if path.exists():
        dm = pd.read_csv(path)
        dm = dm[dm["median_public_rate_pct"].notna()].copy()
        dm = dm.sort_values("n_platforms", ascending=False).head(300)
        return dm[["merchant_id", "merchant", "category", "median_public_rate_pct"]].reset_index(drop=True)
    return pd.DataFrame({
        "merchant_id": range(6), "merchant": ["Amazon", "Fnac", "Sephora", "Booking.com", "Nike", "Uber Eats"],
        "category": ["marketplace", "high_tech", "beauty", "travel", "fashion", "food"],
        "median_public_rate_pct": [1.5, 1.5, 3.0, 4.0, 4.0, 2.0]})


def simulate_users():
    days = (END - START).days
    # signup dates: growth over time + seasonality
    t = RNG.random(N_USERS * 3) * days
    signup = START + pd.to_timedelta(t.astype(int), unit="D")
    month_w = np.array([MONTH_SEASONALITY[m] for m in signup.month])
    growth_w = 0.7 + 0.6 * (t / days)
    keep = RNG.random(len(t)) < (month_w * growth_w) / (month_w * growth_w).max()
    signup = np.sort(signup[keep][:N_USERS])
    n = len(signup)
    # US share ramps up after the US launch (assumption: Sept 2026), otherwise ~5%
    us_p = np.where(signup >= pd.Timestamp("2026-09-01"), 0.30, 0.05)
    users = pd.DataFrame({
        "user_id": np.arange(1, n + 1),
        "signup_date": signup,
        "country": np.where(RNG.random(n) < us_p, "US", "FR"),
        "acquisition_channel": RNG.choice(list(CHANNELS), n, p=list(CHANNELS.values())),
        "platform": RNG.choice(list(PLATFORMS), n, p=list(PLATFORMS.values())),
    })
    ch = users["acquisition_channel"].map(CHANNEL_ENGAGEMENT).to_numpy()
    users["engagement_latent"] = RNG.lognormal(mean=0, sigma=0.6, size=n) * ch
    return users


def simulate_activity(users, merchants):
    """Week-by-week simulation of each user: sessions, searches, clicks, assistant use, purchases."""
    events, purchases = [], []
    weights = merchants["median_public_rate_pct"].rank(pct=True).to_numpy() * 0 + 1
    weights = weights / weights.sum()
    cats = merchants["category"].to_numpy()
    rates = merchants["median_public_rate_pct"].to_numpy()
    mids = merchants["merchant_id"].to_numpy()

    for u in users.itertuples(index=False):
        e = u.engagement_latent
        # assistant adoption: more likely for engaged users (selection bias)
        p_adopt = 1 / (1 + np.exp(-(np.log(e) * 1.8 - 0.9)))
        adopts = RNG.random() < p_adopt
        adopt_week = RNG.integers(0, 8) if adopts else None
        churn_h = 0.11 / e  # weekly churn hazard before modifiers
        first_validation_wait = None
        first_purchase_week = None
        purchased_14d = False
        week_start = pd.Timestamp(u.signup_date).to_pydatetime()
        w = 0
        while week_start <= END_PY:
            month_f = MONTH_SEASONALITY[week_start.month]
            using_assistant = adopts and w >= adopt_week
            # weekly activity
            sessions = RNG.poisson(1.6 * e * (1.0 if w > 0 else 2.0))
            if sessions == 0 and w > 0 and RNG.random() < 0.5:
                pass
            searches = RNG.poisson(0.8 * sessions)
            clicks = RNG.poisson(0.35 * sessions * month_f)
            assistant_q = RNG.poisson(1.5 * sessions) if using_assistant else 0
            lam = 0.16 * e * month_f * (TRUE_ASSISTANT_UPLIFT if using_assistant else 1.0) * (sessions > 0)
            n_purch = RNG.poisson(lam)
            for etype, cnt in (("session", sessions), ("search", searches),
                               ("merchant_click", clicks), ("assistant_query", assistant_q)):
                if cnt:
                    day = week_start + timedelta(days=int(RNG.integers(0, 7)))
                    if day <= END_PY:
                        events.append((u.user_id, day, etype, int(cnt)))
            for _ in range(n_purch):
                day = week_start + timedelta(days=int(RNG.integers(0, 7)))
                if day > END_PY:
                    continue
                k = RNG.choice(len(mids), p=weights)
                amount = round(float(RNG.lognormal(np.log(55), 0.7)), 2)
                mean, sd = VALIDATION_DAYS.get(str(cats[k]).lower(), VALIDATION_DAYS["default"])
                vdays = int(max(3, RNG.normal(mean, sd)))
                status = "cancelled" if RNG.random() < 0.09 else "validated"
                if day + timedelta(days=vdays) > END_PY:
                    status = "pending"
                purchases.append((u.user_id, day, int(mids[k]), amount, float(rates[k]),
                                  round(amount * rates[k] / 100, 2), status,
                                  vdays if status != "pending" else None))
                if (day - pd.Timestamp(u.signup_date).to_pydatetime()).days < 14:
                    purchased_14d = True
                if first_validation_wait is None:
                    first_validation_wait = vdays
                    first_purchase_week = w
            # churn: activation protects, a long first validation wait hurts once the user has
            # waited more than ~5 weeks for that first cashback
            h = churn_h
            if w >= 2:
                h *= 0.45 if purchased_14d else 1.0
            if first_validation_wait is not None and first_validation_wait > 45 and w - first_purchase_week >= 5:
                h *= 2.0
            if RNG.random() < min(h, 0.95):
                break
            week_start += timedelta(days=7)
            w += 1

    ev = pd.DataFrame(events, columns=["user_id", "event_date", "event_type", "event_count"])
    pu = pd.DataFrame(purchases, columns=["user_id", "purchase_date", "merchant_id", "amount_eur",
                                          "cashback_rate_pct", "cashback_eur", "status", "validation_days"])
    pu.insert(0, "purchase_id", np.arange(1, len(pu) + 1))
    pu["validated_date"] = np.where(pu["status"] == "validated",
                                    pu["purchase_date"] + pd.to_timedelta(pu["validation_days"].fillna(0), unit="D"),
                                    pd.NaT)
    return ev, pu


def simulate_payouts(purchases):
    """Users cash out when their validated balance reaches 10 EUR (first time) then in larger chunks."""
    val = purchases[purchases["status"] == "validated"].sort_values("validated_date")
    rows = []
    for uid, g in val.groupby("user_id"):
        bal = 0.0
        for d, c in zip(g["validated_date"], g["cashback_eur"]):
            bal += c
            if bal >= 10 and RNG.random() < 0.7:
                rows.append((uid, pd.Timestamp(d) + pd.Timedelta(days=int(RNG.integers(0, 10))), round(bal, 2)))
                bal = 0.0
    po = pd.DataFrame(rows, columns=["user_id", "payout_date", "amount_eur"])
    po = po[po["payout_date"] <= END]
    po.insert(0, "payout_id", np.arange(1, len(po) + 1))
    return po


def main():
    SIMULATED.mkdir(parents=True, exist_ok=True)
    merchants = load_merchants()
    users = simulate_users()
    ev, pu = simulate_activity(users, merchants)
    po = simulate_payouts(pu)
    users.drop(columns="engagement_latent").to_csv(SIMULATED / "users.csv", index=False)
    ev.to_csv(SIMULATED / "events.csv.gz", index=False)  # compressed: ~700k rows
    pu.to_csv(SIMULATED / "purchases.csv", index=False)
    po.to_csv(SIMULATED / "payouts.csv", index=False)
    merchants.to_csv(SIMULATED / "merchants_used.csv", index=False)
    print(f"SIMULATED: {len(users):,} users, {len(ev):,} event rows, {len(pu):,} purchases, {len(po):,} payouts")


if __name__ == "__main__":
    main()
