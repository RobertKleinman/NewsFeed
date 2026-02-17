"""
Step 9c: Repair — detect and fix mechanical issues in topic cards.
Runs after write, before enrich. No LLM calls for detection;
optional LLM call to regenerate truncated fields.
"""

import json
import re
import time

import llm as llm_caller
from models import StepReport


def _is_truncated(text):
    """Check if text appears to be cut off mid-sentence."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 20:
        return False
    # Ends mid-word (no space before end, no punctuation)
    if text[-1].isalpha() and text[-1].islower():
        return True
    # Ends with comma, colon, or opening bracket
    if text[-1] in [',', ':', '(', '[', '{', '-']:
        return True
    # Ends with common truncation patterns
    truncation_endings = [' the', ' a', ' an', ' of', ' in', ' to', ' for',
                         ' and', ' or', ' is', ' was', ' that', ' with',
                         ' at', ' by', ' on', ' from']
    for ending in truncation_endings:
        if text.endswith(ending):
            return True
    return False


def _check_list_truncation(items):
    """Check if any items in a list are truncated."""
    truncated = []
    if not isinstance(items, list):
        return truncated
    for i, item in enumerate(items):
        if isinstance(item, str) and _is_truncated(item):
            truncated.append(i)
        elif isinstance(item, dict):
            for key, val in item.items():
                if isinstance(val, str) and _is_truncated(val):
                    truncated.append(i)
                    break
    return truncated


def _detect_issues(card):
    """Scan a card for mechanical issues. Returns list of issue dicts."""
    issues = []

    # Check string fields for truncation
    for field in ["what_happened", "implications", "missing_viewpoints", "investigation"]:
        text = card.get(field, "")
        if _is_truncated(text):
            issues.append({
                "type": "truncation",
                "field": field,
                "severity": "error",
                "detail": "Text cut off: '...{}'".format(text[-30:])
            })

    # Check list fields
    for field in ["agreed_facts", "framing", "predictions", "watch_items", "notable_details"]:
        items = card.get(field, [])
        truncated_indices = _check_list_truncation(items)
        for idx in truncated_indices:
            issues.append({
                "type": "truncation",
                "field": "{} [{}]".format(field, idx),
                "severity": "error",
                "detail": "List item {} truncated".format(idx)
            })

    # Check key_unknowns Q&A format
    unknowns = card.get("key_unknowns", [])
    for i, u in enumerate(unknowns):
        if isinstance(u, dict):
            for key in ["question", "answer"]:
                if _is_truncated(u.get(key, "")):
                    issues.append({
                        "type": "truncation",
                        "field": "key_unknowns[{}].{}".format(i, key),
                        "severity": "error",
                        "detail": "Q&A {} truncated".format(key)
                    })

    # Check disputes
    for i, d in enumerate(card.get("disputes", [])):
        if isinstance(d, dict):
            for side in ["side_a", "side_b"]:
                if _is_truncated(d.get(side, "")):
                    issues.append({
                        "type": "truncation",
                        "field": "disputes[{}].{}".format(i, side),
                        "severity": "error",
                        "detail": "Dispute side truncated"
                    })

    # Check for empty required fields
    if not card.get("agreed_facts"):
        issues.append({
            "type": "empty",
            "field": "agreed_facts",
            "severity": "warning",
            "detail": "No confirmed facts"
        })

    if not card.get("what_happened"):
        issues.append({
            "type": "empty",
            "field": "what_happened",
            "severity": "error",
            "detail": "Missing what happened summary"
        })

    return issues


def _repair_truncation(card, issues):
    """Attempt to repair truncated fields by re-calling the writer."""
    truncated_fields = set()
    for issue in issues:
        if issue["type"] == "truncation":
            base_field = issue["field"].split("[")[0].strip()
            truncated_fields.add(base_field)

    if not truncated_fields:
        return card, 0

    # Build repair prompt with just the truncated content
    repair_sections = []
    for field in truncated_fields:
        current = card.get(field, "")
        if isinstance(current, list):
            current = json.dumps(current)[:200]
        elif isinstance(current, str):
            current = current[:200]
        repair_sections.append("{}: {}...".format(field, current))

    prompt = """The following sections of a news analysis card were truncated mid-sentence.
Rewrite ONLY these sections, completing them properly. Return valid JSON with just these fields.

STORY: {title}

TRUNCATED SECTIONS:
{sections}

Return a JSON object with ONLY the truncated fields, completed properly.
Every sentence must be complete. Every list item must be complete.
Do not add new fields. Just fix what was cut off.""".format(
        title=card.get("title", "")[:80],
        sections="\n".join(repair_sections))

    available = llm_caller.get_available_llms()
    # Use same preference as writer
    writer_preference = ["chatgpt", "gemini", "claude", "grok"]
    writer_id = None
    for preferred in writer_preference:
        if preferred in available:
            writer_id = preferred
            break
    if not writer_id:
        return card, 0

    result = llm_caller.call_by_id(writer_id,
        "Complete truncated text. Return valid JSON only. Complete every sentence.",
        prompt, 2000)

    if not result:
        return card, 0

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        repairs = json.loads(m.group() if m else cleaned)

        fixed = 0
        for field, value in repairs.items():
            if field in truncated_fields and value:
                # Only accept if the repair is longer and not itself truncated
                old = card.get(field, "")
                if isinstance(value, str) and isinstance(old, str):
                    if len(value) >= len(old) and not _is_truncated(value):
                        card[field] = value
                        fixed += 1
                elif isinstance(value, list) and isinstance(old, list):
                    if not _check_list_truncation(value):
                        card[field] = value
                        fixed += 1
        return card, fixed
    except Exception as e:
        print("    Repair parse error: {}".format(str(e)[:60]))
        return card, 0


def run(topic_cards):
    """Detect and repair issues in all cards. Returns report."""
    print("\n>>> REPAIR CHECK...")
    report = StepReport("repair", items_in=len(topic_cards))

    total_issues = 0
    total_fixed = 0

    for i, card in enumerate(topic_cards):
        issues = _detect_issues(card)
        card["_repair_issues"] = len(issues)

        if issues:
            total_issues += len(issues)
            trunc_count = sum(1 for iss in issues if iss["type"] == "truncation")

            if trunc_count > 0:
                report.llm_calls += 1
                card, fixed = _repair_truncation(card, issues)
                total_fixed += fixed
                if fixed > 0:
                    report.llm_successes += 1
                    print("    Card {}: {} issues, {} repaired".format(i + 1, len(issues), fixed))
                else:
                    print("    Card {}: {} issues, repair failed".format(i + 1, len(issues)))
            else:
                print("    Card {}: {} non-truncation issues".format(i + 1, len(issues)))

    report.items_out = total_fixed
    report.notes.append("{} issues found, {} repaired".format(total_issues, total_fixed))
    print("    Total: {} issues, {} repaired".format(total_issues, total_fixed))
    return report
