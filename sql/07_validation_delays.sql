-- 07_validation_delays.sql  -  PUBLIC DATA (Widilo merchant data)
-- How long do users wait before cashback is confirmed? Widilo publishes, per merchant, the delay
-- before the cashback is validated (the merchant's return / cancellation period).
-- Merchants without an announced delay are excluded.
SELECT
    m.category,
    count(*)                                         AS merchants_with_delay,
    round(median(o.validation_days_announced), 0)    AS median_days,
    round(quantile_cont(o.validation_days_announced, 0.9), 0) AS p90_days,
    round(100 * avg(CASE WHEN o.validation_days_announced > 60 THEN 1 ELSE 0 END), 1) AS share_over_60_days_pct
FROM fct_cashback_offer o
JOIN dim_merchant m USING (merchant_id)
WHERE o.platform = 'Widilo' AND o.validation_days_announced IS NOT NULL
GROUP BY m.category
ORDER BY median_days DESC, p90_days DESC, category;
