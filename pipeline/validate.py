"""
Quality validation — mechanical checks only. No LLM reviewer.
"""

from models import StepReport


def run(topic_cards):
    """Run mechanical quality checks. Returns (summary, report)."""
    report = StepReport("validate", items_in=len(topic_cards))
    errors = 0
    warnings = 0

    for i, card in enumerate(topic_cards):
        issues = []

        if not card.what_happened or len(card.what_happened) < 20:
            issues.append("ERROR: what_happened empty/short")
            errors += 1

        if card.depth_tier != "brief" and not card.agreed_facts:
            issues.append("ERROR: no facts (non-brief card)")
            errors += 1

        if card.card_mode == "contested" and not card.disputes and not card.framing:
            issues.append("WARNING: contested but no disputes/framing")
            warnings += 1

        if issues:
            print("    Card {}: {}".format(i + 1, "; ".join(issues)))

    report.items_out = len(topic_cards)
    summary = {
        "errors": errors,
        "warnings": warnings,
        "summary": "{} cards, {} errors, {} warnings".format(
            len(topic_cards), errors, warnings),
    }
    print("    {} cards: {} errors, {} warnings".format(len(topic_cards), errors, warnings))
    return summary, report
