"""
Step 4: Select stories by importance with materiality cutoff.
LLMs rate importance 1-10 (not just pick/skip).
Diversity is a soft nudge on ordering, not a hard gate.
Stories below materiality threshold are dropped.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS, TOPICS, MATERIALITY_CUTOFF, MAX_STORIES
from models import RankedStory, StepReport


def run(clusters, topics):
    """Select and rank stories. Returns (ranked_stories, report)."""
    # Only consider clusters worth evaluating (2+ articles or high relevance)
    candidates = []
    for c in clusters:
        if c.size >= 2 or (c.lead and c.lead.relevance_score >= 0.6):
            candidates.append(c)

    candidates.sort(key=lambda c: c.size, reverse=True)
    candidates = candidates[:50]  # Cap for LLM prompt size

    print("\n>>> SELECT: rating {} candidates...".format(len(candidates)))
    report = StepReport("select", items_in=len(candidates))

    # Build candidate list for LLMs
    summaries = []
    for i, c in enumerate(candidates):
        lead = c.lead
        source_list = ", ".join(c.source_names()[:5])
        topic_str = ", ".join(c.topic_spread[:2])
        regions = ", ".join(c.unique_regions()[:3])
        summaries.append("{}. [{}] {} ({} sources from {}: {})".format(
            i, topic_str, lead.title, c.size, regions, source_list))

    stories_text = "\n".join(summaries)

    prompt = """Rate each story's importance for a global intelligence briefing on a 1-10 scale.

The reader cares about: {topic_names}

Rating criteria:
- 9-10: Major global event, affects millions, breaking news
- 7-8: Significant development, policy change, important trend
- 5-6: Noteworthy news, relevant to briefing audience
- 3-4: Minor development, limited impact
- 1-2: Trivial, local interest only, not briefing-worthy

Consider: real-world impact, number of people affected, novelty, geopolitical weight.
More sources covering a story suggests importance but isn't the only factor.

STORIES:
{stories}

Return ONLY a JSON array, one entry per story:
[
  {{"id": 0, "importance": 8, "reason": "Major trade policy shift affecting global markets"}},
  {{"id": 1, "importance": 3, "reason": "Local event with limited broader impact"}},
  ...
]""".format(
        topic_names=", ".join(info["name"] for info in topics.values()),
        stories=stories_text)

    # Collect ratings from multiple LLMs
    all_ratings = {}  # id → [list of scores]
    all_reasons = {}  # id → [list of reasons]
    voters = 0

    available_voters = [k for k in llm_caller.get_available_llms() if k != "gemini_pro"][:3]
    print("    Voters: {}".format(", ".join(LLM_CONFIGS[k]["label"] for k in available_voters)))

    for llm_id in available_voters:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        print("    {} rating...".format(config["label"]))
        result = llm_caller.call_by_id(llm_id,
            "You rate news importance. Return only JSON array.", prompt, 3000)
        time.sleep(1)

        if not result:
            report.llm_failures += 1
            continue

        try:
            cleaned = re.sub(r'```json\s*', '', result)
            cleaned = re.sub(r'```\s*', '', cleaned).strip()
            m = re.search(r'\[.*\]', cleaned, re.DOTALL)
            ratings = json.loads(m.group() if m else cleaned)
            report.llm_successes += 1
            voters += 1

            for entry in ratings:
                idx = entry.get("id", -1)
                score = float(entry.get("importance", 0))
                reason = entry.get("reason", "")
                if 0 <= idx < len(candidates):
                    all_ratings.setdefault(idx, []).append(score)
                    all_reasons.setdefault(idx, []).append(reason)

            print("      {} rated {} stories".format(config["label"], len(ratings)))
        except (json.JSONDecodeError, ValueError, AttributeError):
            report.llm_failures += 1
            print("      {} parse failed".format(config["label"]))

    if not all_ratings:
        print("    No ratings received, using cluster size as proxy")
        ranked = []
        for c in candidates[:MAX_STORIES]:
            ranked.append(RankedStory(
                cluster=c,
                importance_score=min(c.size, 10),
                vote_count=0,
                importance_reason="Fallback: {} sources".format(c.size),
            ))
        report.items_out = len(ranked)
        return _assign_tiers(ranked), report

    # Average ratings and apply materiality cutoff
    ranked = []
    for idx, scores in all_ratings.items():
        avg = sum(scores) / len(scores)
        reasons = all_reasons.get(idx, [])
        # Pick the most informative reason (longest)
        best_reason = max(reasons, key=len) if reasons else ""

        if avg >= MATERIALITY_CUTOFF:
            ranked.append(RankedStory(
                cluster=candidates[idx],
                importance_score=avg,
                vote_count=len(scores),
                importance_reason=best_reason,
            ))

    # Sort by importance (primary) then source count (tiebreaker)
    ranked.sort(key=lambda r: (r.importance_score, r.cluster.size), reverse=True)

    # Soft diversity nudge: if top stories are all same topic, promote variety
    ranked = _soft_diversity(ranked, topics)

    # Safety cap
    ranked = ranked[:MAX_STORIES]

    dropped = len(all_ratings) - len(ranked)
    report.items_out = len(ranked)
    report.notes.append("{} stories above cutoff, {} dropped, {} voters".format(
        len(ranked), dropped, voters))
    print("    {} stories selected ({} below materiality cutoff)".format(
        len(ranked), dropped))

    return _assign_tiers(ranked), report


def _soft_diversity(ranked, topics):
    """Nudge ordering to avoid topic monoculture, without overriding importance."""
    if len(ranked) <= 5:
        return ranked

    # Check if top 5 are dominated by one topic
    top_topics = []
    for r in ranked[:5]:
        top_topics.extend(r.cluster.topic_spread[:1])

    from collections import Counter
    topic_counts = Counter(top_topics)
    dominant = topic_counts.most_common(1)[0] if topic_counts else None

    if dominant and dominant[1] >= 4:
        # Too many of one topic in top 5 — find a different-topic story to promote
        promoted = None
        for i, r in enumerate(ranked[5:], start=5):
            if r.cluster.topic_spread and r.cluster.topic_spread[0] != dominant[0]:
                if r.importance_score >= ranked[4].importance_score * 0.8:
                    promoted = ranked.pop(i)
                    ranked.insert(4, promoted)
                    break

    return ranked


def _assign_tiers(ranked):
    """Assign depth tiers based on importance stars and source count."""
    from config import DEPTH_THRESHOLDS
    for r in ranked:
        stars = r.stars
        source_count = r.cluster.size

        # Single-source stories can't meaningfully compare perspectives
        # Cap them at standard tier max (no investigation)
        if source_count <= 1:
            r.depth_tier = "brief"
        elif source_count <= 2:
            # Two sources — standard at most
            if stars >= DEPTH_THRESHOLDS["standard"]:
                r.depth_tier = "standard"
            else:
                r.depth_tier = "brief"
        else:
            # 3+ sources — full tier based on importance
            if stars >= DEPTH_THRESHOLDS["deep"]:
                r.depth_tier = "deep"
            elif stars >= DEPTH_THRESHOLDS["standard"]:
                r.depth_tier = "standard"
            else:
                r.depth_tier = "brief"
    return ranked
