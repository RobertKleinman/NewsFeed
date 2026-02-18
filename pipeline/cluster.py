"""
Step 3: Cluster articles about the same event.
Two-pass approach:
  Pass 1: Mechanical clustering (entity/word overlap) — fast, free
  Pass 2: LLM review to merge missed clusters and split bad ones — 1-2 calls
"""

import hashlib
import json
import re
import time

import llm as llm_caller
from models import Article, StoryCluster, StepReport

SKIP_WORDS = {
    "the", "and", "but", "for", "new", "how", "why", "what", "who", "when",
    "with", "from", "after", "into", "over", "has", "are", "will", "can",
    "may", "its", "says", "could", "would", "about", "more", "this", "that",
    "than", "just", "also", "been", "some", "all", "not", "was", "his",
    "her", "they", "their", "have", "had", "does", "did", "top", "big",
    "get", "got", "set", "two", "first", "last", "year", "years", "news",
    "report", "says", "said", "told", "according", "amid",
    "people", "world", "time", "make", "back", "take", "state", "still",
    "being", "where", "most", "only", "now", "part", "made", "between",
    "other", "many", "much", "even", "three", "four", "five",
    "before", "under", "every", "show", "here", "week", "month", "day",
    "million", "billion", "percent", "early", "late", "high", "low",
    "former", "current", "major", "expected", "likely", "possible",
    "security", "attack", "system", "technology", "policy", "government",
    "officials", "political", "economic", "global", "international",
    "national", "public", "social", "digital", "data", "online",
}


def _extract_entities(text):
    entities = set()
    for word in text.split():
        clean = re.sub(r"[^a-zA-Z']", "", word)
        if clean and clean[0].isupper() and len(clean) > 2 and clean.lower() not in SKIP_WORDS:
            entities.add(clean.lower())
    return entities


def _extract_terms(text):
    words = set(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())
    return words - SKIP_WORDS - {""}


def _similarity(a, b):
    words_a = _extract_terms(a.title)
    words_b = _extract_terms(b.title)
    title_jaccard = len(words_a & words_b) / max(len(words_a | words_b), 1) if words_a and words_b else 0

    text_a = a.title + " " + a.summary
    text_b = b.title + " " + b.summary
    entities_a = _extract_entities(text_a)
    entities_b = _extract_entities(text_b)
    shared = entities_a & entities_b if entities_a and entities_b else set()
    entity_overlap = len(shared) / max(len(entities_a | entities_b), 1) if entities_a and entities_b else 0
    key_bonus = 0.3 if len(shared) >= 3 else (0.15 if len(shared) >= 2 else 0)

    sum_a = _extract_terms(a.summary[:200])
    sum_b = _extract_terms(b.summary[:200])
    sum_jaccard = len(sum_a & sum_b) / max(len(sum_a | sum_b), 1) if sum_a and sum_b else 0

    topic_bonus = 0.05 if set(a.topics) & set(b.topics) else 0

    return title_jaccard * 0.25 + entity_overlap * 0.35 + sum_jaccard * 0.15 + key_bonus + topic_bonus


def _cluster_id(articles):
    entities = set()
    for a in articles:
        entities.update(_extract_entities(a.title))
    return hashlib.md5(",".join(sorted(entities)[:5]).encode()).hexdigest()[:10]


def _mechanical_cluster(articles):
    """Pass 1: entity-based clustering."""
    groups = []
    used = set()
    articles.sort(key=lambda a: a.relevance_score, reverse=True)

    for i, article in enumerate(articles):
        if i in used:
            continue
        group = [article]
        used.add(i)
        for j, other in enumerate(articles[i+1:], start=i+1):
            if j in used:
                continue
            if _similarity(article, other) > 0.20:
                group.append(other)
                used.add(j)
        groups.append(group)
    return groups


def _llm_review_clusters(groups, report):
    """Pass 2: LLM reviews top clusters for merge/split opportunities."""
    # Only review clusters with 2+ articles (the interesting ones) + singletons nearby
    multi = [(i, g) for i, g in enumerate(groups) if len(g) >= 2]
    if len(multi) < 2:
        return groups  # Not enough to review

    # Build a summary of the top 40 clusters for review
    cluster_summaries = []
    review_indices = []
    for i, g in enumerate(groups[:60]):
        lead = g[0]
        sources = ", ".join(a.source_name for a in g[:3])
        cluster_summaries.append("{}: \"{}\" ({} articles: {})".format(
            i, lead.title[:80], len(g), sources))
        review_indices.append(i)
        if len(cluster_summaries) >= 40:
            break

    prompt = """Review these news article clusters. Each cluster groups articles about the same event.

CLUSTERS:
{}

Identify:
1. MERGE: Which clusters should be combined because they're about the SAME event?
2. No splits needed — mechanical clustering is conservative.

Return JSON:
{{
  "merges": [[2, 5], [8, 12, 15]],
  "notes": "brief explanation"
}}

If no merges needed: {{"merges": [], "notes": "clusters look correct"}}""".format(
        "\n".join(cluster_summaries))

    report.llm_calls += 1
    result = llm_caller.call_by_id("gemini",
        "You review news clustering. Return only JSON.", prompt, 1000)

    if not result:
        report.llm_failures += 1
        return groups

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        review = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        merges = review.get("merges", [])
        if merges:
            # Apply merges (absorb later clusters into earlier ones)
            merged_into = {}  # maps absorbed index → target index
            for merge_set in merges:
                if len(merge_set) < 2:
                    continue
                valid = [idx for idx in merge_set if idx < len(groups)]
                if len(valid) < 2:
                    continue
                target = valid[0]
                for idx in valid[1:]:
                    if idx not in merged_into:
                        groups[target].extend(groups[idx])
                        merged_into[idx] = target

            # Remove absorbed clusters
            groups = [g for i, g in enumerate(groups) if i not in merged_into]
            print("    LLM merged {} cluster sets".format(len(merges)))
    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1

    return groups


def run(articles):
    """Cluster articles. Returns (clusters, report)."""
    print("\n>>> CLUSTER: {} articles...".format(len(articles)))
    report = StepReport("cluster", items_in=len(articles))

    # Pass 1: mechanical
    groups = _mechanical_cluster(articles)
    multi_before = sum(1 for g in groups if len(g) > 1)
    print("    Pass 1: {} clusters ({} multi-source)".format(len(groups), multi_before))

    # Pass 2: LLM review
    groups = _llm_review_clusters(groups, report)
    multi_after = sum(1 for g in groups if len(g) > 1)

    # Convert to StoryCluster objects
    clusters = []
    for g in groups:
        lead = g[0]
        # Aggregate topics across all articles in cluster
        all_topics = []
        for a in g:
            for t in a.topics:
                if t not in all_topics:
                    all_topics.append(t)
        cluster = StoryCluster(
            articles=g,
            cluster_id=_cluster_id(g),
            lead_title=lead.title,
            topic_spread=all_topics,
        )
        clusters.append(cluster)

    report.items_out = len(clusters)
    report.notes.append("{} multi-source clusters".format(multi_after))
    print("    Final: {} clusters ({} multi-source)".format(len(clusters), multi_after))
    return clusters, report
