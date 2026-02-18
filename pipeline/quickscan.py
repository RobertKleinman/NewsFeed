"""
Quickscan: "Today in 60 Seconds" — scannable overview of all stories.
"""

import json
import re

import llm as llm_caller
from config import TOPICS
from models import StepReport


def run(topic_cards):
    """Generate quickscan overview. Returns (data, report)."""
    print("\n>>> QUICKSCAN...")
    report = StepReport("quickscan", items_in=len(topic_cards))

    # Sort by heat score for ranking, preserve original index
    for i, card in enumerate(topic_cards):
        card._original_index = i
    ranked = sorted(topic_cards, key=lambda c: c.heat_score, reverse=True)

    briefs = []
    for i, card in enumerate(ranked[:12]):
        sources = ", ".join(s["name"] for s in card.sources[:3])
        tier = card.depth_tier.upper()
        briefs.append("{i}. [{stars}★ {tier}] {t}\n   What: {w}\n   So what: {sw}".format(
            i=i+1, stars=card.importance, tier=tier,
            t=card.title[:100],
            w=card.what_happened[:120],
            sw=card.so_what[:120]))

    prompt = """Write a quick-scan briefing. Return ONLY valid JSON.

STORIES:
{b}

JSON:
{{
  "key_tensions": [
    {{"tension": "Who disagrees about what.", "type": "data OR framing"}}
  ],
  "watch_list": [
    {{"item": "What to watch.", "time_horizon": "imminent OR this_week OR developing"}}
  ],
  "top_stories": [
    {{
      "rank": 1,
      "headline": "Full headline",
      "one_liner": "One sentence: what happened and why it matters.",
      "consensus": "consensus OR split OR contested"
    }}
  ]
}}

Rules: 3-4 key_tensions, 3-4 watch_list, all stories in top_stories.
Complete sentences only.""".format(b="\n\n".join(briefs))

    available = llm_caller.get_available_llms()
    if not available:
        return _fallback(ranked), report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Return valid JSON only.", prompt, 4000)

    if not result:
        report.llm_failures += 1
        return _fallback(ranked), report

    qs = _parse(result, ranked)
    if qs:
        report.llm_successes += 1
        report.items_out = len(qs.get("top_stories", []))
    else:
        report.llm_failures += 1
        qs = _fallback(ranked)

    # Map indices to original card positions
    for i, s in enumerate(qs.get("top_stories", [])):
        if i < len(ranked):
            s["card_index"] = ranked[i]._original_index
            s["topic"] = ranked[i].topics[0] if ranked[i].topics else "general"
            s["importance"] = ranked[i].importance
        else:
            s["card_index"] = i
            s["topic"] = "general"
            s["importance"] = 3

    return qs, report


def _parse(result, cards):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        for key in ["top_stories", "key_tensions", "watch_list"]:
            if key not in data:
                data[key] = []
        return data
    except Exception as e:
        print("    QS parse error: {}".format(str(e)[:60]))
        return None


def _fallback(ranked):
    stories = []
    for i, c in enumerate(ranked[:12]):
        stories.append({
            "rank": i+1,
            "headline": c.title[:80],
            "one_liner": c.what_happened[:150] if c.what_happened else "See full analysis.",
            "consensus": "split",
            "card_index": getattr(c, '_original_index', i),
            "topic": c.topics[0] if c.topics else "general",
            "importance": c.importance,
        })
    return {"top_stories": stories, "key_tensions": [], "watch_list": []}
