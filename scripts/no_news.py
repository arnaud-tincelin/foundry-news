#!/usr/bin/env python3
"""Publish the "No News Today" newsletter when there is nothing to report.

The pipeline must succeed even in a quiet week, so two situations end here
instead of failing:

* the collector found no new items, so the agent never ran;
* the agent judged every collected item out of scope and wrote a short,
  link-free note instead of a newsletter.

Either way this script writes the newsletter, never the agent, so the published
text is always the same.

Two guards keep that from hiding real news:

* a Microsoft Foundry Blog post is never dropped this way - when one was
  collected, a link-free note is left for the validator to reject;
* a newsletter already committed for the same week is never replaced by a
  "No News Today" stub.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from validate_newsletter import BARE_URL_RE, MD_LINK_RE, REQUIRED_PREFIXES, normalize_url

NOTE_MAX_WORDS = 120
# Sections, bullets and numbered items are how a newsletter makes claims.
STRUCTURE_RE = re.compile(r"^[ \t]*(?:#{2,6}[ \t]|[-*+][ \t]|\d+[.)][ \t])", re.MULTILINE)

STUB = "# Microsoft Foundry Weekly — {week}\n\n_{since} to {until} · 0 updates_\n\nNo News Today\n"


def is_no_news_note(text: str) -> bool:
    """A short note under a heading with no links, sections or bullets claims nothing."""
    if not text.lstrip().startswith("#"):
        return False
    if MD_LINK_RE.search(text) or BARE_URL_RE.search(text):
        return False
    return not STRUCTURE_RE.search(text) and len(text.split()) <= NOTE_MAX_WORDS


def has_required_item(items: list[dict]) -> bool:
    return any(normalize_url(i["url"]).startswith(REQUIRED_PREFIXES) for i in items)


def committed(path: str) -> bool:
    """True when the newsletter already exists in the checked-out commit."""
    try:
        return subprocess.run(["git", "cat-file", "-e", f"HEAD:{path}"], capture_output=True).returncode == 0
    except OSError:
        return False


def set_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the No News Today newsletter when there is nothing to report.")
    parser.add_argument("newsletter")
    parser.add_argument("--digest", default=".work/digest.json")
    args = parser.parse_args()

    with open(args.digest, "r", encoding="utf-8") as fh:
        digest = json.load(fh)
    items = digest.get("items", [])

    if items:
        # No file, an empty file or real content is for the validator to judge.
        if not os.path.exists(args.newsletter):
            set_output("no_news", "false")
            return 0
        with open(args.newsletter, "r", encoding="utf-8") as fh:
            text = fh.read()
        if has_required_item(items) or not is_no_news_note(text):
            set_output("no_news", "false")
            return 0
        reason = f"the agent found none of the {len(items)} collected item(s) newsworthy"
    else:
        reason = "no new items were collected"

    set_output("no_news", "true")

    if committed(args.newsletter):
        subprocess.run(["git", "checkout", "--", args.newsletter], check=True)
        set_output("written", "false")
        print(f"NO NEWS ({reason}), but {args.newsletter} already exists - keeping it.")
        return 0

    os.makedirs(os.path.dirname(args.newsletter) or ".", exist_ok=True)
    with open(args.newsletter, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB.format(week=digest["week"], since=digest["since"][:10], until=digest["until"][:10]))
    set_output("written", "true")

    print(f"NO NEWS ({reason}): wrote {args.newsletter}.")
    for item in items:
        print(f"  - left out: {item['title']} ({item['url']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
