"""
Step 2: Classify articles by topic using keyword matching.
Input: list of Article, topics dict
Output: list of Article (with topics and scores set), StepReport
"""

from models import StepReport


def run(articles, topics):
    """Triage articles by keyword match. Returns (relevant_articles, report)."""
    print("\n>>> TRIAGE: {} articles...".format(len(articles)))
    report = StepReport("triage", items_in=len(articles))

    for article in articles:
        text = "{} {}".format(article.title, article.summary).lower()
        matched = []
        for topic_id, info in topics.items():
            score = sum(1 for kw in info["keywords"] if kw.lower() in text)
            if score >= 1:
                matched.append((topic_id, score))
        matched.sort(key=lambda x: x[1], reverse=True)
        article.topics = [t[0] for t in matched]
        article.importance_score = min(
            len(matched) * 0.3 + (matched[0][1] * 0.2 if matched else 0), 1.0
        )

    relevant = [a for a in articles if a.topics]
    report.items_out = len(relevant)
    print("    {} relevant ({} filtered out)".format(
        len(relevant), len(articles) - len(relevant)))
    return relevant, report
