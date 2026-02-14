#!/usr/bin/env python3
"""
Global Briefing System
======================
An AI-powered news intelligence system that:
1. Pulls from 100+ diverse global sources via RSS
2. Triages articles by topic relevance (cheap model)
3. Identifies multi-perspective stories and gathers contrasting coverage
4. Sends important stories to multiple LLMs for analysis
5. Synthesizes everything into a clean briefing
"""

import json
import os
import sys
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional
import traceback

# --- Dependencies (pip install feedparser requests) ---
import feedparser
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

TOPICS = {
    "world_politics": {
        "name": "World Politics & Geopolitics",
        "icon": "🌍",
        "keywords": ["geopolitics", "diplomacy", "war", "conflict", "UN", "NATO", "sanctions",
                      "treaty", "summit", "foreign policy", "military", "peace", "election",
                      "coup", "protest", "refugee", "international", "alliance"],
    },
    "canada_politics": {
        "name": "Canadian Politics & Policy",
        "icon": "🍁",
        "keywords": ["canada", "canadian", "ottawa", "trudeau", "poilievre", "parliament",
                      "liberal", "conservative", "ndp", "bloc", "senate", "provincial",
                      "ontario", "quebec", "british columbia", "alberta", "federal"],
    },
    "us_politics": {
        "name": "US Politics",
        "icon": "🇺🇸",
        "keywords": ["congress", "senate", "white house", "supreme court", "democrat",
                      "republican", "washington", "biden", "trump", "election", "governor",
                      "legislation", "executive order", "pentagon", "state department"],
    },
    "economics_business": {
        "name": "Economics & Business",
        "icon": "📊",
        "keywords": ["economy", "gdp", "inflation", "interest rate", "central bank",
                      "stock", "market", "trade", "tariff", "recession", "employment",
                      "startup", "merger", "acquisition", "ipo", "venture", "earnings",
                      "supply chain", "manufacturing", "banking"],
    },
    "tech_ai": {
        "name": "Technology & AI",
        "icon": "🤖",
        "keywords": ["artificial intelligence", "machine learning", "AI", "LLM", "chatgpt",
                      "openai", "anthropic", "google deepmind", "meta ai", "robot",
                      "automation", "semiconductor", "chip", "quantum", "software",
                      "cloud", "cybersecurity", "startup", "tech company", "silicon valley"],
    },
    "insurance_canada": {
        "name": "Canadian Insurance Industry",
        "icon": "🛡️",
        "keywords": ["insurance", "insurer", "underwriting", "claims", "actuarial",
                      "reinsurance", "broker", "premium", "FSRA", "OSFI", "IBC",
                      "auto insurance", "property casualty", "P&C", "insurance regulation",
                      "insurance canada", "facility association"],
    },
    "data_privacy_governance": {
        "name": "Data, Privacy & AI Governance",
        "icon": "🔐",
        "keywords": ["data breach", "privacy", "GDPR", "PIPEDA", "data protection",
                      "surveillance", "facial recognition", "biometric", "consent",
                      "data governance", "AI regulation", "AI ethics", "AI safety",
                      "algorithmic", "transparency", "accountability", "CPPA",
                      "Bill C-27", "digital charter", "cookie", "tracking", "personal data",
                      "data commissioner", "information commissioner"],
    },
    "culture_good_news": {
        "name": "Culture, Joy & Good News",
        "icon": "🌈",
        "keywords": ["breakthrough", "discovery", "achievement", "celebration", "art",
                      "music", "film", "book", "festival", "award", "charity",
                      "volunteer", "community", "heartwarming", "inspiring", "milestone",
                      "culture", "museum", "theatre", "theater", "concert", "exhibition"],
    },
}

