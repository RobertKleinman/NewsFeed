"""
Step 3: Cluster articles about the same SPECIFIC EVENT.

Key insight: entity overlap catches topic similarity, not event identity.
"Palestinians return to Gaza" and "Swiss TV pulls Gaza comments" share entities
(Gaza, Israel, Palestinian) but are completely different events.

Approach:
  Pass 1: Mechanical pre-grouping at HIGH threshold (0.45) — only near-duplicates
  Pass 2: LLM clusters articles by SPECIFIC EVENT, in batches by topic area
  Pass 3: LLM validates multi-source clusters — splits bad merges
"""

import hashlib
import json
import re
import time

import llm as llm_caller
from models import StoryCluster, StepReport

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
    # Geographic/conflict terms that cause false grouping
    "gaza", "israel", "israeli", "palestinian", "ukraine", "russia",
    "russian", "trump", "china", "chinese", "iran", "iranian",
    "europe", "european", "canada", "canadian", "united", "states",
    "minister", "president", "country", "countries",
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
    title_j = len(words_a & words_b) / max(len(words_a | words_b), 1) if words_a and words_b else 0

    text_a = a.title + " " + a.summary
    text_b = b.title + " " + b.summary
    ent_a = _extract_entities(text_a)
    ent_b = _extract_entities(text_b)
    shared = ent_a & ent_b if ent_a and ent_b else set()
    ent_overlap = len(shared) / max(len(ent_a | ent_b), 1) if ent_a and ent_b else 0
    key_bonus = 0.3 if len(shared) >= 3 else (0.15 if len(shared) >= 2 else 0)

    sum_a = _extract_terms(a.summary[:200])
    sum_b = _extract_terms(b.summary[:200])
    sum_j = len(sum_a & sum_b) / max(len(sum_a | sum_b), 1) if sum_a and sum_b else 0

    return title_j * 0.25 + ent_overlap * 0.35 + sum_j * 0.15 + key_bonus


def _cluster_id(articles):
    entities = set()
    for a in articles:
        entities.update(_extract_entities(a.title))
    return hashlib.md5(",".join(sorted(entities)[:5]).encode()).hexdigest()[:10]


# ── Pass 1: Mechanical pre-grouping (HIGH threshold) ──────────────────────

def _mechanical_pregroup(articles):
    """Only group near-duplicates (same headline rephrased). Threshold 0.45."""
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
            if _similarity(article, other) > 0.45:
                group.append(other)
                used.add(j)
        groups.append(group)
    return groups


# ── Pass 2: LLM event-based clustering ───────────────────────────────────

def _llm_cluster_batch(article_list, report):
    """Ask LLM to group articles by SPECIFIC EVENT."""
    if len(article_list) < 2:
        return [article_list] if article_list else []

    lines = []
    for i, a in enumerate(article_list):
        lines.append('{}: [{}] "{}" — {}'.format(
            i, a.source_name, a.title[:80], a.summary[:100]))

    prompt = """Group these articles by SPECIFIC EVENT. Articles about the same broad topic
but different events must be in DIFFERENT groups.

CRITICAL DISTINCTION:
- SAME EVENT: "Israel registers West Bank land" from BBC and "Eight countries condemn Israel's land grab" from Al Jazeera → same event
- DIFFERENT EVENTS: "Palestinians return to Gaza" and "Swiss TV pulls Gaza remarks" → different events about Gaza
- DIFFERENT EVENTS: "Jesse Jackson dies" and "US-Iran nuclear talks" → completely unrelated
- DIFFERENT EVENTS: "Trump threatens bridge closure" and "Colbert interview cancelled" → both involve Trump but different events

ARTICLES:
{articles}

Return ONLY a JSON array of arrays. Each inner array contains article numbers that cover the SAME SPECIFIC EVENT:
[[0, 3, 7], [1, 5], [2], [4, 6], ...]

Every article number must appear exactly once. Singles are fine — not every article has a match.""".format(
        articles="\n".join(lines))

    report.llm_calls += 1
    result = llm_caller.call_by_id("gemini",
        "You group news articles by specific event. Return only JSON. Be precise — same topic is NOT same event.",
        prompt, 2000)
    time.sleep(0.5)

    if not result:
        report.llm_failures += 1
        return [[a] for a in article_list]

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\[.*\]', cleaned, re.DOTALL)
        groups_indices = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        # Convert index groups to article groups
        used = set()
        groups = []
        for idx_group in groups_indices:
            if not isinstance(idx_group, list):
                continue
            articles_in_group = []
            for idx in idx_group:
                if isinstance(idx, int) and 0 <= idx < len(article_list) and idx not in used:
                    articles_in_group.append(article_list[idx])
                    used.add(idx)
            if articles_in_group:
                groups.append(articles_in_group)

        # Catch any articles the LLM missed
        for i, a in enumerate(article_list):
            if i not in used:
                groups.append([a])

        return groups
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        report.llm_failures += 1
        print("    Cluster parse error: {}".format(str(e)[:60]))
        return [[a] for a in article_list]


