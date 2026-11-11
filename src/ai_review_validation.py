"""Measure the quality of the AI review classification against human labels (PUBLIC + AI).

Input : eval/review_validation_sample.csv  (100 reviews; column human_theme filled by hand)
Output: eval/review_validation_summary.json

- accuracy  = share of reviews where the AI primary theme equals the human label
- precision per theme = among reviews the AI put in theme T, share the human also put in T
- the keyword baseline (simple rules, no AI) is scored the same way, as a point of comparison
Labelling rule used by the human: the primary theme is the MAIN subject of the review. A detailed review
that ends with a referral code is labelled with its main subject; a review written to share a code is
"referral_code"; one- or two-word praise ("super", "bien") is "other".
"""
import json

import pandas as pd

from ai_common import ROOT


def main():
    s = pd.read_csv(ROOT / "eval" / "review_validation_sample.csv", keep_default_na=False)
    s = s[s["human_theme"].str.len() > 0]
    if s.empty:
        print("human_theme is empty: fill it first")
        return
    acc = (s["primary_theme"] == s["human_theme"]).mean()
    kw = (s["keyword_theme"] == s["human_theme"]).mean()
    by_theme = {}
    for t, g in s.groupby("primary_theme"):
        by_theme[t] = {"n": int(len(g)), "precision": round(float((g["human_theme"] == t).mean()), 3)}
    confusion = pd.crosstab(s["human_theme"], s["primary_theme"])
    confusion.to_csv(ROOT / "eval" / "review_validation_confusion.csv")
    summary = {"n": int(len(s)), "accuracy": round(float(acc), 3), "keyword_accuracy": round(float(kw), 3),
               "by_theme": by_theme,
               "note": ("100 reviews drawn at random (seed 42) and labelled by hand with the AI label visible (not blind). "
                        "Most disagreements: long reviews ending with a referral code (AI: referral_code; human: main subject).")}
    (ROOT / "eval" / "review_validation_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