# RSS Sources - organized by region/type for diversity
# Each source: (name, url, region, bias_label)
RSS_SOURCES = [
    # --- CANADA ---
    ("Globe and Mail", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/news/", "Canada", "centre"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-topstories", "Canada", "centre-left"),
    ("National Post", "https://nationalpost.com/feed", "Canada", "centre-right"),
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=news*&l=50&s=start_time&sd=desc", "Canada", "centre-left"),
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009", "Canada", "centre"),
    ("Global News Canada", "https://globalnews.ca/feed/", "Canada", "centre"),
    ("Macleans", "https://macleans.ca/feed/", "Canada", "centre"),
    ("Canadian Underwriter", "https://www.canadianunderwriter.ca/feed/", "Canada-Insurance", "industry"),
    ("Insurance Business Canada", "https://www.insurancebusinessmag.com/ca/rss/news/", "Canada-Insurance", "industry"),

    # --- USA ---
    ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "USA", "centre-left"),
    ("Washington Post", "https://feeds.washingtonpost.com/rss/world", "USA", "centre-left"),
    ("Wall Street Journal", "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "USA", "centre-right"),
    ("AP News", "https://rsshub.app/apnews/topics/apf-topnews", "USA", "centre"),
    ("Reuters", "https://www.reutersagency.com/feed/", "USA", "centre"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml", "USA", "centre-left"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml", "USA", "right"),
    ("Politico", "https://www.politico.com/rss/politicopicks.xml", "USA", "centre"),
    ("The Hill", "https://thehill.com/feed/", "USA", "centre"),
    ("Reason", "https://reason.com/feed/", "USA", "libertarian"),

    # --- UK ---
    ("BBC News", "http://feeds.bbci.co.uk/news/rss.xml", "UK", "centre"),
    ("The Guardian", "https://www.theguardian.com/world/rss", "UK", "centre-left"),
    ("The Telegraph", "https://www.telegraph.co.uk/rss.xml", "UK", "centre-right"),
    ("Financial Times", "https://www.ft.com/rss/home", "UK", "centre"),
    ("The Economist", "https://www.economist.com/international/rss.xml", "UK", "centre"),

    # --- EUROPE ---
    ("DW News", "https://rss.dw.com/rdf/rss-en-all", "Germany", "centre"),
    ("France 24", "https://www.france24.com/en/rss", "France", "centre"),
    ("EuroNews", "https://www.euronews.com/rss", "Europe", "centre"),
    ("The Local EU", "https://www.thelocal.com/feeds/rss.php", "Europe", "centre"),
    ("Politico EU", "https://www.politico.eu/feed/", "Europe", "centre"),

    # --- MIDDLE EAST ---
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Qatar/ME", "centre"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/", "Israel", "centre"),
    ("Arab News", "https://www.arabnews.com/rss.xml", "Saudi Arabia", "centre"),

    # --- ASIA-PACIFIC ---
    ("South China Morning Post", "https://www.scmp.com/rss/91/feed", "Hong Kong", "centre"),
    ("NHK World", "https://www3.nhk.or.jp/rss/news/cat0.xml", "Japan", "centre"),
    ("The Straits Times", "https://www.straitstimes.com/news/world/rss.xml", "Singapore", "centre"),
    ("ABC Australia", "https://www.abc.net.au/news/feed/2942460/rss.xml", "Australia", "centre"),
    ("India Today", "https://www.indiatoday.in/rss/home", "India", "centre"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss", "Japan", "centre"),

    # --- AFRICA / LATIN AMERICA ---
    ("Al Monitor", "https://www.al-monitor.com/rss", "Middle East/Africa", "centre"),
    ("The East African", "https://www.theeastafrican.co.ke/tea/rss", "East Africa", "centre"),
    ("Buenos Aires Herald", "https://buenosairesherald.com/feed/", "Argentina", "centre"),

    # --- TECH / AI ---
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "USA-Tech", "centre"),
    ("TechCrunch", "https://techcrunch.com/feed/", "USA-Tech", "centre"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "USA-Tech", "centre"),
    ("Wired", "https://www.wired.com/feed/rss", "USA-Tech", "centre"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "USA-Tech", "centre"),
    ("VentureBeat", "https://venturebeat.com/feed/", "USA-Tech", "centre"),
    ("The Register", "https://www.theregister.com/headlines.atom", "UK-Tech", "centre"),
    ("Hacker News (top)", "https://hnrss.org/frontpage", "USA-Tech", "centre"),

    # --- AI SPECIFIC ---
    ("AI News", "https://www.artificialintelligence-news.com/feed/", "Global-AI", "centre"),
    ("The Decoder", "https://the-decoder.com/feed/", "Global-AI", "centre"),
    ("Jack Clark Import AI", "https://importai.substack.com/feed", "Global-AI", "centre"),

    # --- DATA / PRIVACY / GOVERNANCE ---
    ("IAPP", "https://iapp.org/news/feed/", "Global-Privacy", "centre"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "USA-Security", "centre"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "USA-Security", "centre"),
    ("The Record", "https://therecord.media/feed", "USA-Security", "centre"),
    ("Schneier on Security", "https://www.schneier.com/feed/", "USA-Security", "centre"),

    # --- ECONOMICS / BUSINESS ---
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "USA-Finance", "centre"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "USA-Finance", "centre"),
    ("MarketWatch", "https://www.marketwatch.com/rss/topstories", "USA-Finance", "centre"),
    ("BNN Bloomberg Canada", "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/category/news/?outputType=xml", "Canada-Finance", "centre"),

    # --- GOOD NEWS / CULTURE ---
    ("Positive News", "https://www.positive.news/feed/", "UK-Culture", "centre"),
    ("Good News Network", "https://www.goodnewsnetwork.org/feed/", "USA-Culture", "centre"),
    ("Reasons to be Cheerful", "https://reasonstobecheerful.world/feed/", "USA-Culture", "centre"),
    ("Atlas Obscura", "https://www.atlasobscura.com/feeds/latest", "USA-Culture", "centre"),
    ("Aeon", "https://aeon.co/feed.rss", "Global-Culture", "centre"),
]

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Article:
    title: str
    url: str
    source_name: str
    source_region: str
    source_bias: str
    summary: str = ""
    published: str = ""
    topics: list = field(default_factory=list)
    importance_score: float = 0.0
    is_perspective_story: bool = False
    related_articles: list = field(default_factory=list)
    llm_analyses: dict = field(default_factory=dict)

    def uid(self):
        return hashlib.md5(self.url.encode()).hexdigest()[:12]


