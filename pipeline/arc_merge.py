"""
Step 3b: Story Arc Merge — combine related event clusters into single stories.

Two-pass approach:
  Pass 1: EXACT DUPLICATE detection — clusters about literally the same event
          (e.g., "Zuckerberg testifies" from different sources)
  Pass 2: STORY ARC detection — different events that are part of the same
          developing situation (e.g., Iran talks + military buildup + oil spike)

Uses multiple LLMs as voters to catch merges any single model might miss.
"""

import json
import re
import time

import llm as llm_caller
from models import StoryCluster, StepReport


def run(clusters):
    """Merge related clusters into story arcs. Returns (merged_clusters, report)."""
    print("\n>>> STORY ARC MERGE: {} clusters...".format(len(clusters)))
    report = StepReport("arc_merge", items_in=len(clusters))

    if len(clusters) <= 3:
        report.items_out = len(clusters)
        return clusters, report

    available = llm_caller.get_available_llms()
    if not available:
        report.items_out = len(clusters)
        return clusters, report

    # Build rich summaries including sample headlines for better matching
    summaries = []
    for i, c in enumerate(clusters[:50]):
        headlines = [a.title[:80] for a in c.articles[:4]]
        sources = [a.source_name for a in c.articles[:4]]
        summaries.append("{idx}: \"{title}\" | {size} sources: [{srcs}] | Headlines: {hdl}".format(
            idx=i,
            title=c.lead_title[:100],
            size=c.size,
            srcs=", ".join(sources),
            hdl=" /// ".join(headlines)))

    cluster_block = "\n".join(summaries)

    # Collect merge proposals from multiple LLMs
    all_proposals = []
    voters_used = 0

    for llm_id in available[:3]:
        proposals = _get_merge_proposals(llm_id, cluster_block, len(clusters), report)
        if proposals:
            all_proposals.extend(proposals)
            voters_used += 1

    if not all_proposals:
        report.items_out = len(clusters)
        report.notes.append("no merges proposed by any voter")
        return clusters, report

    print("    {} merge proposals from {} voters".format(len(all_proposals), voters_used))

    # Deduplicate and validate proposals — a merge happens if ANY voter suggests it
    # (aggressive merging — we'd rather merge too much than too little)
    merge_groups = _consolidate_proposals(all_proposals, len(clusters))

    if not merge_groups:
        report.items_out = len(clusters)
        report.notes.append("no valid merge groups after consolidation")
        return clusters, report

    # Execute merges
    merged_indices = set()
    new_clusters = []

    for group in merge_groups:
        indices = group["indices"]
        arc_title = group.get("title", "")

        all_articles = []
        all_topics = []
        for idx in indices:
            all_articles.extend(clusters[idx].articles)
            for t in clusters[idx].topic_spread:
                if t not in all_topics:
                    all_topics.append(t)
            merged_indices.add(idx)

        if not arc_title:
            best = max(indices, key=lambda i: clusters[i].size)
            arc_title = clusters[best].lead_title

        new_clusters.append(StoryCluster(
            articles=all_articles,
            cluster_id="arc_" + "_".join(str(i) for i in indices[:4]),
            lead_title=arc_title,
            topic_spread=all_topics,
        ))
        component_titles = [clusters[i].lead_title[:40] for i in indices]
        print("    MERGED: \"{}\" <- [{}]".format(
            arc_title[:60], " + ".join(component_titles)))

    # Add unmerged clusters
    for i, c in enumerate(clusters):
        if i not in merged_indices:
            new_clusters.append(c)

    report.items_out = len(new_clusters)
    report.notes.append("{} groups merged, {} -> {} clusters".format(
        len(merge_groups), len(clusters), len(new_clusters)))
    print("    Result: {} -> {} clusters ({} merge groups)".format(
        len(clusters), len(new_clusters), len(merge_groups)))
    return new_clusters, report


def _get_merge_proposals(llm_id, cluster_block, num_clusters, report):
    """Ask one LLM to identify clusters that should be merged."""
    prompt = """You are reviewing {n} news story clusters. Your job is to find clusters that should be MERGED into a single story card.

CLUSTERS:
{clusters}

Find TWO types of merges:

TYPE 1 — EXACT DUPLICATES: Clusters that are literally about the same event, just sourced from different outlets.
Example: "Zuckerberg grilled about Meta's strategy" and "Mark Zuckerberg testifies in social media trial" = SAME EVENT.
Example: "Top US commander visits Venezuela" and "Head of US Military Command visited Venezuela" = SAME EVENT.

TYPE 2 — STORY ARCS: Different events that are all part of the same developing situation. A reader would want these as ONE comprehensive card.
Example: "US-Iran nuclear talks stall" + "Trump weighs Iran strikes" + "US naval buildup near Iran" + "White House urges Iran deal" + "Regional powers try to prevent US-Iran war" = ALL part of the same Iran crisis story.
Example: "Trump repeals endangerment finding" + "What does endangerment repeal mean for climate" = SAME story.

DO NOT MERGE clusters that just share a country or broad topic but are genuinely separate stories.

Return JSON:
{{
  "merges": [
    {{
      "clusters": [2, 5, 8],
      "title": "Best combined title for this story",
      "type": "duplicate or arc",
      "reason": "Brief explanation"
    }}
  ]
}}

Be AGGRESSIVE about merging. If two clusters are about the same situation, merge them. When in doubt, merge.
If no merges needed: {{"merges": []}}""".format(n=num_clusters, clusters=cluster_block)

    report.llm_calls += 1
    result = llm_caller.call_by_id(llm_id,
        "News editor identifying duplicate and related stories. Return only JSON. Be aggressive about merging.",
        prompt, 3000)
    time.sleep(0.5)

    if not result:
        report.llm_failures += 1
        return []

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        merges = data.get("merges", data.get("arcs", []))
        proposals = []
        for merge in merges:
            indices = merge.get("clusters", [])
            valid = [i for i in indices if isinstance(i, int) and 0 <= i < num_clusters]
            if len(valid) >= 2:
                proposals.append({
                    "indices": valid,
                    "title": merge.get("title", ""),
                    "type": merge.get("type", "arc"),
                })
        return proposals

    except (json.JSONDecodeError, ValueError, AttributeError):
        report.llm_failures += 1
        return []


def _consolidate_proposals(proposals, num_clusters):
    """Merge overlapping proposals into final groups using union-find."""
    # Union-Find to handle overlapping proposals
    parent = list(range(num_clusters))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Title tracking — prefer the title from the largest proposal
    best_titles = {}

    for prop in proposals:
        indices = prop["indices"]
        title = prop.get("title", "")

        # Union all indices in this proposal
        for i in range(1, len(indices)):
            union(indices[0], indices[i])

        # Track best title
        root = find(indices[0])
        if root not in best_titles or len(indices) > len(best_titles[root].get("indices", [])):
            best_titles[root] = {"title": title, "indices": indices}

    # Collect groups
    groups_by_root = {}
    for i in range(num_clusters):
        root = find(i)
        if root not in groups_by_root:
            groups_by_root[root] = set()
        groups_by_root[root].add(i)

    # Only return groups with 2+ members (actual merges)
    result = []
    for root, members in groups_by_root.items():
        if len(members) >= 2:
            title = best_titles.get(root, {}).get("title", "")
            result.append({
                "indices": sorted(members),
                "title": title,
            })

    return result
