"""
Component Testing Framework for Global Briefing v2.

Tests each pipeline component in isolation using cached data from real runs.
Each component has:
  - Sample input (from briefing_data.json)
  - Quality criteria (specific, measurable checks)
  - Optimization loop (try prompt variations, score, keep best)
  - Pass threshold

Usage:
  python test_components.py                    # Test all components
  python test_components.py --component write  # Test one component
  python test_components.py --optimize write   # Optimize write prompts
  python test_components.py --story 3          # Test with specific story index

Requires: API keys as environment variables, briefing_data.json in output/
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
import llm as llm_caller
from config import LLM_CONFIGS


def load_cached_data(path="output/briefing_data.json"):
    """Load cached briefing data from a previous run."""
    p = Path(path)
    if not p.exists():
        print("ERROR: No cached data at {}".format(path))
        print("Run the full pipeline first to generate test data.")
        sys.exit(1)
    with open(p) as f:
        return json.load(f)


def score_with_claude(content, criteria, max_tokens=600):
    """Use Claude to score content against specific criteria."""
    if "claude" not in llm_caller.get_available_llms():
        print("  Claude not available for scoring")
        return None

    prompt = """Score this content against quality criteria. Return ONLY valid JSON.

CONTENT:
{content}

CRITERIA:
{criteria}

Return:
{{
  "score": 1-10,
  "passed": [list of criteria that passed],
  "failed": [list of criteria that failed with brief reason],
  "suggestions": ["specific improvement suggestion"]
}}""".format(content=content[:2000], criteria=criteria)

    result = llm_caller.call_by_id("claude",
        "You are a quality scorer. Be strict. Return valid JSON only.",
        prompt, max_tokens, use_cache=False)

    if not result:
        return None
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        return json.loads(m.group() if m else cleaned)
    except Exception:
        return None


# ============================================================
# COMPONENT TESTS
# ============================================================

def test_write_core(card_data, verbose=True):
    """Test: Does the write step produce complete, non-truncated core fields?"""
    criteria = """