# =============================================================================
# RSS FETCHING
# =============================================================================

def fetch_single_feed(name, url, region, bias, timeout=15):
    """Fetch a single RSS feed, returning articles. Gracefully handles errors."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers={'User-Agent': 'GlobalBriefing/1.0'})
        if feed.bozo and not feed.entries:
            print(f"  ⚠️  {name}: Feed error (skipping)")
            return articles

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        for entry in feed.entries[:15]:  # Max 15 per source to stay manageable
            title = entry.get('title', '').strip()
            link = entry.get('link', '').strip()
            if not title or not link:
                continue

            summary = entry.get('summary', entry.get('description', ''))
            # Strip HTML from summary
            summary = re.sub(r'<[^>]+>', '', summary or '')[:500]

            published = entry.get('published', entry.get('updated', ''))

            articles.append(Article(
                title=title,
                url=link,
                source_name=name,
                source_region=region,
                source_bias=bias,
                summary=summary,
                published=published,
            ))

        print(f"  ✅ {name}: {len(articles)} articles")
    except Exception as e:
        print(f"  ❌ {name}: {str(e)[:80]}")
    return articles


def fetch_all_feeds():
    """Fetch all RSS feeds in parallel."""
    print(f"\n📡 Fetching from {len(RSS_SOURCES)} sources...")
    all_articles = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(fetch_single_feed, name, url, region, bias): name
            for name, url, region, bias in RSS_SOURCES
        }
        for future in as_completed(futures):
            articles = future.result()
            all_articles.extend(articles)

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    print(f"\n📰 Total unique articles: {len(unique)}")
    return unique


# =============================================================================
# TRIAGE - Topic classification & importance scoring (cheap/local)
# =============================================================================

def classify_article_locally(article):
    """
    Fast local keyword-based classification.
    This is the FREE triage layer - no API calls needed.
    """
    text = f"{article.title} {article.summary}".lower()
    matched_topics = []

    for topic_id, topic_info in TOPICS.items():
        score = 0
        for keyword in topic_info["keywords"]:
            if keyword.lower() in text:
                score += 1
        if score >= 1:
            matched_topics.append((topic_id, score))

    # Sort by relevance
    matched_topics.sort(key=lambda x: x[1], reverse=True)
    article.topics = [t[0] for t in matched_topics]

    # Importance heuristic
    article.importance_score = min(len(matched_topics) * 0.3 + matched_topics[0][1] * 0.2 if matched_topics else 0, 1.0)

    return article


def triage_articles(articles):
    """Classify all articles by topic and score importance."""
    print("\n🔍 Triaging articles by topic...")
    for article in articles:
        classify_article_locally(article)

    # Filter to only articles that matched at least one topic
    relevant = [a for a in articles if a.topics]
    print(f"  Relevant to your topics: {len(relevant)}/{len(articles)}")

    return relevant


# =============================================================================
# PERSPECTIVE DETECTION & GROUPING
# =============================================================================

def group_by_story(articles):
    """
    Group articles that are about the same story from different sources.
    Uses simple title similarity. In production, you'd use embeddings.
    """
    def normalize(title):
        return re.sub(r'[^a-z0-9\s]', '', title.lower()).split()

    groups = []
    used = set()

    # Sort by importance
    articles.sort(key=lambda a: a.importance_score, reverse=True)

    for i, article in enumerate(articles):
        if i in used:
            continue

        group = [article]
        words_i = set(normalize(article.title))

        for j, other in enumerate(articles[i+1:], start=i+1):
            if j in used:
                continue
            words_j = set(normalize(other.title))
            # Jaccard similarity
            if len(words_i & words_j) / max(len(words_i | words_j), 1) > 0.3:
                group.append(other)
                used.add(j)

        used.add(i)

        # If multiple sources cover the same story, it's a perspective story
        if len(group) > 1:
            for a in group:
                a.is_perspective_story = True
                a.related_articles = [x.uid() for x in group if x.uid() != a.uid()]

        groups.append(group)

    return groups


def select_top_stories(groups, max_stories=12):
    """Select the top stories to send to LLMs for deep analysis."""
    # Score groups by: number of sources covering it × importance
    scored = []
    for group in groups:
        group_score = (
            max(a.importance_score for a in group) * 0.4 +
            min(len(group) / 5, 1.0) * 0.3 +
            (0.3 if any(a.is_perspective_story for a in group) else 0)
        )
        scored.append((group_score, group))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [g for _, g in scored[:max_stories]]


# =============================================================================
# LLM API CALLS
# =============================================================================

def call_llm(provider, model, system_prompt, user_prompt, api_key, max_tokens=1500):
    """
    Unified LLM caller with retry logic for rate limits.
    Supports: openai (ChatGPT), anthropic (Claude), google (Gemini), xai (Grok).
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            resp = _call_llm_once(provider, model, system_prompt, user_prompt, api_key, max_tokens)
            return resp
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait_time = (attempt + 1) * 15  # 15s, 30s, 45s
                print(f"    ⏳ Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"  ❌ {provider}/{model}: HTTP {e.response.status_code if e.response else 'unknown'}")
                return None
        except Exception as e:
            print(f"  ❌ {provider}/{model}: {str(e)[:100]}")
            return None

    print(f"  ❌ {provider}/{model}: Failed after {max_retries} retries (rate limited)")
    return None


def _call_llm_once(provider, model, system_prompt, user_prompt, api_key, max_tokens=1500):
    """Single LLM API call. Raises HTTPError on failure."""
    if provider == "google":
        # Gemini API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}
        }
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    elif provider == "xai":
        # Grok uses OpenAI-compatible API
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# LLM configurations - uses env vars for API keys
LLM_CONFIGS = {
    "gemini_triage": {
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "env_key": "GOOGLE_API_KEY",
        "label": "Gemini Flash (Triage)",
    },
    "gemini": {
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "env_key": "GOOGLE_API_KEY",
        "label": "Google Gemini",
    },
    "chatgpt": {
        "provider": "openai",
        "model": "gpt-4.1",
        "env_key": "OPENAI_API_KEY",
        "label": "ChatGPT",
    },
    "claude": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY",
        "label": "Claude",
    },
    "grok": {
        "provider": "xai",
        "model": "grok-3-fast",
        "env_key": "XAI_API_KEY",
        "label": "Grok",
    },
}


