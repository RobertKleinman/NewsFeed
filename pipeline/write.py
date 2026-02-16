"""
Step 9: Write the final topic card.
Comparison-first output: facts with source tags, paired disputes,
quoted framing, structured predictions.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(lead_title, topics, selected_sources, missing_perspectives, comparisons, investigation):
    report = StepReport("write")
    if not comparisons:
        return None, report

    comp_sections = []
    for model, text in comparisons.items():
        comp_sections.append("--- {} ANALYSIS ---\n{}".format(model, text))
    comparison_text = "\n\n".join(comp_sections)

    source_lines = []
    for s in selected_sources:
        source_lines.append("- {} ({}, {}, {}): representing \"{}\"".format(
            s["article"].source_name, s["article"].source_region,
            s["article"].source_bias, _source_type(s["article"]),
            s["perspective"]))
    sources_summary = "\n".join(source_lines)

    missing_text = ", ".join(missing_perspectives) if missing_perspectives else "None"

    investigation_text = ""
    if investigation:
        investigation_text = "\nINVESTIGATION AND FORECAST:\n" + investigation

    prompt = """Write a structured topic card. Use ONLY facts from the comparisons and investigation below.
You are an editor. Do not add facts. Do not write prose paragraphs.

EVENT: {title}

SOURCES USED:
{sources}

MISSING PERSPECTIVES: {missing}

COMPARISONS:
{comparisons}
{investigation}

Return a JSON object. Every field must follow its format rules exactly.

{{
  "what_happened": "Max 2 sentences. Actor + action + stake. No adjectives. Include source tag if only one source reports it. Example: The US imposed 25% tariffs on Canadian steel (Reuters, AP). Canada announced retaliatory measures (CBC, Globe and Mail).",

  "agreed_facts": [
    "Fact confirmed by 2+ sources. [Source1, Source2]",
    "Another fact. [Source3, Source4]"
  ],

  "disputes": [
    {{
      "type": "data OR causality OR attribution OR framing",
      "side_a": "What Side A claims. [Source name]",
      "side_b": "What Side B claims. [Source name]"
    }}
  ],

  "framing": [
    {{
      "source": "Source name",
      "quote": "Short quoted phrase showing editorial angle",
      "frame": "Neutral one-sentence description of what this framing implies"
    }}
  ],

  "key_unknowns": [
    "Specific unanswered question"
  ],

  "implications": "2-3 sentences. Who is affected and how.",

  "watch_items": [
    {{
      "event": "Specific development to monitor",
      "time_horizon": "24-72h OR 1-2 weeks OR 1-3 months",
      "driver": "What would trigger this"
    }}
  ],

  "predictions": [
    {{
      "scenario": "What could happen",
      "likelihood": "likely OR possible OR unlikely",
      "condition": "What would need to be true"
    }}
  ],

  "missing_viewpoints": "Which perspectives were unavailable and why they matter. Or empty string."
}}

