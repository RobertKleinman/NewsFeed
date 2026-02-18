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
Plain text, no markdown, no bold, no bullets.

THEMES: 2-3 biggest themes connecting today's stories. 2-3 sentences each.
NOTABLE DISAGREEMENTS: Where did sources most sharply diverge? 1-2 paragraphs.
LOOKING AHEAD: 3-4 specific things to watch in coming days.

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
