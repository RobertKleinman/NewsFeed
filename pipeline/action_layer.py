"""
Action Layer: top-of-brief action buckets.

Generates concise actions organized into watch / prepare / ignore.
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
        return {"watch": [], "prepare": [], "ignore": []}, report

    top = sorted(topic_cards, key=lambda c: c.heat_score, reverse=True)[:5]
    briefs = []
    for i, card in enumerate(top):
        briefs.append("{i}. {title}\n   What: {whats}\n   Why today: {why_today}\n   Why: {why}".format(
            i=i + 1,
            title=card.title[:80],
            whats=(card.whats_happening or card.what_happened)[:150],
            why_today=(card.why_today or "")[:120],
            why=card.why_matters[:150],
        ))

    prompt = """You're writing action guidance for a busy executive.

TOP STORIES:
{stories}

Return JSON object with exactly these keys: watch, prepare, ignore.
Each key is an array of 1-2 short items (max 18 words each), each tied to a story number.

JSON format:
{{
  "watch": [{{"action": "What to monitor now.", "story": 1}}],
  "prepare": [{{"action": "What to prep if trend continues.", "story": 3}}],
  "ignore": [{{"action": "What not to overreact to yet.", "story": 2}}]
}}

Rules:
- Be concrete and decision-oriented.
- No vague advice like 'stay informed'.
- Keep ignore items cautious, not dismissive.
""".format(stories="\n\n".join(briefs))

    report.llm_calls += 1
    result = llm_caller.call_by_id(
        available[0],
        "Concise executive advisor. Return only JSON object.",
        prompt,
        900,
    )

    if not result:
        report.llm_failures += 1
        return {"watch": [], "prepare": [], "ignore": []}, report

    try:
        cleaned = re.sub(r"```json\s*", "", result)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        actions = json.loads(m.group() if m else cleaned)
        if not isinstance(actions, dict):
            raise ValueError("action payload is not object")

        report.llm_successes += 1
        out = {"watch": [], "prepare": [], "ignore": []}
        for bucket in out.keys():
            items = actions.get(bucket, [])
            if not isinstance(items, list):
                continue
            for a in items[:2]:
                if not isinstance(a, dict):
                    continue
                story_num = a.get("story", 1)
                if not isinstance(story_num, int) or not (1 <= story_num <= len(top)):
                    continue
                card = top[story_num - 1]
                mapped = {
                    "action": str(a.get("action", "")).strip(),
                    "story": story_num,
                    "card_title": card.title[:60],
                }
                if not mapped["action"]:
                    continue
                for idx, tc in enumerate(topic_cards):
                    if tc.title == card.title:
                        mapped["card_index"] = idx
                        break
                out[bucket].append(mapped)

        report.items_out = sum(len(v) for v in out.values())
        return out, report

    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1
        return {"watch": [], "prepare": [], "ignore": []}, report
