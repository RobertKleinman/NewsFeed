"""
Quickscan: Generate the "Today in 60 Seconds" quick-scan layer.
Input: list of topic card dicts (from write.py)
Output: quickscan dict with top_stories, tensions, watch_list; StepReport

Ranking uses a pre-calculated heat score (code), not LLM judgment.
The LLM's job is only writing concise one-line summaries.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def calculate_heat_scores(topic_cards):
    """
    Pre-calculate a heat score for each card. Code decides ranking, not LLMs.
    Score = source_count * 2 + perspectives_used * 3 + topic_breadth * 2
    + has_disagreements * 5
    """
    scored = []
    for card in topic_cards:
        source_count = card.get("source_count", 1)
        perspectives = card.get("perspectives_used", 1)
        topic_breadth = len(card.get("topics", []))
        has_disagree = 0
        disagree_text = card.get("disagreements", "")
        if disagree_text and "no substantive" not in disagree_text.lower():
            has_disagree = 1

        heat = (source_count * 2) + (perspectives * 3) + (topic_breadth * 2) + (has_disagree * 5)
        card["_heat_score"] = heat
        scored.append(card)

    scored.sort(key=lambda c: c["_heat_score"], reverse=True)
    return scored


def determine_consensus(card):
    """
    Classify consensus level from the card's disagreements and framing.
    Returns: 'consensus', 'split', or 'contested'
    """
    disagree = card.get("disagreements", "").lower()
    framing = card.get("framing_differences", "").lower()

    if not disagree or "no substantive" in disagree or "none" in disagree:
        if not framing or len(framing) < 50:
            return "consensus"
        return "split"  # framing differs but facts agree

    # Count indicators of sharp disagreement
    sharp_words = ["contradict", "dispute", "deny", "reject", "opposite",
                   "sharply", "starkly", "fundamentally", "conflicting"]
    sharp_count = sum(1 for w in sharp_words if w in disagree or w in framing)

    if sharp_count >= 2:
        return "contested"
    return "split"


def run(topic_cards):
    """Generate quickscan. Returns (quickscan_dict, report)."""
    print("\n>>> QUICKSCAN: generating 60-second overview...")
    report = StepReport("quickscan", items_in=len(topic_cards))

    # Step 1: Score and rank (code, not LLM)
    scored_cards = calculate_heat_scores(topic_cards)

    # Step 2: Determine consensus for each card
    for card in scored_cards:
        card["_consensus"] = determine_consensus(card)

    # Step 3: Build the prompt with pre-ranked cards
    card_briefs = []
    for i, card in enumerate(scored_cards[:12]):
        sources = ", ".join(s["name"] for s in card.get("sources", [])[:4])
        card_briefs.append(
            "{rank}. [Heat: {heat}] [Consensus: {consensus}] {title}\n"
            "   Sources: {sources}\n"
            "   What happened: {what}\n"
            "   Disagreements: {disagree}\n"
            "   Predictions: {predict}".format(
                rank=i+1,
                heat=card.get("_heat_score", 0),
                consensus=card.get("_consensus", "unknown"),
                title=card["title"],
                sources=sources,
                what=card.get("what_happened", "")[:200],
                disagree=card.get("disagreements", "")[:200],
                predict=card.get("predictions", "")[:200],
            ))

    all_briefs = "\n\n".join(card_briefs)

    prompt = """You are writing the quick-scan section of an intelligence briefing.
Below are today's stories, pre-ranked by importance (heat score). For each, you must produce
a concise one-line briefing.

STORIES (ranked by importance):
{briefs}

Produce a JSON object with this EXACT structure. All values must be strings or arrays of objects.
No markdown anywhere. Write complete sentences, not fragments.

{{
  "top_stories": [
    {{
      "rank": 1,
      "headline": "Short punchy headline (5-8 words)",
      "summary_line": "One sentence: what happened, why it matters, and where the tension is. Include which sides disagree and on what.",
      "consensus": "consensus OR split OR contested",
      "key_sources": "2-3 source names that represent different sides"
    }}
  ],
  "key_tensions": [
    {{
      "tension": "One sentence describing the sharpest disagreement across sources. Name the sources and their positions."
    }}
  ],
  "watch_list": [
    {{
      "item": "One sentence: what to watch for and why. Be specific about timeframe if possible.",
      "time_horizon": "imminent OR this_week OR developing"
    }}
  ]
}}

Rules:
- top_stories: Include up to 10 items, in the order given (they are pre-ranked).
- key_tensions: Pick the 3-4 sharpest disagreements across ALL stories.
- watch_list: Pick the 3-4 most important forward-looking items from predictions.
- Every source mentioned must be named. No vague "some sources say."
- Consensus field must match what is provided above for each story.""".format(briefs=all_briefs)

    available = llm_caller.get_available_llms()
    if not available:
        report.llm_failures += 1
        return _fallback(scored_cards), report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "You write ultra-concise intelligence briefing summaries. Return valid JSON only. No markdown. No text outside the JSON.",
        prompt, 2000)

    if not result:
        report.llm_failures += 1
        return _fallback(scored_cards), report

    # Parse JSON
    quickscan = _parse_quickscan(result, scored_cards)
    if quickscan:
        report.llm_successes += 1
        report.items_out = len(quickscan.get("top_stories", []))
    else:
        report.llm_failures += 1
        quickscan = _fallback(scored_cards)

    # Attach card indices for anchor links
    for i, story in enumerate(quickscan.get("top_stories", [])):
        story["card_index"] = i

    return quickscan, report


def _parse_quickscan(result, cards):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = cleaned.strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(cleaned)

        # Ensure required keys exist
        if "top_stories" not in data:
            data["top_stories"] = []
        if "key_tensions" not in data:
            data["key_tensions"] = []
        if "watch_list" not in data:
            data["watch_list"] = []

        # Inject consensus from our calculation if LLM didn't match
        for i, story in enumerate(data["top_stories"]):
            if i < len(cards):
                story["_heat_score"] = cards[i].get("_heat_score", 0)
                if "consensus" not in story or story["consensus"] not in ("consensus", "split", "contested"):
                    story["consensus"] = cards[i].get("_consensus", "split")

        return data

    except Exception as e:
        print("    Quickscan JSON parse error: {}".format(str(e)[:80]))
        return None


def _fallback(scored_cards):
    """Fallback if LLM fails: build quickscan from card data directly."""
    stories = []
    for i, card in enumerate(scored_cards[:10]):
        stories.append({
            "rank": i + 1,
            "headline": card["title"][:60],
            "summary_line": card.get("what_happened", "")[:150],
            "consensus": card.get("_consensus", "split"),
            "key_sources": ", ".join(s["name"] for s in card.get("sources", [])[:3]),
            "card_index": i,
            "_heat_score": card.get("_heat_score", 0),
        })
    return {
        "top_stories": stories,
        "key_tensions": [],
        "watch_list": [],
    }
