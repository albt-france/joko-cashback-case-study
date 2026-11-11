-- 02_rate_comparison.sql  -  PUBLIC DATA
-- Same merchant, two platforms: how different are the rates?
-- Only merchants with a PERCENT rate on both platforms on the same day are compared
-- (fixed-amount offers are not comparable with percentages).
-- One row per merchant. The summary (median gap, share ahead / tied / behind) is computed in
-- the notebook with a bootstrap confidence interval and a Wilcoxon signed-rank test.
WITH pct AS (
    SELECT merchant_id, platform, rate_value
    FROM fct_cashback_offer
    WHERE rate_type = 'percent'
),
paired AS (
    SELECT
        w.merchant_id,
        w.rate_value AS widilo_pct,
        g.rate_value AS igraal_pct
    FROM pct w
    JOIN pct g ON g.merchant_id = w.merchant_id AND g.platform = 'iGraal'
    WHERE w.platform = 'Widilo'
)
SELECT
    p.merchant_id,
    m.merchant,
    m.category,
    p.widilo_pct,
    p.igraal_pct,
    round(p.widilo_pct - p.igraal_pct, 2) AS gap_widilo_minus_igraal_pts,
    CASE WHEN p.widilo_pct > p.igraal_pct THEN 'Widilo higher'
         WHEN p.widilo_pct < p.igraal_pct THEN 'iGraal higher'
         ELSE 'tie' END                   AS outcome
FROM paired p
JOIN dim_merchant m USING (merchant_id)
ORDER BY m.category, m.merchant;
