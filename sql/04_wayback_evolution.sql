-- 04_wayback_evolution.sql  -  PUBLIC DATA (Wayback Machine copies of Joko's App Store pages + today's page)
-- How fast does Joko's App Store footprint grow, in France and in the US?
-- For each storefront and year: last rating count seen that year and ratings added since the previous year.
-- Archived snapshots are irregular, so "last seen in the year" is not always 31 December.
WITH yearly AS (
    SELECT
        storefront,
        year(snapshot::DATE)                         AS year,
        arg_max(rating_count, snapshot::DATE)        AS last_rating_count,
        max(snapshot::DATE)                          AS last_snapshot
    FROM fct_app_rating_history
    GROUP BY storefront, year(snapshot::DATE)
)
SELECT
    storefront,
    year,
    last_snapshot,
    last_rating_count,
    last_rating_count - lag(last_rating_count) OVER (PARTITION BY storefront ORDER BY year) AS ratings_added,
    round(last_rating_count / lag(last_rating_count) OVER (PARTITION BY storefront ORDER BY year), 2) AS growth_multiple
FROM yearly
ORDER BY storefront, year;
