"""
Step 7: Cross-source comparison. Multi-model — this is where bias detection matters most.
Input: list of claim dicts, lead title
Output: dict of {model_label: comparison_text}, StepReport

Two models independently compare claims across sources. Their disagreement about
what counts as a contradiction vs minor difference is itself valuable signal.
"""

import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(claims_data, lead_title):
    """Compare claims across sources. Returns (comparisons_dict, report)."""
    report = StepReport("compare", items_in=len(claims_data))
    if not claims_data:
        return {}, report

    claims_sections = []
    for c in claims_data:
        claims_sections.append(
            "--- SOURCE: {src} ({region}, {bias}) | PERSPECTIVE: {persp} ---\n{text}".format(
                src=c["source"], region=c["region"], bias=c["bias"],
                persp=c["perspective"], text=c["extracted"]))
    claims_text = "\n\n".join(claims_sections)

    prompt = """You are a cross-source news auditor. Below are claim extractions from multiple
sources covering the same event: "{title}"

Each source was selected to represent a different perspective. Compare them and identify
what they agree on, where they genuinely differ, and how they frame things differently.

SOURCES AND CLAIMS:
{claims}

Produce this analysis in plain text (no markdown, no bold, no bullets, no # headers).
Use these exact section labels:

AGREED FACTS:
State facts multiple sources confirm. Name which sources. Only facts actually in the
extractions above. Never invent or assume.

DISAGREEMENTS:
ONLY include genuine contradictions where sources make INCOMPATIBLE claims about THE SAME
specific thing. Two sources covering different aspects of the same story is NOT a disagreement.
Different cities with different crowd sizes is NOT a disagreement. Different emphasis is NOT
a disagreement — that goes in FRAMING DIFFERENCES. If sources complement rather than
contradict each other, write: "No substantive contradictions identified."

For each real disagreement, rate your confidence: [HIGH/MEDIUM/LOW].

FRAMING DIFFERENCES:
How different sources frame the same event. Quote specific short phrases that reveal
editorial angle. IMPORTANT: distinguish between a source's own editorial framing and
quotes from subjects within the article. If a source quotes a politician, note that
the framing is the politician's words, not the outlet's angle.

KEY UNKNOWNS:
Important questions the coverage leaves unanswered. What a well-informed reader would
want to know.""".format(title=lead_title, claims=claims_text)

    comparisons = {}
    available = llm_caller.get_available_llms()
    comparators = available[:2] if len(available) >= 2 else available

    for llm_id in comparators:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        result = llm_caller.call_by_id(llm_id,
            "You are a precise, evidence-based news auditor. Only reference the provided extractions. Never invent facts. Plain text only.",
            prompt, 1500)
        time.sleep(2)
        if result:
            comparisons[config["label"]] = result
            report.llm_successes += 1
        else:
            report.llm_failures += 1

    report.items_out = len(comparisons)
    return comparisons, report
