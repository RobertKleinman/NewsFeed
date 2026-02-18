"""
Step 9: Write topic cards — tiered by importance, field-by-field.

BRIEF (1-2★): summary + so_what only, from cluster data directly
STANDARD (3★): summary + facts + mode-appropriate analysis
DEEP (4-5★): full card with investigation impact

Each field is a separate LLM call to prevent truncation.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import TopicCard, StepReport


def run(ranked_story, selected_sources, missing_perspectives,
        comparison_result=None, investigation_result=None):
    """Write a topic card. Depth varies by tier. Returns (TopicCard, report)."""
    report = StepReport("write")
    cluster = ranked_story.cluster
    tier = ranked_story.depth_tier

    available = llm_caller.get_available_llms()
    writer_id = _pick_writer(available)

    card = TopicCard(
        title=cluster.lead_title,
        topics=cluster.topic_spread[:3],
        depth_tier=tier,
        importance=ranked_story.stars,
        importance_reason=ranked_story.importance_reason,
        source_count=cluster.size,
        missing_perspectives=missing_perspectives,
    )

    # Build source metadata
    card.sources = [
        {
            "name": s.article.source_name,
            "region": s.article.source_region,
            "bias": s.article.source_bias,
            "perspective": s.perspective,
            "angle": s.angle,
            "url": s.article.url,
            "pub_date": s.article.published,
        }
        for s in selected_sources
    ]

    if tier == "brief":
        _write_brief(card, cluster, writer_id, report)
    elif tier == "standard":
        _write_standard(card, cluster, selected_sources, comparison_result,
                       writer_id, report)
    else:  # deep
        _write_deep(card, cluster, selected_sources, comparison_result,
                   investigation_result, writer_id, report)

    card.written_by = LLM_CONFIGS[writer_id]["label"]
    _sanitize_card(card)
    report.items_out = 1
    return card, report


def _write_brief(card, cluster, writer_id, report):
    """Brief card: summary + so_what only. Minimal LLM usage."""
    # Build context from cluster headlines
    headlines = "\n".join(
        "- {} ({}): {}".format(a.source_name, a.source_region, a.title)
        for a in cluster.articles[:8])

    result = _call(writer_id,
        "EVENT: {}\n\nHEADLINES:\n{}".format(cluster.lead_title, headlines),
        "Write exactly 2 sentences. Sentence 1: what happened. Sentence 2: why it matters (the 'so what'). End each with a period.",
        "text", report)

    if result:
        parts = _split_summary(result)
        card.what_happened = parts[0]
        card.so_what = parts[1]
    else:
        card.what_happened = cluster.lead_title
    card.card_mode = "brief"


def _write_standard(card, cluster, sources, comparison, writer_id, report):
    """Standard card: summary + facts + mode-appropriate content."""
    context = _build_context(cluster, comparison)
    contention = comparison.contention_level if comparison else "straight_news"
    card.card_mode = contention

    # Summary
    result = _call(writer_id, context,
        "Write 2 sentences. Sentence 1: what happened (who, what, when). Sentence 2: why it matters. End each with a period.",
        "text", report)
    if result:
        parts = _split_summary(result)
        card.what_happened = parts[0]
        card.so_what = parts[1]

    # Facts You Should Know — ONLY things that add context beyond the summary
    facts = _call(writer_id, context,
        """List 3-5 key facts as a JSON array of strings.
