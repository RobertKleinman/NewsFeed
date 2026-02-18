"""
Step 6: Extract structured claims from each source.
Includes hallucination check — verifies claims trace to source text.
"""

import re
import time

import llm as llm_caller
from models import ClaimSet, StepReport


def run(selected_sources):
    """Extract claims with hallucination checking. Returns (claims, report)."""
    report = StepReport("extract", items_in=len(selected_sources))
    available = llm_caller.get_available_llms()
    if not available:
        return [], report

    # Use cheapest model for extraction
    flash_options = [k for k in available if k not in ("gemini_pro", "claude")]
    extractor_id = flash_options[0] if flash_options else available[0]

    claims = []
    for item in selected_sources:
        article = item.article
        perspective = item.perspective
        source_text = "{} {}".format(article.title, article.summary)

        prompt = """Extract factual claims from this news article.

SOURCE: {source}
PERSPECTIVE: {perspective}
HEADLINE: {title}
CONTENT: {summary}

Extract:
CLAIMS (one per line):
CLAIM: [specific fact] | TYPE: [REPORTED_FACT / OFFICIAL_STATEMENT / ANALYSIS / OPINION] | ATTR: [who said it]

EMPHASIS: What does this source emphasize?
FRAMING: Notable language choices or editorial angle? Quote specific phrases.
NOTABLE_DETAILS: Specific numbers, dates, names, connections.

CRITICAL: Only extract what is EXPLICITLY stated in the content above.
Do NOT infer, assume, or add facts not present in the text.""".format(
            source=article.source_label(),
            perspective=perspective,
            title=article.title,
            summary=article.summary[:500])

        report.llm_calls += 1
        result = llm_caller.call_by_id(extractor_id,
            "Extract only what is explicitly stated. Never invent facts.",
            prompt, 2000)
        time.sleep(0.5)

        if not result:
            report.llm_failures += 1
            continue

        report.llm_successes += 1

        # Hallucination check: look for specific claims not traceable to source
        flags = _check_hallucinations(result, source_text)

        claims.append(ClaimSet(
            source_name=article.source_name,
            source_region=article.source_region,
            source_bias=article.source_bias,
            perspective=perspective,
            headline=article.title,
            url=article.url,
            extracted_text=result,
            hallucination_flags=flags,
        ))

    report.items_out = len(claims)
    flagged = sum(1 for c in claims if c.hallucination_flags)
    if flagged:
        report.notes.append("{} sources flagged for possible hallucination".format(flagged))
        print("    {} sources flagged for possible hallucination".format(flagged))

    return claims, report


def _check_hallucinations(extracted, source_text):
    """Check if extracted claims contain information not in source text."""
    flags = []
    source_lower = source_text.lower()

    # Extract specific numbers from the extraction
    extracted_numbers = set(re.findall(r'\b\d[\d,.]+\b', extracted))
    source_numbers = set(re.findall(r'\b\d[\d,.]+\b', source_text))

    # Numbers in extraction but not in source are suspicious
    phantom_numbers = extracted_numbers - source_numbers
    for num in phantom_numbers:
        # Skip small numbers (1-31) as they could be dates or generic
        try:
            val = float(num.replace(",", ""))
            if val > 31:
                flags.append("Number {} not found in source text".format(num))
        except ValueError:
            pass

    # Extract quoted names (capitalized multi-word sequences)
    name_pattern = re.compile(r'[A-Z][a-z]+ [A-Z][a-z]+')
    extracted_names = set(name_pattern.findall(extracted))
    source_names = set(name_pattern.findall(source_text))
    phantom_names = extracted_names - source_names
    for name in phantom_names:
        # Only flag if the name parts aren't individually present
        parts = name.lower().split()
        if not all(p in source_lower for p in parts):
            flags.append("Name '{}' not found in source text".format(name))

    return flags[:3]  # Cap at 3 flags per source
