"""
Step 9: Write topic cards — restructured around reader questions.

Card structure:
  WHY THIS MATTERS — direct impact / world-shaping / cultural gravity
  WHAT'S HAPPENING — concrete situation right now
  HOW IT'S BEING USED — spin detection + predicted use (contested only)
  WHAT YOU NEED TO KNOW — facts + context + history + unknowns (Q&A)
  BIGGER PICTURE — second/third order effects
  WHAT YOU CAN DO — actionable items (when applicable)

Tiers control depth:
  BRIEF: why_matters + whats_happening only
  STANDARD: + key_facts + context + unknowns + bigger_picture
  DEEP: + spin analysis + spin predictions + actions + full investigation
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import TopicCard, StepReport


def run(ranked_story, selected_sources, missing_perspectives,
        comparison_result=None, investigation_result=None):
    """Write a topic card. Returns (TopicCard, report)."""
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

    # Bridge to legacy fields for backward compat
    card.what_happened = card.whats_happening
    card.so_what = card.why_matters
    card.agreed_facts = card.key_facts
    card.key_unknowns = [{"question": u.get("q", ""), "answer": u.get("a", "")} for u in card.unknowns]

    report.items_out = 1
    return card, report


# ── BRIEF ─────────────────────────────────────────────────────────────────

def _write_brief(card, cluster, writer_id, report):
    """Brief card: why_matters + whats_happening only."""
    headlines = "\n".join(
        "- {} ({}): {}".format(a.source_name, a.source_region, a.title)
        for a in cluster.articles[:8])

    result = _call(writer_id,
        "EVENT: {}\n\nHEADLINES:\n{}".format(cluster.lead_title, headlines),
        """Write two sections. Return JSON:
{{
  "whats_happening": "2-3 sentences. What is concretely happening right now. Who did what, where, when. No analysis.",
  "why_matters": "1-2 sentences. Why should someone care? Cover: direct impact on people's lives OR world-shaping significance OR cultural gravity (everyone will be talking about this). Be specific, not generic.",
  "why_today": "1 sentence. Why this is urgent or decision-relevant today. Concrete trigger or timing only."
}}""",
        "json_object", report)

    if result and isinstance(result, dict):
        card.whats_happening = result.get("whats_happening", "")
        card.why_matters = result.get("why_matters", "")
        card.why_today = result.get("why_today", "")
    else:
        card.whats_happening = cluster.lead_title
    card.card_mode = "brief"


# ── STANDARD ──────────────────────────────────────────────────────────────

def _write_standard(card, cluster, sources, comparison, writer_id, report):
    """Standard card: situation + facts + context + unknowns + spin + bigger picture."""
    context = _build_context(cluster, comparison)
    contention = comparison.contention_level if comparison else "straight_news"
    card.card_mode = contention

    # WHY THIS MATTERS + WHAT'S HAPPENING
    result = _call(writer_id, context,
        """Write two sections. Return JSON:
{{
  "whats_happening": "2-4 sentences. Concrete situation right now. Who did what, where, when. Current state of play. Draw from all sources. No analysis — just what's happening.",
  "why_matters": "2-3 sentences. Why should someone care about this? Address whichever apply: (1) Direct impact — does this affect people's money, rights, safety, or daily life? (2) World-shaping — is this changing power dynamics, could it lead to conflict, is it a turning point? (3) Cultural gravity — will everyone be talking about this, will it shape opinions and decisions? Be specific and concrete, not generic.",
  "why_today": "1 sentence. Why this matters specifically today (deadline, vote, markets open, expected move, immediate risk)."
}}""",
        "json_object", report)

    if result and isinstance(result, dict):
        card.whats_happening = result.get("whats_happening", "")
        card.why_matters = result.get("why_matters", "")
        card.why_today = result.get("why_today", "")

    # HOW IT'S BEING USED — ask LLM directly whether spin exists
    # Don't rely on compare step's contention detection
    spin = _call(writer_id, context,
        """Analyze whether different groups are framing this story to serve different agendas.

THIS IS NOT about minor editorial differences. Only return positions if there are GENUINELY COMPETING POLITICAL AGENDAS at play — groups using this story to advance opposing goals.

