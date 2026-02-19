"""
Step 3b: Story Arc Merge — combine related event clusters into single stories.

After clustering gives us event-level groups, this step identifies clusters
that are part of the same developing story arc and merges them into one.

Example: "US-Iran nuclear talks", "Vance says strikes on table", "Oil jumps 4%",
"Iran fortifying sites" are different events but one story arc.

The reader gets one comprehensive card instead of five shallow ones.
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

    # Only consider clusters with 2+ articles or high-relevance singles
    summaries = []
    for i, c in enumerate(clusters[:40]):
        sources = ", ".join(c.source_names()[:3])
        topics = ", ".join(c.topic_spread[:2])
        summaries.append("{}: \"{}\" ({} sources, topics: {}, sources: {})".format(
            i, c.lead_title[:80], c.size, topics, sources))

    prompt = """Review these news story clusters. Some may be DIFFERENT EVENTS that are part of the SAME DEVELOPING STORY.

CLUSTERS:
{clusters}

Identify clusters that should be MERGED into a single story card because they're
all part of the same developing situation. The reader would benefit from seeing
them as one comprehensive story rather than separate cards.

MERGE when:
- Multiple aspects of the same geopolitical situation (e.g., talks + military buildup + oil impact)
- Different angles on the same policy/event (e.g., a trial from prosecution vs defense angle)
- Cause and effect within the same story (e.g., announcement + market reaction)

DO NOT MERGE when:
- Stories just share a country or topic (e.g., Japan election + Japan earthquake)
- Stories are genuinely independent even if related (e.g., two different Supreme Court cases)

Return JSON:
{{
  "arcs": [
    {{
      "clusters": [2, 5, 8, 12],
      "arc_title": "Best title for the combined story",
      "reason": "Brief explanation"
    }}
  ]
}}

If no merges needed: {{"arcs": []}}""".format(clusters="\n".join(summaries))

    available = llm_caller.get_available_llms()
    if not available:
        report.items_out = len(clusters)
        return clusters, report

    report.llm_calls += 1
    result = llm_caller.call_by_id(available[0],
        "You identify story arcs in news clusters. Return only JSON.",
        prompt, 2000)
    time.sleep(0.5)

    if not result:
        report.llm_failures += 1
        report.items_out = len(clusters)
        return clusters, report

    try:
        cleaned = re.sub(r'```json\s*', '', result)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        data = json.loads(m.group() if m else cleaned)
        report.llm_successes += 1

        arcs = data.get("arcs", [])
        if not arcs:
            report.items_out = len(clusters)
            report.notes.append("no arcs identified")
            return clusters, report

        # Perform merges
        merged_indices = set()
        new_clusters = []

        for arc in arcs:
            indices = arc.get("clusters", [])
            arc_title = arc.get("arc_title", "")
            if len(indices) < 2:
                continue

            # Validate indices
            valid_indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(clusters)]
            if len(valid_indices) < 2:
                continue

            # Merge articles from all clusters in this arc
            all_articles = []
            all_topics = []
            for idx in valid_indices:
                all_articles.extend(clusters[idx].articles)
                for t in clusters[idx].topic_spread:
                    if t not in all_topics:
                        all_topics.append(t)
                merged_indices.add(idx)

            # Use arc title or best cluster title
            if not arc_title:
                # Use the cluster with the most articles as lead
                best = max(valid_indices, key=lambda i: clusters[i].size)
                arc_title = clusters[best].lead_title

            new_clusters.append(StoryCluster(
                articles=all_articles,
                cluster_id="arc_" + "_".join(str(i) for i in valid_indices[:4]),
                lead_title=arc_title,
                topic_spread=all_topics,
            ))
            print("    Arc merged: {} ({} clusters, {} articles)".format(
                arc_title[:60], len(valid_indices), len(all_articles)))

        # Add unmerged clusters
        for i, c in enumerate(clusters):
            if i not in merged_indices:
                new_clusters.append(c)

        report.items_out = len(new_clusters)
        report.notes.append("{} arcs merged, {} -> {} clusters".format(
            len(arcs), len(clusters), len(new_clusters)))
        print("    {} arcs merged: {} -> {} clusters".format(
            len(arcs), len(clusters), len(new_clusters)))
        return new_clusters, report

    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        report.llm_failures += 1
        print("    Arc merge parse error: {}".format(str(e)[:60]))
        report.items_out = len(clusters)
        return clusters, report