1. COMPLETENESS: Every sentence ends with proper punctuation (. ! ?). No mid-word cutoffs.
2. FACTS NOT EMPTY: agreed_facts has at least 2 entries.
3. NO REDUNDANCY: what_happened and agreed_facts contain different information.
4. FRAMING IS INSIGHTFUL: framing entries explain what the angle REVEALS, not just describe coverage.
5. DISPUTES ARE REAL: Any disputes are genuine contradictions, not just different coverage angles.
6. ALL JSON VALID: Every field is properly formatted."""

    issues = []
    score = 10

    # Check truncation in string fields
    for field in ["what_happened", "implications", "missing_viewpoints", "investigation"]:
        text = card_data.get(field, "")
        if text and _is_truncated(text):
            issues.append("TRUNCATED: {} ends with '...{}'".format(field, text[-20:]))
            score -= 2

    # Check truncation in list fields
    for field in ["agreed_facts", "framing", "predictions", "disputes"]:
        items = card_data.get(field, [])
        for i, item in enumerate(items):
            text = json.dumps(item) if isinstance(item, dict) else str(item)
            if _is_truncated(text):
                issues.append("TRUNCATED: {}[{}]".format(field, i))
                score -= 1

    # Check facts not empty
    if not card_data.get("agreed_facts"):
        issues.append("EMPTY: agreed_facts is empty")
        score -= 2

    # Check redundancy
    what = card_data.get("what_happened", "").lower()
    facts = " ".join(str(f) for f in card_data.get("agreed_facts", [])).lower()
    if what and facts:
        what_words = set(what.split())
        facts_words = set(facts.split())
        overlap = len(what_words & facts_words) / max(len(what_words), 1)
        if overlap > 0.6:
            issues.append("REDUNDANT: what_happened and facts overlap {:.0%}".format(overlap))
            score -= 1

    score = max(1, score)

    if verbose:
        print("  Write Core: {}/10".format(score))
        for issue in issues:
            print("    - {}".format(issue))

    return {"component": "write_core", "score": score, "issues": issues,
            "title": card_data.get("title", "")[:60]}


def test_write_extras(card_data, verbose=True):
    """Test: Does the extras pass produce complete, relevant content?"""
    issues = []
    score = 10

    # Check predictions relevance
    preds = card_data.get("predictions", [])
    topics = card_data.get("topics", [])
    is_soft = any(t in ["culture_good_news"] for t in topics)
    if is_soft and preds:
        issues.append("IRRELEVANT: Predictions on a cultural/human interest story")
        score -= 2
    if not is_soft and not preds:
        issues.append("MISSING: No predictions for a hard news story")
        score -= 1

    # Check key_unknowns format
    unknowns = card_data.get("key_unknowns", [])
    for i, u in enumerate(unknowns):
        if isinstance(u, dict):
            if not u.get("answer") or u.get("answer") == "Not yet reported.":
                pass  # Acceptable
            elif _is_truncated(u.get("answer", "")):
                issues.append("TRUNCATED: key_unknowns[{}].answer".format(i))
                score -= 1

    # Check truncation in extras
    for field in ["predictions", "watch_items", "notable_details"]:
        items = card_data.get(field, [])
        for i, item in enumerate(items):
            text = json.dumps(item) if isinstance(item, dict) else str(item)
            if _is_truncated(text):
                issues.append("TRUNCATED: {}[{}]".format(field, i))
                score -= 1

    score = max(1, score)

    if verbose:
        print("  Write Extras: {}/10".format(score))
        for issue in issues:
            print("    - {}".format(issue))

    return {"component": "write_extras", "score": score, "issues": issues,
            "title": card_data.get("title", "")[:60]}


def test_framing_quality(card_data, verbose=True):
    """Test: Is framing analysis insightful and properly attributed?"""
    issues = []
    score = 10

    framing = card_data.get("framing", [])
    if not framing:
        if verbose:
            print("  Framing: N/A (no framing entries)")
        return {"component": "framing", "score": 5, "issues": ["No framing entries"],
                "title": card_data.get("title", "")[:60]}

    obvious_phrases = ["emphasizes", "focuses on", "highlights", "covers",
                       "reports on", "discusses", "addresses", "examines"]

    for i, f in enumerate(framing):
        if not isinstance(f, dict):
            continue
        frame = f.get("frame", "")
        quote = f.get("quote", "")

        # Check for obvious/vague framing
        if any(phrase in frame.lower() for phrase in obvious_phrases) and "reveals" not in frame.lower():
            issues.append("VAGUE: framing[{}] uses obvious language without insight".format(i))
            score -= 1

        # Check for truncation
        if _is_truncated(frame) or _is_truncated(quote):
            issues.append("TRUNCATED: framing[{}]".format(i))
            score -= 2

        # Check for missing quote
        if not quote:
            issues.append("MISSING QUOTE: framing[{}] has no quoted phrase".format(i))
            score -= 1

    score = max(1, score)

    if verbose:
        print("  Framing Quality: {}/10".format(score))
        for issue in issues:
            print("    - {}".format(issue))

    return {"component": "framing", "score": score, "issues": issues,
            "title": card_data.get("title", "")[:60]}


def test_disputes_quality(card_data, verbose=True):
    """Test: Are disputes genuine contradictions?"""
    issues = []
    score = 10

    disputes = card_data.get("disputes", [])
    if not disputes:
        if verbose:
            print("  Disputes: N/A (none claimed)")
        return {"component": "disputes", "score": 8, "issues": [],
                "title": card_data.get("title", "")[:60]}

    # Use Claude to evaluate if disputes are genuine
    disputes_text = json.dumps(disputes, indent=1)
    eval_result = score_with_claude(
        "Story: {}\nDisputes: {}".format(card_data.get("title", ""), disputes_text),
        "1. Each dispute must be a GENUINE CONTRADICTION where two sources claim INCOMPATIBLE things about the SAME fact.\n"
        "2. Different sources covering different aspects is NOT a dispute.\n"
        "3. Different levels of detail is NOT a dispute.\n"
        "4. Each dispute must name specific sources on each side.")

    if eval_result:
        score = eval_result.get("score", 5)
        issues = eval_result.get("failed", [])

    if verbose:
        print("  Disputes Quality: {}/10".format(score))
        for issue in issues:
            print("    - {}".format(issue))

    return {"component": "disputes", "score": score, "issues": issues,
            "title": card_data.get("title", "")[:60]}


def test_source_diversity(card_data, verbose=True):
    """Test: Does the card use diverse sources?"""
    issues = []
    score = 10

    sources = card_data.get("sources", [])
    if not sources:
        return {"component": "sources", "score": 1, "issues": ["No sources"],
                "title": card_data.get("title", "")[:60]}

    # Check region diversity
    regions = set()
    biases = set()
    for s in sources:
        if isinstance(s, dict):
            regions.add(s.get("region", "").split("-")[0].lower())
            biases.add(s.get("bias", "").lower())
        elif isinstance(s, str):
            pass  # Old format, just a name

    if len(regions) <= 1 and len(sources) > 1:
        issues.append("LOW DIVERSITY: All sources from same region")
        score -= 3
    if len(biases) <= 1 and len(sources) > 2:
        issues.append("LOW DIVERSITY: All sources have same political leaning")
        score -= 2

    # Check facts attribution
    facts = card_data.get("agreed_facts", [])
    single_source_facts = sum(1 for f in facts if isinstance(f, str) and "only]" in f.lower())
    if single_source_facts == len(facts) and len(facts) > 0:
        issues.append("SINGLE SOURCE: All facts from one source despite having {}".format(len(sources)))
        score -= 2

    score = max(1, score)

    if verbose:
        print("  Source Diversity: {}/10".format(score))
        for issue in issues:
            print("    - {}".format(issue))

    return {"component": "sources", "score": score, "issues": issues,
            "title": card_data.get("title", "")[:60]}


# ============================================================
# HELPERS
# ============================================================

def _is_truncated(text):
    """Check if text appears cut off mid-sentence."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 20:
        return False
    if text[-1].isalpha() and text[-1].islower():
        return True
    if text[-1] in [',', ':', '(', '[', '{', '-']:
        return True
    truncation_endings = [' the', ' a', ' an', ' of', ' in', ' to', ' for',
                         ' and', ' or', ' is', ' was', ' that', ' with',
                         ' at', ' by', ' on', ' from']
    for ending in truncation_endings:
        if text.endswith(ending):
            return True
    return False


