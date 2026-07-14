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

MAX_ATTEMPTS = 34
INITIAL_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


def _get_with_retry(url, **kwargs):
    """GET a URL, retrying with capped exponential backoff on failure.

    Right after the upstream dataset is pushed, Hugging Face's parquet
    export can 400 while it's still being (re)converted, and there's no
    documented upper bound on how long that takes — on 2026-07-11 it
    outlasted an 8-attempt/~635s budget, so a genuine "text" config update
    still failed outright. This repo's GitHub Actions minutes are free
    (public repo), so there's no reason to be stingy: 34 attempts with
    backoff capped at 60s gives ~1815s (~30 min) of total runway before
    giving up, which is this project's automated stand-in for "someone
    manually re-runs the workflow a while later".
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
            wait = min(INITIAL_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)
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


def _write_summary(text):
    """Append markdown to the GitHub Actions run summary, if running in CI.

    No-op locally (GITHUB_STEP_SUMMARY is unset outside Actions).
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(text)


def _diagnose_fetch_failure(exc):
    """Classify a fetch failure so the run summary says *what kind* of
    problem this was, not just "it failed".

    HF's webhook Activity log only shows whether the webhook was delivered
    (it always shows success here, since this relay always returns 202) —
    it says nothing about whether HF's own data-serving backend was
    actually up, which is one layer deeper and is what this checks.
    """
    try:
        resp = requests.get(
            f"https://datasets-server.huggingface.co/is-valid?dataset={DATASET}",
            timeout=10,
        )
        hf_platform_down = resp.status_code >= 500
    except requests.exceptions.RequestException:
        hf_platform_down = False

    if hf_platform_down:
        return (
            "## ❌ Refresh failed: Hugging Face platform outage (not this pipeline's bug)\n\n"
            f"All {MAX_ATTEMPTS} attempts to fetch `{DATASET}` failed, and "
            "`datasets-server.huggingface.co` itself is returning a 5xx — this looks like "
            "an outage on Hugging Face's side, not a bug here. Nothing to do but wait; "
            "the daily cron will retry automatically once HF recovers.\n\n"
            f"Last error: `{exc}`\n"
        )
    return (
        "## ❌ Refresh failed\n\n"
        f"All {MAX_ATTEMPTS} attempts to fetch `{DATASET}` failed, but "
        "`datasets-server.huggingface.co` looks healthy right now — this doesn't match "
        "the known HF-outage pattern, so it's worth a closer look rather than just waiting.\n\n"
        f"Last error: `{exc}`\n"
    )


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
    try:
        rows = fetch_all_rows()
    except requests.exceptions.RequestException as exc:
        _write_summary(_diagnose_fetch_failure(exc))
        raise
    print(f"fetched {len(rows)} rows from {DATASET}")
    filtered = filter_top_n(rows)
    print(f"kept {len(filtered)} rows across {sorted(TARGET_CATEGORIES)} (top {TOP_N} each)")
    upsert(filtered)
    print("upsert complete")


if __name__ == "__main__":
    main()
