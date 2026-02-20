"""
Step 10: Executive synthesis across all topic cards.
"""

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """Generate executive synthesis. Returns (text, report)."""
    print("\n>>> SYNTHESIZE...")
    report = StepReport("synthesize", items_in=len(topic_cards))
    available = llm_caller.get_available_llms()
    if not available:
        return "No LLM available.", report

    summaries = []
    for i, card in enumerate(topic_cards):
        tier_label = {"deep": "DEEP", "standard": "STD", "brief": "BRIEF"}.get(card.depth_tier, "?")
        summaries.append("{}. [{}★ {}] {} — {}".format(
            i + 1, card.importance, tier_label, card.title,
            card.what_happened[:200]))

    prompt = """Write the executive synthesis for today's intelligence briefing.
Return ONLY valid JSON with this exact structure:

{{
  "action_calls": [
    "One-sentence call to action or key decision point for today.",
    "Another action call.",
    "Third action call."
  ],
  "risks": [
    "One-sentence risk or threat to watch.",
    "Another risk.",
    "Third risk."
  ],
  "watch_items": [
    "One-sentence item to monitor in coming days.",
    "Another watch item.",
    "Third watch item."
  ],
  "themes": "2-3 sentences connecting today's biggest themes across stories.",
  "disagreements": "1-2 sentences on where sources most sharply diverged today."
}}

3 items per bucket, each one sentence max. Be specific and concrete.

STORIES:
""" + "\n\n".join(summaries)

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Concise intelligence briefings. Plain text only.", prompt, 2000)

    if result:
        report.llm_successes += 1
        report.items_out = 1
    else:
        result = "Synthesis generation failed."
        report.llm_failures += 1

    return result, report
