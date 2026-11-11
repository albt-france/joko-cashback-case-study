-- 03_boost_frequency.sql  -  PUBLIC DATA
-- How often are rates "boosted" (temporarily raised), and by how much?
-- A boost is flagged by the platform itself ("au lieu de X %" / previous value shown).
-- boost_multiplier = boosted rate / usual rate.
SELECT
    o.platform,
    m.category,
    count(*)                                                    AS offers,
    sum(CASE WHEN o.is_boosted THEN 1 ELSE 0 END)               AS boosted_offers,
    round(100 * avg(CASE WHEN o.is_boosted THEN 1 ELSE 0 END), 1) AS share_boosted_pct,
    round(median(o.rate_value / nullif(o.rate_before_boost, 0))
          FILTER (WHERE o.is_boosted AND o.rate_before_boost > 0), 2) AS median_boost_multiplier
FROM fct_cashback_offer o
JOIN dim_merchant m USING (merchant_id)
GROUP BY ROLLUP (o.platform, m.category)
ORDER BY o.platform NULLS FIRST, share_boosted_pct DESC, m.category;
