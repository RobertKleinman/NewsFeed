#!/usr/bin/env python3
"""
Global Briefing System v2
=========================
Pipeline: Fetch -> Triage -> Cluster -> Select Stories -> Map Perspectives ->
          Select Sources -> Extract Claims -> Compare -> Write -> Synthesize -> Publish

Key design: LLMs advise, code decides. Source selection is deterministic.
Multi-model diversity is concentrated where editorial judgment matters most.
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
from dataclasses import dataclass, field
from typing import Optional
import traceback

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

    def uid(self):
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def source_label(self):
        return "{name} ({region}, {bias})".format(
            name=self.source_name, region=self.source_region, bias=self.source_bias
        )


# =============================================================================
# LLM CALLER
# =============================================================================

LLM_CONFIGS = {
    "gemini": {
        "provider": "google", "model": "gemini-3-flash-preview",
        "env_key": "GOOGLE_API_KEY", "label": "Gemini",
    },
    "chatgpt": {
        "provider": "openai", "model": "gpt-4.1",
        "env_key": "OPENAI_API_KEY", "label": "ChatGPT",
    },
    "claude": {
        "provider": "anthropic", "model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY", "label": "Claude",
    },
    "grok": {
        "provider": "xai", "model": "grok-3-fast",
        "env_key": "XAI_API_KEY", "label": "Grok",
    },
}


def get_available_llms(exclude=None):
    exclude = exclude or []
    return [k for k, v in LLM_CONFIGS.items()
            if k not in exclude and os.environ.get(v["env_key"])]


def call_llm_by_id(llm_id, system_prompt, user_prompt, max_tokens=1500):
    config = LLM_CONFIGS[llm_id]
    api_key = os.environ.get(config["env_key"])
    if not api_key:
        return None
    return call_llm(config["provider"], config["model"],
                    system_prompt, user_prompt, api_key, max_tokens)


def call_llm(provider, model, system_prompt, user_prompt, api_key, max_tokens=1500):
    for attempt in range(3):
        try:
            return _call_llm_once(provider, model, system_prompt, user_prompt, api_key, max_tokens)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = (attempt + 1) * 15
                print("    ⏳ Rate limited, waiting {}s...".format(wait))
                time.sleep(wait)
            else:
                code = e.response.status_code if e.response else "unknown"
                print("  ❌ {}/{}: HTTP {}".format(provider, model, code))
                return None
        except Exception as e:
            print("  ❌ {}/{}: {}".format(provider, model, str(e)[:100]))
            return None
    return None


def _call_llm_once(provider, model, system_prompt, user_prompt, api_key, max_tokens):
    if provider == "google":
        url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}".format(model, api_key)
        payload = {
            "contents": [{"parts": [{"text": system_prompt + "\n\n" + user_prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}
        }
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens, "temperature": 0.3
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key, "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model, "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    elif provider == "xai":
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens, "temperature": 0.3
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# =============================================================================
# STEP 1: FETCH
# =============================================================================

def fetch_single_feed(name, url, region, bias, timeout=15):
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
        print("  ❌ {}: {}".format(name, str(e)[:60]))
    return articles


def fetch_all_feeds():
    print("\n📡 Fetching from {} sources...".format(len(RSS_SOURCES)))
    all_articles = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(fetch_single_feed, n, u, r, b): n
            for n, u, r, b in RSS_SOURCES
        }
        for future in as_completed(futures):
            all_articles.extend(future.result())
    seen = set()
    unique = []
    for a in all_articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)
    print("📰 Total unique articles: {}".format(len(unique)))
    return unique


# =============================================================================
# STEP 2: TRIAGE
# =============================================================================

def triage_articles(articles):
    print("\n🔍 Triaging articles by topic...")
    for article in articles:
        text = "{} {}".format(article.title, article.summary).lower()
        matched = []
        for topic_id, info in TOPICS.items():
            score = sum(1 for kw in info["keywords"] if kw.lower() in text)
            if score >= 1:
                matched.append((topic_id, score))
        matched.sort(key=lambda x: x[1], reverse=True)
        article.topics = [t[0] for t in matched]
        article.importance_score = min(
            len(matched) * 0.3 + (matched[0][1] * 0.2 if matched else 0), 1.0
        )
    relevant = [a for a in articles if a.topics]
    print("  Relevant: {}/{}".format(len(relevant), len(articles)))
    return relevant


# =============================================================================
# STEP 3: CLUSTER
# =============================================================================

def extract_entities(text):
    entities = set()
    skip = {"The", "And", "But", "For", "New", "How", "Why", "What", "Who",
            "With", "From", "After", "Into", "Over", "Has", "Are", "Will",
            "Can", "May", "Its", "Says", "Could", "Would", "About", "More",
            "This", "That", "Than", "Just", "Also", "Been", "Some", "All"}
    for word in text.split():
        clean = re.sub(r"[^a-zA-Z]", "", word)
        if clean and clean[0].isupper() and len(clean) > 2 and clean not in skip:
            entities.add(clean.lower())
    return entities


def cluster_articles(articles):
    print("\n📑 Clustering articles by event...")

    def normalize(title):
        return set(re.sub(r"[^a-z0-9\s]", "", title.lower()).split())

    groups = []
    used = set()
    articles.sort(key=lambda a: a.importance_score, reverse=True)

    for i, article in enumerate(articles):
        if i in used:
            continue
        group = [article]
        words_i = normalize(article.title)
        entities_i = extract_entities(article.title)
        used.add(i)

        for j, other in enumerate(articles[i+1:], start=i+1):
            if j in used:
                continue
            words_j = normalize(other.title)
            entities_j = extract_entities(other.title)

            jaccard = len(words_i & words_j) / max(len(words_i | words_j), 1)
            entity_overlap = 0
            if entities_i and entities_j:
                entity_overlap = len(entities_i & entities_j) / max(len(entities_i | entities_j), 1)

            score = jaccard * 0.6 + entity_overlap * 0.4
            if score > 0.25:
                group.append(other)
                used.add(j)

        groups.append(group)

    multi = sum(1 for g in groups if len(g) > 1)
    print("  {} clusters ({} multi-source)".format(len(groups), multi))
    return groups


# =============================================================================
# STEP 4: SELECT STORIES (multi-model voting + topic minimums)
# =============================================================================

def select_stories(story_groups, max_stories=12):
    print("\n🗳️  Selecting stories (multi-model voting)...")

    summaries = []
    for i, group in enumerate(story_groups[:50]):
        lead = group[0]
        sources = ", ".join(set(a.source_name for a in group))
        topics = ", ".join(lead.topics[:2])
        summaries.append("{}. [{}] [{}] {} ({} sources)".format(
            i, topics, sources, lead.title, len(group)))

    stories_list = "\n".join(summaries)
    prompt = """You are a news editor selecting stories for an intelligence briefing.
