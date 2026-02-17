"""
Step 9: Write the final topic card.
Two-pass approach:
  Pass 1: Core card (what_happened, agreed_facts, disputes, framing) — must complete
  Pass 2: Extras (predictions, watch_items, key_unknowns, notable_details) — separate call
This prevents models from running out of steam on the core content.
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

    # Select writer model
    used_labels = set(comparisons.keys())
    available = llm_caller.get_available_llms()
    writer_id = _pick_writer(available, used_labels)

    # === PASS 1: Core card ===
    core_prompt = """Write a structured topic card. Use ONLY facts from the comparisons below.
You are an editor. Do not add facts. Do not write prose paragraphs.

CRITICAL: Every string value must end with a period. If a sentence ends mid-word, the entire output is INVALID.

EVENT: {title}

SOURCES USED:
{sources}

MISSING PERSPECTIVES: {missing}

COMPARISONS:
{comparisons}

Return a JSON object with ONLY these fields:
{{
  "what_happened": "Max 2 sentences. THE HEADLINE — what happened, who did it, what's at stake. This is the overview, NOT the evidence.",

  "agreed_facts": [
    "Specific verifiable EVIDENCE — numbers, dates, names, actions. Do NOT repeat what_happened. These are the supporting facts, not the summary."
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
      "frame": "What this framing REVEALS about the source's priorities. Not obvious observations. If quote is from a person in the article, say: [Person] quoted by [Source] — this reveals X."
    }}
  ],

  "implications": "2-3 sentences. Who is affected and how.",

  "missing_viewpoints": "Which perspectives were unavailable and why they matter. Or empty string."
}}

RULES:
- FOCUS: If comparisons mention multiple unrelated topics, write about the PRIMARY story in the headline ONLY. Ignore unrelated facts completely — do not include them in any field.
- agreed_facts: Include ALL key facts. If 2+ sources confirm, list both. If 1 source, tag [Source only]. NEVER leave empty.
- disputes: ONLY genuine contradictions about THE SAME THING. If comparison says "no contradictions," leave as empty array [].
- framing: Must be INSIGHTFUL. Don't state the obvious. Explain what the angle REVEALS. If nothing insightful, omit that source.
- COMPLETE every sentence. Never truncate. If running low on space, write fewer items but complete ones.
- No markdown. No bold. Plain text only.""".format(
        title=lead_title,
        sources=sources_summary,
        missing=missing_text,
        comparisons=comparison_text)

    report.llm_calls += 1
    core_result = llm_caller.call_by_id(writer_id,
        "Return valid JSON only. COMPLETE every sentence. Short but complete.",
        core_prompt, 4000)
    time.sleep(1)

    if core_result:
        # Check if JSON was truncated
        stripped = core_result.strip().rstrip('`').strip()
        if stripped and not stripped.endswith('}'):
            print("    Core truncated (no closing brace), retrying with shorter output...")
            report.llm_calls += 1
            core_result = llm_caller.call_by_id(writer_id,
                "Return valid JSON only. BE CONCISE. 3 facts max. 2 framing max. COMPLETE every sentence.",
                core_prompt, 4000, use_cache=False)
            time.sleep(1)

    if not core_result:
        report.llm_failures += 1
        return None, report

    card = _parse_core(core_result)
    if not card:
        report.llm_failures += 1
        report.notes.append("Core JSON parse failed")
        return _fallback_card(core_result, lead_title, topics, selected_sources,
                             missing_perspectives, comparisons, investigation), report

    report.llm_successes += 1

    # === PASS 2: Extras ===
    extras_prompt = """Based on this news story, add analysis fields. Use the investigation research below.

CRITICAL: Every string value must end with a period. If a sentence ends mid-word, the entire output is INVALID.

EVENT: {title}
SUMMARY: {what}
{investigation}

