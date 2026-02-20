"""
Step 1b: Syndication Detection — identify wire republication.

Detects when multiple outlets are republishing the same wire story
(AP, Reuters, AFP). Tags each article with:
  - wire_origin: the likely originating wire service (or None)
  - is_independent: whether this is original reporting

This prevents inflated source counts from creating false consensus.
No LLM calls — purely mechanical similarity detection.
"""

from collections import defaultdict
from models import StepReport


# Known wire services and syndication networks
WIRE_SERVICES = {
    "Associated Press", "AP", "AP News",
    "Reuters", "Thomson Reuters",
    "AFP", "Agence France-Presse", "Agence France Presse",
    "PA Media", "Press Association",
    "EFE", "Xinhua", "TASS", "Anadolu Agency",
    "UPI", "United Press International",
}

# Phrases that signal wire origin in text
WIRE_SIGNALS = [
    "(AP)", "(Reuters)", "(AFP)", "— AP", "— Reuters",
    "— AFP", "(PA)", "Associated Press", "Reuters reported",
]


def _normalize_text(text):
    """Normalize text for comparison: lowercase, strip punctuation."""
    if not text:
        return ""
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _word_set(text):
    """Get set of meaningful words (5+ chars) from text."""
    return set(w for w in _normalize_text(text).split() if len(w) >= 5)


def _jaccard(set_a, set_b):
    """Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def run(articles):
    """Detect syndication and tag articles. Returns (tagged_articles, report)."""
    print("\n>>> SYNDICATION DETECTION: {} articles...".format(len(articles)))
    report = StepReport("syndication", items_in=len(articles))

    # Phase 1: Tag articles from known wire services
    for article in articles:
        article.wire_origin = None
        article.is_independent = True

        # Check if source IS a wire service
        if article.source_name in WIRE_SERVICES:
            article.wire_origin = article.source_name
            article.is_independent = True  # Wire originals are independent
            continue

        # Check for wire signals in summary text
        for signal in WIRE_SIGNALS:
            if signal.lower() in (article.summary or "").lower():
                article.wire_origin = signal.strip("()— ").split(" ")[0]
                article.is_independent = False
                break

    # Phase 2: Content similarity clustering to detect unlabeled republication
    # Group articles by title+summary similarity
    text_features = []
    for article in articles:
        combined = (article.title + " " + article.summary[:200])
        text_features.append(_word_set(combined))

    # Find groups of near-identical articles (Jaccard > 0.7)
    syndication_groups = []
    assigned = set()

    for i in range(len(articles)):
        if i in assigned:
            continue
        group = [i]
        for j in range(i + 1, len(articles)):
            if j in assigned:
                continue
            sim = _jaccard(text_features[i], text_features[j])
            if sim > 0.7:
                group.append(j)
                assigned.add(j)

        if len(group) >= 3:  # 3+ near-identical = likely syndication
            syndication_groups.append(group)
            assigned.update(group)

    # Phase 3: Within each syndication group, identify the original
    wire_tagged = 0
    for group in syndication_groups:
        group_articles = [articles[i] for i in group]

        # The original is: a wire service, OR the source with the longest summary,
        # OR the earliest published article
        original = None
        for a in group_articles:
            if a.source_name in WIRE_SERVICES:
                original = a
                break

        if not original:
            # Pick the one with longest summary (likely most original content)
            original = max(group_articles, key=lambda a: len(a.summary or ""))

        wire_name = original.wire_origin or original.source_name

        # Tag all non-original articles in the group
        for a in group_articles:
            if a is not original:
                if not a.wire_origin:  # Don't overwrite explicit wire tags
                    a.wire_origin = wire_name
                a.is_independent = False
                wire_tagged += 1

    # Count results
    independent = sum(1 for a in articles if a.is_independent)
    republished = sum(1 for a in articles if not a.is_independent)

    report.items_out = len(articles)
    report.notes.append("{} independent, {} republished, {} syndication groups".format(
        independent, republished, len(syndication_groups)))
    print("    {} independent, {} wire/republished ({} syndication groups)".format(
        independent, republished, len(syndication_groups)))

    return articles, report