Pick 15-20 of the most important stories for a reader interested in: world politics,
Canadian politics, US politics, economics/business, AI/technology, Canadian insurance,
data privacy/AI governance, and culture/good news.

Prioritize: genuine significance, diverse topics, multiple perspectives available,
and at least 1-2 uplifting/cultural stories.

Return ONLY a JSON array of story numbers, e.g. [0, 3, 5, 12, ...]

Stories:
""" + stories_list

    vote_counts = {}
    voters = 0

    for llm_id in get_available_llms()[:3]:
        config = LLM_CONFIGS[llm_id]
        print("  🗳️  {} voting...".format(config["label"]))
        result = call_llm_by_id(llm_id,
            "You are a concise news editor. Return only a JSON array.", prompt, 200)
        time.sleep(3)
        if result:
            try:
                match = re.search(r'\[[\d,\s]+\]', result)
                if match:
                    indices = json.loads(match.group())
                    voters += 1
                    for idx in indices:
                        if idx < len(story_groups):
                            vote_counts[idx] = vote_counts.get(idx, 0) + 1
                    print("    ✅ {} picked {} stories".format(config["label"], len(indices)))
            except Exception:
                print("    ⚠️  Could not parse response")

    if not vote_counts:
        print("  ⚠️  No votes, using keyword ranking")
        return story_groups[:max_stories]

    sorted_cands = sorted(vote_counts.items(), key=lambda x: (-x[1], x[0]))

    # First pass: one story per topic to guarantee diversity
    selected = []
    topics_covered = set()
    for idx, votes in sorted_cands:
        group = story_groups[idx]
        lead = group[0]
        new_topics = set(lead.topics) - topics_covered
        if new_topics and len(selected) < max_stories:
            selected.append(group)
            topics_covered.update(lead.topics)

    # Second pass: fill by vote count
    for idx, votes in sorted_cands:
        group = story_groups[idx]
        if group not in selected and len(selected) < max_stories:
            selected.append(group)

    print("  Selected {} stories covering {} topics".format(
        len(selected), len(topics_covered)))
    return selected


# =============================================================================
# STEP 5: MAP PERSPECTIVES (multi-model — diversity matters here)
# =============================================================================

def map_perspectives(story_group):
    lead = story_group[0]
    source_lines = []
    for a in story_group[:10]:
        source_lines.append("- {} (region: {}, leaning: {}): \"{}\"".format(
            a.source_name, a.source_region, a.source_bias, a.title))
    source_list = "\n".join(source_lines)

    prompt = """This story is about: {title}

