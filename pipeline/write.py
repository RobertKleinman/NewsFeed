"""
Step 9: Write the final topic card.
Input: comparisons, investigation, selected sources, missing perspectives
Output: structured topic card dict, StepReport

Uses a model NOT used in compare or investigate to avoid compounding bias.
Output is structured (not just prose) so publish.py can render both
quick-scan visuals AND expandable detail.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(lead_title, topics, selected_sources, missing_perspectives, comparisons, investigation):
    """Write structured topic card. Returns (card_dict, report)."""
    report = StepReport("write")
    if not comparisons:
        return None, report

    comp_sections = []
    for model, text in comparisons.items():
        comp_sections.append("--- {} ANALYSIS ---\n{}".format(model, text))
    comparison_text = "\n\n".join(comp_sections)

    source_lines = []
    for s in selected_sources:
        source_lines.append("- {} ({}, {}): representing \"{}\"".format(
            s["article"].source_name, s["article"].source_region,
            s["article"].source_bias, s["perspective"]))
    sources_summary = "\n".join(source_lines)

    missing_text = ", ".join(missing_perspectives) if missing_perspectives else "None"

    investigation_text = ""
    if investigation:
        investigation_text = "\nINVESTIGATION AND FORECAST:\n" + investigation

    prompt = """Write a topic card for this news event. Use ONLY facts from the comparisons and investigation below.
You are an editor, not a reporter. Do not add facts.

EVENT: {title}

SOURCES USED:
{sources}

MISSING PERSPECTIVES: {missing}

COMPARISONS:
{comparisons}
{investigation}

Return a JSON object with this EXACT structure. All values must be strings. Write in plain
complete sentences, not fragments. No markdown anywhere.

{{
  "what_happened": "2-3 sentence neutral summary from agreed facts only",
  "agreed_facts": "Each fact on its own line. Include source names. Example:\\nThe trade deal was confirmed by Reuters and BBC.\\nThe timeline starts March 1 according to AP.",
  "disagreements": "Each disagreement on its own line with source attribution. Or 'No substantive contradictions identified.'",
  "framing_differences": "Each source's framing on its own line. Include the source name, its perspective label, and what it emphasizes. Quote specific language where available.",
  "key_unknowns": "Each unknown on its own line.",
  "implications": "2-3 sentences on who is affected and broader consequences.",
  "what_to_watch": "Each item on its own line. Specific things to monitor.",
  "predictions": "2-3 plausible scenarios, each on its own line. Note likelihood.",
  "missing_viewpoints": "Which perspectives were unavailable and why they matter. Or 'All identified perspectives were represented.'"
}}""".format(
        title=lead_title,
        sources=sources_summary,
        missing=missing_text,
        comparisons=comparison_text,
        investigation=investigation_text)

    # Pick writer: prefer a model NOT used for comparison or investigation
    used_labels = set(comparisons.keys())
    available = llm_caller.get_available_llms()
    writer_id = None
    for llm_id in available:
        if LLM_CONFIGS[llm_id]["label"] not in used_labels:
            writer_id = llm_id
            break
    if not writer_id:
        writer_id = available[-1]

    report.llm_calls += 1
    result = llm_caller.call_by_id(writer_id,
        "You write structured intelligence briefing cards. Return valid JSON only. No markdown. No extra text outside the JSON.",
        prompt, 2000)
    time.sleep(1)

    if not result:
        report.llm_failures += 1
        return None, report

    # Parse JSON
    card = _parse_card(result, lead_title, topics, selected_sources, missing_perspectives, comparisons, investigation)
    if card:
        report.llm_successes += 1
        report.items_out = 1
        writer_label = LLM_CONFIGS[writer_id]["label"]
        card["written_by"] = writer_label
    else:
        report.llm_failures += 1
        report.notes.append("JSON parse failed, using raw text")

    return card, report


def _parse_card(result, title, topics, sources, missing, comparisons, investigation):
    """Try to parse the structured JSON card. Fallback to raw text."""
    try:
        # Strip markdown fences if present
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = cleaned.strip()

        # Find the JSON object
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            card = json.loads(json_match.group())
        else:
            card = json.loads(cleaned)

        # Ensure all expected fields exist
        expected = ["what_happened", "agreed_facts", "disagreements",
                    "framing_differences", "key_unknowns", "implications",
                    "what_to_watch", "predictions", "missing_viewpoints"]
        for field in expected:
            if field not in card:
                card[field] = ""

        # Add metadata
        card["title"] = title
        card["topics"] = topics
        card["source_count"] = sum(1 for _ in sources)
        card["perspectives_used"] = len(sources)
        card["sources"] = [
            {"name": s["article"].source_name,
             "region": s["article"].source_region,
             "bias": s["article"].source_bias,
             "perspective": s["perspective"],
             "url": s["article"].url}
            for s in sources
        ]
        card["missing_perspective_list"] = missing
        card["comparisons"] = comparisons
        card["investigation"] = investigation
        return card

    except (json.JSONDecodeError, Exception) as e:
        # Fallback: wrap raw text
        return {
            "title": title,
            "topics": topics,
            "source_count": len(sources),
            "perspectives_used": len(sources),
            "sources": [
                {"name": s["article"].source_name,
                 "region": s["article"].source_region,
                 "bias": s["article"].source_bias,
                 "perspective": s["perspective"],
                 "url": s["article"].url}
                for s in sources
            ],
            "missing_perspective_list": missing,
            "comparisons": comparisons,
            "investigation": investigation,
            "what_happened": result[:500],
            "agreed_facts": "",
            "disagreements": "",
            "framing_differences": "",
            "key_unknowns": "",
            "implications": "",
            "what_to_watch": "",
            "predictions": "",
            "missing_viewpoints": ", ".join(missing) if missing else "",
            "written_by": "fallback",
        }
