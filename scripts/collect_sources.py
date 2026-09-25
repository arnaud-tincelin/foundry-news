#!/usr/bin/env python3
"""Collect Microsoft Foundry news items from official Microsoft sources.

This runs *before* the agent and is deliberately deterministic: it fetches
official Microsoft RSS feeds, keeps only Foundry-related entries, drops
anything already covered by a previous newsletter, and writes a digest.

The agent is only ever allowed to write about items present in that digest,
which is what keeps every newsletter bullet grounded in a real Microsoft URL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict

USER_AGENT = "foundry-news-bot/1.0 (+https://github.com/arnaud-tincelin/foundry-news)"
TIMEOUT = 60

# Only official Microsoft properties. Anything else is rejected downstream.
ALLOWED_DOMAINS = (
    "devblogs.microsoft.com",
    "azure.microsoft.com",
    "learn.microsoft.com",
    "techcommunity.microsoft.com",
    "blogs.microsoft.com",
    "news.microsoft.com",
    "microsoft.com",
)


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    # When True every entry is assumed Foundry-relevant (dedicated Foundry feed).
    implicit_foundry: bool = False


FEEDS: tuple[Feed, ...] = (
    Feed("Microsoft Foundry Blog", "https://devblogs.microsoft.com/foundry/feed/", implicit_foundry=True),
    Feed("Azure Blog", "https://azure.microsoft.com/en-us/blog/feed/"),
    Feed("Azure Updates", "https://www.microsoft.com/releasecommunications/api/v2/azure/rss"),
)

# Reference pages the agent may consult to verify details (regions, model
# availability, pricing). Not parsed here - HTML scraping is too brittle - but
# handed to the agent as fetchable, citable official documentation.
REFERENCE_URLS = (
    "https://learn.microsoft.com/en-us/azure/ai-foundry/whats-new-azure-ai-foundry",
    "https://azure.microsoft.com/en-us/pricing/details/ai-foundry/",
)

# A hit on any of these marks an item as Foundry-related.
FOUNDRY_PATTERNS = (
    r"\bmicrosoft\s+foundry\b",
    r"\bazure\s+ai\s+foundry\b",
    r"\bai\s+foundry\b",
    r"\bfoundry\s+(agent|local|models|service|sdk|portal|tools)\b",
    r"\bfoundry\b",
)

# Categories the newsletter must cover, used to pre-tag items for the agent.
CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("ga", r"\bgenerally\s+available\b|\bnow\s+ga\b|\bgeneral\s+availability\b"),
    ("preview", r"\bpublic\s+preview\b|\bprivate\s+preview\b|\bpreview\b"),
    ("models", r"\bmodels?\b|\bgpt\b|\bclaude\b|\bllama\b|\bmistral\b|\bgrok\b|\bphi\b|\bdeepseek\b|\bembedding\b|\bsora\b"),
    ("pricing", r"\bpric(?:e|es|ing)\b|\bcost\b|\bbilling\b|\bfree\s+tier\b|\bquota\b|\bdiscount\b"),
    ("regions", r"\bregions?\b|\bregional\b|\bavailable\s+in\b|\bdata\s+residency\b|\bgeograph"),
    ("retirement", r"\bretir(?:e|es|ing|ement)\b|\bdeprecat\w*\b|\bend\s+of\s+(?:life|support)\b|\bsunset\b"),
)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def log(msg: str) -> None:
    print(f"[collect] {msg}", file=sys.stderr, flush=True)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def strip_html(raw: str, limit: int = 600) -> str:
    text = TAG_RE.sub(" ", raw or "")
    text = html.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    return text[:limit].strip()


DATE_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)


def parse_date(raw: str) -> dt.datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"\s+\([A-Za-z ]+\)$", "", raw).replace("GMT", "+0000").replace("UTC", "+0000")
    for fmt in DATE_FORMATS:
        try:
            parsed = dt.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def normalize_url(url: str) -> str:
    """Canonical form used as the dedupe identity of an item."""
    url = (url or "").strip()
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query)
    # Tracking parameters must not make an old item look new next week.
    query = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "msockid", "ocid", "wt."))]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parts.scheme.lower() or "https", parts.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def domain_allowed(url: str) -> bool:
    host = urllib.parse.urlsplit(url).netloc.lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def is_foundry(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in FOUNDRY_PATTERNS)


def categorize(text: str) -> list[str]:
    found = [name for name, pattern in CATEGORY_RULES if re.search(pattern, text, re.IGNORECASE)]
    return found or ["feature"]


@dataclass
class Item:
    id: str
    title: str
    url: str
    source: str
    published: str
    summary: str
    categories: list[str] = field(default_factory=list)


def _text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None and node.text else ""


def parse_feed(raw: bytes, feed: Feed) -> list[Item]:
    # Feeds are served with a UTF-8 BOM, which ElementTree refuses.
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        log(f"  ! unparseable XML from {feed.name}: {exc}")
        return []

    atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{atom}entry")
    items: list[Item] = []

    for node in nodes:
        title = strip_html(_text(node.find("title")) or _text(node.find(f"{atom}title")), 300)

        link = _text(node.find("link"))
        if not link:
            link_node = node.find(f"{atom}link")
            if link_node is not None:
                link = (link_node.get("href") or "").strip()
        if not link:
            link = _text(node.find("guid"))

        description = _text(node.find("description")) or _text(node.find(f"{atom}summary"))
        content = _text(node.find("{http://purl.org/rss/1.0/modules/content/}encoded"))
        summary = strip_html(description or content)

        published_raw = (
            _text(node.find("pubDate"))
            or _text(node.find("{http://purl.org/dc/elements/1.1/}date"))
            or _text(node.find(f"{atom}updated"))
            or _text(node.find(f"{atom}published"))
        )
        published = parse_date(published_raw)

        url = normalize_url(link)
        if not url or not title or published is None:
            continue
        if not domain_allowed(url):
            continue

        haystack = f"{title} {summary}"
        if not (feed.implicit_foundry or is_foundry(haystack)):
            continue

        items.append(
            Item(
                id=url,
                title=title,
                url=url,
                source=feed.name,
                published=published.isoformat(),
                summary=summary,
                categories=categorize(haystack),
            )
        )
    return items


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"seen": [], "last_run": None, "last_covered_through": None}
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            log("! state file corrupt, starting fresh")
            return {"seen": [], "last_run": None, "last_covered_through": None}
    data.setdefault("seen", [])
    return data


def iso_week_label(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect grounded Microsoft Foundry news items.")
    parser.add_argument("--since", help="Inclusive start date (YYYY-MM-DD). Defaults to state, else bootstrap date.")
    parser.add_argument("--until", help="Exclusive end date (YYYY-MM-DD). Defaults to now.")
    parser.add_argument("--state", default="state/seen-items.json")
    parser.add_argument("--out-dir", default=".work")
    parser.add_argument("--bootstrap-since", default="2026-09-01", help="Start date for the very first newsletter.")
    parser.add_argument(
        "--ignore-state",
        action="store_true",
        help="Ignore previously covered items and re-collect the whole window. Use with --since to rebuild a week.",
    )
    args = parser.parse_args()

    state = load_state(args.state)
    seen: set[str] = set() if args.ignore_state else {normalize_url(u) for u in state.get("seen", []) if u}

    until = (
        dt.datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        if args.until
        else dt.datetime.now(dt.timezone.utc)
    )

    if args.since:
        since = dt.datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    elif state.get("last_covered_through"):
        since = dt.datetime.fromisoformat(state["last_covered_through"])
    else:
        # First ever run: start from the configured bootstrap date.
        since = dt.datetime.strptime(args.bootstrap_since, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)

    log(f"window {since.date()} -> {until.date()} | {len(seen)} previously covered items")
    if args.ignore_state:
        log("--ignore-state: re-collecting the full window, previously covered items are not filtered out")

    collected: dict[str, Item] = {}
    failures: list[str] = []

    for feed in FEEDS:
        try:
            raw = fetch(feed.url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log(f"  ! {feed.name} unreachable: {exc}")
            failures.append(feed.name)
            continue

        parsed = parse_feed(raw, feed)
        kept = 0
        for item in parsed:
            published = dt.datetime.fromisoformat(item.published)
            if not (since <= published < until):
                continue
            if item.id in seen or item.id in collected:
                continue
            collected[item.id] = item
            kept += 1
        log(f"  {feed.name}: {len(parsed)} foundry items, {kept} new in window")

    if failures and len(failures) == len(FEEDS):
        log("! every feed failed - aborting so we do not publish an unfounded newsletter")
        return 2

    items = sorted(collected.values(), key=lambda i: i.published, reverse=True)

    os.makedirs(args.out_dir, exist_ok=True)
    week_label = iso_week_label(until.date())

    digest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "week": week_label,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "is_bootstrap": state.get("last_covered_through") is None,
        "newsletter_path": f"newsletters/{week_label}.md",
        "failed_feeds": failures,
        "reference_urls": list(REFERENCE_URLS),
        "item_count": len(items),
        "items": [asdict(i) for i in items],
    }

    digest_path = os.path.join(args.out_dir, "digest.json")
    with open(digest_path, "w", encoding="utf-8") as fh:
        json.dump(digest, fh, indent=2, ensure_ascii=False)

    lines = [
        f"# Grounded source material - {week_label}",
        "",
        f"Window: {since.date()} to {until.date()} (exclusive). New items: {len(items)}.",
        "",
    ]
    if failures:
        lines += [f"> Feeds unavailable this run: {', '.join(failures)}.", ""]
    for item in items:
        lines += [
            f"## {item.title}",
            f"- URL: {item.url}",
            f"- Source: {item.source}",
            f"- Published: {item.published[:10]}",
            f"- Signals: {', '.join(item.categories)}",
            f"- Excerpt: {item.summary}",
            "",
        ]
    brief_path = os.path.join(args.out_dir, "brief.md")
    with open(brief_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    log(f"wrote {digest_path} and {brief_path} ({len(items)} items)")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"item_count={len(items)}\n")
            fh.write(f"has_news={'true' if items else 'false'}\n")
            fh.write(f"week={week_label}\n")
            fh.write(f"newsletter_path=newsletters/{week_label}.md\n")
            fh.write(f"since={since.date()}\n")
            fh.write(f"until={until.date()}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