Here are the sources covering it:
{sources}

Identify 3-5 meaningfully different perspectives or stakeholder positions on this story.
These could be political (left/right), regional (Western/Global South), institutional
(government/industry/civil society), ideological, religious, economic, or any other axis
that matters for THIS specific story.

Don't default to generic left/right if other axes are more relevant.
For each perspective, name which of the available sources above would best represent it.

Return ONLY a JSON array like:
[
  {{"perspective": "US administration position", "sources": ["Fox News", "AP News"], "reasoning": "brief why"}},
  {{"perspective": "Canadian sovereignty concern", "sources": ["CBC News"], "reasoning": "brief why"}}
]""".format(title=lead.title, sources=source_list)

    all_perspectives = []
    available = get_available_llms()

    for llm_id in available[:3]:
        config = LLM_CONFIGS[llm_id]
        print("      🔎 {} mapping perspectives...".format(config["label"]))
        result = call_llm_by_id(llm_id,
            "You are a media analyst who understands editorial perspectives globally. Return only JSON.",
            prompt, 600)
        time.sleep(3)
        if result:
            try:
                json_match = re.search(r'\[.*\]', result, re.DOTALL)
                if json_match:
                    perspectives = json.loads(json_match.group())
                    for p in perspectives:
                        p["identified_by"] = config["label"]
                    all_perspectives.extend(perspectives)
                    print("        ✅ {} found {} perspectives".format(
                        config["label"], len(perspectives)))
            except Exception as e:
                print("        ⚠️  Parse error: {}".format(str(e)[:60]))

    merged = merge_perspectives(all_perspectives)
    print("      📊 {} unique perspectives after merge".format(len(merged)))
    return merged


def merge_perspectives(perspectives):
    if not perspectives:
        return []
    merged = []
    for p in perspectives:
        name = p.get("perspective", "").lower().strip()
        is_dup = False
        for existing in merged:
            ex_name = existing.get("perspective", "").lower().strip()
            words_a = set(name.split())
            words_b = set(ex_name.split())
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            if overlap > 0.4:
                # Merge
                existing["identified_by"] = existing.get("identified_by", "") + ", " + p.get("identified_by", "")
                existing_sources = set(existing.get("sources", []))
                new_sources = set(p.get("sources", []))
                existing["sources"] = list(existing_sources | new_sources)
                is_dup = True
                break
        if not is_dup:
            merged.append(p)
    return merged[:5]


# =============================================================================
# STEP 6: SELECT SOURCES (code decides, not LLMs)
# =============================================================================

def select_sources(story_group, perspectives):
    available = {a.source_name: a for a in story_group}
    selected = []
    used = set()
    missing = []

    for persp in perspectives:
        recommended = persp.get("sources", [])
        picked = None
        for src in recommended:
            if src in available and src not in used:
                picked = available[src]
                break
        if picked:
            used.add(picked.source_name)
            selected.append({
                "article": picked,
                "perspective": persp.get("perspective", ""),
                "identified_by": persp.get("identified_by", ""),
            })
        else:
            missing.append(persp.get("perspective", "Unknown"))

    # Always include lead if nothing matched
    if not selected and story_group:
        selected.append({
            "article": story_group[0],
            "perspective": "Primary report",
            "identified_by": "system",
        })

    return selected, missing


# =============================================================================
# STEP 7: EXTRACT CLAIMS (one cheap model per source)
# =============================================================================

def extract_claims(selected_sources):
    print("    📋 Extracting claims...")
    all_claims = []
    extractors = get_available_llms()
    if not extractors:
        return all_claims
    extractor_id = extractors[0]  # cheapest available

    for item in selected_sources:
        article = item["article"]
        perspective = item["perspective"]

        prompt = """Extract factual claims from this news article.

SOURCE: {source}
PERSPECTIVE: This source represents: {perspective}
HEADLINE: {title}
CONTENT: {summary}

For each claim, identify:
1. The claim itself (one sentence)
2. Type: REPORTED_FACT / OFFICIAL_STATEMENT / ANALYSIS / OPINION
3. Attribution (who said or reported it)

Also note:
EMPHASIS: What does this source emphasize that others covering the same event might not?
FRAMING: Any notable language choices, loaded words, or editorial angle?

Format each claim on its own line:
CLAIM: [text] | TYPE: [type] | ATTR: [attribution]

