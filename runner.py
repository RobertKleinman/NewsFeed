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
from pipeline import fetch, triage, cluster, select, perspectives, extract, compare, investigate, write, repair, enrich, synthesize, quickscan, validate, publish


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
        # Quality gate: check for material errors and re-write if needed
        card = _quality_gate(card, lead.title, lead.topics, selected_sources,
                            missing, comparisons, investigation, reports)
        print("      Topic card complete")
    return card, reports


def _quality_gate(card, title, topics, sources, missing, comparisons, investigation, reports, max_attempts=2):
    """Check card for material errors. Re-write if fixable. Max 2 retries."""
    material_issues = []

    # Check 1: Completely empty facts (misleading — implies no verified info)
    if not card.get("agreed_facts"):
        material_issues.append("agreed_facts is empty — every story has facts")

    # Check 2: What happened is empty or truncated to uselessness
    what = card.get("what_happened", "")
    if not what or len(what) < 30:
        material_issues.append("what_happened is empty or too short")

    # Check 3: Disputes that are obviously not contradictions (different sources ≠ dispute)
    for d in card.get("disputes", []):
        if isinstance(d, dict):
            side_a = d.get("side_a", "").lower()
            side_b = d.get("side_b", "").lower()
            # If both sides reference different sources but no actual contradiction
            if "not mention" in side_a or "not mention" in side_b:
                material_issues.append("Fake dispute: 'not mentioning' something is not a contradiction")
            if "different" in side_a and "different" in side_b:
                material_issues.append("Fake dispute: different coverage angles, not contradictory claims")

    # Check 4: Mixed stories (facts about unrelated topics)
    # Simple heuristic: if title mentions one topic but facts mention clearly unrelated topics
    # This is hard to detect without Claude, so skip for now

    if not material_issues:
        return card  # Card passes quality gate

    # Only retry if we haven't exhausted attempts
    attempt = card.get("_qa_attempt", 0)
    if attempt >= max_attempts:
        print("      Quality gate: {} material issues remain after {} attempts".format(
            len(material_issues), max_attempts))
        card["_qa_issues"] = material_issues
        return card

    print("      Quality gate: {} material issues, re-writing...".format(len(material_issues)))
    for issue in material_issues:
        print("        - {}".format(issue))

    # Re-write with feedback
    card_v2, rewrite_report = write.run(
        title, topics, sources, missing, comparisons, investigation)
    reports.append(rewrite_report)

    if card_v2:
        card_v2["_qa_attempt"] = attempt + 1
        # Recursively check the rewrite
        return _quality_gate(card_v2, title, topics, sources, missing,
                            comparisons, investigation, reports, max_attempts)

    # Rewrite failed, return original
    card["_qa_issues"] = material_issues
    return card


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

    # Step 9c: Repair truncation and mechanical issues
    repair_report = repair.run(topic_cards)
    all_reports.append(repair_report)

    # Enrich: compute metadata (no LLM calls)
    enrich_report = enrich.run(topic_cards)
    all_reports.append(enrich_report)

    # Step 10: Synthesize
    synth, synth_report = synthesize.run(topic_cards)
    all_reports.append(synth_report)

    # Step 10b: Quickscan
    qscan, qscan_report = quickscan.run(topic_cards)
    all_reports.append(qscan_report)

    # Step 10c: Quality validation (Claude)
    quality_review, validate_report = validate.run(topic_cards)
    all_reports.append(validate_report)

    # Step 11: Publish
    run_time = int(time.time() - start_time)
    html = publish.run(topic_cards, synth, qscan, all_reports, run_time, quality_review)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print("\nBriefing: {}".format(output_path))

    # Cache data for backtesting AND component testing
    import json
    from datetime import datetime, timezone
    cache = {
        "date": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": run_time,
        "cards": []
    }
    for card in topic_cards:
        cache["cards"].append({
            "title": card.get("title", ""),
            "topics": card.get("topics", []),
            "source_count": card.get("source_count", 0),
            "sources": card.get("sources", []),
            "what_happened": card.get("what_happened", ""),
            "agreed_facts": card.get("agreed_facts", []),
            "disputes": card.get("disputes", []),
            "framing": card.get("framing", []),
            "predictions": card.get("predictions", []),
            "watch_items": card.get("watch_items", []),
            "key_unknowns": card.get("key_unknowns", []),
            "notable_details": card.get("notable_details", []),
            "implications": card.get("implications", ""),
            "missing_viewpoints": card.get("missing_viewpoints", ""),
            "investigation": card.get("investigation", ""),
            "comparisons": {k: v[:1000] if isinstance(v, str) else v
                          for k, v in card.get("comparisons", {}).items()},
            "written_by": card.get("written_by", ""),
            "_political_balance": card.get("_political_balance", ""),
            "_coverage_depth": card.get("_coverage_depth", ""),
            "_repair_issues": card.get("_repair_issues", 0),
        })
    cache_path = output_dir / "briefing_data.json"
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print("Cache: {}".format(cache_path))

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
