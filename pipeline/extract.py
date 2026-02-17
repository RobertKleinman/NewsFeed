"""
Step 6: Extract structured claims from each source article.
Input: list of {article, perspective} dicts
Output: list of claim dicts, StepReport

Uses one cheap model. Extracts facts, attribution, framing — not summaries.
"""

import time

import llm as llm_caller
from models import StepReport


def run(selected_sources):
    """Extract claims from each source. Returns (claims_list, report)."""
    report = StepReport("extract", items_in=len(selected_sources))
    available = llm_caller.get_available_llms()
    if not available:
        return [], report
    # Use cheapest model for extraction — gemini flash preferred, skip pro
    flash_options = [k for k in available if k != "gemini_pro"]
    extractor_id = flash_options[0] if flash_options else available[0]

    claims = []
    for item in selected_sources:
        article = item["article"]
        perspective = item["perspective"]

        prompt = """Extract factual claims and notable details from this news article.

SOURCE: {source}
PERSPECTIVE: This source represents: {perspective}
HEADLINE: {title}
CONTENT: {summary}

Extract ALL of the following:

CLAIMS (one per line):
CLAIM: [specific factual statement] | TYPE: [REPORTED_FACT / OFFICIAL_STATEMENT / ANALYSIS / OPINION] | ATTR: [who said or reported it]

EMPHASIS: What does this source emphasize that others might not? What angle does it take?

FRAMING: Any notable language choices, loaded words, or editorial angle? Quote specific phrases.

NOTABLE_DETAILS: Any interesting facts, statistics, historical connections, or context that adds depth beyond the core story. Include specific names, numbers, dates, and connections.

Be thorough. Extract every specific claim, number, name, and date mentioned.""".format(
            source=article.source_label(),
            perspective=perspective,
            title=article.title,
            summary=article.summary[:500])

        report.llm_calls += 1
        result = llm_caller.call_by_id(extractor_id,
            "You extract structured claims from news. Be precise. Only extract what is stated. Never invent facts.",
            prompt, 3000)
        time.sleep(1)

        if result:
            report.llm_successes += 1
            claims.append({
                "source": article.source_name,
                "region": article.source_region,
                "bias": article.source_bias,
                "perspective": perspective,
                "headline": article.title,
                "url": article.url,
                "extracted": result,
            })
        else:
            report.llm_failures += 1

    report.items_out = len(claims)
    return claims, report