CRITICAL: Do NOT repeat information already in this summary: "{summary}"
Only include facts that ADD new context: specific numbers, dates, names, background details, or consequences not covered in the summary.
If the summary already covers everything, return just 1-2 additional contextual facts.
Return: ["additional fact 1.", "additional fact 2."]""".format(
            summary=(card.what_happened + " " + card.so_what)[:200]),
        "json_array", report)
    if facts:
        card.agreed_facts = facts

    if contention == "contested":
        # Disputes
        disputes = _call(writer_id, context,
            'List real factual contradictions as JSON array. Each: {"type": "data", "side_a": "Claim. [Source]", "side_b": "Contradicting claim. [Source]"}. If none: return []',
            "json_array", report)
        if disputes:
            card.disputes = disputes

        # Framing/bias analysis
        framing = _call(writer_id, context,
            'For 2-3 sources, explain how their framing shapes reader beliefs. Return JSON: [{"source": "Name", "quote": "phrase", "frame": "What readers are led to think."}]',
            "json_array", report)
        if framing:
            card.framing = framing
    else:
        # Coverage note for straight news
        if card.missing_perspectives:
            card.coverage_note = "Coverage note: missing perspectives from {}.".format(
                ", ".join(card.missing_perspectives[:3]))

    # Fallback facts
    if not card.agreed_facts and card.what_happened:
        sentences = [s.strip() for s in card.what_happened.split(".") if s.strip() and len(s.strip()) > 15]
        card.agreed_facts = [s + "." for s in sentences[:3]]

    if comparison:
        card.comparisons = comparison.comparisons


def _write_deep(card, cluster, sources, comparison, investigation, writer_id, report):
    """Deep card: full analysis with investigation impact."""
    # Start with standard content
    _write_standard(card, cluster, sources, comparison, writer_id, report)

    # Add investigation impact (only if it adds value)
    if investigation and investigation.adds_value:
        card.investigation_impact = investigation.story_impact
        card.investigation_raw = investigation.raw_text

        # Investigation-informed extras
        context = _build_context(cluster, comparison)
        context += "\n\nINVESTIGATION FINDINGS:\n" + investigation.raw_text[:1500]

        extras = _call(writer_id, context,
            """Based on the investigation findings, return JSON:
{{
  "key_unknowns": [{{"question": "Gap in coverage.", "answer": "What investigation found."}}],
  "predictions": [{{"scenario": "Likely development.", "likelihood": "likely", "condition": "Trigger."}}]
}}
2-3 items max per field. Complete sentences.""",
            "json_object", report, max_tokens=2000)

        if extras and isinstance(extras, dict):
            for key in ["key_unknowns", "predictions"]:
                if key in extras and isinstance(extras[key], list):
                    setattr(card, key, extras[key])
    elif investigation:
        # Investigation ran but didn't add value — note that
        card.investigation_raw = investigation.raw_text
        card.coverage_note = (card.coverage_note + " " if card.coverage_note else "") + \
            "Investigation confirmed coverage is substantially accurate."


def _build_context(cluster, comparison):
    """Build shared context string for LLM calls."""
    sources_summary = "\n".join(
        "- {} ({}, {})".format(a.source_name, a.source_region, a.source_bias)
        for a in cluster.articles[:8])

    comp_text = ""
    if comparison and comparison.comparisons:
        sections = []
        for model, text in comparison.comparisons.items():
            sections.append("--- {} ---\n{}".format(model, text))
        comp_text = "\n\n".join(sections)

    return "EVENT: {title}\nSOURCES:\n{sources}\n\nCOMPARISONS:\n{comp}".format(
        title=cluster.lead_title,
        sources=sources_summary,
        comp=comp_text[:3000])


def _split_summary(text):
    """Split a 2-sentence text into what_happened and so_what."""
    sentences = [s.strip() for s in text.split(".") if s.strip() and len(s.strip()) > 10]
    if len(sentences) >= 2:
        return sentences[0] + ".", ". ".join(sentences[1:]) + "."
    return text, ""


def _call(writer_id, context, instruction, output_type, report, max_tokens=1500):
    """Single field LLM call. Returns parsed content or None."""
    prompt = "{}\n\n{}".format(context, instruction)
    report.llm_calls += 1
    result = llm_caller.call_by_id(writer_id,
        "News editor. Use ONLY provided facts. Return ONLY requested output. Every sentence ends with a period.",
        prompt, max_tokens)
    time.sleep(0.5)

    if not result:
        report.llm_failures += 1
        return None
    report.llm_successes += 1

    result = result.strip()
    result = re.sub(r'```json\s*', '', result)
    result = re.sub(r'```\s*', '', result).strip()

    if output_type == "text":
        return result.strip('"').strip("'") or None
    elif output_type == "json_array":
        try:
            m = re.search(r'\[.*\]', result, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                return parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, ValueError):
            pass
        return None
    elif output_type == "json_object":
        try:
            m = re.search(r'\{.*\}', result, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
        return None
    return None


def _pick_writer(available):
    for pref in ["chatgpt", "claude", "gemini", "grok"]:
        if pref in available:
            return pref
    return available[-1] if available else "gemini"


def _sanitize_card(card):
    """Clean non-ASCII artifacts from all string fields."""
    for field_name in ["what_happened", "so_what", "coverage_note",
                       "investigation_impact", "investigation_raw"]:
        val = getattr(card, field_name, "")
        if isinstance(val, str):
            setattr(card, field_name, _sanitize_text(val))

    for field_name in ["agreed_facts", "notable_details"]:
        val = getattr(card, field_name, [])
        if isinstance(val, list):
            setattr(card, field_name, [
                _sanitize_text(item) if isinstance(item, str) else
                {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in item.items()}
                if isinstance(item, dict) else item
                for item in val
            ])

    for field_name in ["disputes", "framing", "key_unknowns", "predictions"]:
        val = getattr(card, field_name, [])
        if isinstance(val, list):
            setattr(card, field_name, [
                {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in item.items()}
                if isinstance(item, dict) else item
                for item in val
            ])


def _sanitize_text(text):
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u2018-\u201D\u2013\u2014\u2026\u20AC\u00A3]+', '', text)
    return re.sub(r'  +', ' ', cleaned).strip()
