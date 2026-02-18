#!/usr/bin/env python3
"""
Global Briefing v3 Runner
=========================
Importance-driven pipeline with depth tiers:
  BRIEF (1-2★): summary only
  STANDARD (3★): perspectives → extract → compare → write
  DEEP (4-5★): + investigate → full analysis

Fetch → Triage → Cluster → Select → [per story: tiered processing] →
Enrich → Synthesize → Quickscan → Validate → Publish
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from config import get_active_sources, get_active_topics, load_query_pack, LLM_CONFIGS
import llm as llm_caller
from pipeline import (fetch, triage, cluster, select, perspectives,
                      extract, compare, investigate, write, enrich,
                      synthesize, quickscan, validate, publish)


def process_brief(ranked_story, story_num, total):
    """BRIEF tier: minimal processing, summary from cluster data."""
    cluster_obj = ranked_story.cluster
    print("\n" + "-" * 50)
    print("STORY {}/{} [BRIEF {}★]: {}".format(
        story_num, total, ranked_story.stars, cluster_obj.lead_title[:70]))

    reports = []

    # Minimal source selection (just use first few sources)
    from models import SelectedSource
    selected = [
        SelectedSource(
            article=a,
            perspective="General coverage",
            angle=""
        )
        for a in cluster_obj.articles[:3]
    ]

    card, write_report = write.run(
        ranked_story, selected, [], None, None)
    reports.append(write_report)

    return card, reports


def process_standard(ranked_story, story_num, total):
    """STANDARD tier: perspectives + compare + write."""
    cluster_obj = ranked_story.cluster
    print("\n" + "=" * 60)
    print("STORY {}/{} [STANDARD {}★]: {}".format(
        story_num, total, ranked_story.stars, cluster_obj.lead_title[:70]))
    print("  Sources: {}".format(cluster_obj.size))

    reports = []

    # Step 5: Perspectives
    print("  [5] Mapping perspectives...")
    selected, missing, persp_report = perspectives.run(cluster_obj)
    reports.append(persp_report)
    print("      {} sources, {} missing".format(len(selected), len(missing)))

    # Step 6: Extract
    print("  [6] Extracting claims...")
    claims, extract_report = extract.run(selected)
    reports.append(extract_report)
    if not claims:
        print("      No claims, falling back to brief")
        card, wr = write.run(ranked_story, selected, missing, None, None)
        reports.append(wr)
        return card, reports

    # Step 7: Compare
    print("  [7] Comparing...")
    comp_result, comp_report = compare.run(claims, cluster_obj.lead_title)
    reports.append(comp_report)

    # Step 9: Write
    print("  [9] Writing card ({})...".format(comp_result.contention_level))
    card, write_report = write.run(
        ranked_story, selected, missing, comp_result, None)
    reports.append(write_report)

    print("      {} mode, {}★".format(card.card_mode, card.importance))
    return card, reports


def process_deep(ranked_story, story_num, total):
    """DEEP tier: full pipeline including investigation."""
    cluster_obj = ranked_story.cluster
    print("\n" + "=" * 70)
    print("STORY {}/{} [DEEP {}★]: {}".format(
        story_num, total, ranked_story.stars, cluster_obj.lead_title[:70]))
    print("  Sources: {}".format(cluster_obj.size))

    reports = []

    # Step 5: Perspectives
    print("  [5] Mapping perspectives...")
    selected, missing, persp_report = perspectives.run(cluster_obj)
    reports.append(persp_report)
    print("      {} sources, {} missing".format(len(selected), len(missing)))

    # Step 6: Extract
    print("  [6] Extracting claims...")
    claims, extract_report = extract.run(selected)
    reports.append(extract_report)
    if not claims:
        print("      No claims, falling back to standard")
        card, wr = write.run(ranked_story, selected, missing, None, None)
        reports.append(wr)
        return card, reports

    # Step 7: Compare
    print("  [7] Comparing...")
    comp_result, comp_report = compare.run(claims, cluster_obj.lead_title)
    reports.append(comp_report)

    # Step 8: Investigate
    print("  [8] Investigating...")
    inv_result, inv_report = investigate.run(
        comp_result, claims, cluster_obj.lead_title)
    reports.append(inv_report)
    if inv_result.adds_value:
        print("      Investigation adds value: {}".format(inv_result.story_impact[:80]))
    else:
        print("      Investigation confirms coverage — no new findings")

    # Step 9: Write
    print("  [9] Writing deep card ({})...".format(comp_result.contention_level))
    card, write_report = write.run(
        ranked_story, selected, missing, comp_result, inv_result)
    reports.append(write_report)

    print("      {} mode, {}★".format(card.card_mode, card.importance))
    return card, reports


def main():
    parser = argparse.ArgumentParser(description="Global Intelligence Briefing v3")
    parser.add_argument("--config", help="Path to query pack JSON", default=None)
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 70)
    print("GLOBAL INTELLIGENCE BRIEFING v3")
    print("=" * 70)

    pack = load_query_pack(args.config)
    if pack:
        print("Config: {}".format(pack.get("name", args.config)))
    sources = get_active_sources(pack)
    topics = get_active_topics(pack)

    available = llm_caller.get_available_llms()
    if not available:
        print("\nNo LLM API keys found.")
        sys.exit(1)
    print("LLMs: {}".format(", ".join(LLM_CONFIGS[k]["label"] for k in available)))
    print("Sources: {} | Topics: {}".format(len(sources), len(topics)))

    all_reports = []

    # Step 1: Fetch
    articles, fetch_report = fetch.run(sources)
    all_reports.append(fetch_report)
    if not articles:
        print("No articles fetched")
        sys.exit(1)

    # Step 2: Triage (LLM-based)
    relevant, triage_report = triage.run(articles, topics)
    all_reports.append(triage_report)
    if not relevant:
        print("No relevant articles")
        sys.exit(1)

    # Step 3: Cluster (mechanical + LLM review)
    clusters, cluster_report = cluster.run(relevant)
    all_reports.append(cluster_report)

    # Step 4: Select (importance rating + materiality cutoff)
    ranked_stories, select_report = select.run(clusters, topics)
    all_reports.append(select_report)

    if not ranked_stories:
        print("No stories above materiality cutoff")
        sys.exit(1)

    # Report tier breakdown
    tier_counts = {"deep": 0, "standard": 0, "brief": 0}
    for r in ranked_stories:
        tier_counts[r.depth_tier] = tier_counts.get(r.depth_tier, 0) + 1
    print("\nStory tiers: {} deep, {} standard, {} brief".format(
        tier_counts["deep"], tier_counts["standard"], tier_counts["brief"]))

    # Process each story by tier
    topic_cards = []
    for i, ranked in enumerate(ranked_stories):
        try:
            if ranked.depth_tier == "deep":
                card, story_reports = process_deep(ranked, i + 1, len(ranked_stories))
            elif ranked.depth_tier == "standard":
                card, story_reports = process_standard(ranked, i + 1, len(ranked_stories))
            else:
                card, story_reports = process_brief(ranked, i + 1, len(ranked_stories))

            all_reports.extend(story_reports)
            if card:
                topic_cards.append(card)
        except Exception as e:
            print("  ERROR: {}".format(str(e)[:100]))
            traceback.print_exc()

    if not topic_cards:
        print("\nNo topic cards generated")
        sys.exit(1)
    print("\n{} topic cards generated".format(len(topic_cards)))

    # Enrich
    enrich_report = enrich.run(topic_cards)
    all_reports.append(enrich_report)

    # Synthesize
    synth, synth_report = synthesize.run(topic_cards)
    all_reports.append(synth_report)

    # Quickscan
    qscan, qscan_report = quickscan.run(topic_cards)
    all_reports.append(qscan_report)

    # Validate
    quality, validate_report = validate.run(topic_cards)
    all_reports.append(validate_report)

    # Publish
    run_time = int(time.time() - start_time)
    html = publish.run(topic_cards, synth, qscan, all_reports, run_time, quality)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    print("\nBriefing: output/index.html")

    # Cache data
    cache = {
        "date": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": run_time,
        "tier_counts": tier_counts,
        "cards": [card.to_dict() for card in topic_cards],
    }
    (output_dir / "briefing_data.json").write_text(
        json.dumps(cache, indent=2, default=str), encoding="utf-8")

    # Run report
    print("\n" + "=" * 70)
    print("RUN REPORT")
    print("=" * 70)
    for r in all_reports:
        if r.llm_calls > 0 or r.items_out > 0:
            print("  " + r.summary())
    print("  Total runtime: {}s".format(run_time))
    print("=" * 70)


if __name__ == "__main__":
    main()
