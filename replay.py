"""
Replay: Re-run write + repair + validate on cached comparison data.
Skips fetch, triage, cluster, select, perspectives, extract, compare.
Takes ~2-3 minutes instead of 20.

Usage:
  python replay.py                        # Replay all 12 stories
  python replay.py --stories 1,3,5        # Replay specific stories (1-indexed)
  python replay.py --stories 1 --verbose  # Detailed output for one story

Requires: API keys, output/briefing_data.json from a previous full run.
The cached data must include 'comparisons' and 'investigation' fields.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import llm as llm_caller
from pipeline import write, repair, enrich, validate, publish, quickscan, synthesize


def load_cache(path="output/briefing_data.json"):
    p = Path(path)
    if not p.exists():
        print("ERROR: No cached data at {}".format(path))
        print("Run the full pipeline first, then replay.")
        sys.exit(1)
    with open(p) as f:
        data = json.load(f)
    # Verify it has comparison data
    cards = data.get("cards", [])
    if not cards:
        print("ERROR: No cards in cache")
        sys.exit(1)
    has_comparisons = any(c.get("comparisons") for c in cards)
    if not has_comparisons:
        print("ERROR: Cache doesn't include comparison data.")
        print("You need a cache from a run that saved intermediate data.")
        print("Run the full pipeline once more to generate the right cache format.")
        sys.exit(1)
    return data


class FakeArticle:
    """Minimal article stand-in for write.py compatibility."""
    def __init__(self, source_data):
        self.source_name = source_data.get("name", "")
        self.source_region = source_data.get("region", "")
        self.source_bias = source_data.get("bias", "")
        self.url = source_data.get("url", "")
        self.published = source_data.get("pub_date", "")

    def source_label(self):
        return "{} ({}, {})".format(self.source_name, self.source_region, self.source_bias)


def replay_card(cached_card, verbose=False):
    """Re-run write step for one cached card."""
    title = cached_card.get("title", "Untitled")
    topics = cached_card.get("topics", [])
    comparisons = cached_card.get("comparisons", {})
    investigation = cached_card.get("investigation", "")
    sources_data = cached_card.get("sources", [])

    if not comparisons:
        if verbose:
            print("  Skipping: no comparison data cached")
        return None

    # Reconstruct source objects
    selected_sources = []
    for s in sources_data:
        if isinstance(s, dict):
            fake_article = FakeArticle(s)
            selected_sources.append({
                "article": fake_article,
                "perspective": s.get("perspective", "General coverage"),
            })
        elif isinstance(s, str):
            # Old format — just a name, no metadata
            fake_article = FakeArticle({"name": s})
            selected_sources.append({
                "article": fake_article,
                "perspective": "General coverage",
            })

    missing = cached_card.get("missing_perspective_list", [])
    if not missing:
        missing = []

    if verbose:
        print("  Title: {}".format(title[:70]))
        print("  Sources: {}".format(len(selected_sources)))
        print("  Comparisons from: {}".format(", ".join(comparisons.keys())))

    card, report = write.run(title, topics, selected_sources, missing, comparisons, investigation)

    if verbose and card:
        print("  Written by: {}".format(card.get("written_by", "?")))
        print("  Facts: {}".format(len(card.get("agreed_facts", []))))
        print("  Disputes: {}".format(len(card.get("disputes", []))))
        print("  Framing: {}".format(len(card.get("framing", []))))
        trunc = sum(1 for f in ["what_happened", "implications", "investigation"]
                   if card.get(f, "") and _quick_truncation_check(card.get(f, "")))
        print("  Truncated fields: {}".format(trunc))

    return card


def _quick_truncation_check(text):
    if not text or len(text) < 20:
        return False
    text = text.strip()
    if text[-1].isalpha() and text[-1].islower():
        return True
    if text[-1] in [',', ':', '(', '[', '{']:
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Replay write+validate on cached data")
    parser.add_argument("--stories", help="Comma-separated story indices (1-indexed). Default: all")
    parser.add_argument("--verbose", action="store_true", help="Detailed output per story")
    parser.add_argument("--data", default="output/briefing_data.json", help="Cache file path")
    parser.add_argument("--output", default="output/replay.html", help="Output HTML path")
    args = parser.parse_args()

    start = time.time()
    data = load_cache(args.data)
    all_cards = data.get("cards", [])
    print("Loaded {} cached cards from {}".format(len(all_cards), data.get("date", "?")))

    # Select which stories to replay
    if args.stories:
        indices = [int(x.strip()) - 1 for x in args.stories.split(",")]
        cards_to_replay = [(i, all_cards[i]) for i in indices if 0 <= i < len(all_cards)]
    else:
        cards_to_replay = list(enumerate(all_cards))

    print("Replaying {} stories...\n".format(len(cards_to_replay)))

    # Re-run write for each
    topic_cards = []
    for idx, cached in cards_to_replay:
        print("Story {}/{}: {}".format(idx + 1, len(all_cards), cached.get("title", "")[:60]))
        card = replay_card(cached, verbose=args.verbose)
        if card:
            topic_cards.append(card)
            print("  OK")
        else:
            print("  FAILED")
        time.sleep(0.5)

    if not topic_cards:
        print("\nNo cards generated")
        sys.exit(1)

    # Repair
    print("\nRepairing...")
    repair.run(topic_cards)

    # Enrich
    enrich.run(topic_cards)

    # Validate
    print("\nValidating...")
    quality_review, _ = validate.run(topic_cards)

    # Quick summary
    print("\n" + "=" * 60)
    print("REPLAY RESULTS")
    print("=" * 60)
    print("Quality: {}".format(quality_review.get("summary", "?")))

    truncated_cards = 0
    for card in topic_cards:
        for field in ["what_happened", "implications", "investigation"]:
            if _quick_truncation_check(card.get(field, "")):
                truncated_cards += 1
                break
    print("Cards with truncation: {}/{}".format(truncated_cards, len(topic_cards)))

    empty_facts = sum(1 for c in topic_cards if not c.get("agreed_facts"))
    print("Cards with empty facts: {}/{}".format(empty_facts, len(topic_cards)))

    runtime = int(time.time() - start)
    print("Runtime: {}s".format(runtime))

    # Optionally publish
    try:
        synth, _ = synthesize.run(topic_cards)
        qscan, _ = quickscan.run(topic_cards)
        html = publish.run(topic_cards, synth, qscan, [], runtime, quality_review)
        output_path = Path(args.output)
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        print("\nReplay output: {}".format(output_path))
    except Exception as e:
        print("\nPublish failed: {} (cards still validated above)".format(str(e)[:60]))

    print("=" * 60)


if __name__ == "__main__":
    main()
