"""
Step 1: Fetch RSS feeds in parallel.
Supports non-English sources — translates title+summary via LLM.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser

import llm as llm_caller
from models import Article, StepReport


def fetch_single_feed(name, url, region, bias, language="en"):
    articles = []
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "GlobalBriefing/3.0"})
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
                language=language,
            ))
    except Exception:
        pass
    return articles


def translate_article(article):
    """Translate non-English article title + summary to English."""
    if article.language == "en":
        return article
    prompt = "Translate to English. Return ONLY the translation, nothing else.\n\nTitle: {}\nSummary: {}".format(
        article.title, article.summary[:300])
    result = llm_caller.call_by_id("gemini",
        "You are a translator. Return only the English translation. Format: Title: ...\nSummary: ...",
        prompt, 400)
    if result:
        lines = result.strip().split("\n", 1)
        for line in lines:
            if line.lower().startswith("title:"):
                article.title = line.split(":", 1)[1].strip()
            elif line.lower().startswith("summary:"):
                article.summary = line.split(":", 1)[1].strip()
    return article


def run(sources):
    """Fetch all feeds, translate non-English. Returns (articles, report)."""
    print("\n>>> FETCH: {} sources...".format(len(sources)))
    report = StepReport("fetch", items_in=len(sources))

    all_articles = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(fetch_single_feed, *s): s[0]
            for s in sources
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

    # Translate non-English articles
    non_en = [a for a in unique if a.language != "en"]
    if non_en:
        print("    Translating {} non-English articles...".format(len(non_en)))
        translated = 0
        for a in non_en:
            translate_article(a)
            translated += 1
            report.llm_calls += 1
            report.llm_successes += 1
        print("    {} translated".format(translated))

    report.items_out = len(unique)
    print("    {} unique articles".format(len(unique)))
    return unique, report