End with EMPHASIS and FRAMING lines.""".format(
            source=article.source_label(),
            perspective=perspective,
            title=article.title,
            summary=article.summary[:400])

        result = call_llm_by_id(extractor_id,
            "You extract structured claims from news. Be precise. Only extract what is stated or clearly implied. Never invent facts.",
            prompt, 800)
        time.sleep(3)

        if result:
            all_claims.append({
                "source": article.source_name,
                "region": article.source_region,
                "bias": article.source_bias,
                "perspective": perspective,
                "headline": article.title,
                "url": article.url,
                "extracted": result,
            })
            print("      ✅ {} ({} chars)".format(article.source_name, len(result)))
        else:
            print("      ⚠️  {} failed".format(article.source_name))

    return all_claims


# =============================================================================
# STEP 8: COMPARE (multi-model — bias detection matters most here)
# =============================================================================

def compare_claims(claims_data, lead_title):
    print("    🔍 Cross-source comparison...")
    if not claims_data:
        return {}

    claims_sections = []
    for c in claims_data:
        claims_sections.append(
            "--- SOURCE: {src} ({region}, {bias}) | PERSPECTIVE: {persp} ---\n{text}".format(
                src=c["source"], region=c["region"], bias=c["bias"],
                persp=c["perspective"], text=c["extracted"]))
    claims_text = "\n\n".join(claims_sections)

    prompt = """You are a cross-source news auditor. Below are claim extractions from multiple
sources covering the same event: "{title}"

Each source was selected to represent a different perspective. Your job is to compare
and identify what they agree on, where they differ, and how they frame things differently.

SOURCES AND CLAIMS:
{claims}

