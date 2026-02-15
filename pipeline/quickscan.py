"""
Quickscan: Generate the "Today in 60 Seconds" quick-scan layer.
Input: list of topic card dicts (from write.py)
Output: quickscan dict with top_stories, tensions, watch_list; StepReport
"""

import json
import re

import llm as llm_caller
from models import StepReport


def calculate_heat_scores(topic_cards):
    scored = []
    for card in topic_cards:
        src = card.get("source_count", 1)
        persp = card.get("perspectives_used", 1)
        topics = len(card.get("topics", []))
        has_disagree = 0
        dt = card.get("disagreements", "")
        if dt and "no substantive" not in dt.lower():
            has_disagree = 1
        card["_heat_score"] = (src * 2) + (persp * 3) + (topics * 2) + (has_disagree * 5)
        scored.append(card)
    scored.sort(key=lambda c: c["_heat_score"], reverse=True)
    return scored


def determine_consensus(card):
    disagree = card.get("disagreements", "").lower()
    framing = card.get("framing_differences", "").lower()
    if not disagree or "no substantive" in disagree or "none identified" in disagree:
        if not framing or len(framing) < 30:
            return "consensus"
        return "split"
    sharp = ["contradict", "dispute", "deny", "reject", "opposite",
             "sharply", "starkly", "fundamentally", "conflicting",
             "contested", "denied", "opposing", "clashed"]
    count = sum(1 for w in sharp if w in disagree or w in framing)
    if count >= 2:
        return "contested"
    return "split"


def run(topic_cards):
    print("\n>>> QUICKSCAN...")
    report = StepReport("quickscan", items_in=len(topic_cards))
    scored = calculate_heat_scores(topic_cards)
    for card in scored:
        card["_consensus"] = determine_consensus(card)

    briefs = []
    for i, card in enumerate(scored[:10]):
        sources = ", ".join(s["name"] for s in card.get("sources", [])[:3])
        briefs.append("{i}. [{con}] {t}\n   Src: {s}\n   What: {w}\n   Disagree: {d}".format(
            i=i+1, con=card["_consensus"], t=card["title"][:100],
            s=sources, w=card.get("what_happened", "")[:120],
            d=card.get("disagreements", "")[:80]))

    prompt = """Write a quick-scan briefing. Return ONLY valid JSON, no other text.

STORIES:
{b}

JSON structure:
{{
  "key_tensions": [
    {{"tension": "Who disagrees with whom about what. Name specific sources and positions."}}
  ],
  "watch_list": [
    {{"item": "What to watch and why.", "time_horizon": "imminent OR this_week OR developing"}}
  ],
  "top_stories": [
    {{
      "rank": 1,
      "headline": "Full headline 6-10 words",
      "summary_line": "Full sentence: what happened, why it matters, who disagrees. Name sources.",
      "consensus": "consensus OR split OR contested",
      "key_sources": "2-3 source names on different sides"
    }}
  ]
}}

RULES:
- key_tensions: 3-4 items, sharpest disagreements across all stories
- watch_list: 3-4 items, most important next developments
- top_stories: up to 10, in order given
- NEVER truncate mid-word. All headlines and summaries must be COMPLETE.
- Use consensus value from brackets.""".format(b="\n\n".join(briefs))

    available = llm_caller.get_available_llms()
    if not available:
        return _fallback(scored), report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Return valid JSON only. Complete sentences. Never truncate.", prompt, 3500)

    if not result:
        report.llm_failures += 1
        return _fallback(scored), report

    qs = _parse(result, scored)
    if qs:
        report.llm_successes += 1
        report.items_out = len(qs.get("top_stories", []))
    else:
        report.llm_failures += 1
        qs = _fallback(scored)

    for i, s in enumerate(qs.get("top_stories", [])):
        s["card_index"] = i
    return qs, report


def _parse(result, cards):
    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        for key in ["top_stories", "key_tensions", "watch_list"]:
            if key not in data:
                data[key] = []
        for i, s in enumerate(data["top_stories"]):
            if i < len(cards):
                s["_heat_score"] = cards[i].get("_heat_score", 0)
                if s.get("consensus") not in ("consensus", "split", "contested"):
                    s["consensus"] = cards[i].get("_consensus", "split")
        return data
    except Exception as e:
        print("    QS parse error: {}".format(str(e)[:60]))
        return None


def _fallback(scored):
    stories = []
    for i, c in enumerate(scored[:10]):
        stories.append({
            "rank": i+1, "headline": c["title"][:80],
            "summary_line": c.get("what_happened", "")[:200],
            "consensus": c.get("_consensus", "split"),
            "key_sources": ", ".join(s["name"] for s in c.get("sources", [])[:3]),
            "card_index": i, "_heat_score": c.get("_heat_score", 0)})
    return {"top_stories": stories, "key_tensions": [], "watch_list": []}
