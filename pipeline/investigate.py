"""
Step 8: Investigate gaps using web search.
Key change: output is framed as "what changes the story," not raw research.
If investigation adds nothing new, it says so explicitly.
Only runs for DEEP tier stories.
"""

import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import InvestigationResult, StepReport


def run(comparison_result, claims_data, lead_title):
    """Investigate and frame findings as story impact. Returns (InvestigationResult, report)."""
    report = StepReport("investigate", items_in=1)
    available = llm_caller.get_available_llms()
    if not available:
        return InvestigationResult(), report

    # Extract unknowns from comparisons
    all_unknowns = []
    for model, text in comparison_result.comparisons.items():
        if "KEY UNKNOWNS:" in text:
            section = text.split("KEY UNKNOWNS:")[-1].strip()
            all_unknowns.append(section[:400])
    unknowns_text = "\n".join(all_unknowns) if all_unknowns else "No specific unknowns identified."

    # What the coverage says (for comparison)
    coverage_summary = ""
    for model, text in comparison_result.comparisons.items():
        if "AGREED FACTS:" in text:
            facts = text.split("AGREED FACTS:")[-1]
            for next_sec in ["DISAGREEMENTS:", "FRAMING", "KEY UNKNOWNS:"]:
                if next_sec in facts:
                    facts = facts.split(next_sec)[0]
            coverage_summary = facts.strip()[:500]
            break

    prompt = """Research this news event and assess whether your findings change the story.

EVENT: {title}

WHAT COVERAGE SAYS:
{coverage}

GAPS IN COVERAGE:
{unknowns}

Search for current information. Then answer:

1. WHAT I FOUND: (3-5 sentences) Key background and context from research.

2. DOES THIS CHANGE THE STORY?
Answer ONE of:
a) "YES — [explain how]" if your research reveals something that materially changes
   how a reader should understand this event. Example: coverage omits crucial context,
   a key claim is contradicted by evidence, an important stakeholder is being ignored.
b) "NO — coverage is substantially accurate" if your research confirms what sources
   already reported. Don't pad with redundant context.

3. IF YES — STORY IMPACT: (1-2 sentences) How should the reader adjust their understanding?

Be honest. Most stories' coverage is adequate. Only flag genuine story-changers.
Plain text only. Complete every sentence.""".format(
        title=lead_title,
        coverage=coverage_summary,
        unknowns=unknowns_text)

    # Prefer Gemini Pro for web search
    investigator_id = None
    use_search = False

    if "gemini_pro" in available:
        investigator_id = "gemini_pro"
        use_search = True
    elif "gemini" in available:
        investigator_id = "gemini"
        use_search = True
    else:
        comparator_labels = set(comparison_result.comparisons.keys())
        for llm_id in available:
            if LLM_CONFIGS[llm_id]["label"] not in comparator_labels:
                investigator_id = llm_id
                break
        if not investigator_id:
            investigator_id = available[-1]

    report.llm_calls += 1
    result = llm_caller.call_by_id(investigator_id,
        "Research analyst. Be honest about whether findings add value. Plain text only.",
        prompt, 3000, web_search=use_search)
    time.sleep(1)

    if not result:
        report.llm_failures += 1
        return InvestigationResult(), report

    report.llm_successes += 1
    report.items_out = 1

    # Parse whether investigation adds value
    adds_value = _assess_value(result)
    story_impact = _extract_impact(result)

    return InvestigationResult(
        raw_text=result,
        story_impact=story_impact,
        adds_value=adds_value,
    ), report


def _assess_value(text):
    """Determine if investigation found something that changes the story."""
    lower = text.lower()
    # Explicit "yes" signals
    if "yes —" in lower or "yes—" in lower or "yes -" in lower:
        return True
    if "materially changes" in lower or "crucial context" in lower:
        return True
    if "contradicted by" in lower or "omits" in lower:
        return True
    # Explicit "no" signals
    if "no —" in lower or "no—" in lower or "no -" in lower:
        return False
    if "substantially accurate" in lower or "coverage is adequate" in lower:
        return False
    if "confirms what" in lower or "consistent with" in lower:
        return False
    # Default: if there's a STORY IMPACT section with content, it adds value
    if "story impact:" in lower:
        impact = lower.split("story impact:")[-1].strip()
        return len(impact) > 30
    return False


def _extract_impact(text):
    """Extract the story impact statement."""
    # Look for explicit impact section
    for marker in ["STORY IMPACT:", "Story Impact:", "story impact:"]:
        if marker in text:
            impact = text.split(marker)[-1].strip()
            # Take first 2-3 sentences
            sentences = [s.strip() for s in impact.split(".") if s.strip()]
            return ". ".join(sentences[:3]) + "." if sentences else ""

    # Look for "YES —" explanation
    for marker in ["YES —", "YES —", "YES -", "Yes —"]:
        if marker in text:
            explanation = text.split(marker)[-1].strip()
            sentences = [s.strip() for s in explanation.split(".") if s.strip()]
            return ". ".join(sentences[:2]) + "." if sentences else ""

    return ""
