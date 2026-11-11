-- 06_page7_metrics.sql  -  SIMULATED DATA
-- The metrics proposed on page 7, by signup cohort (month) and country:
--   activation rate, D90 retention rate, retention of activated vs not activated users,
--   retention by delay of the first validated cashback, validated cashback per user.
-- Uses the semantic layer views (00_semantic_layer.sql).
SELECT
    signup_month,
    country,
    count(*)                                                        AS new_users,
    round(100 * avg(activated::INT), 1)                             AS activation_rate_pct,
    round(100 * avg(retained_d90::INT), 1)                          AS d90_retention_pct,
    round(100 * avg(retained_d90::INT) FILTER (WHERE activated), 1)     AS d90_retention_activated_pct,
    round(100 * avg(retained_d90::INT) FILTER (WHERE NOT activated), 1) AS d90_retention_not_activated_pct,
    round(100 * avg(retained_d90::INT) FILTER (WHERE first_validation_days <= 45), 1) AS d90_ret_first_val_le45_pct,
    round(100 * avg(retained_d90::INT) FILTER (WHERE first_validation_days > 45), 1)  AS d90_ret_first_val_gt45_pct,
    round(avg(validated_cashback_eur), 2)                           AS validated_cashback_per_user_eur
FROM v_user_metrics
GROUP BY signup_month, country
ORDER BY signup_month, country;
