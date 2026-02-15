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
    print("\n>>> SELECT: voting on {} candidates...".format(min(len(story_groups), 50)))
    report = StepReport("select", items_in=len(story_groups))

    summaries = []
    for i, group in enumerate(story_groups[:50]):
        lead = group[0]
        source_details = []
        for a in group[:5]:
            source_details.append("{} ({})".format(a.source_name, a.source_region))
        sources = ", ".join(source_details)
        topic_str = ", ".join(lead.topics[:2])
        summaries.append("{}. [{}] {} ({} sources: {})".format(
            i, topic_str, lead.title, len(group), sources))

    stories_list = "\n".join(summaries)
    prompt = """You are a news editor selecting stories for a global intelligence briefing.
Pick 15-20 of the most important stories. The reader cares about: world politics,
Canadian politics, US politics, economics/business, AI/technology, Canadian insurance,
data privacy/AI governance, and culture/good news.

Selection criteria IN ORDER OF PRIORITY:
1. IMPORTANCE: Genuine significance and real-world impact comes first. A major story
   covered by only 2 sources beats a minor story covered by 10.
2. TOPIC DIVERSITY: Ensure coverage across different topic areas, not just politics.
3. SOURCE DIVERSITY: When two stories are equally important, prefer the one with
   coverage from more diverse regions/perspectives.
4. Include at least 1-2 uplifting/cultural stories.

Return ONLY a JSON array of story numbers, e.g. [0, 3, 5, 12, ...]

Stories:
""" + stories_list

    vote_counts = {}
    voters = 0

    available_voters = llm_caller.get_available_llms()[:3]
    print("    Voters: {}".format(", ".join(LLM_CONFIGS[k]["label"] for k in available_voters)))

    for llm_id in available_voters:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        print("    {} voting...".format(config["label"]))
        result = llm_caller.call_by_id(llm_id,
            "You are a concise news editor. Return only a JSON array.", prompt, 200)
        time.sleep(1)
        if result:
            try:
                # Try multiple parsing strategies
                parsed = None
                # Strategy 1: exact array match
                match = re.search(r'\[[\d,\s]+\]', result)
                if match:
                    parsed = json.loads(match.group())
                # Strategy 2: strip markdown and try again
                if not parsed:
                    cleaned = result.replace('```json', '').replace('```', '').strip()
                    match = re.search(r'\[[\d,\s]+\]', cleaned)
                    if match:
                        parsed = json.loads(match.group())
                # Strategy 3: extract all numbers if response looks like a list
                if not parsed:
                    nums = re.findall(r'\b(\d{1,2})\b', result)
                    if len(nums) >= 5:
                        parsed = [int(n) for n in nums]

                if parsed:
                    voters += 1
                    report.llm_successes += 1
                    for idx in parsed:
                        if idx < len(story_groups):
                            vote_counts[idx] = vote_counts.get(idx, 0) + 1
                    print("      {} picked {} stories".format(config["label"], len(parsed)))
                else:
                    report.llm_failures += 1
                    print("      {} not parseable: {}".format(config["label"], result[:80]))
            except Exception as e:
                report.llm_failures += 1
                print("      {} parse error: {}".format(config["label"], str(e)[:60]))
        else:
            report.llm_failures += 1
            print("      {} returned nothing".format(config["label"]))

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
