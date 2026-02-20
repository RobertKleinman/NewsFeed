"""
Action Layer: "If you only do 1 thing today..."

Generates 3 concise action items for the top of the briefing.
Each references a specific story and gives a concrete recommendation.
Runs after quickscan, reads top cards.
"""

import json
import re

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """Generate action items. Returns (action_data, report)."""
    print("\n>>> ACTION LAYER...")
    report = StepReport("action_layer", items_in=len(topic_cards))

    available = llm_caller.get_available_llms()
    if not available or len(topic_cards) < 2:
        return [], report

    # Use top 5 cards by importance
    top = sorted(topic_cards, key=lambda c: c.heat_score, reverse=True)[:5]
    briefs = []
    for i, card in enumerate(top):
        briefs.append("{i}. {title}\n   What: {whats}\n   Why: {why}".format(
            i=i+1, title=card.title[:80],
            whats=(card.whats_happening or card.what_happened)[:150],
            why=card.why_matters[:150]))

    prompt = """You're writing the "If you only do 1 thing today" section for a busy executive.

TOP STORIES:
{stories}

Generate exactly 3 action items. Each must be:
- ONE sentence, max 20 words
- A CONCRETE action: read, watch, prepare for, tell your team about, check whether...
- Tied to a specific story (by number)

Return JSON array:
[
  {{"action": "Brief concrete action sentence.", "story": 1}},
  {{"action": "Another concrete action.", "story": 3}},
  {{"action": "Third action.", "story": 2}}
]

NOT acceptable: vague advice like "stay informed" or "monitor developments."
GOOD examples: "Check if your portfolio has Iran exposure before markets open."
"Brief your team on the new EPA ruling's compliance implications." """.format(
        stories="\n\n".join(briefs))

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Concise executive advisor. Return only JSON array.",
        prompt, 800)

    if not result:
        report.llm_failures += 1
        return [], report

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\[.*\]', cleaned, re.DOTALL)
        actions = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        # Map story numbers to card indices
        for a in actions[:3]:
            story_num = a.get("story", 1)
            if 1 <= story_num <= len(top):
                card = top[story_num - 1]
                a["card_title"] = card.title[:60]
                # Find original index
                for idx, tc in enumerate(topic_cards):
                    if tc.title == card.title:
                        a["card_index"] = idx
                        break

        report.items_out = min(len(actions), 3)
        return actions[:3], report

    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1
        return [], report
