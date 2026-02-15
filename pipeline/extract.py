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
    extractor_id = available[0]  # Use cheapest available

    claims = []
    for item in selected_sources:
        article = item["article"]
        perspective = item["perspective"]

        prompt = """Extract factual claims from this news article.

SOURCE: {source}
PERSPECTIVE: This source represents: {perspective}
HEADLINE: {title}
CONTENT: {summary}

For each claim, identify:
1. The claim itself (one sentence)
2. Type: REPORTED_FACT / OFFICIAL_STATEMENT / ANALYSIS / OPINION
3. Attribution (who said or reported it)

Also note:
EMPHASIS: What does this source emphasize that others might not?
FRAMING: Any notable language choices, loaded words, or editorial angle?

Format each claim on its own line:
CLAIM: [text] | TYPE: [type] | ATTR: [attribution]

End with EMPHASIS and FRAMING lines.""".format(
            source=article.source_label(),
            perspective=perspective,
            title=article.title,
            summary=article.summary[:400])

        report.llm_calls += 1
        result = llm_caller.call_by_id(extractor_id,
            "You extract structured claims from news. Be precise. Only extract what is stated. Never invent facts.",
            prompt, 800)
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
