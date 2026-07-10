"""Rebuild data/data.json from the ai_model_leaderboard table in Supabase.

Uses the most recent snapshot_date present per category (categories can in
principle refresh on different days) and writes out the same shape the
frontend previously had hardcoded: {category: [{model_name, organization,
rating, vote_count, rank}, ...]}.

Also diffs each category's latest snapshot against its previous one and
writes the result to a "changelog" key, so the dashboard can show what
changed since the last upstream update without any extra API/LLM calls —
the history is already sitting in the snapshot_date column.
"""
import json
import os
from pathlib import Path

import psycopg2

CATEGORIES = ["overall", "coding", "math"]
CATEGORY_LABELS = {"overall": "Overall", "coding": "Coding", "math": "Math"}
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


def fetch_snapshot_dates(cur, category):
    """Up to the 2 most recent distinct snapshot dates for a category, newest first."""
    cur.execute(
        """
        select distinct snapshot_date
        from ai_model_leaderboard
        where category = %s
        order by snapshot_date desc
        limit 2
        """,
        (category,),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_ranks(cur, category, snapshot_date):
    cur.execute(
        """
        select model_name, rank
        from ai_model_leaderboard
        where category = %s and snapshot_date = %s
        """,
        (category, snapshot_date),
    )
    return {model_name: rank for model_name, rank in cur.fetchall()}


def diff_ranks(previous_ranks, current_ranks):
    """Compare two {model_name: rank} snapshots and bucket what changed."""
    moved = []
    entered = []
    dropped = []
    for model_name, to_rank in current_ranks.items():
        from_rank = previous_ranks.get(model_name)
        if from_rank is None:
            entered.append({"model_name": model_name, "rank": to_rank})
        elif from_rank != to_rank:
            moved.append({"model_name": model_name, "from_rank": from_rank, "to_rank": to_rank})
    for model_name, from_rank in previous_ranks.items():
        if model_name not in current_ranks:
            dropped.append({"model_name": model_name, "last_rank": from_rank})

    moved.sort(key=lambda m: abs(m["from_rank"] - m["to_rank"]), reverse=True)
    entered.sort(key=lambda e: e["rank"])
    dropped.sort(key=lambda d: d["last_rank"])
    return {"moved": moved, "entered": entered, "dropped": dropped}


def build_headline(diffs):
    """Pick the single most notable change across all categories as one sentence."""
    for category in CATEGORIES:
        for m in diffs[category]["moved"]:
            if m["to_rank"] == 1:
                return f'{m["model_name"]}이 {CATEGORY_LABELS[category]} 부문 {m["from_rank"]}위→1위로 올라섰습니다'
        for e in diffs[category]["entered"]:
            if e["rank"] == 1:
                return f'{e["model_name"]}이 {CATEGORY_LABELS[category]} 부문 1위로 새로 진입했습니다'

    best_move = None
    for category in CATEGORIES:
        for m in diffs[category]["moved"]:
            delta = abs(m["from_rank"] - m["to_rank"])
            if best_move is None or delta > best_move[0]:
                best_move = (delta, category, m)
    if best_move:
        _, category, m = best_move
        direction = "올라섰습니다" if m["to_rank"] < m["from_rank"] else "내려갔습니다"
        return f'{m["model_name"]}이 {CATEGORY_LABELS[category]} 부문 {m["from_rank"]}위→{m["to_rank"]}위로 {direction}'

    best_entry = None
    for category in CATEGORIES:
        for e in diffs[category]["entered"]:
            if best_entry is None or e["rank"] < best_entry[1]["rank"]:
                best_entry = (category, e)
    if best_entry:
        category, e = best_entry
        return f'{e["model_name"]}이 {CATEGORY_LABELS[category]} 부문 {e["rank"]}위로 새로 진입했습니다'

    return None


def build_changelog(cur):
    """Diff each category's latest snapshot against its previous one.

    Returns None if no category has a previous snapshot yet (e.g. the very
    first run against a freshly created table).
    """
    diffs = {}
    current_dates = []
    previous_dates = []
    for category in CATEGORIES:
        dates = fetch_snapshot_dates(cur, category)
        if len(dates) < 2:
            diffs[category] = {"moved": [], "entered": [], "dropped": []}
            continue
        current_date, previous_date = dates
        current_dates.append(current_date)
        previous_dates.append(previous_date)
        diffs[category] = diff_ranks(
            fetch_ranks(cur, category, previous_date),
            fetch_ranks(cur, category, current_date),
        )

    if not current_dates:
        return None

    return {
        "previous_snapshot_date": min(previous_dates).isoformat(),
        "current_snapshot_date": max(current_dates).isoformat(),
        "headline": build_headline(diffs),
        **diffs,
    }


def main():
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            data = {category: fetch_category(cur, category) for category in CATEGORIES}
            changelog = build_changelog(cur)
    finally:
        conn.close()

    if changelog is not None:
        data["changelog"] = changelog

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    row_count = sum(len(v) for v in data.values() if isinstance(v, list))
    print(f"wrote {OUTPUT_PATH} ({row_count} rows)")


if __name__ == "__main__":
    main()