def smart_triage_with_llm(story_groups):
    """
    Use Gemini Flash (very cheap) to do a smarter triage pass on the top candidates.
    This refines the local keyword triage with actual understanding.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("  ⚠️  No Google API key - skipping LLM triage, using keyword triage only")
        return story_groups

    # Build a compact summary of candidate stories
    story_summaries = []
    for i, group in enumerate(story_groups[:50]):  # Top 50 candidates
        lead = group[0]
        sources = ", ".join(set(a.source_name for a in group))
        story_summaries.append(f"{i}. [{sources}] {lead.title}")

    newline = "\n"
    stories_list = newline.join(story_summaries)
    prompt = f"""You are a news editor. From these candidate stories, pick the 15-20 most important
and interesting ones for a reader interested in: world politics, Canadian politics, US politics,
economics/business, AI/technology, Canadian insurance, data privacy/AI governance, and uplifting culture stories.

Return ONLY a JSON array of the story numbers, e.g. [0, 3, 5, 12, ...]
Pick stories that are: genuinely significant, have real-world impact, represent diverse topics,
and include at least 1-2 uplifting/cultural stories.

Stories:
{stories_list}"""

    print("\n🧠 Smart triage with Gemini Flash...")
    result = call_llm("google", "gemini-3-flash-preview", "You are a concise news editor.", prompt, api_key, max_tokens=200)

    if result:
        try:
            # Parse the JSON array from the response
            match = re.search(r'\[[\d,\s]+\]', result)
            if match:
                indices = json.loads(match.group())
                selected = [story_groups[i] for i in indices if i < len(story_groups)]
                print(f"  LLM selected {len(selected)} stories")
                return selected
        except Exception as e:
            print(f"  ⚠️  Could not parse LLM triage response: {e}")

    return story_groups[:20]


def analyze_story_with_llms(story_group):
    """Send a story to multiple LLMs for diverse analysis."""
    lead = story_group[0]

    # Build context with all perspectives
    perspectives = ""
    if len(story_group) > 1:
        perspectives = "\n\nMULTIPLE SOURCE COVERAGE:\n"
        for a in story_group:
            perspectives += f"- {a.source_name} ({a.source_region}, {a.source_bias}): {a.title}\n  {a.summary[:200]}\n"

    system_prompt = """You are a sharp, insightful news analyst. Provide a brief but substantive analysis
