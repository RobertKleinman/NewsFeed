"""
Step 2: Triage — classify articles by topic using LLM (batched).
Replaces keyword matching with LLM understanding.
Batch size ~20 articles per call for cost efficiency.
"""

import json
import re
import time

import llm as llm_caller
from config import TOPICS
from models import StepReport

BATCH_SIZE = 20


def run(articles, topics):
    """Classify articles by topic using batched LLM calls. Returns (relevant, report)."""
    print("\n>>> TRIAGE: {} articles...".format(len(articles)))
    report = StepReport("triage", items_in=len(articles))

    topic_list = "\n".join(
        "- {}: {}".format(tid, info["name"])
        for tid, info in topics.items()
    )

    # Process in batches
    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start:batch_start + BATCH_SIZE]
        _classify_batch(batch, topic_list, report)
        time.sleep(0.5)

    # Filter: keep articles with at least one topic and relevance > 0
    relevant = [a for a in articles if a.topics and a.relevance_score > 0]

    report.items_out = len(relevant)
    print("    {} relevant ({} filtered out)".format(
        len(relevant), len(articles) - len(relevant)))
    return relevant, report


def _classify_batch(batch, topic_list, report):
    """Classify a batch of articles with one LLM call."""
    article_lines = []
    for i, a in enumerate(batch):
        article_lines.append("{}: [{}] {} — {}".format(
            i, a.source_name, a.title, a.summary[:150]))

    prompt = """Classify each article into one or more topics. Rate relevance 0-10.
0 = not relevant to any topic. 10 = critically important.

TOPICS:
{topics}

ARTICLES:
{articles}

Return ONLY a JSON array. One entry per article, same order:
[
  {{"id": 0, "topics": ["world_politics", "economics_business"], "relevance": 7}},
  {{"id": 1, "topics": [], "relevance": 0}},
  ...
]

Rules:
- An article can match 0, 1, or multiple topics
- Be generous with matching — if an article touches a topic, include it
- Relevance reflects importance and newsworthiness, not just topic match
- Soft news, PR, listicles, and how-to articles get low relevance (1-3)
- Breaking news, policy changes, major events get high relevance (7-10)""".format(
        topics=topic_list,
        articles="\n".join(article_lines))

    report.llm_calls += 1
    result = llm_caller.call_by_id("gemini",
        "You classify news articles. Return only JSON. Be accurate.",
        prompt, 2000)

    if not result:
        report.llm_failures += 1
        # Fallback: mark all as general with low relevance
        for a in batch:
            a.topics = []
            a.relevance_score = 0
        return

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\[.*\]', cleaned, re.DOTALL)
        classifications = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        for entry in classifications:
            idx = entry.get("id", -1)
            if 0 <= idx < len(batch):
                topics_matched = entry.get("topics", [])
                # Validate topic IDs
                valid_topics = [t for t in topics_matched if t in TOPICS]
                batch[idx].topics = valid_topics
                batch[idx].relevance_score = float(entry.get("relevance", 0)) / 10.0
    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1
        # On parse failure, leave batch unclassified
        for a in batch:
            a.topics = []
            a.relevance_score = 0