Produce this analysis in plain text (no markdown, no bold, no bullet points, no headers with #):

AGREED FACTS:
State facts that multiple sources confirm. Name which sources agree. Only include facts
that are actually stated in the extractions. Never invent or assume.

DISAGREEMENTS:
Where sources report different facts, numbers, or conclusions. Be specific about what
each source says differently. If no real contradictions exist, say "No substantive
contradictions identified."

FRAMING DIFFERENCES:
How do different sources frame the same event? Quote specific language. What does each
source emphasize or downplay? This section is where editorial perspective becomes visible.

KEY UNKNOWNS:
Important questions the coverage leaves unanswered. What would a well-informed reader
want to know that none of these sources provide?""".format(
        title=lead_title, claims=claims_text)

    comparisons = {}
    available = get_available_llms()
    # Use 2 models if possible for comparison — this is where multi-model matters
    comparators = available[:2] if len(available) >= 2 else available

    for llm_id in comparators:
        config = LLM_CONFIGS[llm_id]
        print("      🔎 {} comparing...".format(config["label"]))
        result = call_llm_by_id(llm_id,
            "You are a precise, evidence-based news auditor. Reference only what is in the provided extractions. Never invent facts. Write plain text only.",
            prompt, 1500)
        time.sleep(5)

        if result:
            comparisons[config["label"]] = result
            print("        ✅ {} chars".format(len(result)))
        else:
            print("        ⚠️  Failed")

    return comparisons


# =============================================================================
# STEP 9: WRITE TOPIC CARD (one model, strict editor role)
# =============================================================================

def write_topic_card(lead_title, topics, selected_sources, missing_perspectives, comparisons):
    print("    ✍️  Writing topic card...")
    if not comparisons:
        return None

    comp_sections = []
    for model, text in comparisons.items():
        comp_sections.append("--- {} ANALYSIS ---\n{}".format(model, text))
    comparison_text = "\n\n".join(comp_sections)

    source_lines = []
    for s in selected_sources:
        source_lines.append("- {} ({}): representing {}".format(
            s["article"].source_name, s["article"].source_region,
            s["perspective"]))
    sources_summary = "\n".join(source_lines)

    missing_text = ", ".join(missing_perspectives) if missing_perspectives else "None"

    prompt = """Write a topic card for this news event based ONLY on the comparison analyses below.
You are an editor. Do NOT add any facts beyond what the comparisons contain.

EVENT: {title}

SOURCES USED:
{sources}

MISSING PERSPECTIVES: {missing}

COMPARISON ANALYSES:
{comparisons}

Write the topic card using this EXACT structure. Use plain text only. No markdown, no bold,
no bullet points, no # headers. Use the section labels exactly as shown.

WHAT HAPPENED:
2-3 sentences. Neutral summary from agreed facts only.

AGREED FACTS:
Key facts confirmed by multiple sources. Name the sources for each. One sentence per fact.
Separate facts with line breaks.

POINTS OF DISAGREEMENT:
Where sources differ on facts, interpretation, or emphasis. Be specific.
If the comparison analysts themselves disagreed about what counts as a disagreement, note that.

FRAMING AND PERSPECTIVE:
How different sources frame this story. Quote specific language where the comparisons
identified it. Note what each perspective emphasizes or downplays.

KEY UNKNOWNS:
Questions no source answered. What should the reader watch for.

WHY IT MATTERS:
2-3 sentences on broader significance. Connect to larger trends if the comparisons support it.

MISSING VIEWPOINTS:
Note any perspectives that were identified as relevant but had no source available.""".format(
        title=lead_title, sources=sources_summary,
        missing=missing_text, comparisons=comparison_text)

    # Use whichever model was NOT used for comparison to avoid compounding bias
    available = get_available_llms()
    comparator_ids = []
    for llm_id in available:
        if LLM_CONFIGS[llm_id]["label"] in comparisons:
            comparator_ids.append(llm_id)
    non_comparators = [x for x in available if x not in comparator_ids]
    writer_id = non_comparators[0] if non_comparators else available[-1]

    result = call_llm_by_id(writer_id,
        "You are a precise intelligence briefing editor. Write plain text only. No markdown. Do not add facts beyond what is provided. Attribute everything.",
        prompt, 2000)
    time.sleep(3)

    if result:
        writer_label = LLM_CONFIGS[writer_id]["label"]
        print("      ✅ Written by {} ({} chars)".format(writer_label, len(result)))
    return result


# =============================================================================
# ORCHESTRATOR: Process one story through the full pipeline
# =============================================================================

def process_story(story_group, story_num, total):
    lead = story_group[0]
    topic_names = ", ".join(TOPICS[t]["name"] for t in lead.topics[:2] if t in TOPICS)
    print("\n" + "=" * 70)
    print("📰 Story {}/{}: {}".format(story_num, total, lead.title[:80]))
    print("   Topics: {} | Sources in cluster: {}".format(topic_names, len(story_group)))

    # Step 5: Map perspectives
    print("    Step 5: Mapping perspectives...")
    perspectives = map_perspectives(story_group)

    if not perspectives:
        # Fallback: use all available sources without perspective mapping
        print("    ⚠️  No perspectives mapped, using available sources directly")
        perspectives = [{"perspective": "General coverage",
                        "sources": [a.source_name for a in story_group[:3]]}]

    # Step 6: Select sources (code decides)
    print("    Step 6: Selecting sources...")
    selected_sources, missing = select_sources(story_group, perspectives)
    print("      {} sources selected, {} perspectives missing".format(
        len(selected_sources), len(missing)))

    # Step 7: Extract claims
    print("    Step 7: Extracting claims...")
    claims = extract_claims(selected_sources)

    if not claims:
        print("    ⚠️  No claims extracted, skipping story")
        return None

    # Step 8: Compare
    print("    Step 8: Comparing across sources...")
    comparisons = compare_claims(claims, lead.title)

    if not comparisons:
        print("    ⚠️  No comparisons generated, skipping story")
        return None

    # Step 9: Write topic card
    print("    Step 9: Writing topic card...")
    card_text = write_topic_card(
        lead.title, lead.topics, selected_sources, missing, comparisons)

    if not card_text:
        print("    ⚠️  Topic card writing failed")
        return None

    return {
        "title": lead.title,
        "topics": lead.topics,
        "source_count": len(story_group),
        "perspectives_used": len(selected_sources),
        "missing_perspectives": missing,
        "sources": [
            {"name": s["article"].source_name,
             "region": s["article"].source_region,
             "bias": s["article"].source_bias,
             "perspective": s["perspective"],
             "url": s["article"].url}
            for s in selected_sources
        ],
        "card_text": card_text,
        "comparisons": comparisons,
    }


# =============================================================================
# STEP 10: SYNTHESIZE
# =============================================================================

def generate_synthesis(topic_cards):
    print("\n📝 Generating executive synthesis...")
    available = get_available_llms()
    if not available:
        return "No LLM API keys configured."

    card_summaries = []
    for i, card in enumerate(topic_cards):
        # Extract just the WHAT HAPPENED section for synthesis
        what_happened = ""
        if "WHAT HAPPENED:" in card["card_text"]:
            parts = card["card_text"].split("WHAT HAPPENED:")
            if len(parts) > 1:
                what_happened = parts[1].split("\n\n")[0].strip()[:300]
        if not what_happened:
            what_happened = card["card_text"][:200]

        topics = ", ".join(card["topics"][:2])
        card_summaries.append("Story {num}: [{topics}] {title}\n{summary}\nSources: {count}, Perspectives: {persp}".format(
            num=i+1, topics=topics, title=card["title"],
            summary=what_happened, count=card["source_count"],
            persp=card["perspectives_used"]))

    all_summaries = "\n\n".join(card_summaries)

    prompt = """You are writing the executive synthesis for a daily intelligence briefing.
Based on these topic cards, write a compelling 4-5 paragraph overview that:
1. Identifies the 2-3 biggest themes of the day
2. Notes where different sources and perspectives disagreed on key stories
3. Calls out connecting threads between stories
4. Ends with 2-3 specific things to watch in the coming days

Write in plain text only. No markdown, no bold, no headers, no bullet points.
Write as if briefing a senior executive who needs signal, not noise.

TODAY'S STORIES:
""" + all_summaries

    return call_llm_by_id(available[0],
        "You write concise intelligence briefings. Plain text only. No markdown.",
        prompt, 2000)


# =============================================================================
# STEP 11: PUBLISH (HTML generation)
# =============================================================================

def generate_html(topic_cards, synthesis, run_time):
    """Generate the HTML briefing page with topic cards."""

    # Build story cards HTML
    stories_html = ""
    for card in topic_cards:
        topic_tags = " ".join(
            '<span class="topic-tag" data-topic="{tid}">{icon} {name}</span>'.format(
                tid=t, icon=TOPICS[t]["icon"], name=TOPICS[t]["name"])
            for t in card["topics"][:3] if t in TOPICS
        )

        # Source pills
        source_pills = ""
        for s in card["sources"]:
            source_pills += '<span class="source-pill" title="{persp}">{name} <span class="bias-label">({bias})</span></span> '.format(
                persp=s["perspective"], name=s["name"], bias=s["bias"])

        # Missing perspectives
        missing_html = ""
        if card["missing_perspectives"]:
            missing_list = ", ".join(card["missing_perspectives"])
            missing_html = '<div class="missing-perspectives">⚠️ Missing perspectives: {}</div>'.format(missing_list)

        # Format the topic card text into HTML sections
        card_html = format_card_text(card["card_text"])

        # Comparison details (collapsible)
        comp_html = ""
        if card["comparisons"]:
            comp_details = ""
            for model, text in card["comparisons"].items():
                escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                comp_details += '<div class="comparison-block"><div class="comp-model">{model}</div><div class="comp-text">{text}</div></div>'.format(
                    model=model, text=escaped.replace("\n", "<br>"))

            comp_html = """<details class="raw-comparisons">
                <summary>🔍 Raw Model Comparisons ({count} models)</summary>
                {details}
            </details>""".format(count=len(card["comparisons"]), details=comp_details)

        stories_html += """
        <article class="story-card" data-topics="{topic_ids}">
            <div class="topic-tags">{tags}</div>
            <h2 class="story-title">{title}</h2>
            <div class="story-meta">
                <span class="source-count">📰 {src_count} sources</span>
                <span class="perspective-count">🔎 {persp_count} perspectives</span>
            </div>
            <div class="sources-used">{pills}</div>
            {missing}
            <div class="topic-card-content">{card}</div>
            {comparisons}
        </article>""".format(
            topic_ids=" ".join(card["topics"][:3]),
            tags=topic_tags,
            title=card["title"],
            src_count=card["source_count"],
            persp_count=card["perspectives_used"],
            pills=source_pills,
            missing=missing_html,
            card=card_html,
            comparisons=comp_html)

    # Synthesis formatting
    synthesis_html = ""
    if synthesis:
        synthesis_escaped = synthesis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        synthesis_html = synthesis_escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
        synthesis_html = "<p>" + synthesis_html + "</p>"

    # Topic filter buttons
    filter_buttons = '<button class="filter-btn active" data-filter="all">All</button>'
    for tid, info in TOPICS.items():
        filter_buttons += '<button class="filter-btn" data-filter="{tid}">{icon} {name}</button>'.format(
            tid=tid, icon=info["icon"], name=info["name"])

    # Run stats
    llms_used = ", ".join(LLM_CONFIGS[k]["label"] for k in get_available_llms())

    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Intelligence Briefing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #0a0e17;
    --card-bg: #111827;
    --card-border: #1e293b;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #f59e0b;
    --accent2: #3b82f6;
    --section-bg: #0f172a;
    --agreed: #10b981;
    --disagree: #ef4444;
    --framing: #a78bfa;
    --unknown: #64748b;
    --matters: #3b82f6;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    padding: 0 1rem;
    max-width: 900px;
    margin: 0 auto;
}}
.masthead {{
    text-align: center;
    padding: 2rem 0 1rem;
    border-bottom: 1px solid var(--card-border);
    margin-bottom: 1.5rem;
}}
.masthead h1 {{
    font-family: 'Newsreader', serif;
    font-size: 2rem;
    color: var(--accent);
    margin-bottom: 0.3rem;
}}
.masthead .meta {{
    font-size: 0.85rem;
    color: var(--text-muted);
}}
.synthesis-box {{
    background: var(--card-bg);
    border-left: 3px solid var(--accent);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
}}
.synthesis-box h2 {{
    font-family: 'Newsreader', serif;
    color: var(--accent);
    font-size: 1.3rem;
    margin-bottom: 1rem;
}}
.synthesis-box p {{
    margin-bottom: 0.8rem;
    color: var(--text);
}}
.filter-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 1.5rem;
    padding: 0.5rem 0;
}}
.filter-btn {{
    background: var(--card-bg);
    color: var(--text-muted);
    border: 1px solid var(--card-border);
    border-radius: 20px;
    padding: 0.3rem 0.8rem;
    font-size: 0.8rem;
    cursor: pointer;
    font-family: 'DM Sans', sans-serif;
}}
.filter-btn.active {{
    background: var(--accent);
    color: #000;
    border-color: var(--accent);
    font-weight: 600;
}}
.story-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}}
.topic-tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.8rem;
}}
.topic-tag {{
    font-size: 0.75rem;
    padding: 0.2rem 0.6rem;
    border-radius: 12px;
    border: 1px solid var(--card-border);
    color: var(--text-muted);
}}
.story-title {{
    font-family: 'Newsreader', serif;
    font-size: 1.3rem;
    line-height: 1.4;
    margin-bottom: 0.5rem;
}}
.story-meta {{
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
    display: flex;
    gap: 1rem;
}}
.sources-used {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-bottom: 0.8rem;
}}
.source-pill {{
    font-size: 0.75rem;
    padding: 0.2rem 0.5rem;
    background: var(--section-bg);
    border-radius: 10px;
    color: var(--text-muted);
}}
.bias-label {{ color: var(--accent); font-size: 0.7rem; }}
.missing-perspectives {{
    font-size: 0.8rem;
    color: var(--disagree);
    padding: 0.4rem 0.6rem;
    background: rgba(239, 68, 68, 0.1);
    border-radius: 6px;
    margin-bottom: 0.8rem;
}}
.topic-card-content {{
    margin-top: 1rem;
}}
.card-section {{
    margin-bottom: 1rem;
    padding: 0.8rem;
    border-radius: 6px;
    background: var(--section-bg);
}}
.card-section-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.4rem;
    font-weight: 600;
}}
.section-what-happened .card-section-label {{ color: var(--accent2); }}
.section-agreed .card-section-label {{ color: var(--agreed); }}
.section-disagreements .card-section-label {{ color: var(--disagree); }}
.section-framing .card-section-label {{ color: var(--framing); }}
.section-unknowns .card-section-label {{ color: var(--unknown); }}
.section-matters .card-section-label {{ color: var(--matters); }}
.section-missing .card-section-label {{ color: var(--disagree); }}
.card-section-text {{
    font-size: 0.9rem;
    line-height: 1.6;
    color: var(--text);
}}
.raw-comparisons {{
    margin-top: 1rem;
    border-top: 1px solid var(--card-border);
    padding-top: 0.5rem;
}}
.raw-comparisons summary {{
    font-size: 0.8rem;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0.3rem 0;
}}
.comparison-block {{
    margin-top: 0.8rem;
    padding: 0.8rem;
    background: var(--section-bg);
    border-radius: 6px;
}}
.comp-model {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--accent);
    margin-bottom: 0.3rem;
}}
.comp-text {{
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.5;
}}
.run-report {{
    margin-top: 2rem;
    padding: 1rem;
    background: var(--card-bg);
    border-radius: 8px;
    font-size: 0.8rem;
    color: var(--text-muted);
    text-align: center;
    border: 1px solid var(--card-border);
}}
@media (max-width: 600px) {{
    body {{ padding: 0 0.5rem; }}
    .story-card {{ padding: 1rem; }}
    .masthead h1 {{ font-size: 1.5rem; }}
}}
</style>
</head>
<body>

<div class="masthead">
    <h1>🗞️ Global Intelligence Briefing</h1>
    <div class="meta">{date} | {num_stories} stories | {num_sources} source feeds | Models: {llms}</div>
</div>

<div class="synthesis-box">
    <h2>📋 Executive Synthesis</h2>
    {synthesis}
</div>

<div class="filter-bar">
    {filters}
</div>

{stories}

<div class="run-report">
    Generated {date} | Pipeline: Fetch → Triage → Cluster → Vote → Map Perspectives → Extract → Compare → Write<br>
    Runtime: {runtime}s | Models: {llms}
</div>

<script>
document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const filter = btn.dataset.filter;
        document.querySelectorAll('.story-card').forEach(card => {{
            if (filter === 'all' || card.dataset.topics.includes(filter)) {{
                card.style.display = '';
            }} else {{
                card.style.display = 'none';
            }}
        }});
    }});
}});
</script>
</body>
</html>""".format(
        date=now,
        num_stories=len(topic_cards),
        num_sources=len(RSS_SOURCES),
        llms=llms_used,
        synthesis=synthesis_html,
        filters=filter_buttons,
        stories=stories_html,
        runtime=run_time)

    return html


def format_card_text(text):
    """Parse the structured topic card text into styled HTML sections."""
    sections = {
        "WHAT HAPPENED:": ("what-happened", "What Happened"),
        "AGREED FACTS:": ("agreed", "Agreed Facts"),
        "POINTS OF DISAGREEMENT:": ("disagreements", "Points of Disagreement"),
        "FRAMING AND PERSPECTIVE:": ("framing", "Framing & Perspective"),
        "KEY UNKNOWNS:": ("unknowns", "Key Unknowns"),
        "WHY IT MATTERS:": ("matters", "Why It Matters"),
        "MISSING VIEWPOINTS:": ("missing", "Missing Viewpoints"),
    }

    html_parts = []
    remaining = text

    # Try to parse each section in order
    section_keys = list(sections.keys())
    for i, key in enumerate(section_keys):
        if key not in remaining:
            continue

        # Find start of this section's content
        start = remaining.index(key) + len(key)

        # Find end (start of next section, or end of text)
        end = len(remaining)
        for next_key in section_keys[i+1:]:
            if next_key in remaining[start:]:
                end = start + remaining[start:].index(next_key)
                break

        content = remaining[start:end].strip()
        if content:
            css_class, label = sections[key]
            escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            formatted = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_parts.append(
                '<div class="card-section section-{cls}"><div class="card-section-label">{label}</div><div class="card-section-text"><p>{text}</p></div></div>'.format(
                    cls=css_class, label=label, text=formatted))

    if not html_parts:
        # Fallback: just render the whole text
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return '<div class="card-section"><div class="card-section-text"><p>{}</p></div></div>'.format(
            escaped.replace("\n", "<br>"))

    return "\n".join(html_parts)


# =============================================================================
# MAIN
# =============================================================================

def main():
    start_time = time.time()
    print("=" * 70)
    print("🗞️  GLOBAL INTELLIGENCE BRIEFING v2")
    print("=" * 70)
    print("Pipeline: Fetch > Triage > Cluster > Vote > Perspectives > Extract > Compare > Write > Synthesize > Publish")

    available = get_available_llms()
    if not available:
        print("\n❌ No LLM API keys found. Set at least GOOGLE_API_KEY.")
        sys.exit(1)
    print("\n🤖 Available LLMs: {}".format(
        ", ".join(LLM_CONFIGS[k]["label"] for k in available)))

    # Step 1: Fetch
    articles = fetch_all_feeds()
    if not articles:
        print("❌ No articles fetched")
        sys.exit(1)

    # Step 2: Triage
    relevant = triage_articles(articles)
    if not relevant:
        print("❌ No relevant articles after triage")
        sys.exit(1)

    # Step 3: Cluster
    clusters = cluster_articles(relevant)

    # Step 4: Select stories
    selected = select_stories(clusters, max_stories=12)

    # Steps 5-9: Process each story through the full pipeline
    topic_cards = []
    for i, group in enumerate(selected):
        try:
            card = process_story(group, i + 1, len(selected))
            if card:
                topic_cards.append(card)
        except Exception as e:
            print("  ❌ Story processing failed: {}".format(str(e)[:100]))
            traceback.print_exc()
            continue

    if not topic_cards:
        print("\n❌ No topic cards generated")
        sys.exit(1)

    print("\n✅ Generated {} topic cards".format(len(topic_cards)))

    # Step 10: Synthesize
    synthesis = generate_synthesis(topic_cards)
    if not synthesis:
        synthesis = "Synthesis generation failed. See individual topic cards below."

    # Step 11: Publish
    run_time = int(time.time() - start_time)
    html = generate_html(topic_cards, synthesis, run_time)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print("\n📄 Briefing written to {}".format(output_path))

    # Run report
    print("\n" + "=" * 70)
    print("📊 RUN REPORT")
    print("=" * 70)
    print("  Articles fetched: {}".format(len(articles)))
    print("  Relevant after triage: {}".format(len(relevant)))
    print("  Clusters formed: {}".format(len(clusters)))
    print("  Stories selected: {}".format(len(selected)))
    print("  Topic cards generated: {}".format(len(topic_cards)))
    print("  LLMs used: {}".format(", ".join(LLM_CONFIGS[k]["label"] for k in available)))
    print("  Runtime: {}s".format(run_time))
    print("=" * 70)


if __name__ == "__main__":
    main()
