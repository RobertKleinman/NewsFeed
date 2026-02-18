"""
Quickscan: "Today in 60 Seconds" — scannable overview.
Each story gets: headline, one-liner summary, and why-it-matters.
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

    for i, card in enumerate(topic_cards):
        card._original_index = i
    ranked = sorted(topic_cards, key=lambda c: c.heat_score, reverse=True)

    # Build briefs with full context so LLM doesn't truncate
    briefs = []
    for i, card in enumerate(ranked[:15]):
        briefs.append("{i}. [{stars}★] {t}\n   What: {w}\n   Why: {sw}".format(
            i=i+1, stars=card.importance,
            t=card.title,
            w=card.what_happened[:200],
            sw=card.so_what[:200]))

    prompt = """Write a quick-scan for an intelligence briefing. Return ONLY valid JSON.

STORIES:
{b}

JSON structure:
{{
  "key_tensions": [
    {{"tension": "One sentence: who disagrees about what.", "type": "data OR framing"}}
  ],
  "watch_list": [
    {{"item": "What to watch and why.", "time_horizon": "imminent OR this_week OR developing"}}
  ],
  "top_stories": [
    {{
      "rank": 1,
      "headline": "FULL headline — never truncate, use the complete title",
      "one_liner": "One COMPLETE sentence: what happened.",
      "why_care": "One COMPLETE sentence: why this matters to the reader."
    }}
  ]
}}

CRITICAL RULES:
- EVERY field must be a COMPLETE sentence ending with a period. NEVER truncate.
- headline: use the FULL story title. Do not shorten.
- one_liner: complete sentence explaining what happened.
- why_care: complete sentence explaining why the reader should care about this.
- 3-4 key_tensions, 3-4 watch_list, ALL stories in top_stories.
- If a sentence would be too long, make it shorter but COMPLETE.""".format(
        b="\n\n".join(briefs))

    available = llm_caller.get_available_llms()
    if not available:
        return _fallback(ranked), report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Return valid JSON only. Every sentence must be complete — ending with a period.",
        prompt, 5000)

    if not result:
        report.llm_failures += 1
        return _fallback(ranked), report

    qs = _parse(result)
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
            s["card_mode"] = ranked[i].card_mode
        else:
            s["card_index"] = i
            s["topic"] = "general"
            s["importance"] = 3
            s["card_mode"] = "straight_news"

    return qs, report


def _parse(result):
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
    for i, c in enumerate(ranked[:15]):
        stories.append({
            "rank": i+1,
            "headline": c.title,
            "one_liner": c.what_happened[:200] if c.what_happened else "See full card.",
            "why_care": c.so_what[:200] if c.so_what else "",
            "card_index": getattr(c, '_original_index', i),
            "topic": c.topics[0] if c.topics else "general",
            "importance": c.importance,
            "card_mode": c.card_mode,
        })
    return {"top_stories": stories, "key_tensions": [], "watch_list": []}
