"""
Step 10c: Quality validation using Claude.
Reviews each topic card for common issues and produces structured
quality data for the review panel.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def run(topic_cards):
    """Review all cards for quality issues. Returns (review_data, report)."""
    print("\n>>> QUALITY REVIEW...")
    report = StepReport("validate", items_in=len(topic_cards))

    # Check if Claude is available
    if "claude" not in llm_caller.get_available_llms():
        print("    Claude not available, skipping quality review")
        return {"reviews": [], "summary": "Quality review skipped (no Claude API key)"}, report

    reviews = []
    error_count = 0
    warning_count = 0
    note_count = 0

    for i, card in enumerate(topic_cards):
        review = _review_card(card, i)
        if review:
            reviews.append(review)
            for issue in review.get("issues", []):
                sev = issue.get("severity", "note")
                if sev == "error":
                    error_count += 1
                elif sev == "warning":
                    warning_count += 1
                else:
                    note_count += 1
            report.llm_successes += 1
        else:
            report.llm_failures += 1
        report.llm_calls += 1
        time.sleep(1)

    summary = "{} cards reviewed: {} errors, {} warnings, {} notes".format(
        len(topic_cards), error_count, warning_count, note_count)
    print("    " + summary)

    report.items_out = len(reviews)
    return {
        "reviews": reviews,
        "summary": summary,
        "error_count": error_count,
        "warning_count": warning_count,
        "note_count": note_count
    }, report


def _review_card(card, card_index):
    """Send one card to Claude for quality review."""
    title = card.get("title", "Untitled")

    # Build compact card summary for review
    card_summary = """CARD {idx}: {title}
Writer: {writer}
Sources: {src_count}

WHAT HAPPENED: {what}

CONFIRMED FACTS: {facts}

DISPUTES: {disputes}

FRAMING: {framing}

PREDICTIONS: {preds}

INVESTIGATION: {invest}""".format(
        idx=card_index + 1,
        title=title,
        writer=card.get("written_by", "unknown"),
        src_count=card.get("source_count", 0),
        what=card.get("what_happened", "")[:300],
        facts=json.dumps(card.get("agreed_facts", []))[:500],
        disputes=json.dumps(card.get("disputes", []))[:500],
        framing=json.dumps(card.get("framing", []))[:500],
        preds=json.dumps(card.get("predictions", []))[:400],
        invest=(card.get("investigation", "") or "")[:300])

    prompt = """Review this news briefing card for quality issues. Return ONLY valid JSON.

{card}

Check for these specific problems:
1. FAKE DISPUTES: Are the "disputes" actually contradictions, or just different facts about different aspects? Two cities reporting different crowd sizes is NOT a dispute. Different sources covering different angles is NOT a dispute.
2. FRAMING MISATTRIBUTION: Are "framing" quotes from the outlet's own editorial angle, or from people quoted WITHIN the article? If a source quotes a politician, the framing is the politician's, not the outlet's.
3. IRRELEVANT PREDICTIONS: Does this story type warrant predictions? Cultural events, human interest, single-event stories usually don't need scenario forecasting.
4. MISSING CONTEXT: Does the investigation provide enough background for a reader to understand why this matters? Are well-known triggering events mentioned?
5. TRUNCATED TEXT: Any text that appears cut off mid-sentence or mid-word?
6. REDUNDANCY: Do sections repeat the same information?
7. VAGUE ENTRIES: Are facts, disputes, or framing entries too vague to be useful?

Return:
{{
  "card_index": {idx},
  "card_title": "{title_esc}",
  "quality_score": 1-10,
  "issues": [
    {{
      "severity": "error OR warning OR note",
      "section": "disputes OR framing OR predictions OR investigation OR facts OR general",
      "problem": "Brief description of what's wrong",
      "suggestion": "How to fix it"
    }}
  ],
  "strengths": "What this card does well (1 sentence)"
}}""".format(
        card=card_summary,
        idx=card_index + 1,
        title_esc=title.replace('"', '\\"')[:60])

    result = llm_caller.call_by_id("claude",
        "You are a quality reviewer for a news intelligence briefing. Be specific and actionable. Return valid JSON only.",
        prompt, 800, use_cache=False)

    if not result:
        return None

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        data["card_index"] = card_index + 1
        data["card_title"] = title[:80]
        return data
    except Exception as e:
        print("    Review parse error card {}: {}".format(card_index + 1, str(e)[:60]))
        return None
