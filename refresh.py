"""
Refresh Mode: Lightweight pipeline for incremental updates.

Instead of running the full 200+ LLM call pipeline, refresh mode:
  1. Fetches new articles
  2. Runs syndication detection (mechanical, free)
  3. Quick-triages against existing card titles (1 LLM call)
  4. Only fully processes genuinely NEW stories (not seen in last run)
  5. Merges new cards into existing briefing
  6. Regenerates quickscan + action layer (2 LLM calls)

Target: ~20-40 LLM calls vs 200-470 for full run.
"""

import json
import time
import traceback
from pathlib import Path

from config import get_active_sources, get_active_topics, load_query_pack, LLM_CONFIGS
import llm as llm_caller
import card_store
from models import StepReport
from pipeline import (fetch, syndication, triage, cluster, select,
                      perspectives, extract, compare, write, enrich,
                      card_dedup, predictions, quickscan, action_layer,
                      validate, publish, synthesize)


def _is_new_story(cluster_obj, existing_titles):
    """Check if a cluster represents a genuinely new story."""
    if not existing_titles:
        return True

    lead_words = set(cluster_obj.lead_title.lower().split())
    for existing in existing_titles:
        existing_words = set(existing.lower().split())
        if len(lead_words) > 0 and len(existing_words) > 0:
            overlap = len(lead_words & existing_words) / min(len(lead_words), len(existing_words))
            if overlap > 0.4:
                return False
    return True


def run_refresh(pack=None):
    """Run lightweight refresh. Returns HTML string or None on failure."""
    start_time = time.time()
    print("=" * 70)
    print("GLOBAL INTELLIGENCE BRIEFING v3 — REFRESH MODE")
    print("=" * 70)

    sources = get_active_sources(pack)
    topics = get_active_topics(pack)
    available = llm_caller.get_available_llms()
    if not available:
        print("No LLM API keys found.")
        return None

    print("LLMs: {}".format(", ".join(LLM_CONFIGS[k]["label"] for k in available)))

    # Load existing cards from last run
    existing_cards = card_store.get_latest_cards()
    existing_titles = card_store.get_latest_titles()
    print("Previous run: {} cards loaded".format(len(existing_cards)))

    if not existing_cards:
        print("No previous cards — falling back to full run")
        return None  # Caller should run full pipeline

    all_reports = []

    # Step 1: Fetch (same as full)
    articles, fetch_report = fetch.run(sources)
    all_reports.append(fetch_report)
    if not articles:
        print("No articles fetched — keeping previous briefing")
        return None

    # Step 1b: Syndication (mechanical, free)
    articles, synd_report = syndication.run(articles)
    all_reports.append(synd_report)

    # Step 2: Triage (same as full — need topic assignment)
    relevant, triage_report = triage.run(articles, topics)
    all_reports.append(triage_report)
    if not relevant:
        print("No relevant articles — keeping previous briefing")
        return None

    # Step 3: Cluster (same as full)
    clusters, cluster_report = cluster.run(relevant)
    all_reports.append(cluster_report)

    # Filter to NEW stories only
    new_clusters = [c for c in clusters if _is_new_story(c, existing_titles)]
    continuing = len(clusters) - len(new_clusters)
    print("\n{} new story clusters ({} continuing from previous)".format(
        len(new_clusters), continuing))

    if not new_clusters:
        print("No new stories — keeping previous briefing")
        # Still regenerate HTML with updated timestamp
        from models import TopicCard
        existing_topic_cards = _reconstruct_cards(existing_cards)
        run_time = int(time.time() - start_time)
        card_store.save_run(existing_topic_cards, run_time, mode="refresh_no_change")
        return _republish(existing_topic_cards, all_reports, run_time)

    # Step 4: Select only new clusters (quick — fewer items)
    ranked_new, select_report = select.run(new_clusters, topics)
    all_reports.append(select_report)

    # Process new stories (standard tier max to save costs in refresh)
    new_cards = []
    for i, ranked in enumerate(ranked_new[:5]):  # Cap at 5 new stories per refresh
        try:
            # Force standard tier max in refresh (no deep investigation)
            if ranked.depth_tier == "deep":
                ranked.depth_tier = "standard"

            if ranked.depth_tier == "standard":
                card, story_reports = _process_standard_quick(ranked, i + 1, len(ranked_new))
            else:
                card, story_reports = _process_brief(ranked, i + 1, len(ranked_new))

            all_reports.extend(story_reports)
            if card:
                card.depth_tier = ranked.depth_tier
                new_cards.append(card)
        except Exception as e:
            print("  ERROR: {}".format(str(e)[:100]))
            traceback.print_exc()

    print("\n{} new cards generated".format(len(new_cards)))

    # Merge new cards into existing
    from models import TopicCard
    existing_topic_cards = _reconstruct_cards(existing_cards)
    all_cards = new_cards + existing_topic_cards

    # Dedup in case new stories overlap with existing
    all_cards, dedup_report = card_dedup.run(all_cards)
    all_reports.append(dedup_report)

    # Re-enrich all cards
    enrich_report = enrich.run(all_cards)
    all_reports.append(enrich_report)

    # Regenerate cross-card features
    preds_data, preds_report = predictions.run(all_cards)
    all_reports.append(preds_report)

    synth, synth_report = synthesize.run(all_cards)
    all_reports.append(synth_report)

    qscan, qscan_report = quickscan.run(all_cards)
    all_reports.append(qscan_report)

    act_data, act_report = action_layer.run(all_cards)
    all_reports.append(act_report)

    quality, validate_report = validate.run(all_cards)
    all_reports.append(validate_report)

    # Publish
    run_time = int(time.time() - start_time)
    html = publish.run(all_cards, synth, qscan, all_reports, run_time, quality, preds_data, act_data)

    # Save to card store
    card_store.save_run(all_cards, run_time, mode="refresh")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    print("\nRefresh complete: output/index.html ({} cards, {}s)".format(
        len(all_cards), run_time))

    return html