Return JSON with ONLY these fields:
{{
  "key_unknowns": [
    {{
      "question": "Unanswered question from the coverage",
      "answer": "Best answer from investigation. Or 'Not yet reported.'"
    }}
  ],

  "watch_items": [
    {{
      "event": "What to monitor",
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

  "notable_details": [
    "Interesting fact adding color or context. Historical parallels, surprising connections, notable quotes."
  ]
}}

RULES:
- predictions: Skip entirely (empty array) for cultural, human interest, obituaries, or single-event stories.
- key_unknowns: 2-4 items max. Answer from investigation if possible.
- watch_items: 2-3 items max. Specific and actionable.
- notable_details: 1-3 items. Only genuinely interesting facts.
- COMPLETE every sentence. If running low, write fewer items but complete ones.""".format(
        title=lead_title,
        what=card.get("what_happened", "")[:200],
        investigation=investigation_text)

    report.llm_calls += 1
    extras_result = llm_caller.call_by_id(writer_id,
        "Return valid JSON only. COMPLETE every sentence.",
        extras_prompt, 4000)
    time.sleep(1)

    if extras_result:
        # Check if JSON was truncated (doesn't end with closing brace)
        stripped = extras_result.strip().rstrip('`').strip()
        if stripped and not stripped.endswith('}'):
            print("    Extras truncated (no closing brace), retrying...")
            report.llm_calls += 1
            extras_result = llm_caller.call_by_id(writer_id,
                "Return valid JSON only. KEEP IT SHORT. 2 items max per field. COMPLETE every sentence.",
                extras_prompt, 4000, use_cache=False)
            time.sleep(1)

    if extras_result:
        extras = _parse_extras(extras_result)
        if extras:
            report.llm_successes += 1
            for key in ["key_unknowns", "watch_items", "predictions", "notable_details"]:
                if key in extras and extras[key]:
                    card[key] = extras[key]
        else:
            report.llm_failures += 1
    else:
        report.llm_failures += 1

    # Attach metadata
    card = _attach_metadata(card, lead_title, topics, selected_sources,
                           missing_perspectives, comparisons, investigation)
    card["written_by"] = LLM_CONFIGS[writer_id]["label"]
    report.items_out = 1
    return card, report


def _pick_writer(available, used_labels):
    """Always prefer ChatGPT for writing — it completes JSON most reliably.
    Don't skip it just because it was a comparator; writing is a different task."""
    writer_preference = ["chatgpt", "claude", "gemini", "grok"]
    for preferred in writer_preference:
        if preferred in available:
            return preferred
    return available[-1] if available else "gemini"


def _sanitize_text(text):
    """Remove garbled non-ASCII characters (e.g. Chinese mixed into English)."""
    if not isinstance(text, str):
        return text
    # Keep basic Latin, common punctuation, currency symbols
    cleaned = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u2018-\u201D\u2013\u2014\u2026\u20AC\u00A3]+', '', text)
    # Clean up double spaces from removals
    cleaned = re.sub(r'  +', ' ', cleaned).strip()
    return cleaned


def _sanitize_card(card):
    """Sanitize all string values in a card dict."""
    for key, val in card.items():
        if isinstance(val, str):
            card[key] = _sanitize_text(val)
        elif isinstance(val, list):
            sanitized = []
            for item in val:
                if isinstance(item, str):
                    sanitized.append(_sanitize_text(item))
                elif isinstance(item, dict):
                    sanitized.append({k: _sanitize_text(v) if isinstance(v, str) else v for k, v in item.items()})
                else:
                    sanitized.append(item)
            card[key] = sanitized
    return card


def _parse_core(result):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        card = json.loads(json_match.group() if json_match else cleaned)

        # Sanitize all string values — strip garbled non-ASCII
        card = _sanitize_card(card)

        if not isinstance(card.get("agreed_facts"), list):
            old = card.get("agreed_facts", "")
            card["agreed_facts"] = [l.strip() for l in old.split("\n") if l.strip()] if isinstance(old, str) else []

        # Fallback: if facts are empty, extract from what_happened
        if not card["agreed_facts"] and card.get("what_happened"):
            sentences = [s.strip() for s in card["what_happened"].split(".") if s.strip() and len(s.strip()) > 15]
            card["agreed_facts"] = [s + "." for s in sentences[:3]]

        if not isinstance(card.get("disputes"), list):
            card["disputes"] = []
        if not isinstance(card.get("framing"), list):
            card["framing"] = []
        for field in ["what_happened", "implications", "missing_viewpoints"]:
            if field not in card:
                card[field] = ""
        for field in ["key_unknowns", "watch_items", "predictions", "notable_details"]:
            if field not in card:
                card[field] = []
        return card
    except Exception as e:
        print("    Core parse error: {}".format(str(e)[:80]))
        return None


def _parse_extras(result):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        extras = json.loads(json_match.group() if json_match else cleaned)

        if "key_unknowns" in extras and isinstance(extras["key_unknowns"], list):
            normalized = []
            for item in extras["key_unknowns"]:
                if isinstance(item, str):
                    normalized.append({"question": item.strip(), "answer": "Not yet reported."})
                elif isinstance(item, dict):
                    normalized.append(item)
            extras["key_unknowns"] = normalized

        for field in ["watch_items", "predictions", "notable_details"]:
            if field in extras and not isinstance(extras[field], list):
                extras[field] = []
        return extras
    except Exception as e:
        print("    Extras parse error: {}".format(str(e)[:80]))
        return None


def _attach_metadata(card, title, topics, sources, missing, comparisons, investigation):
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
         "pub_date": getattr(s["article"], "published", ""),
         "source_type": _source_type(s["article"])}
        for s in sources
    ]
    card["missing_perspective_list"] = missing
    card["comparisons"] = comparisons
    card["investigation"] = investigation

    card["disagreements"] = "\n".join(
        "{}: {} vs {}".format(d.get("type", ""), d.get("side_a", ""), d.get("side_b", ""))
        for d in card["disputes"]) if card["disputes"] else "No substantive contradictions identified."
    card["framing_differences"] = "\n".join(
        "{}: \"{}\" - {}".format(f.get("source", ""), f.get("quote", ""), f.get("frame", ""))
        for f in card["framing"]) if card["framing"] else ""
    return card


def _fallback_card(result, title, topics, sources, missing, comparisons, investigation):
    clean_text = ""
    if result:
        clean_text = re.sub(r'[{}\[\]"\\]', '', result[:300]).strip()
        for field in ["what_happened", "agreed_facts", "disputes", "framing"]:
            clean_text = clean_text.replace(field, "").replace(":", " ").strip()

    card = {
        "what_happened": clean_text if clean_text else "Analysis could not be completed.",
        "agreed_facts": [], "disputes": [], "framing": [],
        "key_unknowns": [], "implications": "",
        "watch_items": [], "predictions": [], "notable_details": [],
        "missing_viewpoints": "", "disagreements": "", "framing_differences": "",
        "written_by": "fallback",
    }
    return _attach_metadata(card, title, topics, sources, missing, comparisons, investigation)


def _source_type(article):
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
