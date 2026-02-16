"""
Step 8: Investigate gaps using web search + LLM knowledge.
Uses Gemini with Google Search grounding when available for current context.
Output is structured and concise — no essay-length prose.
"""

import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(comparisons, claims_data, lead_title):
    report = StepReport("investigate", items_in=len(comparisons))
    available = llm_caller.get_available_llms()
    if not available or not comparisons:
        return None, report

    # Extract unknowns from comparisons
    all_unknowns = []
    for model, text in comparisons.items():
        if "KEY UNKNOWNS:" in text:
            section = text.split("KEY UNKNOWNS:")[-1].strip()
            all_unknowns.append(section[:400])

    unknowns_text = "\n".join(all_unknowns) if all_unknowns else "No specific unknowns."

    source_summary = "\n".join([
        "- {} ({}): {}".format(c["source"], c["perspective"], c["headline"])
        for c in claims_data
    ])

    prompt = """Research this news event and provide brief, structured context.

EVENT: {title}
SOURCES: {sources}
GAPS IDENTIFIED: {unknowns}

Search for current information about this event. Then provide:

CONTEXT: (3-5 sentences max)
State the essential background a reader needs. What triggered this event?
What recent developments led here? State established facts directly — do not
hedge on well-documented history. Be specific about dates, names, and events.

KEY FINDING: (1-2 sentences)
The single most important piece of context that the original news coverage missed
or underemphasized.

Write concisely. No filler. No preamble. Plain text only.""".format(
        title=lead_title,
        sources=source_summary,
        unknowns=unknowns_text)

    # Prefer Gemini for web search grounding
    investigator_id = None
    use_search = False

    # First try: Gemini with web search
    if "gemini" in available:
        investigator_id = "gemini"
        use_search = True
        print("      Using Gemini with web search")
    else:
        # Fallback: use a model not used for comparison
        comparator_labels = set(comparisons.keys())
        for llm_id in available:
            if LLM_CONFIGS[llm_id]["label"] not in comparator_labels:
                investigator_id = llm_id
                break
        if not investigator_id:
            investigator_id = available[-1]

    report.llm_calls += 1
    result = llm_caller.call_by_id(investigator_id,
        "You are a research analyst. Be concise and factual. State established facts directly. Plain text only.",
        prompt, 800, web_search=use_search)
    time.sleep(1)

    if result:
        report.llm_successes += 1
        report.items_out = 1
    else:
        report.llm_failures += 1

    return result, report