def _process_standard_quick(ranked_story, story_num, total):
    """Lighter standard processing — skip investigation."""
    cluster_obj = ranked_story.cluster
    print("\n  REFRESH {}/{} [STD]: {}".format(story_num, total, cluster_obj.lead_title[:60]))

    reports = []

    print("    [5] Perspectives...")
    selected, missing, persp_report = perspectives.run(cluster_obj)
    reports.append(persp_report)

    print("    [6] Extract...")
    claims, extract_report = extract.run(selected)
    reports.append(extract_report)

    if not claims:
        card, wr = write.run(ranked_story, selected, missing, None, None)
        reports.append(wr)
        return card, reports

    print("    [7] Compare...")
    comp_result, comp_report = compare.run(claims, cluster_obj.lead_title)
    reports.append(comp_report)

    print("    [9] Write...")
    card, write_report = write.run(ranked_story, selected, missing, comp_result, None)
    reports.append(write_report)

    return card, reports


def _process_brief(ranked_story, story_num, total):
    """Brief processing for refresh."""
    cluster_obj = ranked_story.cluster
    print("\n  REFRESH {}/{} [BRIEF]: {}".format(story_num, total, cluster_obj.lead_title[:60]))

    from models import SelectedSource
    selected = [
        SelectedSource(article=a, perspective="General coverage", angle="")
        for a in cluster_obj.articles[:3]
    ]

    card, write_report = write.run(ranked_story, selected, [], None, None)
    return card, [write_report]


def _reconstruct_cards(card_dicts):
    """Reconstruct TopicCard objects from stored dicts."""
    from models import TopicCard
    cards = []
    for d in card_dicts:
        card = TopicCard()
        for key, val in d.items():
            if hasattr(card, key):
                try:
                    setattr(card, key, val)
                except (TypeError, AttributeError):
                    pass
        cards.append(card)
    return cards


def _republish(topic_cards, reports, run_time):
    """Republish existing cards with updated timestamp."""
    synth, synth_report = synthesize.run(topic_cards)
    reports.append(synth_report)

    qscan, qscan_report = quickscan.run(topic_cards)
    reports.append(qscan_report)

    act_data, act_report = action_layer.run(topic_cards)
    reports.append(act_report)

    quality, validate_report = validate.run(topic_cards)
    reports.append(validate_report)

    preds_data, _ = predictions.run(topic_cards)

    html = publish.run(topic_cards, synth, qscan, reports, run_time, quality, preds_data, act_data)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")

    return html
