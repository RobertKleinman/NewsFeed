"""
Step 4: Select top stories via multi-LLM voting + topic diversity enforcement.
Input: list of story groups, topics dict, max_stories
Output: list of story groups (selected), StepReport
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(story_groups, topics, max_stories=12):
    """Multi-model voting with topic minimums. Returns (selected, report)."""
    print("\n>>> SELECT: voting on {} candidates...".format(min(len(story_groups), 50)))
    report = StepReport("select", items_in=len(story_groups))

    summaries = []
    for i, group in enumerate(story_groups[:50]):
        lead = group[0]
        sources = ", ".join(set(a.source_name for a in group))
        topic_str = ", ".join(lead.topics[:2])
        summaries.append("{}. [{}] [{}] {} ({} sources)".format(
            i, topic_str, sources, lead.title, len(group)))

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

    for llm_id in llm_caller.get_available_llms()[:3]:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        print("    {} voting...".format(config["label"]))
        result = llm_caller.call_by_id(llm_id,
            "You are a concise news editor. Return only a JSON array.", prompt, 200)
        time.sleep(3)
        if result:
            try:
                match = re.search(r'\[[\d,\s]+\]', result)
                if match:
                    indices = json.loads(match.group())
                    voters += 1
                    report.llm_successes += 1
                    for idx in indices:
                        if idx < len(story_groups):
                            vote_counts[idx] = vote_counts.get(idx, 0) + 1
                    print("      picked {} stories".format(len(indices)))
            except Exception:
                report.llm_failures += 1
        else:
            report.llm_failures += 1

    if not vote_counts:
        print("    No votes received, using keyword ranking")
        selected = story_groups[:max_stories]
        report.items_out = len(selected)
        return selected, report

    sorted_cands = sorted(vote_counts.items(), key=lambda x: (-x[1], x[0]))

    # First pass: ensure topic diversity
    selected = []
    topics_covered = set()
    for idx, votes in sorted_cands:
        group = story_groups[idx]
        lead = group[0]
        new_topics = set(lead.topics) - topics_covered
        if new_topics and len(selected) < max_stories:
            selected.append(group)
            topics_covered.update(lead.topics)

    # Second pass: fill by votes
    for idx, votes in sorted_cands:
        group = story_groups[idx]
        if group not in selected and len(selected) < max_stories:
            selected.append(group)

    report.items_out = len(selected)
    report.notes.append("{} topics covered by {} voters".format(
        len(topics_covered), voters))
    print("    {} stories selected, {} topics covered".format(
        len(selected), len(topics_covered)))
    return selected, report
