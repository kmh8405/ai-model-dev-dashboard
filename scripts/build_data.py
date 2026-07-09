"""Rebuild data/data.json from the ai_model_leaderboard table in Supabase.

Uses the most recent snapshot_date present per category (categories can in
principle refresh on different days) and writes out the same shape the
frontend previously had hardcoded: {category: [{model_name, organization,
rating, vote_count, rank}, ...]}.
"""
import json
import os
from pathlib import Path

import psycopg2

CATEGORIES = ["overall", "coding", "math"]
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "data.json"


def fetch_category(cur, category):
    cur.execute(
        """
        select model_name, organization, rank, rating, vote_count
        from ai_model_leaderboard
        where category = %s
          and snapshot_date = (
            select max(snapshot_date) from ai_model_leaderboard where category = %s
          )
        order by rank asc
        """,
        (category, category),
    )
    return [
        {
            "model_name": model_name,
            "organization": organization,
            "rank": rank,
            "rating": float(rating),
            "vote_count": int(vote_count),
        }
        for model_name, organization, rank, rating, vote_count in cur.fetchall()
    ]


def main():
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            data = {category: fetch_category(cur, category) for category in CATEGORIES}
    finally:
        conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({sum(len(v) for v in data.values())} rows)")


if __name__ == "__main__":
    main()