def _llm_cluster_all(pregroups, report):
    """LLM-cluster all pre-groups, batched by topic similarity."""
    # Flatten singletons and small groups for re-clustering
    # Keep large mechanical groups (3+) as-is — they're likely correct
    confirmed = []
    to_recluster = []

    for group in pregroups:
        if len(group) >= 3:
            # Large mechanical group — likely correct, keep it
            confirmed.append(group)
        else:
            # Single or pair — needs LLM clustering
            to_recluster.extend(group)

    if not to_recluster:
        return confirmed

    print("    LLM clustering {} articles...".format(len(to_recluster)))

    # Batch by primary topic to keep batches coherent and manageable
    topic_batches = {}
    no_topic = []
    for a in to_recluster:
        if a.topics:
            primary = a.topics[0]
            topic_batches.setdefault(primary, []).append(a)
        else:
            no_topic.append(a)

    all_groups = list(confirmed)

    for topic_id, batch in topic_batches.items():
        # Sub-batch if too large (max 25 per LLM call)
        for i in range(0, len(batch), 25):
            sub = batch[i:i+25]
            groups = _llm_cluster_batch(sub, report)
            all_groups.extend(groups)
            time.sleep(0.5)

    # No-topic articles as singletons
    for a in no_topic:
        all_groups.append([a])

    return all_groups


# ── Pass 3: LLM validates multi-source clusters ──────────────────────────

def _llm_validate_clusters(groups, report):
    """Check that multi-source clusters are actually about the same event."""
    multi = [(i, g) for i, g in enumerate(groups) if len(g) >= 2]
    if not multi:
        return groups

    # Only validate clusters that might be wrong (2-5 articles from mixed topics)
    to_validate = []
    for i, g in multi:
        topics = set()
        for a in g:
            topics.update(a.topics[:1])
        # Mixed-topic clusters are suspicious
        if len(topics) > 2 or len(g) >= 4:
            to_validate.append((i, g))

    if not to_validate:
        return groups

    lines = []
    validate_map = {}  # maps line index → (group_index, group)
    for vi, (gi, g) in enumerate(to_validate[:15]):
        articles = "; ".join('"{}" [{}]'.format(a.title[:60], a.source_name) for a in g[:6])
        lines.append("{}: {}".format(vi, articles))
        validate_map[vi] = gi

    prompt = """Check if these article clusters are correct. Each cluster should contain articles about the SAME SPECIFIC EVENT.

CLUSTERS:
{}

For each cluster, answer: are ALL articles about the same specific event?
Return JSON:
{{
  "splits": {{
    "0": [[0, 2], [1, 3]],
    "3": [[0], [1, 2]]
  }},
  "ok": [1, 2, 4]
}}

splits: cluster number → how to split it (sub-arrays of article indices within that cluster)
ok: cluster numbers that are correct

If all clusters are correct: {{"splits": {{}}, "ok": [0, 1, 2, ...]}}""".format(
        "\n".join(lines))

    report.llm_calls += 1
    result = llm_caller.call_by_id("gemini",
        "Validate news clusters. Return JSON only.", prompt, 1500)
    time.sleep(0.5)

    if not result:
        report.llm_failures += 1
        return groups

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        validation = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        splits = validation.get("splits", {})
        if splits:
            split_count = 0
            for vi_str, sub_groups in splits.items():
                vi = int(vi_str)
                if vi not in validate_map:
                    continue
                gi = validate_map[vi]
                original = groups[gi]
                # Replace the original group with splits
                new_groups = []
                used = set()
                for sub in sub_groups:
                    sub_articles = []
                    for idx in sub:
                        if isinstance(idx, int) and 0 <= idx < len(original) and idx not in used:
                            sub_articles.append(original[idx])
                            used.add(idx)
                    if sub_articles:
                        new_groups.append(sub_articles)
                # Catch missed articles
                for idx, a in enumerate(original):
                    if idx not in used:
                        new_groups.append([a])

                # Replace in groups list
                groups[gi] = new_groups[0] if new_groups else original
                groups.extend(new_groups[1:])
                split_count += 1

            if split_count:
                print("    Validation split {} clusters".format(split_count))

    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1

    return groups


# ── Main entry ────────────────────────────────────────────────────────────

def run(articles):
    """Cluster articles by specific event. Returns (clusters, report)."""
    print("\n>>> CLUSTER: {} articles...".format(len(articles)))
    report = StepReport("cluster", items_in=len(articles))

    # Pass 1: mechanical pre-grouping (high threshold, only near-duplicates)
    pregroups = _mechanical_pregroup(articles)
    mechanical_multi = sum(1 for g in pregroups if len(g) > 1)
    print("    Pass 1 (mechanical): {} groups ({} multi-source)".format(
        len(pregroups), mechanical_multi))

    # Pass 2: LLM event-based clustering
    groups = _llm_cluster_all(pregroups, report)
    llm_multi = sum(1 for g in groups if len(g) > 1)
    print("    Pass 2 (LLM cluster): {} groups ({} multi-source)".format(
        len(groups), llm_multi))

    # Pass 3: validate multi-source clusters
    groups = _llm_validate_clusters(groups, report)
    final_multi = sum(1 for g in groups if len(g) > 1)
    print("    Pass 3 (validation): {} groups ({} multi-source)".format(
        len(groups), final_multi))

    # Convert to StoryCluster objects
    clusters = []
    for g in groups:
        lead = g[0]
        all_topics = []
        for a in g:
            for t in a.topics:
                if t not in all_topics:
                    all_topics.append(t)
        clusters.append(StoryCluster(
            articles=g,
            cluster_id=_cluster_id(g),
            lead_title=lead.title,
            topic_spread=all_topics,
        ))

    report.items_out = len(clusters)
    report.notes.append("{} multi-source clusters".format(final_multi))
    print("    Final: {} clusters ({} multi-source)".format(len(clusters), final_multi))
    return clusters, report