Examples of real spin:
- Israel/Palestine: pro-Israel sources frame actions as security; critics frame them as occupation
- Climate policy: supporters frame repeal as economic freedom; opponents frame as environmental destruction
- Military action: hawks frame as necessary deterrence; doves frame as dangerous escalation

Examples that are NOT spin (do not return positions for these):
- A natural disaster reported from different angles
- A court sentencing reported by different outlets with same framing
- Different levels of detail in coverage

Return JSON:
{{
  "is_contested": true or false,
  "contested_reason": "One sentence explaining WHY this is contested. E.g., 'Framing of military action differs between US administration supporters and critics.'",
  "positions": [
    {{
      "position": "One-line description of this side's stance",
      "who": "Who holds this position (be specific: 'Israeli government officials', not 'one side')",
      "key_claim": "The main factual claim they use to support their position",
      "verified": "Verified / Partially verified / Unverified — with brief explanation"
    }}
  ],
  "watch_for": [
    {{
      "prediction": "How this story will likely be used or spun going forward. Be specific.",
      "confidence": "likely or speculative"
    }}
  ]
}}

If this story is NOT being used to push competing agendas: {{"is_contested": false, "contested_reason": "", "positions": [], "watch_for": []}}
2-3 positions max. 2-3 watch_for max.""",
        "json_object", report, max_tokens=2500)

    if spin and isinstance(spin, dict):
        is_contested = spin.get("is_contested", False)
        positions = spin.get("positions", [])
        if is_contested and positions and isinstance(positions, list) and len(positions) >= 2:
            card.spin_positions = positions
            card.card_mode = "contested"
            card.contested_reason = spin.get("contested_reason", "")
            watch = spin.get("watch_for", [])
            if watch and isinstance(watch, list):
                card.spin_predictions = watch

    # WHAT YOU NEED TO KNOW: key facts
    summary_so_far = (card.whats_happening + " " + card.why_matters)[:300]
    facts = _call(writer_id, context,
        """List 3-5 key facts the reader needs to know. Return JSON array of strings.
CRITICAL: Do NOT repeat information already covered here: "{summary}"
Only include facts that ADD context: specific numbers, names, dates, background, consequences.
Return: ["fact 1.", "fact 2."]""".format(summary=summary_so_far),
        "json_array", report)
    if facts:
        card.key_facts = facts

    # WHAT YOU NEED TO KNOW: unknowns (Q&A) — capped at 3
    unknowns = _call(writer_id, context,
        """Identify 2-3 important questions this coverage does NOT answer. Maximum 3.
Return JSON: [{{"q": "Important unanswered question?", "a": "What we know so far, or 'Not yet reported.' if nothing."}}]
Focus on gaps that would change how a reader understands this story.""",
        "json_array", report)
    if unknowns:
        card.unknowns = unknowns[:3]

    # BIGGER PICTURE
    bigger = _call(writer_id, context,
        """Where is this story heading? Write 2-3 sentences about second and third order effects.
Think: what happens next, who else is affected, what chain reactions could this trigger?
Connect to broader trends when relevant. Be specific.""",
        "text", report)
    if bigger:
        card.bigger_picture = bigger

    # Fallback
    if not card.key_facts and card.whats_happening:
        sentences = [s.strip() for s in card.whats_happening.split(".") if s.strip() and len(s.strip()) > 15]
        card.key_facts = [s + "." for s in sentences[:3]]

    if comparison:
        card.comparisons = comparison.comparisons


# ── DEEP ──────────────────────────────────────────────────────────────────

def _write_deep(card, cluster, sources, comparison, investigation, writer_id, report):
    """Deep card: full analysis including investigation and per-card predictions."""
    # Standard content (includes spin detection)
    _write_standard(card, cluster, sources, comparison, writer_id, report)

    context = _build_context(cluster, comparison)

    # Add investigation findings to WHAT YOU NEED TO KNOW
    if investigation and investigation.adds_value:
        card.investigation_impact = investigation.story_impact
        card.investigation_raw = investigation.raw_text

        # Extract context and history from investigation
        inv_context = context + "\n\nINVESTIGATION FINDINGS:\n" + investigation.raw_text[:2000]

        extras = _call(writer_id, inv_context,
            """Based on the investigation findings, extract additional context for the reader.
