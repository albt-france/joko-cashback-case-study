-- =============================================================================================
-- 00_semantic_layer.sql  -  SIMULATED data only
-- A small "semantic layer": clear names + one place where every metric is defined.
-- These three views are the ONLY objects the "Ask the data" assistant is allowed to query.
-- Metric definitions are documented in METRICS.md (same wording).
-- =============================================================================================

-- ---------------------------------------------------------------------------------------------
-- v_purchases_enriched: one row per tracked purchase, with merchant and user attributes
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_purchases_enriched AS
SELECT
    p.purchase_id,
    p.user_id,
    p.purchase_date,
    date_trunc('month', p.purchase_date)::DATE        AS purchase_month,
    m.merchant,
    m.category,
    u.country,
    u.acquisition_channel,
    u.platform,
    p.amount_eur,
    p.cashback_rate_pct,
    p.cashback_eur,
    p.status,                                          -- pending / validated / cancelled
    p.validation_days,                                 -- days from purchase to validation (validated or cancelled)
    p.validated_date
FROM purchases p
JOIN merchants m USING (merchant_id)
JOIN users     u USING (user_id);

-- ---------------------------------------------------------------------------------------------
-- v_user_metrics: one row per user, with the user-level metrics
--   activated            = at least one non-cancelled purchase in the 30 days after signup
--   retained_d90         = at least one session between day 61 and day 90 after signup
--                          (NULL when the user signed up less than 90 days before the data end)
--   first_validation_days= validation delay of the user's first validated purchase
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_user_metrics AS
WITH data_end AS (SELECT DATE '2026-10-31' AS d),
first_purchase AS (
    SELECT user_id,
           min(purchase_date) FILTER (WHERE status <> 'cancelled') AS first_purchase_date
    FROM purchases GROUP BY user_id
),
first_validation AS (
    SELECT user_id, arg_min(validation_days, purchase_date) AS first_validation_days
    FROM purchases WHERE status = 'validated' GROUP BY user_id
),
late_sessions AS (
    SELECT e.user_id, sum(e.event_count) AS sessions_d61_d90
    FROM events e JOIN users u USING (user_id)
    WHERE e.event_type = 'session'
      AND e.event_date BETWEEN u.signup_date + INTERVAL 61 DAY AND u.signup_date + INTERVAL 90 DAY
    GROUP BY e.user_id
),
totals AS (
    SELECT user_id,
           count(*)                                              AS purchases,
           sum(amount_eur)                                       AS gmv_eur,
           sum(cashback_eur) FILTER (WHERE status = 'validated') AS validated_cashback_eur
    FROM purchases GROUP BY user_id
)
SELECT
    u.user_id,
    u.signup_date,
    date_trunc('month', u.signup_date)::DATE AS signup_month,
    u.country,
    u.acquisition_channel,
    u.platform,
    coalesce(fp.first_purchase_date <= u.signup_date + INTERVAL 30 DAY, FALSE) AS activated,
    CASE WHEN u.signup_date + INTERVAL 90 DAY > (SELECT d FROM data_end) THEN NULL
         ELSE coalesce(ls.sessions_d61_d90, 0) > 0 END              AS retained_d90,
    fv.first_validation_days,
    coalesce(t.purchases, 0)               AS purchases,
    coalesce(t.gmv_eur, 0)                 AS gmv_eur,
    coalesce(t.validated_cashback_eur, 0)  AS validated_cashback_eur
FROM users u
LEFT JOIN first_purchase   fp USING (user_id)
LEFT JOIN first_validation fv USING (user_id)
LEFT JOIN late_sessions    ls USING (user_id)
LEFT JOIN totals           t  USING (user_id);

-- ---------------------------------------------------------------------------------------------
-- v_monthly_kpis: one row per month and country
--   mau                        = users with at least one session in the month
--   validated_cashback_eur     = cashback of purchases validated in the month
--   cashback_cost_per_mau_eur  = validated_cashback_eur / mau
--   median_validation_days     = median delay of purchases validated in the month
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_kpis AS
WITH months AS (
    SELECT DISTINCT date_trunc('month', event_date)::DATE AS month FROM events
),
mau AS (
    SELECT date_trunc('month', e.event_date)::DATE AS month, u.country, count(DISTINCT e.user_id) AS mau
    FROM events e JOIN users u USING (user_id)
    WHERE e.event_type = 'session' GROUP BY 1, 2
),
signups AS (
    SELECT date_trunc('month', signup_date)::DATE AS month, country, count(*) AS new_users
    FROM users GROUP BY 1, 2
),
purch AS (
    SELECT purchase_month AS month, country, count(*) AS purchases, sum(amount_eur) AS gmv_eur
    FROM v_purchases_enriched GROUP BY 1, 2
),
valid AS (
    SELECT date_trunc('month', validated_date)::DATE AS month, country,
           sum(cashback_eur) AS validated_cashback_eur,
           median(validation_days) AS median_validation_days
    FROM v_purchases_enriched WHERE status = 'validated' GROUP BY 1, 2
)
SELECT
    m.month,
    c.country,
    coalesce(s.new_users, 0)                         AS new_users,
    coalesce(a.mau, 0)                               AS mau,
    coalesce(p.purchases, 0)                         AS purchases,
    round(coalesce(p.gmv_eur, 0), 2)                 AS gmv_eur,
    round(coalesce(v.validated_cashback_eur, 0), 2)  AS validated_cashback_eur,
    round(coalesce(v.validated_cashback_eur, 0) / nullif(a.mau, 0), 3) AS cashback_cost_per_mau_eur,
    v.median_validation_days
FROM months m
CROSS JOIN (SELECT DISTINCT country FROM users) c
LEFT JOIN signups s ON s.month = m.month AND s.country = c.country
LEFT JOIN mau     a ON a.month = m.month AND a.country = c.country
LEFT JOIN purch   p ON p.month = m.month AND p.country = c.country
LEFT JOIN valid   v ON v.month = m.month AND v.country = c.country
WHERE m.month <= DATE '2026-10-01';
