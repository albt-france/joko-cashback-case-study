# Metrics that matter for a cashback app

One definition per metric, written once in SQL (`sql/00_semantic_layer.sql`) and reused by the dashboard,
the notebook and the "Ask the data" assistant. The numbers in this repository that use these metrics are
**SIMULATED** (see `data/ASSUMPTIONS.md`); the definitions are the deliverable.

| Metric | Definition | Grain | Why it matters | Watch out |
|---|---|---|---|---|
| **New users** | users whose `signup_date` falls in the period | month × country | top of funnel | sign-up ≠ installed app |
| **MAU** | users with ≥ 1 session in the month | month × country | active base, denominator of cost metrics | define "session" once (app open or extension activity) |
| **Activated user** | ≥ 1 non-cancelled tracked purchase within 30 days of sign-up | user | the moment a user sees the product work | 30 days (not 14) because purchases cluster around paydays and sales |
| **Activation rate** | activated users / new users of the cohort | sign-up cohort | onboarding quality, by channel | compare cohorts only once 30 days have passed |
| **Validated cashback** | cashback of purchases confirmed by the merchant (status `validated`) | month (validation date) | what the user actually gets, and what the company actually earns commission on | pending and cancelled amounts are excluded |
| **Time-to-validation** | days from purchase to merchant confirmation; reported as median and 90th percentile | purchase → month | the "waiting" users complain about (page 5); merchants' return periods drive it (page 2) | report the first validation of each user separately: it drives retention |
| **Time-to-first-validated-cashback** | days from sign-up to the user's first validated cashback | user | proposed north-star for onboarding | right-censored for recent users |
| **D90 retention** | ≥ 1 session between day 61 and day 90 after sign-up | sign-up cohort | durable usage | NULL for users who signed up < 90 days before the data end (censoring) |
| **Cashback cost per active user** | validated cashback of the month / MAU | month × country | unit economics of the rewards programme | pair it with commission revenue per MAU when available |
| **Cancellation rate** | cancelled purchases / tracked purchases | merchant, category | tracking quality and merchant behaviour | a spike is often a tracking incident, not user fraud |

## Proposed dashboard (self-service)
- One row of filters: country · acquisition channel · platform · sign-up month.
- Tiles: MAU, activation rate, D90 retention, cashback cost per MAU.
- Trends: MAU, median time-to-validation with a 45-day alert line, activation by channel.
- Every tile links to its definition above. Built on the semantic views, so a number means the same thing everywhere.

## How the AI assistant uses these definitions
`src/ai_ask_data.py` gives the model the semantic layer documentation (views, columns, metric formulas) and nothing else.
It can only query `v_monthly_kpis`, `v_user_metrics` and `v_purchases_enriched`, read-only.
