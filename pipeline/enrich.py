"""
Enrich: Compute metadata for each card from source data.
No LLM calls — pure data computation.
Adds: political balance score, geographic diversity, coverage depth.
"""

from models import StepReport


# Bias spectrum scoring
BIAS_SCORES = {
    "left": -2, "centre-left": -1, "centre": 0, "center": 0,
    "centre-right": 1, "right": 2, "libertarian": 1,
    "industry": 0, "religious": 1,
}

# Region grouping
REGION_GROUPS = {
    "Canada": "North America", "USA": "North America",
    "UK": "Europe", "Germany": "Europe", "France": "Europe",
    "Europe": "Europe",
    "Qatar/ME": "Middle East", "Israel": "Middle East",
    "Saudi Arabia": "Middle East", "Middle East/Africa": "Middle East",
    "Hong Kong": "Asia-Pacific", "Japan": "Asia-Pacific",
    "Singapore": "Asia-Pacific", "Australia": "Asia-Pacific",
    "India": "Asia-Pacific",
    "East Africa": "Africa", "Argentina": "Latin America",
}


def run(topic_cards):
    """Enrich each card with computed metadata. Returns report."""
    report = StepReport("enrich", items_in=len(topic_cards))

    for card in topic_cards:
        sources = card.get("sources", [])

        # Political balance
        bias_values = []
        left_count = 0
        right_count = 0
        center_count = 0
        for s in sources:
            bias = s.get("bias", "centre").lower()
            score = BIAS_SCORES.get(bias, 0)
            bias_values.append(score)
            if score < 0:
                left_count += 1
            elif score > 0:
                right_count += 1
            else:
                center_count += 1

        if bias_values:
            avg_bias = sum(bias_values) / len(bias_values)
            if avg_bias < -0.5:
                card["_political_balance"] = "leans_left"
            elif avg_bias > 0.5:
                card["_political_balance"] = "leans_right"
            else:
                card["_political_balance"] = "balanced"
        else:
            card["_political_balance"] = "unknown"

        card["_bias_breakdown"] = {
            "left": left_count, "center": center_count, "right": right_count
        }

        # Geographic diversity
        regions = set()
        for s in sources:
            region = s.get("region", "")
            # Strip suffixes like "USA-Tech", "Canada-Insurance"
            base_region = region.split("-")[0] if "-" in region else region
            group = REGION_GROUPS.get(base_region, "Other")
            regions.add(group)
        card["_geo_diversity"] = len(regions)
        card["_geo_regions"] = sorted(list(regions))

        # Coverage depth indicator
        src_count = len(sources)
        has_disputes = bool(card.get("disputes", []))
        has_framing = bool(card.get("framing", []))
        if src_count >= 4 and has_disputes and has_framing:
            card["_coverage_depth"] = "deep"
        elif src_count >= 2 and (has_disputes or has_framing):
            card["_coverage_depth"] = "moderate"
        else:
            card["_coverage_depth"] = "thin"

        report.items_out += 1

    return report
