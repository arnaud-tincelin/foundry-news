#!/usr/bin/env python3
"""Validate a generated newsletter before it is allowed to be committed.

The agent is creative about prose but must not be creative about facts. This
gate enforces the grounding contract:

1. Every link points at an official Microsoft domain.
2. Every link was either collected from a feed this run or is an approved
   Microsoft Learn reference page - no invented URLs.
3. At least one collected item is actually cited.
4. The newsletter stays short.

Any violation fails the workflow, so a bad newsletter never reaches the
default branch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse

ALLOWED_DOMAINS = (
    "devblogs.microsoft.com",
    "azure.microsoft.com",
    "learn.microsoft.com",
    "techcommunity.microsoft.com",
    "blogs.microsoft.com",
    "news.microsoft.com",
    "microsoft.com",
)

# Docs domains are stable, official and safe to cite beyond the collected set.
FREEFORM_DOMAINS = ("learn.microsoft.com",)

MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"(?<![(\[])\bhttps?://[^\s<>)\]]+")

MAX_WORDS = 900


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query)
    query = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "msockid", "ocid", "wt."))]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parts.scheme.lower() or "https", parts.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().split(":")[0]


def domain_allowed(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def is_freeform_domain(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in FREEFORM_DOMAINS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate newsletter grounding.")
    parser.add_argument("newsletter")
    parser.add_argument("--digest", default=".work/digest.json")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    try:
        with open(args.newsletter, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        print(f"FAIL: the agent did not create {args.newsletter}", file=sys.stderr)
        return 1

    with open(args.digest, "r", encoding="utf-8") as fh:
        digest = json.load(fh)

    collected = {normalize_url(i["url"]) for i in digest.get("items", [])}
    references = {normalize_url(u) for u in digest.get("reference_urls", [])}
    approved = collected | references

    if not text.strip():
        errors.append("newsletter is empty")

    if not text.lstrip().startswith("#"):
        errors.append("newsletter must start with a markdown heading")

    links = set(MD_LINK_RE.findall(text))
    bare = {u.rstrip(".,;:") for u in BARE_URL_RE.findall(text)}
    all_urls = links | bare

    if not all_urls:
        errors.append("newsletter contains no source links - every item must be grounded")

    cited_collected = set()
    for url in sorted(all_urls):
        norm = normalize_url(url)
        if not domain_allowed(norm):
            errors.append(f"non-Microsoft link is not allowed: {url}")
            continue
        if norm in collected:
            cited_collected.add(norm)
        elif norm in references or is_freeform_domain(norm):
            continue
        else:
            errors.append(f"link was not collected from an official feed this run: {url}")

    if collected and not cited_collected:
        errors.append("newsletter cites none of the collected items")

    words = len(text.split())
    if words > MAX_WORDS:
        errors.append(f"newsletter is too long: {words} words (max {MAX_WORDS})")

    uncited = collected - cited_collected
    if uncited:
        warnings.append(f"{len(uncited)} collected item(s) were judged not newsworthy and left out")

    for warning in warnings:
        print(f"note: {warning}")

    if errors:
        print(f"\nFAIL: {len(errors)} grounding problem(s) in {args.newsletter}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"OK: {args.newsletter} - {words} words, "
        f"{len(cited_collected)}/{len(collected)} collected items cited, all links official."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