Return JSON:
{{
  "research_context": ["Important context from research that readers need. Label each as coming from research.", "Another piece of context."],
  "historical_context": ["Relevant historical background that helps understand this story."],
  "unknowns_answered": [{{"q": "Question the coverage left open", "a": "What investigation found."}}],
  "actions": ["Concrete action the reader could take based on this story. Only include if genuinely actionable."],
  "why_today": "Optional one-line urgency update for today only; empty string if no new urgency."
}}
Be concise. 2-3 items max per field. Empty arrays are fine if nothing fits.""",
            "json_object", report, max_tokens=2500)

        if extras and isinstance(extras, dict):
            # Merge research context into card.context
            research = extras.get("research_context", [])
            if research and isinstance(research, list):
                card.context = research

            # Merge historical context
            history = extras.get("historical_context", [])
            if history and isinstance(history, list):
                card.history = history

            # Add answered unknowns to the unknowns list
            answered = extras.get("unknowns_answered", [])
            if answered and isinstance(answered, list):
                card.unknowns.extend(answered)

            # Actions
            actions = extras.get("actions", [])
            if actions and isinstance(actions, list):
                card.actions = [a for a in actions if a.strip()]

            why_today = extras.get("why_today", "")
            if isinstance(why_today, str) and why_today.strip():
                card.why_today = why_today.strip()

    elif investigation:
        card.investigation_raw = investigation.raw_text
        card.coverage_note = (card.coverage_note + " " if card.coverage_note else "") + \
            "Investigation confirmed coverage is substantially accurate."


# ── Helpers ───────────────────────────────────────────────────────────────

def _is_politically_significant(cluster):
    """Check if story topics suggest political spin is likely."""
    political_topics = {"world_politics", "us_politics", "canadian_politics",
                       "climate_energy", "data_privacy_governance"}
    return bool(set(cluster.topic_spread) & political_topics)


def _build_context(cluster, comparison):
    """Build shared context string for LLM calls."""
    sources_summary = "\n".join(
        "- {} ({}, {})".format(a.source_name, a.source_region, a.source_bias)
        for a in cluster.articles[:10])

    headlines = "\n".join(
        "- {}: {}".format(a.source_name, a.title[:100])
        for a in cluster.articles[:10])

    comp_text = ""
    if comparison and comparison.comparisons:
        sections = []
        for model, text in comparison.comparisons.items():
            sections.append("--- {} ---\n{}".format(model, text))
        comp_text = "\n\n".join(sections)

    return "EVENT: {title}\n\nSOURCES:\n{sources}\n\nHEADLINES:\n{headlines}\n\nCOMPARISONS:\n{comp}".format(
        title=cluster.lead_title,
        sources=sources_summary,
        headlines=headlines,
        comp=comp_text[:3000])


def _call(writer_id, context, instruction, output_type, report, max_tokens=1500):
    """Single field LLM call. Returns parsed content or None."""
    prompt = "{}\n\n{}".format(context, instruction)
    report.llm_calls += 1
    result = llm_caller.call_by_id(writer_id,
        "Intelligence analyst writing a briefing. Use ONLY provided facts. Return ONLY requested output. Every sentence ends with a period.",
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
    for field_name in ["whats_happening", "why_matters", "bigger_picture",
                       "what_happened", "so_what", "coverage_note",
                       "investigation_impact", "investigation_raw"]:
        val = getattr(card, field_name, "")
        if isinstance(val, str):
            setattr(card, field_name, _sanitize_text(val))

    for field_name in ["key_facts", "context", "history", "actions",
                       "agreed_facts", "notable_details"]:
        val = getattr(card, field_name, [])
        if isinstance(val, list):
            setattr(card, field_name, [
                _sanitize_text(item) if isinstance(item, str) else
                {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in item.items()}
                if isinstance(item, dict) else item
                for item in val
            ])

    for field_name in ["spin_positions", "spin_predictions", "unknowns",
                       "disputes", "framing", "key_unknowns", "predictions"]:
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
