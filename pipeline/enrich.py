"""
Enrich: Compute metadata for each card. No LLM calls.
"""

from models import StepReport

BIAS_SCORES = {
    "left": -2, "centre-left": -1, "centre": 0, "center": 0,
    "centre-right": 1, "right": 2, "libertarian": 1,
    "industry": 0, "religious": 1, "religious-right": 2,
}

REGION_GROUPS = {
    "Canada": "North America", "USA": "North America",
    "UK": "Europe", "Germany": "Europe", "France": "Europe",
    "Europe": "Europe", "Spain": "Europe", "Italy": "Europe",
    "Ireland": "Europe", "Netherlands": "Europe",
    "Qatar/ME": "Middle East", "Israel": "Middle East",
    "Saudi Arabia": "Middle East", "UK/ME": "Middle East",
    "UK/Iran": "Middle East", "Turkey": "Middle East",
    "Hong Kong": "Asia-Pacific", "Japan": "Asia-Pacific",
    "Singapore": "Asia-Pacific", "Australia": "Asia-Pacific",
    "India": "Asia-Pacific", "South Korea": "Asia-Pacific",
    "Taiwan": "Asia-Pacific", "Philippines": "Asia-Pacific",
    "Indonesia": "Asia-Pacific", "Thailand": "Asia-Pacific",
    "East Africa": "Africa", "South Africa": "Africa",
    "Nigeria": "Africa", "Kenya": "Africa", "Tanzania": "Africa",
    "Argentina": "Latin America", "Mexico": "Latin America",
    "Brazil": "Latin America", "Latin America": "Latin America",
}


def run(topic_cards):
    """Enrich cards with computed metadata. Returns report."""
    report = StepReport("enrich", items_in=len(topic_cards))

    for card in topic_cards:
        sources = card.sources

        # Political balance
        bias_values = []
        left = center = right = 0
        for s in sources:
            bias = s.get("bias", "centre").lower()
            score = BIAS_SCORES.get(bias, 0)
            bias_values.append(score)
            if score < 0: left += 1
            elif score > 0: right += 1
            else: center += 1

        if bias_values:
            avg = sum(bias_values) / len(bias_values)
            card.political_balance = "leans_left" if avg < -0.5 else ("leans_right" if avg > 0.5 else "balanced")
        else:
            card.political_balance = "unknown"

        # Geographic diversity
        regions = set()
        for s in sources:
            base = s.get("region", "").split("-")[0]
            regions.add(REGION_GROUPS.get(base, "Other"))
        card.geo_diversity = len(regions)

        # Coverage depth
        has_disputes = bool(card.disputes)
        has_framing = bool(card.framing)
        if card.source_count >= 4 and has_disputes and has_framing:
            card.coverage_depth = "deep"
        elif card.source_count >= 2 and (has_disputes or has_framing):
            card.coverage_depth = "moderate"
        else:
            card.coverage_depth = "thin"

        # Heat score for quickscan ranking
        card.heat_score = (
            card.source_count * 2 +
            len(sources) * 3 +
            len(card.topics) * 2 +
            (5 if has_disputes else 0) +
            (card.importance * 3)
        )

        report.items_out += 1

    return report