of this story in 2-3 paragraphs. Cover: what happened, why it matters, and what to watch for next.
If multiple source perspectives are provided, note any interesting differences in framing or emphasis.
Be direct, avoid filler. Write for a smart reader who wants signal, not noise."""

    user_prompt = f"""STORY: {lead.title}
SOURCE: {lead.source_name} ({lead.source_region})
SUMMARY: {lead.summary[:400]}
{perspectives}

Analyze this story concisely."""

    analyses = {}

    # Only use LLMs that have API keys configured
    llms_to_use = ["gemini", "chatgpt", "claude", "grok"]

    for llm_id in llms_to_use:
        config = LLM_CONFIGS[llm_id]
        api_key = os.environ.get(config["env_key"])
        if not api_key:
            print(f"    ⏭️  {config['label']}: No API key, skipping")
            continue

        print(f"    🤖 {config['label']}...")
        result = call_llm(config["provider"], config["model"], system_prompt, user_prompt, api_key)
        if result:
            print(f"    ✅ {config['label']}: Got {len(result)} chars")
            analyses[config["label"]] = result
        else:
            print(f"    ⚠️  {config['label']}: Empty or failed response")

        # Rate limit: wait between calls (especially important for Gemini free tier)
        time.sleep(5)

    return analyses


def synthesize_briefing(top_stories, all_analyses):
    """Create a final synthesis of all the analyses."""
    # Use whichever LLM is available for synthesis
    api_key = None
    provider = None
    model = None

    for llm_id in ["gemini", "claude", "chatgpt", "grok"]:
        config = LLM_CONFIGS[llm_id]
        key = os.environ.get(config["env_key"])
        if key:
            api_key = key
            provider = config["provider"]
            model = config["model"]
            break

    if not api_key:
        return "No LLM API keys configured - cannot generate synthesis."

    # Build synthesis prompt
    newline = "\n"
    story_summaries = []
    for i, (group, analyses) in enumerate(zip(top_stories, all_analyses)):
        lead = group[0]
        analysis_text = ""
        for llm_name, analysis in analyses.items():
            analysis_text += f"\n{llm_name}: {analysis[:200]}..."
        story_summaries.append(f"Story {i+1}: {lead.title}\nTopic: {', '.join(lead.topics[:2])}\n{analysis_text}")

    prompt = f"""You are writing the executive synthesis for a daily intelligence briefing.
Based on these stories and multi-LLM analyses, write a compelling 3-4 paragraph overview that:
1. Identifies the 2-3 biggest themes of the day
2. Notes where different analysts/sources agreed or disagreed
3. Calls out any connecting threads between stories
4. Ends with a "watch for" note about developing situations

