"""Classify public App Store reviews of Joko into a CLOSED list of themes (PUBLIC + AI).

Input : data/public/fct_app_reviews.csv  (no author fields)
Output: data/public/fct_app_reviews_themed.csv  (adds primary_theme, themes, sentiment, method)
        eval/review_validation_sample.csv       (sample for human validation)

With an API key: Claude classifies reviews in batches of 20, with a strict JSON schema whose
theme field is an enum, so the model cannot invent a theme.
Without a key: a transparent keyword baseline (rules below) is used and labelled as such.
"""
import json
import re

import pandas as pd

from ai_common import ROOT, call_json, has_key

THEMES = {
    "cashback_validation_delay": "cashback stays pending / takes weeks or months to be validated",
    "missing_cashback_tracking": "purchase or cashback not detected, not credited, cancelled or refused",
    "payout": "withdrawing money, payout threshold, bank transfer, gift cards as payout",
    "bank_card_linking": "connecting a bank account or card, open banking, security of bank data",
    "app_ux_bugs": "app design, ease of use, bugs, crashes, login problems, performance",
    "savings_value": "how much money users save or earn, cashback rates, value for money",
    "coupons_promo_codes": "promo codes, automatic coupons, browser extension codes",
    "assistant_ai": "the AI shopping assistant (Juno), product search, price comparison",
    "customer_support": "contacting support, response time, quality of help",
    "referral_code": "review mainly shares or asks for a referral / sponsorship code",
    "other": "anything else, or too vague to classify",
}
SENTIMENTS = ["positive", "negative", "mixed"]

SYSTEM = (
    "You label app-store reviews of a cashback and AI shopping app. Reviews may be in French or English. "
    "Use ONLY the theme ids given. primary_theme is the main subject of the review. "
    "themes lists 1 or 2 theme ids (primary first). If a review mostly shares a referral code, use referral_code. "
    "Return one object per review id, in the same order."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "primary_theme": {"type": "string", "enum": list(THEMES)},
                    "themes": {"type": "array", "items": {"type": "string", "enum": list(THEMES)}},
                    "sentiment": {"type": "string", "enum": SENTIMENTS},
                },
                "required": ["id", "primary_theme", "themes", "sentiment"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}

# ---------- keyword baseline (used without an API key) ----------------------------------------
RULES = [
    ("referral_code", r"parrain|referral|code\s*:?\s*[a-z0-9]{5,7}\b|sponsor"),
    ("cashback_validation_delay", r"attente|en attente|pending|valid|mois|months|weeks|semaines|délai|delai"),
    ("missing_cashback_tracking", r"pas (été )?(crédit|pris en compte|détect)|not (credited|tracked)|annul|refus|jamais reçu|never received"),
    ("payout", r"virement|retrait|withdraw|payout|cagnotte|transfer|carte cadeau|gift card|bon d.achat"),
    ("bank_card_linking", r"banque|bank|carte bancaire|card|connexion bancaire|open banking"),
    ("customer_support", r"service client|support|sav|réponse|answer|contact"),
    ("assistant_ai", r"juno|assistant|\bia\b|\bai\b"),
    ("coupons_promo_codes", r"code promo|coupon|promo code|extension"),
    ("app_ux_bugs", r"bug|crash|beug|lent|slow|connexion|login|interface|ergonom"),
    ("savings_value", r"économ|econom|save|gagn|earn|argent|money|€|\$"),
]


def keyword_theme(text):
    t = (text or "").lower()
    for theme, pat in RULES:
        if re.search(pat, t):
            return theme
    return "other"


def keyword_sentiment(rating):
    return "positive" if rating >= 4 else ("negative" if rating <= 2 else "mixed")


def classify_with_ai(df, batch_size=20):
    rows = []
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start:start + batch_size]
        theme_list = "\n".join(f"- {k}: {v}" for k, v in THEMES.items())
        reviews = "\n\n".join(
            f"id={r.review_key}\nrating={r.rating}/5\ntitle={r.title}\ntext={str(r.text)[:1200]}"
            for r in batch.itertuples())
        user = f"Themes:\n{theme_list}\n\nReviews:\n{reviews}"
        out, _ = call_json(SYSTEM, user, SCHEMA, max_tokens=4000, task="review_themes")
        got = {lab["id"]: lab for lab in out["labels"]}
        for r in batch.itertuples():
            lab = got.get(r.review_key)
            if lab is None:  # the model skipped a review: fall back to the keyword rule
                rows.append((r.review_key, keyword_theme(f"{r.title} {r.text}"), "", keyword_sentiment(r.rating), "keyword_fallback"))
            else:
                rows.append((r.review_key, lab["primary_theme"], "|".join(lab["themes"]), lab["sentiment"], "ai"))
        print(f"  classified {min(start + batch_size, len(df))}/{len(df)}")
    return pd.DataFrame(rows, columns=["review_key", "primary_theme", "themes", "sentiment", "method"])


def main():
    df = pd.read_csv(ROOT / "data" / "public" / "fct_app_reviews.csv")
    if has_key():
        labels = classify_with_ai(df)
    else:
        print("No ANTHROPIC_API_KEY: using the keyword baseline")
        labels = pd.DataFrame({
            "review_key": df["review_key"],
            "primary_theme": [keyword_theme(f"{a} {b}") for a, b in zip(df["title"], df["text"])],
            "themes": "", "sentiment": [keyword_sentiment(x) for x in df["rating"]], "method": "keyword"})
    labels["keyword_theme"] = [keyword_theme(f"{a} {b}") for a, b in zip(df["title"], df["text"])]
    out = df.merge(labels, on="review_key", how="left")
    out.to_csv(ROOT / "data" / "public" / "fct_app_reviews_themed.csv", index=False)

    # validation sample: 100 reviews drawn at random (fixed seed), or all of them if fewer
    sample = out.sample(min(100, len(out)), random_state=42)
    path = ROOT / "eval" / "review_validation_sample.csv"
    keep_cols = ["review_key", "country", "rating", "title", "text", "primary_theme", "keyword_theme"]
    if path.exists():  # never overwrite human labels already entered
        print(f"{path.name} exists: kept as is (human labels preserved)")
    else:
        s = sample[keep_cols].copy()
        s["human_theme"] = ""
        s.to_csv(path, index=False)
        print(f"wrote {path.name} ({len(s)} reviews) - fill human_theme, then run ai_review_validation.py")
    print(out["primary_theme"].value_counts())


if __name__ == "__main__":
    main()