RULES:
- agreed_facts: Only include if confirmed by 2+ sources. Always include source names in brackets.
- disputes: ONLY include genuine contradictions where two sources make INCOMPATIBLE claims about THE SAME THING. Different facts about different aspects are NOT disputes. Two different cities reporting different crowd sizes is NOT a dispute. If sources complement rather than contradict each other, leave disputes as an empty array []. For each dispute, include your confidence (high/medium/low) at the end of side_a.
- framing: Must include a direct quoted phrase from the source material. Distinguish between a source's own editorial angle and quotes from subjects within the article. If the quote is from a person in the article, say so.
- predictions: Skip entirely (empty array) for cultural events, human interest stories, celebrations, or single-event stories where future scenarios would be speculative and low-stakes. Only include for policy, conflict, economic, or diplomatic stories where real consequences are developing.
- No prose paragraphs anywhere. Bullets and structured entries only.
- No markdown. No bold. Plain text in all string values.""".format(
        title=lead_title,
        sources=sources_summary,
        missing=missing_text,
        comparisons=comparison_text,
        investigation=investigation_text)

    used_labels = set(comparisons.keys())
    available = llm_caller.get_available_llms()
    writer_id = None

    # Priority: ChatGPT > Gemini > Claude > Grok for card writing
    writer_preference = ["chatgpt", "gemini", "claude", "grok"]
    for preferred in writer_preference:
        if preferred in available and LLM_CONFIGS[preferred]["label"] not in used_labels:
            writer_id = preferred
            break
    if not writer_id:
        for preferred in writer_preference:
            if preferred in available:
                writer_id = preferred
                break
    if not writer_id:
        writer_id = available[-1]

    report.llm_calls += 1
    result = llm_caller.call_by_id(writer_id,
        "Return valid JSON only. No markdown. Structured entries, not prose.",
        prompt, 2500)
    time.sleep(1)

    if not result:
        report.llm_failures += 1
        return None, report

    card = _parse_card(result, lead_title, topics, selected_sources, missing_perspectives, comparisons, investigation)
    if card:
        report.llm_successes += 1
        report.items_out = 1
        card["written_by"] = LLM_CONFIGS[writer_id]["label"]
    else:
        report.llm_failures += 1
        report.notes.append("JSON parse failed")

    return card, report


def _source_type(article):
    """Infer source type from region/bias tags."""
    region = article.source_region.lower()
    if "insurance" in region or "privacy" in region or "security" in region:
        return "niche"
    if "tech" in region or "ai" in region:
        return "niche"
    if "policy" in region or "legal" in region:
        return "think_tank"
    if "finance" in region:
        return "mainstream"
    if "culture" in region:
        return "niche"
    if "labor" in region:
        return "advocacy"
    bias = article.source_bias.lower()
    if bias in ("left", "right", "libertarian"):
        return "opinion"
    if "religious" in bias:
        return "opinion"
    if "industry" in bias:
        return "niche"
    return "mainstream"


def _parse_card(result, title, topics, sources, missing, comparisons, investigation):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            card = json.loads(json_match.group())
        else:
            card = json.loads(cleaned)

        # Normalize: ensure all fields exist with correct types
        if "agreed_facts" not in card or not isinstance(card["agreed_facts"], list):
            # Convert old string format to list
            old = card.get("agreed_facts", "")
            card["agreed_facts"] = [l.strip() for l in old.split("\n") if l.strip()] if isinstance(old, str) else []

        if "disputes" not in card or not isinstance(card["disputes"], list):
            old = card.get("disagreements", card.get("disputes", ""))
            if isinstance(old, str):
                card["disputes"] = [{"type": "framing", "side_a": old, "side_b": ""}] if old and "no substantive" not in old.lower() else []
            else:
                card["disputes"] = old if isinstance(old, list) else []

        if "framing" not in card or not isinstance(card["framing"], list):
            old = card.get("framing_differences", card.get("framing", ""))
            if isinstance(old, str):
                card["framing"] = [{"source": "", "quote": l.strip(), "frame": ""} for l in old.split("\n") if l.strip()] if old else []
            else:
                card["framing"] = old if isinstance(old, list) else []

        if "watch_items" not in card or not isinstance(card["watch_items"], list):
            old = card.get("what_to_watch", card.get("watch_items", ""))
            if isinstance(old, str):
                card["watch_items"] = [{"event": l.strip(), "time_horizon": "", "driver": ""} for l in old.split("\n") if l.strip()] if old else []
            else:
                card["watch_items"] = old if isinstance(old, list) else []

        if "predictions" not in card or not isinstance(card["predictions"], list):
            old = card.get("predictions", "")
            if isinstance(old, str):
                card["predictions"] = [{"scenario": l.strip(), "likelihood": "", "condition": ""} for l in old.split("\n") if l.strip()] if old else []
            else:
                card["predictions"] = old if isinstance(old, list) else []

        for field in ["what_happened", "key_unknowns", "implications", "missing_viewpoints"]:
            if field not in card:
                card[field] = "" if field != "key_unknowns" else []

        if isinstance(card["key_unknowns"], str):
            card["key_unknowns"] = [l.strip() for l in card["key_unknowns"].split("\n") if l.strip()]

        # Compute source type counts for coverage spectrum
        type_counts = {}
        for s in sources:
            st = _source_type(s["article"])
            type_counts[st] = type_counts.get(st, 0) + 1

        card["title"] = title
        card["topics"] = topics
        card["source_count"] = len(sources)
        card["perspectives_used"] = len(sources)
        card["source_type_counts"] = type_counts
        card["sources"] = [
            {"name": s["article"].source_name,
             "region": s["article"].source_region,
             "bias": s["article"].source_bias,
             "perspective": s["perspective"],
             "url": s["article"].url,
             "source_type": _source_type(s["article"])}
            for s in sources
        ]
        card["missing_perspective_list"] = missing
        card["comparisons"] = comparisons
        card["investigation"] = investigation

        # Backwards compat: keep old field names for anything still reading them
        card["disagreements"] = "\n".join(
            "{}: {} vs {}".format(d.get("type", ""), d.get("side_a", ""), d.get("side_b", ""))
            for d in card["disputes"]) if card["disputes"] else "No substantive contradictions identified."
        card["framing_differences"] = "\n".join(
            "{}: \"{}\" - {}".format(f.get("source", ""), f.get("quote", ""), f.get("frame", ""))
            for f in card["framing"]) if card["framing"] else ""

        return card

    except Exception as e:
        print("    Write parse error: {}".format(str(e)[:80]))
        return {
            "title": title, "topics": topics,
            "source_count": len(sources), "perspectives_used": len(sources),
            "source_type_counts": {},
            "sources": [
                {"name": s["article"].source_name, "region": s["article"].source_region,
                 "bias": s["article"].source_bias, "perspective": s["perspective"],
                 "url": s["article"].url, "source_type": _source_type(s["article"])}
                for s in sources],
            "missing_perspective_list": missing,
            "comparisons": comparisons, "investigation": investigation,
            "what_happened": result[:500] if result else "",
            "agreed_facts": [], "disputes": [], "framing": [],
            "key_unknowns": [], "implications": "",
            "watch_items": [], "predictions": [],
            "missing_viewpoints": "", "disagreements": "", "framing_differences": "",
            "written_by": "fallback",
        }
