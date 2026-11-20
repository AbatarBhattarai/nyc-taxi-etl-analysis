"""
clean_data.py — Clean one month of NYC TLC yellow taxi trip data and load it
into a SQLite star schema.

Source data (not included in the repo, see README "How to run"):
    data/yellow_tripdata_2025-01.parquet   (NYC TLC, January 2025)
    data/taxi_zone_lookup.csv              (NYC TLC zone lookup, 265 zones)

Output:
    nyc_taxi.db with two tables:
        fact_trips  — one row per cleaned trip
        dim_zones   — one row per taxi zone (LocationID, Borough, Zone, service_zone)

Every cleaning rule below is applied in order and the script logs how many
rows each rule removed. The rules were written after profiling the raw file;
the raw-data counts behind each rule are documented in the README.

Design decision worth calling out: 540,149 rows (15.5% of the file) have
payment_type = 0 ("Flex Fare" trips). For those rows the TLC feed does not
report passenger_count, RatecodeID, congestion_surcharge or Airport_fee at
all — the fields are null for the entire block, not scattered randomly.
Those are real, paid trips, so they are KEPT. passenger_count is stored as
NULL (unknown) for them instead of dropping 15% of the month or inventing
a value.
"""

import sqlite3

import pandas as pd

RAW_TRIPS = "data/yellow_tripdata_2025-01.parquet"
RAW_ZONES = "data/taxi_zone_lookup.csv"
DB_PATH = "nyc_taxi.db"

# The file is defined as trips picked up in January 2025.
MONTH_START = pd.Timestamp("2025-01-01")
MONTH_END = pd.Timestamp("2025-02-01")

# A yellow-cab trip inside NYC zones cannot average more than 65 mph over its
# whole duration, and 99.9% of trips in the raw file finish in under 99
# minutes. Rows past these limits are meters left running / clock errors.
MAX_AVG_MPH = 65
MAX_DURATION_MIN = 180

# The longest legitimate yellow-taxi trip (e.g. far Queens / airport runs)
# is well under 100 miles. The raw file's maximum is 276,423 miles, which
# is an odometer/meter glitch, not a trip.
MAX_DISTANCE_MI = 100


def drop(df, mask, label, log):
    """Drop rows matching mask, record how many, return the smaller frame."""
    n = int(mask.sum())
    log.append((label, n))
    return df[~mask]


