"""
make_charts.py — Build the README charts from nyc_taxi.db with matplotlib.
All values come straight from SQL queries against the cleaned data.
"""

import sqlite3

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = "nyc_taxi.db"
OUT_DIR = "charts"

conn = sqlite3.connect(DB_PATH)

# --- Chart 1: Trips by pickup hour -------------------------------------------
rows = conn.execute(
    "SELECT pickup_hour, COUNT(*) FROM fact_trips GROUP BY pickup_hour ORDER BY pickup_hour"
).fetchall()
hours = [r[0] for r in rows]
trips = [r[1] for r in rows]
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.bar(hours, trips, color="#2b6cb0")
ax.set_xlabel("Pickup hour (24h)")
ax.set_ylabel("Trips")
ax.set_title("Yellow taxi trips by pickup hour — January 2025 (cleaned)")
ax.set_xticks(range(24))
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT_DIR}/trips_by_hour.png", dpi=130)
plt.close(fig)

# --- Chart 2: Revenue by pickup borough ---------------------------------------
rows = conn.execute(
    """
    SELECT z.borough, SUM(f.total_amount) / 1e6
    FROM fact_trips f JOIN dim_zones z ON z.location_id = f.pu_location_id
    WHERE z.borough IN ('Manhattan', 'Queens', 'Brooklyn', 'Bronx', 'Staten Island')
    GROUP BY z.borough ORDER BY SUM(f.total_amount) DESC
    """
).fetchall()
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar([r[0] for r in rows], [r[1] for r in rows], color="#2f855a")
ax.set_ylabel("Total revenue ($ millions)")
ax.set_title("Revenue by pickup borough — January 2025 (cleaned)")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT_DIR}/revenue_by_borough.png", dpi=130)
plt.close(fig)

# --- Chart 3: Average fare by distance band ------------------------------------
rows = conn.execute(
    """
    SELECT CASE
             WHEN trip_distance <= 1  THEN '0-1 mi'
             WHEN trip_distance <= 2  THEN '1-2 mi'
             WHEN trip_distance <= 3  THEN '2-3 mi'
             WHEN trip_distance <= 5  THEN '3-5 mi'
             WHEN trip_distance <= 10 THEN '5-10 mi'
             ELSE '10+ mi' END AS band,
           AVG(fare_amount), AVG(fare_amount / trip_distance)
    FROM fact_trips GROUP BY band ORDER BY MIN(trip_distance)
    """
).fetchall()
bands = [r[0] for r in rows]
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar(bands, [r[1] for r in rows], color="#6b46c1", label="Avg fare ($)")
ax.plot(bands, [r[2] for r in rows], color="#c53030", marker="o", label="Avg fare per mile ($)")
ax.set_ylabel("USD")
ax.set_title("Average fare and fare per mile by distance band — January 2025")
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT_DIR}/fare_by_distance_band.png", dpi=130)
plt.close(fig)

# --- Chart 4: Hourly pattern, weekday vs weekend -------------------------------
rows = conn.execute(
    """
    SELECT pickup_hour,
           SUM(CASE WHEN is_weekend = 0 THEN 1 ELSE 0 END) AS weekday_trips,
           SUM(CASE WHEN is_weekend = 1 THEN 1 ELSE 0 END) AS weekend_trips
    FROM fact_trips GROUP BY pickup_hour ORDER BY pickup_hour
    """
).fetchall()
# January 2025 had 23 weekdays and 8 weekend days — normalize to trips per day.
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot([r[0] for r in rows], [r[1] / 23 for r in rows], marker="o", label="Weekday (per day)")
ax.plot([r[0] for r in rows], [r[2] / 8 for r in rows], marker="s", label="Weekend (per day)")
ax.set_xlabel("Pickup hour (24h)")
ax.set_ylabel("Trips per day")
ax.set_title("Demand pattern by hour: weekday vs weekend — January 2025")
ax.set_xticks(range(24))
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT_DIR}/weekday_vs_weekend_by_hour.png", dpi=130)
plt.close(fig)

conn.close()
print("Charts written to", OUT_DIR)
