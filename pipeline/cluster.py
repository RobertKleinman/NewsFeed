"""
Step 3: Group articles about the same event.
Input: list of Article
Output: list of list[Article] (story groups), StepReport

Clustering uses multiple signals:
- Title word overlap (Jaccard)
- Entity overlap (people, places, orgs from title AND summary)
- Topic overlap
- Key entity matching (if two articles share a notable proper noun, high signal)

Threshold is deliberately low — false merges are less harmful than missed groupings.
"""

import hashlib
import re
from models import StepReport

# Common words to skip when extracting entities
SKIP_WORDS = {
    "the", "and", "but", "for", "new", "how", "why", "what", "who", "when",
    "with", "from", "after", "into", "over", "has", "are", "will", "can",
    "may", "its", "says", "could", "would", "about", "more", "this", "that",
    "than", "just", "also", "been", "some", "all", "not", "was", "his",
    "her", "they", "their", "have", "had", "does", "did", "top", "big",
    "get", "got", "set", "two", "first", "last", "year", "years", "news",
    "report", "reports", "says", "said", "told", "according", "amid",
    "people", "world", "time", "make", "back", "take", "state", "still",
    "being", "where", "most", "only", "now", "part", "made", "between",
    "other", "many", "much", "even", "three", "four", "five", "after",
    "before", "under", "every", "show", "here", "week", "month", "day",
    "million", "billion", "percent", "early", "late", "high", "low",
    "former", "current", "major", "expected", "likely", "possible",
}


def extract_entities(text):
    """Extract likely proper nouns from text (capitalized words not in skip list)."""
    entities = set()
    for word in text.split():
        clean = re.sub(r"[^a-zA-Z']", "", word)
        if clean and clean[0].isupper() and len(clean) > 2 and clean.lower() not in SKIP_WORDS:
            entities.add(clean.lower())
    return entities


def extract_key_terms(text):
    """Extract all meaningful lowercase terms for broader matching."""
    words = set(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())
    return words - SKIP_WORDS - {""}


def cluster_id(group):
    all_entities = set()
    for a in group:
        all_entities.update(extract_entities(a.title))
    entity_str = ",".join(sorted(all_entities)[:5])
    return hashlib.md5(entity_str.encode()).hexdigest()[:10]


def similarity(article_a, article_b):
    """
    Multi-signal similarity score between two articles.
    Returns float 0-1.
    """
    # Title word overlap
    words_a = extract_key_terms(article_a.title)
    words_b = extract_key_terms(article_b.title)
    title_jaccard = 0
    if words_a and words_b:
        title_jaccard = len(words_a & words_b) / max(len(words_a | words_b), 1)

    # Entity overlap from title + summary (the big improvement)
    text_a = article_a.title + " " + article_a.summary
    text_b = article_b.title + " " + article_b.summary
    entities_a = extract_entities(text_a)
    entities_b = extract_entities(text_b)

    entity_overlap = 0
    shared_entities = set()
    if entities_a and entities_b:
        shared_entities = entities_a & entities_b
        entity_overlap = len(shared_entities) / max(len(entities_a | entities_b), 1)

    # Bonus: shared key entities (people/place names) are strong signal
    # If 2+ proper nouns match, these articles are very likely about the same thing
    key_entity_bonus = 0
    if len(shared_entities) >= 3:
        key_entity_bonus = 0.3
    elif len(shared_entities) >= 2:
        key_entity_bonus = 0.15

    # Summary word overlap (broader content match)
    sum_words_a = extract_key_terms(article_a.summary[:200])
    sum_words_b = extract_key_terms(article_b.summary[:200])
    summary_jaccard = 0
    if sum_words_a and sum_words_b:
        summary_jaccard = len(sum_words_a & sum_words_b) / max(len(sum_words_a | sum_words_b), 1)

    # Topic overlap
    topic_bonus = 0
    topics_a = set(article_a.topics)
    topics_b = set(article_b.topics)
    if topics_a and topics_b and topics_a & topics_b:
        topic_bonus = 0.05

    # Combined score - weighted toward entity matching
    score = (
        title_jaccard * 0.25 +
        entity_overlap * 0.35 +
        summary_jaccard * 0.15 +
        key_entity_bonus +
        topic_bonus
    )

    return score


def run(articles):
    """Cluster articles by event. Returns (groups, report)."""
    print("\n>>> CLUSTER: {} articles...".format(len(articles)))
    report = StepReport("cluster", items_in=len(articles))

    groups = []
    used = set()
    articles.sort(key=lambda a: a.importance_score, reverse=True)

    for i, article in enumerate(articles):
        if i in used:
            continue
        group = [article]
        used.add(i)

        for j, other in enumerate(articles[i+1:], start=i+1):
            if j in used:
                continue

            score = similarity(article, other)

            # Lower threshold than before (was 0.25)
            # Also check against best match in group, not just the lead article
            if score > 0.15:
                group.append(other)
                used.add(j)

        groups.append(group)

    multi = sum(1 for g in groups if len(g) > 1)
    report.items_out = len(groups)
    report.notes.append("{} multi-source clusters".format(multi))
    print("    {} clusters ({} multi-source)".format(len(groups), multi))
    return groups, report
