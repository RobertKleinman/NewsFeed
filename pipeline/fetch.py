"""
Step 1: Fetch RSS feeds in parallel.
Input: list of (name, url, region, bias) tuples
Output: list of Article, StepReport
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser

from models import Article, StepReport


def fetch_single_feed(name, url, region, bias):
    articles = []
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "GlobalBriefing/2.0"})
        if feed.bozo and not feed.entries:
            return articles
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            summary = entry.get("summary", entry.get("description", ""))
            summary = re.sub(r"<[^>]+>", "", summary or "")[:500]
            published = entry.get("published", entry.get("updated", ""))
            articles.append(Article(
                title=title, url=link, source_name=name,
                source_region=region, source_bias=bias,
                summary=summary, published=published,
            ))
    except Exception as e:
        pass  # Silently skip bad feeds
    return articles


def run(sources):
    """Fetch all feeds. Returns (articles, report)."""
    print("\n>>> FETCH: {} sources...".format(len(sources)))
    report = StepReport("fetch", items_in=len(sources))

    all_articles = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(fetch_single_feed, n, u, r, b): n
            for n, u, r, b in sources
        }
        for future in as_completed(futures):
            all_articles.extend(future.result())

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    report.items_out = len(unique)
    print("    {} unique articles".format(len(unique)))
    return unique, report
