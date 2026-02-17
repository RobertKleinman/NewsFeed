"""
Quickscan: "Today in 60 Seconds" + Key Tensions + Watch List.
Grouped by topic. Each story includes a fault line (axis of disagreement).
Card indices map to the ORIGINAL topic_cards order for anchor links.
"""

import json
import re

import llm as llm_caller
from config import TOPICS
from models import StepReport


def calculate_heat_scores(topic_cards):
    for card in topic_cards:
        src = card.get("source_count", 1)
        persp = card.get("perspectives_used", 1)
        topics = len(card.get("topics", []))
        has_disagree = 0
        dt = card.get("disagreements", "")
        if dt and "no substantive" not in dt.lower():
            has_disagree = 1
        card["_heat_score"] = (src * 2) + (persp * 3) + (topics * 2) + (has_disagree * 5)


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

    # Score and tag each card (preserving original indices)
    calculate_heat_scores(topic_cards)
    for i, card in enumerate(topic_cards):
        card["_consensus"] = determine_consensus(card)
        card["_original_index"] = i  # This maps to topic-card-{i} in HTML

    # Sort by heat for ranking, but keep original index for anchors
    ranked = sorted(topic_cards, key=lambda c: c["_heat_score"], reverse=True)

    briefs = []
    for i, card in enumerate(ranked[:10]):
        sources = ", ".join(s["name"] for s in card.get("sources", [])[:3])
        primary_topic = card.get("topics", ["general"])[0]
        topic_label = TOPICS.get(primary_topic, {}).get("name", primary_topic)
        briefs.append("{i}. [{con}] [{topic}] {t}\n   Src: {s}\n   What: {w}\n   Disagree: {d}".format(
            i=i+1, con=card["_consensus"], topic=topic_label,
            t=card["title"][:100], s=sources,
            w=card.get("what_happened", "")[:120],
            d=card.get("disagreements", "")[:80]))

    prompt = """Write a quick-scan briefing. Return ONLY valid JSON.

STORIES:
{b}

JSON structure:
{{
  "key_tensions": [
    {{"tension": "Who disagrees with whom about what. Name sources and positions.", "type": "data OR causality OR attribution OR framing"}}
  ],
  "watch_list": [
    {{"item": "What to watch and why.", "time_horizon": "imminent OR this_week OR developing"}}
  ],
  "top_stories": [
    {{
      "rank": 1,
      "headline": "Full headline 6-10 words, NEVER truncated",
      "summary": "One sentence explaining what happened and why it matters.",
      "fault_line": "If disputed: X says A while Y says B. If consensus: All sources agree that [key point]. NEVER say 'no substantive contradictions' — always give useful content.",
      "consensus": "consensus OR split OR contested",
      "key_sources": "2-3 source names"
    }}
  ]
}}

RULES:
- key_tensions: 3-4 items with type tag
- watch_list: 3-4 items
- top_stories: all stories given, in order
- EVERY story MUST have BOTH a summary AND a fault_line
- summary: Always a useful one-sentence explanation of the story
- fault_line: NEVER just say "no contradictions." For consensus stories, summarize what all sources agree on. For disputed stories, show the specific disagreement.
- COMPLETE sentences only. NEVER truncate mid-word.
- Use consensus value from brackets.""".format(b="\n\n".join(briefs))

    available = llm_caller.get_available_llms()
    if not available:
        return _fallback(ranked), report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "Return valid JSON only. Complete sentences. Never truncate.", prompt, 5000)

    if not result:
        report.llm_failures += 1
        return _fallback(ranked), report

    qs = _parse(result, ranked)
    if qs:
        report.llm_successes += 1
        report.items_out = len(qs.get("top_stories", []))
    else:
        report.llm_failures += 1
        qs = _fallback(ranked)

    # Map card indices to ORIGINAL order (for anchor links)
    for i, s in enumerate(qs.get("top_stories", [])):
        if i < len(ranked):
            s["card_index"] = ranked[i].get("_original_index", i)
            s["topic"] = ranked[i].get("topics", ["general"])[0]
        else:
            s["card_index"] = i
            s["topic"] = "general"

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


def _fallback(ranked):
    stories = []
    for i, c in enumerate(ranked[:10]):
        stories.append({
            "rank": i+1, "headline": c["title"][:80],
            "fault_line": c.get("disagreements", "")[:150] or "See full analysis",
            "consensus": c.get("_consensus", "split"),
            "key_sources": ", ".join(s["name"] for s in c.get("sources", [])[:3]),
            "card_index": c.get("_original_index", i),
            "topic": c.get("topics", ["general"])[0],
            "_heat_score": c.get("_heat_score", 0)})
    return {"top_stories": stories, "key_tensions": [], "watch_list": []}
