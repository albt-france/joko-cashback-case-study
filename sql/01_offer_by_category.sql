-- 01_offer_by_category.sql  -  PUBLIC DATA (Widilo + iGraal snapshot, France)
-- What does the French cashback market pay, by category?
-- One row per category: number of merchants, median % rate, share of fixed-amount offers,
-- share of boosted offers. Rates are taken per platform, then summarised.
WITH offers AS (
    SELECT o.*, m.category
    FROM fct_cashback_offer o
    JOIN dim_merchant m USING (merchant_id)
)
SELECT
    category,
    count(DISTINCT merchant_id)                                         AS merchants,
    round(median(rate_value) FILTER (WHERE rate_type = 'percent'), 2)   AS median_rate_pct,
    round(quantile_cont(rate_value, 0.75) FILTER (WHERE rate_type = 'percent'), 2) AS p75_rate_pct,
    round(100 * avg(CASE WHEN rate_type = 'fixed' THEN 1 ELSE 0 END), 1) AS share_fixed_pct,
    round(100 * avg(CASE WHEN is_boosted THEN 1 ELSE 0 END), 1)          AS share_boosted_pct,
    round(median(validation_days_announced), 0)                         AS median_validation_days_widilo
FROM offers
GROUP BY category
ORDER BY median_rate_pct DESC, category;
