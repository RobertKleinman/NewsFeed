"""
Step 3: Group articles about the same event.
Input: list of Article
Output: list of list[Article] (story groups), StepReport

Clustering uses title word overlap (Jaccard) + entity overlap.
Each group = one event covered by one or more sources.
"""

import hashlib
import re
from models import StepReport


def extract_entities(text):
    skip = {"The", "And", "But", "For", "New", "How", "Why", "What", "Who",
            "With", "From", "After", "Into", "Over", "Has", "Are", "Will",
            "Can", "May", "Its", "Says", "Could", "Would", "About", "More",
            "This", "That", "Than", "Just", "Also", "Been", "Some", "All",
            "Not", "Was", "His", "Her", "They", "Their", "Have", "Had",
            "Does", "Did", "Top", "Big", "Get", "Got", "Set", "Two"}
    entities = set()
    for word in text.split():
        clean = re.sub(r"[^a-zA-Z]", "", word)
        if clean and clean[0].isupper() and len(clean) > 2 and clean not in skip:
            entities.add(clean.lower())
    return entities


def cluster_id(group):
    """Generate a stable ID for a cluster based on shared entities + date."""
    all_entities = set()
    for a in group:
        all_entities.update(extract_entities(a.title))
    entity_str = ",".join(sorted(all_entities)[:5])
    return hashlib.md5(entity_str.encode()).hexdigest()[:10]


def run(articles):
    """Cluster articles by event. Returns (groups, report)."""
    print("\n>>> CLUSTER: {} articles...".format(len(articles)))
    report = StepReport("cluster", items_in=len(articles))

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
            entity_ov = 0
            if entities_i and entities_j:
                entity_ov = len(entities_i & entities_j) / max(len(entities_i | entities_j), 1)

            score = jaccard * 0.6 + entity_ov * 0.4
            if score > 0.25:
                group.append(other)
                used.add(j)

        groups.append(group)

    multi = sum(1 for g in groups if len(g) > 1)
    report.items_out = len(groups)
    report.notes.append("{} multi-source clusters".format(multi))
    print("    {} clusters ({} multi-source)".format(len(groups), multi))
    return groups, report
