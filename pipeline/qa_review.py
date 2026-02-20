"""
Step 9d: Semantic QA Review — LLM-based quality check on written cards.

Catches errors that mechanical validation can't see:
  - TL;DR contradicts Bigger Picture
  - Spin section cites positions not supported by sources
  - Claims stated as verified that shouldn't be
  - Overclaiming (stating speculation as fact)
  - Inconsistency between card fields

Runs after write, before publish. 1 LLM call per card.
Cards receive qa_warnings list — publish renders them if present.
"""

import json
import re

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """QA review each card. Adds qa_warnings to cards. Returns report."""
    print("\n>>> QA REVIEW: checking {} cards...".format(len(topic_cards)))
    report = StepReport("qa_review", items_in=len(topic_cards))

    available = llm_caller.get_available_llms()
    if not available:
        report.items_out = len(topic_cards)
        return report

    # Use a different model than the writer when possible
    preferred = ["claude", "chatgpt", "gemini_pro", "gemini", "grok"]
    reviewer_id = next((p for p in preferred if p in available), available[0])

    total_warnings = 0

    for card in topic_cards:
        # Skip brief cards — not enough content to meaningfully QA
        if card.depth_tier == "brief":
            continue

        d = card.to_dict()
        card_text = """TITLE: {title}
TL;DR (from why_matters): {why}
WHAT'S HAPPENING: {whats}
KEY FACTS: {facts}
BIGGER PICTURE: {bigger}
CONTESTED: {contested}
SPIN POSITIONS: {spin}
WRITTEN BY: {writer}""".format(
            title=d.get("title", ""),
            why=d.get("why_matters", "")[:300],
            whats=d.get("whats_happening", "")[:300],
            facts=json.dumps(d.get("key_facts", [])[:5]),
            bigger=d.get("bigger_picture", "")[:300],
            contested=d.get("card_mode", "straight_news"),
            spin=json.dumps(d.get("spin_positions", [])[:3], default=str)[:500],
            writer=d.get("written_by", "unknown"))

        prompt = """You are an INTERNAL CONSISTENCY checker for an AI-generated intelligence card.

CRITICAL RULES:
- Do NOT use your own knowledge of world events to judge the card. You don't know what's current.
- Do NOT question whether events actually happened. The card is based on real news sources.
- Do NOT flag missing dates, timelines, or temporal context — the briefing is daily.
- ONLY flag problems visible within the card's own text.

Check ONLY for:
1. CONTRADICTION: One section directly contradicts another (TL;DR says X, Bigger Picture says not-X)
2. OVERCLAIMING: Speculation stated as certain fact (e.g., "this WILL cause" vs "this could cause")
3. UNSUPPORTED SPIN: The spin section attributes positions to groups not mentioned in the story
4. FACTUAL ERROR: A name, number, or role is internally inconsistent across sections

CARD TO REVIEW:
{card}

Return ONLY a JSON array. If no problems found, return [] — an empty array is the CORRECT response for a well-written card. Most cards should have 0-1 warnings.
Each warning: {{"type": "contradiction|overclaiming|unsupported_spin|factual_error", "detail": "Specific problem."}}""".format(card=card_text)

        report.llm_calls += 1
        result = llm_caller.call_by_id(reviewer_id,
            "Strict fact-checker. Only flag genuine problems. Return JSON array.",
            prompt, 1000)

        if not result:
            report.llm_failures += 1
            continue

        try:
            cleaned = re.sub(r'```json\s*', '', result)
            cleaned = re.sub(r'```\s*', '', cleaned).strip()
            m = re.search(r'\[.*\]', cleaned, re.DOTALL)
            warnings = json.loads(m.group() if m else cleaned)
            report.llm_successes += 1

            if warnings and isinstance(warnings, list):
                card.qa_warnings = [
                    w.get("detail", str(w))
                    for w in warnings[:2]
                    if isinstance(w, dict)
                ]
                total_warnings += len(card.qa_warnings)
                if card.qa_warnings:
                    print("    {} warnings on: {}".format(
                        len(card.qa_warnings), card.title[:50]))

        except (json.JSONDecodeError, ValueError, AttributeError):
            report.llm_failures += 1

    report.items_out = len(topic_cards)
    report.notes.append("{} warnings across {} cards".format(
        total_warnings, len(topic_cards)))
    print("    {} total QA warnings".format(total_warnings))
    return report
