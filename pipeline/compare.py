"""
Step 7: Cross-source comparison. Multi-model.
Outputs structured contention assessment alongside comparison text.
"""

import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import ComparisonResult, StepReport


def run(claims_data, lead_title):
    """Compare claims across sources. Returns (ComparisonResult, report)."""
    report = StepReport("compare", items_in=len(claims_data))
    if not claims_data:
        return ComparisonResult(), report

    claims_sections = []
    for c in claims_data:
        flags_note = ""
        if c.hallucination_flags:
            flags_note = "\n  [CAUTION: extraction may contain unverified details: {}]".format(
                "; ".join(c.hallucination_flags[:2]))
        claims_sections.append(
            "--- SOURCE: {src} ({region}, {bias}) | PERSPECTIVE: {persp} ---\n{text}{flags}".format(
                src=c.source_name, region=c.source_region, bias=c.source_bias,
                persp=c.perspective, text=c.extracted_text, flags=flags_note))
    claims_text = "\n\n".join(claims_sections)

    prompt = """You are a cross-source news auditor. Compare claim extractions from multiple
sources covering: "{title}"

SOURCES AND CLAIMS:
{claims}

Produce analysis in plain text (no markdown, no bold, no bullets):

AGREED FACTS:
Facts multiple sources confirm. Name which sources. Only facts in the extractions.

DISAGREEMENTS:
ONLY genuine contradictions — sources making INCOMPATIBLE claims about THE SAME thing.
Different coverage ≠ disagreement. Different emphasis ≠ disagreement.
If no real contradictions: "No substantive contradictions identified."
For each real disagreement, rate confidence: [HIGH/MEDIUM/LOW].

FRAMING DIFFERENCES:
How sources frame the same event differently. Quote specific phrases.
Distinguish source editorial framing from quotes of subjects in the article.

KEY UNKNOWNS:
Important questions the coverage leaves unanswered.""".format(
        title=lead_title, claims=claims_text)

    comparisons = {}
    available = llm_caller.get_available_llms()

    # Use best models for comparison
    preferred = ["gemini_pro", "chatgpt", "claude", "gemini", "grok"]
    comparators = [p for p in preferred if p in available][:2]
    if not comparators:
        comparators = available[:2] if len(available) >= 2 else available

    for llm_id in comparators:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        result = llm_caller.call_by_id(llm_id,
            "Precise, evidence-based news auditor. Only reference provided extractions. Plain text.",
            prompt, 3000)
        time.sleep(2)
        if result:
            comparisons[config["label"]] = result
            report.llm_successes += 1
        else:
            report.llm_failures += 1

    # Detect contention level from comparison outputs
    contention = _detect_contention(comparisons)

    result = ComparisonResult(
        comparisons=comparisons,
        contention_level=contention,
        has_real_disputes=(contention == "contested"),
    )

    report.items_out = len(comparisons)
    return result, report


def _detect_contention(comparisons):
    """Detect whether sources genuinely disagree."""
    combined = " ".join(comparisons.values()).lower()

    # Strong agreement signals
    agreement_phrases = [
        "no substantive contradictions",
        "no genuine contradictions",
        "no real disagreements",
        "no significant disagreements",
        "sources broadly agree",
        "sources are largely consistent",
        "no incompatible claims",
        "complement rather than contradict",
    ]
    for phrase in agreement_phrases:
        if phrase in combined:
            return "straight_news"

    # Strong dispute signals
    dispute_phrases = [
        "contradicts", "incompatible claim", "directly conflicts",
        "disputes the figure", "different numbers",
        "conflicting accounts", "[high]",
    ]
    dispute_count = sum(1 for p in dispute_phrases if p in combined)
    if dispute_count >= 2:
        return "contested"

    # Check DISAGREEMENTS section length
    for text in comparisons.values():
        lower = text.lower()
        if "disagreements:" in lower:
            parts = lower.split("disagreements:")
            if len(parts) > 1:
                rest = parts[1]
                for next_sec in ["framing", "key unknowns", "---"]:
                    if next_sec in rest:
                        rest = rest.split(next_sec)[0]
                if len(rest.strip()) > 80:
                    return "contested"

    return "straight_news"
