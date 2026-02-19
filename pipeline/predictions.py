"""
Step 9c: Predictions — cross-story intelligence forecasting.

Runs after all cards are written. Sees ALL stories together to:
1. Identify cross-story connections individual card writers couldn't see
2. Make structured predictions with timeframes and confidence levels
3. Flag disconfirming signals — what would prove the prediction wrong

Output feeds a "What's Coming" section in the briefing.
"""

import json
import re
import time

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """Generate cross-story predictions. Returns (predictions_data, report)."""
    print("\n>>> PREDICTIONS: analyzing {} cards...".format(len(topic_cards)))
    report = StepReport("predictions", items_in=len(topic_cards))

    if len(topic_cards) < 2:
        report.items_out = 0
        return {}, report

    available = llm_caller.get_available_llms()
    if not available:
        report.items_out = 0
        return {}, report

    # Build card summaries for the prediction engine
    card_briefs = []
    for i, card in enumerate(topic_cards):
        d = card.to_dict()
        title = d.get("title", "")
        whats = d.get("whats_happening", d.get("what_happened", ""))[:200]
        bigger = d.get("bigger_picture", "")[:200]
        topics = ", ".join(d.get("topics", [])[:2])
        card_briefs.append("{i}. [{topics}] {title}\n   Situation: {whats}\n   Trajectory: {bigger}".format(
            i=i+1, topics=topics, title=title[:80],
            whats=whats, bigger=bigger))

    prompt = """You are an intelligence analyst reviewing today's complete briefing. Your job is to identify CROSS-STORY CONNECTIONS and make PREDICTIONS that individual story analysts would miss.

TODAY'S STORIES:
{cards}

Generate predictions in three categories:

1. CROSS-STORY PREDICTIONS — developments that emerge from the INTERACTION of multiple stories above. These are the highest-value predictions because they connect dots across stories.
   Example: "If Iran talks fail (story 3) AND US withdraws from Syria (story 8), Gulf states will accelerate independent security pacts within weeks."

2. NEXT 48 HOURS — what is most likely to happen in the immediate term across all stories.

3. THIS WEEK / THIS MONTH — medium-term developments.

For each prediction, include:
- What you predict will happen (be specific)
- Which stories feed into this prediction (by number)
- Confidence: likely / possible / speculative
- Disconfirming signal: what would prove this prediction WRONG
- Timeframe: 48_hours / this_week / this_month

Return JSON:
{{
  "cross_story": [
    {{
      "prediction": "Specific prediction connecting multiple stories.",
      "stories": [3, 8],
      "confidence": "possible",
      "disconfirm": "What would prove this wrong.",
      "timeframe": "this_week"
    }}
  ],
  "near_term": [
    {{
      "prediction": "What happens in the next 48 hours.",
      "stories": [1],
      "confidence": "likely",
      "disconfirm": "What would prove this wrong.",
      "timeframe": "48_hours"
    }}
  ],
  "medium_term": [
    {{
      "prediction": "This week or this month development.",
      "stories": [2, 5],
      "confidence": "possible",
      "disconfirm": "What would prove this wrong.",
      "timeframe": "this_month"
    }}
  ]
}}

RULES:
- 2-3 predictions per category max.
- Cross-story predictions MUST reference 2+ stories.
- Be SPECIFIC — not "tensions may rise" but "Saudi Arabia will likely call an emergency GCC meeting."
- Disconfirming signals should be concrete and observable.
- If you can't make a strong cross-story prediction, say why.""".format(
        cards="\n\n".join(card_briefs))

    # Use the best available LLM for predictions
    preferred = ["chatgpt", "claude", "gemini_pro", "gemini", "grok"]
    predictor = next((p for p in preferred if p in available), available[0])

    report.llm_calls += 1
    result = llm_caller.call_by_id(predictor,
        "Intelligence analyst making structured predictions. Return only JSON. Be specific and concrete.",
        prompt, 4000)
    time.sleep(1)

    if not result:
        report.llm_failures += 1
        return {}, report

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        # Validate and clean predictions
        for category in ["cross_story", "near_term", "medium_term"]:
            preds = data.get(category, [])
            if not isinstance(preds, list):
                data[category] = []
                continue
            # Cap at 3 per category
            data[category] = preds[:3]

        total = sum(len(data.get(c, [])) for c in ["cross_story", "near_term", "medium_term"])
        report.items_out = total
        report.notes.append("{} predictions across 3 categories".format(total))
        print("    {} predictions generated".format(total))

        # Map story numbers to titles for display
        data["story_titles"] = {}
        for i, card in enumerate(topic_cards):
            data["story_titles"][str(i + 1)] = card.title[:60]

        return data, report

    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        report.llm_failures += 1
        print("    Predictions parse error: {}".format(str(e)[:60]))
        return {}, report
