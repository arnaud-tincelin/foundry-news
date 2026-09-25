#!/usr/bin/env python3
"""Record this run's items as covered so next week only reports the delta.

Runs only after the newsletter passed validation and is about to be committed.
Storing every item id (not just a cursor date) means a missed, re-run or
backfilled week can never produce duplicate coverage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

MAX_HISTORY = 2000


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the seen-items state file.")
    parser.add_argument("--digest", default=".work/digest.json")
    parser.add_argument("--state", default="state/seen-items.json")
    args = parser.parse_args()

    with open(args.digest, "r", encoding="utf-8") as fh:
        digest = json.load(fh)

    state = {"seen": [], "last_run": None, "last_covered_through": None, "history": []}
    if os.path.exists(args.state):
        with open(args.state, "r", encoding="utf-8") as fh:
            try:
                state.update(json.load(fh))
            except json.JSONDecodeError:
                pass

    seen: list[str] = list(state.get("seen", []))
    known = set(seen)
    for item in digest.get("items", []):
        url = item["url"]
        if url not in known:
            seen.append(url)
            known.add(url)

    # Keep the newest ids; feeds only surface recent posts so older ids can
    # never resurface and do not need to be retained forever.
    if len(seen) > MAX_HISTORY:
        seen = seen[-MAX_HISTORY:]

    history = list(state.get("history", []))
    history.append(
        {
            "week": digest["week"],
            "since": digest["since"],
            "until": digest["until"],
            "item_count": digest["item_count"],
            "newsletter": digest["newsletter_path"],
        }
    )

    # Rebuilding an older week must not rewind the cursor, or the next
    # scheduled run would re-scan a period that is already covered.
    covered_through = digest["until"]
    previous = state.get("last_covered_through")
    if previous and previous > covered_through:
        print(f"keeping existing cursor {previous[:10]} (this run only covered up to {covered_through[:10]})")
        covered_through = previous

    state.update(
        {
            "seen": seen,
            "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
            # Next run's window starts exactly where this one ended: no gaps, no overlap.
            "last_covered_through": covered_through,
            "history": history[-200:],
        }
    )

    os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
    with open(args.state, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"state updated: {len(seen)} items covered, next window starts {covered_through[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