Be sharp, concise, and insightful. Write as if briefing a senior executive.

TODAY'S STORIES:
{newline.join(story_summaries[:10])}"""

    print("\n📝 Generating synthesis...")
    return call_llm(provider, model, "You are an expert intelligence briefing writer.", prompt, api_key, max_tokens=1000)


# =============================================================================
# HTML GENERATION
# =============================================================================

def generate_html(top_stories, all_analyses, synthesis, run_time):
    """Generate a beautiful, mobile-friendly HTML briefing page."""

    stories_html = ""
    for group, analyses in zip(top_stories, all_analyses):
        lead = group[0]
        topic_tags = " ".join(
            f'<span class="topic-tag" data-topic="{t}">{TOPICS[t]["icon"]} {TOPICS[t]["name"]}</span>'
            for t in lead.topics[:3] if t in TOPICS
        )

        # Multi-source indicator
        sources_html = ""
        if len(group) > 1:
            source_list = ", ".join(f'{a.source_name} <span class="bias-label">({a.source_bias})</span>' for a in group[:5])
            sources_html = f'<div class="multi-source"><span class="perspective-badge">📰 {len(group)} sources</span> {source_list}</div>'

        # LLM analyses
        analyses_html = ""
        for llm_name, analysis in analyses.items():
            # Escape HTML
            analysis_escaped = analysis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            analyses_html += f'''
            <div class="llm-analysis">
                <div class="llm-name">{llm_name}</div>
                <div class="llm-text">{analysis_escaped}</div>
            </div>'''

        stories_html += f'''
        <article class="story-card" data-topics="{' '.join(lead.topics)}">
            <div class="story-header">
                <div class="topic-tags">{topic_tags}</div>
                <h2 class="story-title"><a href="{lead.url}" target="_blank" rel="noopener">{lead.title}</a></h2>
                <div class="story-meta">
                    <span class="source">{lead.source_name}</span>
                    <span class="region">{lead.source_region}</span>
                </div>
            </div>
            {sources_html}
            <p class="story-summary">{lead.summary[:300]}</p>
            <div class="analyses-container">
                <button class="toggle-analyses" onclick="this.parentElement.classList.toggle('open')">
                    🤖 AI Analysis ({len(analyses)} perspectives) <span class="arrow">▾</span>
                </button>
                <div class="analyses-content">
                    {analyses_html}
                </div>
            </div>
        </article>'''

    # Escape synthesis
    synthesis_escaped = (synthesis or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Pre-build filter buttons (avoid backslash in f-string)
    filter_buttons = "".join(
        '<button class="filter-btn" onclick="filterStories(\'{tid}\')">{icon} {name}</button>'.format(
            tid=tid, icon=t["icon"], name=t["name"]
        )
        for tid, t in TOPICS.items()
    )

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global Briefing — {run_time.strftime("%B %d, %Y")}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,300;0,400;0,600;1,400&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0a0c;
            --bg-card: #111116;
            --bg-card-hover: #16161d;
            --bg-analysis: #0d0d12;
            --text-primary: #e8e6e1;
            --text-secondary: #8a8a95;
            --text-dim: #55555f;
            --accent-gold: #c9a84c;
            --accent-blue: #4a7cc9;
            --accent-green: #4caa7c;
            --accent-red: #c94a5a;
            --accent-purple: #8a5cc9;
            --border: #1e1e28;
            --border-subtle: #15151d;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'DM Sans', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 0 20px;
        }}

        /* HEADER */
        header {{
            padding: 40px 0 30px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 30px;
        }}

        .masthead {{
            font-family: 'Newsreader', serif;
            font-size: 2.2rem;
            font-weight: 300;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }}

        .masthead .accent {{ color: var(--accent-gold); }}

        .run-info {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 6px;
        }}

        .run-info strong {{ color: var(--text-primary); font-weight: 500; }}

        /* FILTER TABS */
        .filter-bar {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .filter-btn {{
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-family: 'DM Sans', sans-serif;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }}

        .filter-btn:hover, .filter-btn.active {{
            border-color: var(--accent-gold);
            color: var(--accent-gold);
            background: rgba(201, 168, 76, 0.08);
        }}

        /* SYNTHESIS */
        .synthesis {{
            background: linear-gradient(135deg, #111118, #0f0f1a);
            border: 1px solid var(--border);
            border-left: 3px solid var(--accent-gold);
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 32px;
        }}

        .synthesis h2 {{
            font-family: 'Newsreader', serif;
            font-size: 1.3rem;
            font-weight: 400;
            color: var(--accent-gold);
            margin-bottom: 14px;
        }}

        .synthesis p {{
            font-size: 0.92rem;
            color: var(--text-secondary);
            line-height: 1.7;
            white-space: pre-wrap;
        }}

        /* STORY CARDS */
        .story-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 22px;
            margin-bottom: 16px;
            transition: background 0.2s;
        }}

        .story-card:hover {{ background: var(--bg-card-hover); }}

        .topic-tags {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }}

        .topic-tag {{
            font-size: 0.7rem;
            padding: 3px 10px;
            border-radius: 12px;
            background: rgba(201, 168, 76, 0.1);
            color: var(--accent-gold);
            border: 1px solid rgba(201, 168, 76, 0.15);
        }}

        .story-title {{
            font-family: 'Newsreader', serif;
            font-size: 1.2rem;
            font-weight: 400;
            line-height: 1.4;
            margin-bottom: 8px;
        }}

        .story-title a {{
            color: var(--text-primary);
            text-decoration: none;
            transition: color 0.2s;
        }}

        .story-title a:hover {{ color: var(--accent-gold); }}

        .story-meta {{
            font-size: 0.78rem;
            color: var(--text-dim);
            display: flex;
            gap: 12px;
        }}

        .story-summary {{
            font-size: 0.88rem;
            color: var(--text-secondary);
            margin: 12px 0;
            line-height: 1.6;
        }}

        /* MULTI-SOURCE */
        .multi-source {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin: 10px 0;
            padding: 8px 12px;
            background: rgba(74, 124, 201, 0.06);
            border-radius: 6px;
            border: 1px solid rgba(74, 124, 201, 0.1);
        }}

        .perspective-badge {{
            color: var(--accent-blue);
            font-weight: 600;
            margin-right: 6px;
        }}

        .bias-label {{
            color: var(--text-dim);
            font-size: 0.75rem;
        }}

        /* ANALYSES ACCORDION */
        .analyses-container {{ margin-top: 12px; }}

        .toggle-analyses {{
            width: 100%;
            background: var(--bg-analysis);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 0.82rem;
            font-family: 'DM Sans', sans-serif;
            cursor: pointer;
            text-align: left;
            transition: all 0.2s;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .toggle-analyses:hover {{ border-color: var(--accent-purple); color: var(--text-primary); }}

        .analyses-content {{
            display: none;
            margin-top: 8px;
        }}

        .analyses-container.open .analyses-content {{ display: block; }}
        .analyses-container.open .arrow {{ transform: rotate(180deg); }}

        .llm-analysis {{
            background: var(--bg-analysis);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 14px;
            margin-bottom: 8px;
        }}

        .llm-name {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--accent-purple);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .llm-text {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            line-height: 1.65;
            white-space: pre-wrap;
        }}

        /* FOOTER */
        footer {{
            text-align: center;
            padding: 30px 0;
            margin-top: 40px;
            border-top: 1px solid var(--border);
            font-size: 0.78rem;
            color: var(--text-dim);
        }}

        /* RESPONSIVE */
        @media (max-width: 600px) {{
            .masthead {{ font-size: 1.6rem; }}
            .story-card {{ padding: 16px; }}
            .story-title {{ font-size: 1.05rem; }}
            header {{ padding: 24px 0 20px; }}
        }}

        /* TOPIC-SPECIFIC COLORS */
        [data-topic="world_politics"] {{ background: rgba(74, 124, 201, 0.1); border-color: rgba(74, 124, 201, 0.2); color: #6a9cd9; }}
        [data-topic="canada_politics"] {{ background: rgba(201, 76, 76, 0.1); border-color: rgba(201, 76, 76, 0.2); color: #d97a7a; }}
        [data-topic="us_politics"] {{ background: rgba(76, 100, 201, 0.1); border-color: rgba(76, 100, 201, 0.2); color: #7a8ed9; }}
        [data-topic="economics_business"] {{ background: rgba(76, 170, 124, 0.1); border-color: rgba(76, 170, 124, 0.2); color: #6ac9a0; }}
        [data-topic="tech_ai"] {{ background: rgba(138, 92, 201, 0.1); border-color: rgba(138, 92, 201, 0.2); color: #a87ed9; }}
        [data-topic="insurance_canada"] {{ background: rgba(201, 168, 76, 0.1); border-color: rgba(201, 168, 76, 0.2); color: #d9c06a; }}
        [data-topic="data_privacy_governance"] {{ background: rgba(76, 180, 201, 0.1); border-color: rgba(76, 180, 201, 0.2); color: #6ad0d9; }}
        [data-topic="culture_good_news"] {{ background: rgba(201, 140, 76, 0.1); border-color: rgba(201, 140, 76, 0.2); color: #d9b06a; }}

        /* Loading shimmer for future use */
        .loading {{ opacity: 0.5; animation: pulse 1.5s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 0.5; }} 50% {{ opacity: 0.8; }} }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="masthead">Global <span class="accent">Briefing</span></div>
            <div class="run-info">
                <strong>{run_time.strftime("%A, %B %d, %Y • %I:%M %p %Z")}</strong><br>
                {len(top_stories)} stories from {len(set(a.source_name for g in top_stories for a in g))} sources •
                Analyzed by {len(set(k for analyses in all_analyses for k in analyses))} AI models
            </div>
        </header>

        <div class="filter-bar">
            <button class="filter-btn active" onclick="filterStories('all')">All</button>
            {filter_buttons}
        </div>

        <div class="synthesis">
            <h2>📋 Today's Synthesis</h2>
            <p>{synthesis_escaped}</p>
        </div>

        <div id="stories">
            {stories_html}
        </div>

        <footer>
            Global Briefing • AI-powered intelligence system<br>
            Sources: {len(RSS_SOURCES)} feeds across {len(set(s[2].split('-')[0] for s in RSS_SOURCES))} regions
        </footer>
    </div>

    <script>
        function filterStories(topic) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');

            document.querySelectorAll('.story-card').forEach(card => {{
                if (topic === 'all') {{
                    card.style.display = 'block';
                }} else {{
                    const topics = card.getAttribute('data-topics').split(' ');
                    card.style.display = topics.includes(topic) ? 'block' : 'none';
                }}
            }});
        }}
    </script>
</body>
</html>'''

    return html


# =============================================================================
# MAIN
# =============================================================================

def main():
    run_time = datetime.now(timezone.utc)
    print(f"🌐 Global Briefing — {run_time.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # 1. Fetch all feeds
    articles = fetch_all_feeds()

    if not articles:
        print("❌ No articles fetched. Check your internet connection and feed URLs.")
        sys.exit(1)

    # 2. Triage by topic
    relevant = triage_articles(articles)

    # 3. Group by story
    story_groups = group_by_story(relevant)
    print(f"\n📑 Story groups: {len(story_groups)} ({sum(1 for g in story_groups if len(g) > 1)} multi-source)")

    # 4. Smart triage with LLM (if available)
    top_stories = smart_triage_with_llm(story_groups)
    if len(top_stories) > 20:
        top_stories = top_stories[:12]

    print(f"\n⭐ Top stories selected: {len(top_stories)}")
    for i, group in enumerate(top_stories):
        lead = group[0]
        print(f"  {i+1}. [{', '.join(lead.topics[:2])}] {lead.title[:80]}... ({len(group)} sources)")

    # 5. Analyze with multiple LLMs
    print("\n🤖 Analyzing stories with multiple LLMs...")
    all_analyses = []
    for i, group in enumerate(top_stories):
        print(f"\n  Story {i+1}/{len(top_stories)}: {group[0].title[:60]}...")
        analyses = analyze_story_with_llms(group)
        all_analyses.append(analyses)

    # 6. Synthesize
    synthesis = synthesize_briefing(top_stories, all_analyses)

    # 7. Generate HTML
    print("\n🎨 Generating briefing page...")
    html = generate_html(top_stories, all_analyses, synthesis, run_time)

    # Write output
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Always write to index.html (for GitHub Pages) and a timestamped copy
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    timestamp_file = output_dir / f"briefing-{run_time.strftime('%Y%m%d-%H%M')}.html"
    timestamp_file.write_text(html, encoding="utf-8")

    print(f"\n✅ Briefing generated: {output_dir / 'index.html'}")
    print(f"   Archive copy: {timestamp_file}")


if __name__ == "__main__":
    main()
