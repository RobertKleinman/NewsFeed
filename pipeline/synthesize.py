"""
Step 10: Executive synthesis across all topic cards.
Input: list of topic card dicts
Output: synthesis text, StepReport
"""

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """Generate executive synthesis. Returns (synthesis_text, report)."""
    print("\n>>> SYNTHESIZE...")
    report = StepReport("synthesize", items_in=len(topic_cards))
    available = llm_caller.get_available_llms()
    if not available:
        return "No LLM available for synthesis.", report

    card_summaries = []
    for i, card in enumerate(topic_cards):
        what = card.get("what_happened", "")[:300]
        topics = ", ".join(card.get("topics", [])[:2])
        card_summaries.append(
            "Story {}: [{}] {}\n{}\nSources: {}, Perspectives: {}".format(
                i + 1, topics, card["title"], what,
                card.get("source_count", 0), card.get("perspectives_used", 0)))

    all_summaries = "\n\n".join(card_summaries)

    prompt = """You are writing the executive synthesis for a daily intelligence briefing.
Based on these topic cards, write a compelling overview with this structure
(plain text, no markdown, no bold, no bullets):

THEMES:
Identify the 2-3 biggest themes and connecting threads across stories today.
2-3 sentences per theme.

NOTABLE DISAGREEMENTS:
Where did different sources and perspectives most sharply diverge today?
Which stories had the most contested framing? 1-2 paragraphs.

LOOKING AHEAD:
What are the 3-4 most important things to watch in the coming days
based on today's stories? Be specific.

TODAY'S STORIES:
""" + all_summaries

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "You write concise intelligence briefings. Plain text only. No markdown.",
        prompt, 2000)

    if result:
        report.llm_successes += 1
        report.items_out = 1
    else:
        result = "Synthesis generation failed."
        report.llm_failures += 1

    return result, report
