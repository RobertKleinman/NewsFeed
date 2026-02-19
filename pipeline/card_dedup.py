"""
Step 9b: Card Dedup — merge duplicate or overlapping cards after writing.

By the time cards are written, duplicates are obvious from titles and content.
This step catches anything the pre-write arc_merge missed.

Approach:
  1. LLM reviews all card titles + why_matters summaries
  2. Identifies cards that should be merged
  3. Keeps the richer card (more sources, deeper tier) and folds the other's
     sources and facts into it
"""

import json
import re
import time

import llm as llm_caller
from models import StepReport


def run(topic_cards):
    """Deduplicate written cards. Modifies list in place. Returns report."""
    print("\n>>> CARD DEDUP: {} cards...".format(len(topic_cards)))
    report = StepReport("card_dedup", items_in=len(topic_cards))

    if len(topic_cards) <= 3:
        report.items_out = len(topic_cards)
        return topic_cards, report

    available = llm_caller.get_available_llms()
    if not available:
        report.items_out = len(topic_cards)
        return topic_cards, report

    # Build card summaries for comparison
    lines = []
    for i, card in enumerate(topic_cards):
        d = card.to_dict()
        title = d.get("title", "")
        whats = d.get("whats_happening", d.get("what_happened", ""))[:150]
        why = d.get("why_matters", d.get("so_what", ""))[:150]
        src_count = d.get("source_count", 0)
        tier = d.get("depth_tier", "standard")
        lines.append('{}: [{}★ {}] "{}" | {} | {}'.format(
            i, d.get("importance", 3), tier, title[:80], whats[:100], why[:100]))

    prompt = """Review these written news cards. Some may be DUPLICATES or part of the SAME STORY that should be merged into one card.

CARDS:
{cards}

Find cards that should be MERGED because they cover:
1. The SAME EVENT from different angles (exact duplicates)
2. The SAME DEVELOPING STORY (story arcs that belong together)

Examples of what to merge:
- "Zuckerberg grilled about Meta targeting teens" + "Zuckerberg testifies in social media trial" = SAME
- "Trump weighs Iran strikes" + "US naval buildup near Iran" + "White House urges Iran deal" = SAME STORY
- "US commander visits Venezuela" + "Head of US Military visits Venezuela" = SAME
- "Trump repeals endangerment finding" + "What does endangerment repeal mean" = SAME

Return JSON:
{{
  "merges": [
    {{
      "cards": [2, 7, 11],
      "keep": 2,
      "reason": "All about the same Iran crisis"
    }}
  ]
}}

"keep" = the card index to keep as primary (pick the one with more sources or deeper analysis).
Other cards in the group will be folded into it.

Be AGGRESSIVE. If two cards are about the same situation, merge them.
If no merges: {{"merges": []}}""".format(cards="\n".join(lines))

    # Get proposals from multiple voters
    all_proposals = []
    for llm_id in available[:2]:
        report.llm_calls += 1
        result = llm_caller.call_by_id(llm_id,
            "News editor finding duplicate stories. Return only JSON. Be aggressive about merging.",
            prompt, 2000)
        time.sleep(0.5)

        if not result:
            report.llm_failures += 1
            continue

        try:
            cleaned = re.sub(r'```json\s*', '', result)
            cleaned = re.sub(r'```\s*', '', cleaned).strip()
            m = re.search(r'\{.*\}', cleaned, re.DOTALL)
            data = json.loads(m.group() if m else cleaned)
            report.llm_successes += 1

            for merge in data.get("merges", []):
                cards = merge.get("cards", [])
                valid = [i for i in cards if isinstance(i, int) and 0 <= i < len(topic_cards)]
                if len(valid) >= 2:
                    keep = merge.get("keep", valid[0])
                    if keep not in valid:
                        keep = valid[0]
                    all_proposals.append({"cards": valid, "keep": keep})
        except (json.JSONDecodeError, ValueError, AttributeError):
            report.llm_failures += 1

    if not all_proposals:
        report.items_out = len(topic_cards)
        report.notes.append("no card merges found")
        return topic_cards, report

    # Consolidate proposals with union-find
    n = len(topic_cards)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Track which card to keep in each group
    keep_votes = {}
    for prop in all_proposals:
        cards = prop["cards"]
        keep = prop["keep"]
        for i in range(1, len(cards)):
            union(cards[0], cards[i])
        root = find(cards[0])
        keep_votes.setdefault(root, []).append(keep)

    # Build groups
    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    # Process merges
    to_remove = set()
    for root, members in groups.items():
        if len(members) < 2:
            continue

        # Pick the keep card (most votes, or highest source count)
        votes = keep_votes.get(root, [])
        if votes:
            # Most voted keep card
            from collections import Counter
            keep_idx = Counter(votes).most_common(1)[0][0]
        else:
            keep_idx = members[0]

        # Ensure keep_idx is valid
        if keep_idx not in members:
            keep_idx = members[0]

        primary = topic_cards[keep_idx]
        primary_d = primary.to_dict()

        # Fold other cards' data into primary
        for idx in members:
            if idx == keep_idx:
                continue
            donor = topic_cards[idx]
            donor_d = donor.to_dict()

            # Merge sources
            existing_urls = {s.get("url") for s in primary_d.get("sources", [])}
            for s in donor_d.get("sources", []):
                if s.get("url") not in existing_urls:
                    primary.sources.append(s)
                    primary.source_count += 1

            # Merge key facts (dedup by content)
            existing_facts = set(f.lower()[:50] for f in (primary.key_facts or primary.agreed_facts))
            for f in (donor.key_facts or donor.agreed_facts):
                if isinstance(f, str) and f.lower()[:50] not in existing_facts:
                    primary.key_facts.append(f)
                    existing_facts.add(f.lower()[:50])

            # Merge context
            for c in (donor.context or []):
                if isinstance(c, str) and c not in primary.context:
                    primary.context.append(c)

            # Merge unknowns
            existing_qs = {u.get("q", u.get("question", "")).lower()[:40]
                          for u in (primary.unknowns or [])}
            for u in (donor.unknowns or []):
                q = u.get("q", u.get("question", "")).lower()[:40]
                if q and q not in existing_qs:
                    primary.unknowns.append(u)

            to_remove.add(idx)
            print("    MERGED card {} into {}: \"{}\" <- \"{}\"".format(
                idx, keep_idx,
                primary_d.get("title", "")[:40],
                donor_d.get("title", "")[:40]))

    # Remove merged cards
    result_cards = [c for i, c in enumerate(topic_cards) if i not in to_remove]

    report.items_out = len(result_cards)
    report.notes.append("{} cards merged away, {} -> {}".format(
        len(to_remove), len(topic_cards), len(result_cards)))
    print("    Result: {} -> {} cards ({} merged)".format(
        len(topic_cards), len(result_cards), len(to_remove)))
    return result_cards, report
