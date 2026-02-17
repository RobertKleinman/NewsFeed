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
    """Attempt to repair truncated fields one at a time."""
    truncated_fields = set()
    for issue in issues:
        if issue["type"] == "truncation":
            base_field = issue["field"].split("[")[0].strip()
            truncated_fields.add(base_field)

    if not truncated_fields:
        return card, 0

    available = llm_caller.get_available_llms()
    writer_preference = ["chatgpt", "gemini", "claude", "grok"]
    writer_id = None
    for preferred in writer_preference:
        if preferred in available:
            writer_id = preferred
            break
    if not writer_id:
        return card, 0

    fixed = 0
    for field_name in truncated_fields:
        current = card.get(field_name, "")
        if isinstance(current, list):
            current_text = json.dumps(current, indent=1)[:400]
        elif isinstance(current, str):
            current_text = current[:400]
        else:
            continue

        prompt = """This text was cut off mid-sentence. Complete it.

STORY: {title}
FIELD: {field}
CURRENT (TRUNCATED):
{current}

Return ONLY the completed version of this field. If it's a JSON array, return the complete array.
If it's a string, return the complete string. COMPLETE every sentence. Do not add unrelated content.""".format(
            title=card.get("title", "")[:80],
            field=field_name,
            current=current_text)

        result = llm_caller.call_by_id(writer_id,
            "Complete the truncated text. Return only the fixed content. No markdown.",
            prompt, 2000)
        time.sleep(0.5)

        if not result:
            continue

        try:
            result = result.strip()
            # Try parsing as JSON first (for list fields)
            if isinstance(current, list):
                cleaned = re.sub(r'```json\s*', '', result)
                cleaned = re.sub(r'```\s*', '', cleaned).strip()
                m = re.search(r'\[.*\]', cleaned, re.DOTALL)
                if m:
                    repaired = json.loads(m.group())
                    if isinstance(repaired, list) and len(repaired) > 0:
                        if not _check_list_truncation(repaired):
                            card[field_name] = repaired
                            fixed += 1
            elif isinstance(current, str):
                # Accept any complete result (not truncated)
                cleaned = result.strip().strip('"').strip("'")
                # Remove JSON wrapper if present
                cleaned = re.sub(r'```json\s*', '', cleaned)
                cleaned = re.sub(r'```\s*', '', cleaned).strip()
                if cleaned and not _is_truncated(cleaned) and len(cleaned) > 20:
                    card[field_name] = cleaned
                    fixed += 1
        except Exception as e:
            print("      Repair error on {}: {}".format(field_name, str(e)[:50]))
            continue

    return card, fixed


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
