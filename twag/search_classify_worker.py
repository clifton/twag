"""Bounded subprocess worker for live-search triage."""

from __future__ import annotations

import json
import sys

from .db import get_connection, get_tweets_by_ids
from .processor import process_unprocessed


def main() -> int:
    """Classify the tweet IDs supplied on stdin without emitting secrets."""
    try:
        payload = json.load(sys.stdin)
        tweet_ids = {str(tweet_id) for tweet_id in payload if tweet_id}
        with get_connection(readonly=True) as conn:
            rows_by_id = get_tweets_by_ids(conn, tweet_ids)
        rows = [row for row in rows_by_id.values() if row["processed_at"] is None]
        if rows:
            process_unprocessed(limit=len(rows), rows=rows, triage_only=True)
    except BaseException:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
