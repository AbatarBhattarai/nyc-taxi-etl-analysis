-- queries.sql — Business questions answered against nyc_taxi.db
-- (fact_trips + dim_zones, January 2025 yellow taxi trips, cleaned).
-- Run with:  python run_queries.py     (writes verified output to query-results.md)
-- Payment type codes (TLC data dictionary):
--   0 = Flex Fare, 1 = Credit card, 2 = Cash, 3 = No charge, 4 = Dispute, 5 = Unknown

-- Q1: Peak demand — trips by pickup hour
-- When is demand highest and lowest across the day?
SELECT
    pickup_hour,
    COUNT(*)                                   AS trips,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_trips,
    ROUND(AVG(total_amount), 2)                AS avg_total_usd
FROM fact_trips
GROUP BY pickup_hour
ORDER BY pickup_hour;

-- Q2: Revenue by pickup borough
-- Which boroughs generate the trips and the money?
SELECT
    z.borough,
    COUNT(*)                        AS trips,
    ROUND(SUM(f.total_amount), 2)   AS total_revenue_usd,
    ROUND(AVG(f.total_amount), 2)   AS avg_total_usd,
    ROUND(AVG(f.trip_distance), 2)  AS avg_distance_mi
FROM fact_trips f
JOIN dim_zones z ON z.location_id = f.pu_location_id
GROUP BY z.borough
ORDER BY total_revenue_usd DESC;

-- Q3: Average fare by distance band
-- How does the fare build as trips get longer?
SELECT
    CASE
        WHEN trip_distance <= 1  THEN '0-1 mi'
        WHEN trip_distance <= 2  THEN '1-2 mi'
        WHEN trip_distance <= 3  THEN '2-3 mi'
        WHEN trip_distance <= 5  THEN '3-5 mi'
        WHEN trip_distance <= 10 THEN '5-10 mi'
        ELSE '10+ mi'
    END                             AS distance_band,
    COUNT(*)                        AS trips,
    ROUND(AVG(fare_amount), 2)      AS avg_fare_usd,
    ROUND(AVG(total_amount), 2)     AS avg_total_usd,
    ROUND(AVG(fare_amount / trip_distance), 2) AS avg_fare_per_mile_usd
FROM fact_trips
GROUP BY distance_band
ORDER BY MIN(trip_distance);

-- Q4: Tip behavior by payment type
-- Note: the meter only records tip amounts for credit-card payments.
-- Cash tips are not captured in TLC data, so tip % is only meaningful
-- for payment_type = 1. This query shows why that caveat matters.
SELECT
    payment_type,
    CASE payment_type
        WHEN 0 THEN 'Flex Fare' WHEN 1 THEN 'Credit card' WHEN 2 THEN 'Cash'
        WHEN 3 THEN 'No charge' WHEN 4 THEN 'Dispute'    WHEN 5 THEN 'Unknown'
    END                             AS payment_label,
    COUNT(*)                        AS trips,
    ROUND(AVG(tip_amount), 2)       AS avg_tip_usd,
    ROUND(100.0 * AVG(tip_amount / fare_amount), 2) AS avg_tip_pct_of_fare
FROM fact_trips
GROUP BY payment_type
ORDER BY trips DESC;

-- Q5: Airport trips (JFK = zone 132, LaGuardia = zone 138, Newark = zone 1)
-- How big is the airport business, and what is an airport trip worth
-- versus a typical trip?
SELECT
    CASE
        WHEN pu_location_id = 132 OR do_location_id = 132 THEN 'JFK'
        WHEN pu_location_id = 138 OR do_location_id = 138 THEN 'LaGuardia'
        WHEN pu_location_id = 1   OR do_location_id = 1   THEN 'Newark (EWR)'
    END                             AS airport,
    COUNT(*)                        AS trips,
    ROUND(SUM(total_amount), 2)     AS total_revenue_usd,
    ROUND(AVG(total_amount), 2)     AS avg_total_usd,
    ROUND(AVG(trip_distance), 2)    AS avg_distance_mi,
    ROUND(AVG(duration_min), 1)     AS avg_duration_min
FROM fact_trips
WHERE pu_location_id IN (1, 132, 138) OR do_location_id IN (1, 132, 138)
GROUP BY airport
ORDER BY trips DESC;

-- Q6: Weekday vs weekend patterns
-- Does the weekend change trip volume, distance, or spend?
SELECT
    CASE is_weekend WHEN 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    COUNT(*)                        AS trips,
    ROUND(AVG(total_amount), 2)     AS avg_total_usd,
    ROUND(AVG(trip_distance), 2)    AS avg_distance_mi,
    ROUND(AVG(duration_min), 1)     AS avg_duration_min,
    ROUND(AVG(passenger_count), 2)  AS avg_passengers_reported
FROM fact_trips
GROUP BY is_weekend
ORDER BY is_weekend;

-- Q7: Top 10 pickup zones by trips
-- Where do trips actually start?
SELECT
    z.zone,
    z.borough,
    COUNT(*)                        AS trips,
    ROUND(SUM(f.total_amount), 2)   AS total_revenue_usd,
    ROUND(AVG(f.total_amount), 2)   AS avg_total_usd
FROM fact_trips f
JOIN dim_zones z ON z.location_id = f.pu_location_id
GROUP BY z.zone, z.borough
ORDER BY trips DESC
LIMIT 10;