# ============================================================
# RUNNER
# ============================================================

def run_all_tests(data, story_idx=None, verbose=True):
    """Run all component tests on cached data."""
    cards = data.get("cards", [])
    if not cards:
        print("No cards in cached data")
        return

    if story_idx is not None:
        if story_idx < 0 or story_idx >= len(cards):
            print("Story index {} out of range (0-{})".format(story_idx, len(cards) - 1))
            return
        cards_to_test = [(story_idx, cards[story_idx])]
    else:
        # Test 3 random cards
        import random
        indices = random.sample(range(len(cards)), min(3, len(cards)))
        cards_to_test = [(i, cards[i]) for i in indices]

    all_results = []

    for idx, card in cards_to_test:
        print("\n{'='*60}")
        print("TESTING CARD {}: {}".format(idx + 1, card.get("title", "")[:60]))
        print("Written by: {}".format(card.get("written_by", "unknown")))
        print("{'='*60}")

        results = []
        results.append(test_write_core(card, verbose))
        results.append(test_write_extras(card, verbose))
        results.append(test_framing_quality(card, verbose))
        results.append(test_disputes_quality(card, verbose))
        results.append(test_source_diversity(card, verbose))

        avg_score = sum(r["score"] for r in results) / len(results)
        print("\n  OVERALL: {:.1f}/10".format(avg_score))

        all_results.extend(results)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    by_component = {}
    for r in all_results:
        comp = r["component"]
        if comp not in by_component:
            by_component[comp] = []
        by_component[comp].append(r["score"])

    for comp, scores in by_component.items():
        avg = sum(scores) / len(scores)
        print("  {}: {:.1f}/10 (tested {} cards)".format(comp, avg, len(scores)))

    total_issues = sum(len(r["issues"]) for r in all_results)
    total_score = sum(r["score"] for r in all_results) / max(len(all_results), 1)
    print("\n  Total issues: {}".format(total_issues))
    print("  Overall score: {:.1f}/10".format(total_score))

    # Save results
    results_path = Path("output/test_results.json")
    results_path.write_text(json.dumps({
        "date": datetime.utcnow().isoformat(),
        "results": all_results,
        "summary": {comp: sum(s)/len(s) for comp, s in by_component.items()},
        "total_score": total_score,
        "total_issues": total_issues
    }, indent=2))
    print("\nResults saved to {}".format(results_path))

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Component testing for Global Briefing v2")
    parser.add_argument("--component", help="Test specific component: write, framing, disputes, sources")
    parser.add_argument("--story", type=int, help="Test specific story by index (0-based)")
    parser.add_argument("--data", default="output/briefing_data.json", help="Path to cached data")
    parser.add_argument("--optimize", help="Optimize prompts for a component (NOT YET IMPLEMENTED)")
    args = parser.parse_args()

    data = load_cached_data(args.data)
    print("Loaded {} cards from {}".format(len(data.get("cards", [])), args.data))
    print("Generated: {}\n".format(data.get("date", "unknown")))

    if args.optimize:
        print("Prompt optimization not yet implemented.")
        print("Coming next: automatic prompt variation testing for each component.")
        return

    run_all_tests(data, story_idx=args.story)


if __name__ == "__main__":
    main()
