"""
Step 8: Investigate gaps and generate forward-looking analysis.
Input: comparisons dict, claims data, lead title
Output: investigation text, StepReport

When comparisons identify unknowns or missing perspectives, this step asks LLMs
to fill gaps using their training knowledge (clearly labeled as inference, not reporting).
Also generates implications and predictions.
"""

import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(comparisons, claims_data, lead_title):
    """Investigate gaps and forecast. Returns (investigation_text, report)."""
    report = StepReport("investigate", items_in=len(comparisons))
    available = llm_caller.get_available_llms()
    if not available or not comparisons:
        return None, report

    # Merge comparison outputs to find gaps
    all_unknowns = []
    for model, text in comparisons.items():
        if "KEY UNKNOWNS:" in text:
            unknowns_section = text.split("KEY UNKNOWNS:")[-1].strip()
            # Take first 500 chars of unknowns
            all_unknowns.append("{} noted: {}".format(model, unknowns_section[:500]))

    unknowns_text = "\n".join(all_unknowns) if all_unknowns else "No specific unknowns identified."

    # Build source context
    source_summary = "\n".join([
        "- {} ({}, {}): {}".format(c["source"], c["region"], c["perspective"], c["headline"])
        for c in claims_data
    ])

    prompt = """You are a senior intelligence analyst. A news event has been analyzed by multiple
sources and comparison models. Your job is two-fold:

1. INVESTIGATE GAPS: The comparison identified these unknowns and gaps:
{unknowns}

Using your training knowledge (not the articles), provide brief context that helps
explain these gaps. What background does the reader need? What historical context
is relevant? Be clear about what is established background vs your inference.

2. FORWARD ANALYSIS: Based on the event and sources below, provide:
- IMPLICATIONS: What are the likely consequences of this event? Who is affected and how?
- WHAT TO WATCH: What specific developments should the reader look for in the coming days/weeks?
- PREDICTIONS: What are 2-3 plausible scenarios for how this develops? Note which is most likely and why.

EVENT: {title}
SOURCES:
{sources}

Write in plain text only. No markdown, no bold, no bullets. Use these section labels exactly:

BACKGROUND AND CONTEXT:
[your background analysis — label anything that is inference vs established fact]

IMPLICATIONS:
[who is affected, how, why it matters beyond the headline]

WHAT TO WATCH:
[specific things the reader should monitor]

PREDICTIONS:
[2-3 scenarios, noting likelihood]""".format(
        unknowns=unknowns_text,
        title=lead_title,
        sources=source_summary)

    # Use a different model than the comparators for perspective diversity
    comparator_labels = set(comparisons.keys())
    investigator_id = None
    for llm_id in available:
        if LLM_CONFIGS[llm_id]["label"] not in comparator_labels:
            investigator_id = llm_id
            break
    if not investigator_id:
        investigator_id = available[-1]

    report.llm_calls += 1
    result = llm_caller.call_by_id(investigator_id,
        "You are a senior intelligence analyst. Clearly distinguish established facts from inference. Plain text only.",
        prompt, 1500)
    time.sleep(1)

    if result:
        report.llm_successes += 1
        report.items_out = 1
    else:
        report.llm_failures += 1

    return result, report
