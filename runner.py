#!/usr/bin/env python3
"""
Global Briefing Runner
======================
Orchestrates the pipeline: Fetch > Triage > Cluster > Select > Perspectives >
Extract > Compare > Investigate > Write > Synthesize > Publish

Usage:
  python runner.py                          # Default broad briefing
  python runner.py --config config/broad.json  # Specific query pack
"""

import argparse
import sys
import time
import traceback
from pathlib import Path

from config import get_active_sources, get_active_topics, load_query_pack, LLM_CONFIGS
import llm as llm_caller
from pipeline import fetch, triage, cluster, select, perspectives, extract, compare, investigate, write, synthesize, quickscan, publish


def process_story(story_group, story_num, total):
    """Run one story through steps 5-9."""
    lead = story_group[0]
    print("\n" + "=" * 70)
    print("STORY {}/{}: {}".format(story_num, total, lead.title[:80]))
    print("  Sources in cluster: {}".format(len(story_group)))

    reports = []

    # Step 5: Map perspectives + select sources
    print("  [5] Mapping perspectives...")
    selected_sources, missing, persp_list, persp_report = perspectives.run(story_group)
    reports.append(persp_report)
    print("      {} sources, {} missing perspectives".format(
        len(selected_sources), len(missing)))

    # Step 6: Extract claims
    print("  [6] Extracting claims...")
    claims, extract_report = extract.run(selected_sources)
    reports.append(extract_report)
    if not claims:
        print("      No claims extracted, skipping")
        return None, reports

    # Step 7: Compare
    print("  [7] Comparing across sources...")
    comparisons, compare_report = compare.run(claims, lead.title)
    reports.append(compare_report)
    if not comparisons:
        print("      No comparisons, skipping")
        return None, reports

    # Step 8: Investigate gaps + forecast
    print("  [8] Investigating gaps & forecasting...")
    investigation, invest_report = investigate.run(comparisons, claims, lead.title)
    reports.append(invest_report)

    # Step 9: Write topic card
    print("  [9] Writing topic card...")
    card, write_report = write.run(
        lead.title, lead.topics, selected_sources,
        missing, comparisons, investigation)
    reports.append(write_report)

    if card:
        print("      Topic card complete")
    return card, reports


def main():
    parser = argparse.ArgumentParser(description="Global Intelligence Briefing")
    parser.add_argument("--config", help="Path to query pack JSON", default=None)
    parser.add_argument("--max-stories", type=int, default=12)
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 70)
    print("GLOBAL INTELLIGENCE BRIEFING v2")
    print("=" * 70)

    # Load config
    pack = load_query_pack(args.config)
    if pack:
        print("Config pack: {}".format(pack.get("name", args.config)))
    sources = get_active_sources(pack)
    topics = get_active_topics(pack)

    available = llm_caller.get_available_llms()
    if not available:
        print("\nNo LLM API keys found. Set at least GOOGLE_API_KEY.")
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

    # Step 2: Triage
    relevant, triage_report = triage.run(articles, topics)
    all_reports.append(triage_report)
    if not relevant:
        print("No relevant articles")
        sys.exit(1)

    # Step 3: Cluster
    clusters, cluster_report = cluster.run(relevant)
    all_reports.append(cluster_report)

    # Step 4: Select stories
    selected, select_report = select.run(clusters, topics, args.max_stories)
    all_reports.append(select_report)

    # Steps 5-9: Process each story
    topic_cards = []
    for i, group in enumerate(selected):
        try:
            card, story_reports = process_story(group, i + 1, len(selected))
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

    # Step 10: Synthesize
    synth, synth_report = synthesize.run(topic_cards)
    all_reports.append(synth_report)

    # Step 10b: Quickscan
    qscan, qscan_report = quickscan.run(topic_cards)
    all_reports.append(qscan_report)

    # Step 11: Publish
    run_time = int(time.time() - start_time)
    html = publish.run(topic_cards, synth, qscan, all_reports, run_time)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print("\nBriefing: {}".format(output_path))

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
