-- 05_ratings_over_time.sql  -  PUBLIC DATA
-- Review ratings by store and half-year, with the number of reviews behind each average.
-- Averages on fewer than 10 reviews are flagged and must not be interpreted.
SELECT
    store,
    country,
    year(date::DATE) || '-H' || CASE WHEN month(date::DATE) <= 6 THEN 1 ELSE 2 END AS half_year,
    count(*)                       AS reviews,
    round(avg(rating), 2)          AS avg_rating,
    round(100 * avg(CASE WHEN rating <= 2 THEN 1 ELSE 0 END), 1) AS share_1_2_stars_pct,
    count(*) < 10                  AS too_few_to_interpret
FROM fct_app_reviews
GROUP BY ALL
ORDER BY store, country, half_year;