def main():
    df = pd.read_parquet(RAW_TRIPS)
    zones = pd.read_csv(RAW_ZONES)
    start_rows = len(df)
    log = []

    # --- Rule 1: pickup outside January 2025 --------------------------------
    # The monthly file is defined by pickup month. A handful of rows carry
    # December 2024 or February 2025 pickups (meter clock drift); they belong
    # to other months' files.
    df = drop(
        df,
        (df["tpep_pickup_datetime"] < MONTH_START)
        | (df["tpep_pickup_datetime"] >= MONTH_END),
        "Pickup timestamp outside January 2025",
        log,
    )

    # Duration is needed by several rules; compute it once.
    df["duration_min"] = (
        df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    ).dt.total_seconds() / 60

    # --- Rule 2: dropoff at or before pickup --------------------------------
    # Zero or negative trip length is a clock error, not a trip.
    df = drop(df, df["duration_min"] <= 0, "Dropoff at/before pickup (duration <= 0)", log)

    # --- Rule 3: trip longer than 3 hours ------------------------------------
    # Meters left running after the passenger left. 99.9% of raw trips are
    # under 99 minutes, so 180 is a generous ceiling.
    df = drop(df, df["duration_min"] > MAX_DURATION_MIN, "Duration over 180 minutes", log)

    # --- Rule 4: fare of zero or less ---------------------------------------
    # Negative fares are refunds/voids/adjustments recorded in the trip feed
    # (they cluster in Dispute / No charge payment types), and a $0 fare is
    # not a paid trip. Neither belongs in revenue or fare analysis.
    df = drop(df, df["fare_amount"] <= 0, "Fare amount <= 0 (refunds, voids, no-charge)", log)

    # --- Rule 5: total amount of zero or less -------------------------------
    # Same reasoning as Rule 4, applied to the final charged total.
    df = drop(df, df["total_amount"] <= 0, "Total amount <= 0", log)

    # --- Rule 6: negative tip ------------------------------------------------
    # A negative tip is a keying error. Only ~100 rows, so dropping is safer
    # than guessing the intended value.
    df = drop(df, df["tip_amount"] < 0, "Negative tip amount", log)

    # --- Rule 7: trip distance of zero ---------------------------------------
    # 90k+ rows recorded 0.00 miles, most with a positive fare — the meter or
    # GPS recorded no movement. With no distance, the row cannot support any
    # distance, speed, or per-mile analysis, and a 0-mile "trip" is not a trip.
    df = drop(df, df["trip_distance"] <= 0, "Trip distance <= 0 (no movement recorded)", log)

    # --- Rule 8: trip distance over 100 miles --------------------------------
    df = drop(df, df["trip_distance"] > MAX_DISTANCE_MI, "Trip distance > 100 miles", log)

    # --- Rule 9: impossible average speed ------------------------------------
    # Average speed over the full trip above 65 mph cannot happen in NYC
    # traffic; these are short clock errors paired with real distances.
    df["avg_mph"] = df["trip_distance"] / (df["duration_min"] / 60)
    df = drop(df, df["avg_mph"] > MAX_AVG_MPH, "Implied average speed > 65 mph", log)

    # --- Rule 10: impossible passenger counts (where reported) ---------------
    # 0 passengers means no trip happened; a yellow cab cannot legally carry
    # more than 6. Rows where passenger_count was never reported (Flex Fare)
    # are kept with NULL — see the module docstring.
    reported = df["passenger_count"].notna()
    df = drop(
        df,
        reported & ((df["passenger_count"] == 0) | (df["passenger_count"] > 6)),
        "Passenger count 0 or > 6 (where reported)",
        log,
    )

    # --- Build the fact table -------------------------------------------------
    fact = pd.DataFrame(
        {
            "vendor_id": df["VendorID"].astype(int),
            "pickup_datetime": df["tpep_pickup_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "dropoff_datetime": df["tpep_dropoff_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "pickup_date": df["tpep_pickup_datetime"].dt.strftime("%Y-%m-%d"),
            "pickup_hour": df["tpep_pickup_datetime"].dt.hour.astype(int),
            "day_of_week": df["tpep_pickup_datetime"].dt.day_name(),
            "is_weekend": (df["tpep_pickup_datetime"].dt.day_of_week >= 5).astype(int),
            # Nullable integer: stays NULL for Flex Fare rows (never reported).
            "passenger_count": df["passenger_count"].astype("Int64"),
            "trip_distance": df["trip_distance"].round(2),
            "pu_location_id": df["PULocationID"].astype(int),
            "do_location_id": df["DOLocationID"].astype(int),
            "payment_type": df["payment_type"].astype(int),
            "fare_amount": df["fare_amount"].round(2),
            "tip_amount": df["tip_amount"].round(2),
            "tolls_amount": df["tolls_amount"].round(2),
            "total_amount": df["total_amount"].round(2),
            "duration_min": df["duration_min"].round(2),
            "airport_fee": df["Airport_fee"].round(2),  # NULL for Flex Fare rows
        }
    ).reset_index(drop=True)
    fact.insert(0, "trip_id", range(1, len(fact) + 1))

    dim_zones = zones.rename(
        columns={"LocationID": "location_id", "Borough": "borough", "Zone": "zone"}
    )[["location_id", "borough", "zone", "service_zone"]]

    # --- Load into SQLite ------------------------------------------------------
    conn = sqlite3.connect(DB_PATH)
    fact.to_sql("fact_trips", conn, if_exists="replace", index=False)
    dim_zones.to_sql("dim_zones", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX idx_fact_pu ON fact_trips(pu_location_id)")
    conn.execute("CREATE INDEX idx_fact_do ON fact_trips(do_location_id)")
    conn.execute("CREATE INDEX idx_fact_hour ON fact_trips(pickup_hour)")
    conn.commit()
    conn.close()

    # --- Report -----------------------------------------------------------------
    print(f"Raw rows:        {start_rows:,}")
    removed_total = 0
    for label, n in log:
        print(f"  - {label}: {n:,}")
        removed_total += n
    print(f"Total removed:   {removed_total:,}")
    print(f"Cleaned rows:    {len(fact):,}  (written to {DB_PATH}: fact_trips)")
    print(f"Zones written:   {len(dim_zones):,}  (dim_zones)")


if __name__ == "__main__":
    main()
