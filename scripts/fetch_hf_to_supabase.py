"""Pull the latest lmarena-ai/leaderboard-dataset snapshot and upsert it into Supabase.

Uses the dataset's parquet export (one file download, ~9.7k rows covering all
29 lmarena categories) rather than the datasets-server /rows preview API,
which is rate-limited to 100 rows/page and prone to transient 502s.
"""
import io
import os
import time

import psycopg2
import pyarrow.parquet as pq
import requests

DATASET = "lmarena-ai/leaderboard-dataset"
CONFIG = "text"
SPLIT = "latest"
TARGET_CATEGORIES = {"overall", "coding", "math"}
TOP_N = 20

PARQUET_INDEX_URL = (
    f"https://huggingface.co/api/datasets/{DATASET}/parquet/{CONFIG}/{SPLIT}"
)

MAX_ATTEMPTS = 8
INITIAL_BACKOFF_SECONDS = 5


def _get_with_retry(url, **kwargs):
    """GET a URL, retrying with exponential backoff on failure.

    Right after the upstream dataset is pushed, Hugging Face's parquet
    export can 400 while it's still being (re)converted. On 2026-07-11 this
    took longer than the previous 5-attempt/~75s budget, so a genuine "text"
    config update (2026-07-10 snapshot) still failed outright. 8 attempts
    (~635s / ~10.5 min worst case) gives the conversion much more room
    without making a truly broken run hang forever.
    """
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt == MAX_ATTEMPTS - 1:
                raise
            wait = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
            print(
                f"GET {url} failed ({exc}); retrying in {wait}s "
                f"(attempt {attempt + 1}/{MAX_ATTEMPTS})"
            )
            time.sleep(wait)
    raise last_exc  # pragma: no cover - unreachable, loop always returns or raises


def fetch_all_rows():
    resp = _get_with_retry(PARQUET_INDEX_URL, timeout=30)
    parquet_urls = resp.json()

    rows = []
    for url in parquet_urls:
        data = _get_with_retry(url, timeout=60).content
        table = pq.read_table(io.BytesIO(data))
        rows.extend(table.to_pylist())
    return rows


def filter_top_n(rows):
    return [
        r for r in rows
        if r["category"] in TARGET_CATEGORIES and r["rank"] is not None and r["rank"] <= TOP_N
    ]


def upsert(rows):
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    insert into ai_model_leaderboard
                        (model_name, organization, category, rank, rating, vote_count, snapshot_date)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (category, model_name, snapshot_date)
                    do update set
                        organization = excluded.organization,
                        rank = excluded.rank,
                        rating = excluded.rating,
                        vote_count = excluded.vote_count,
                        fetched_at = now()
                    """,
                    (
                        r["model_name"],
                        r["organization"],
                        r["category"],
                        int(r["rank"]),
                        r["rating"],
                        int(r["vote_count"]),
                        r["leaderboard_publish_date"],
                    ),
                )
    finally:
        conn.close()


def main():
    rows = fetch_all_rows()
    print(f"fetched {len(rows)} rows from {DATASET}")
    filtered = filter_top_n(rows)
    print(f"kept {len(filtered)} rows across {sorted(TARGET_CATEGORIES)} (top {TOP_N} each)")
    upsert(filtered)
    print("upsert complete")


if __name__ == "__main__":
    main()
