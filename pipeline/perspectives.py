"""
Step 5: Identify perspectives from actual sources in the cluster.
Looks at what angles are PRESENT, not what axes might theoretically exist.
No artificial limit on perspective count.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import Perspective, SelectedSource, StepReport


def run(cluster):
    """Identify perspectives and select sources. Returns (selected, missing, report)."""
    report = StepReport("perspectives", items_in=cluster.size)

    # Build source descriptions from actual cluster content
    source_lines = []
    for a in cluster.articles[:15]:  # Cap to keep prompt reasonable
        source_lines.append(
            '- {} (region: {}, leaning: {}): "{}" — {}'.format(
                a.source_name, a.source_region, a.source_bias,
                a.title, a.summary[:120]))
    source_list = "\n".join(source_lines)

    prompt = """Look at these sources covering the same story and identify what different angles they bring.

STORY: {title}

SOURCES:
{sources}

For each source, describe what angle or perspective it actually takes based on its headline and summary.
Then group sources with similar angles.
Finally, identify any important perspectives that are MISSING — viewpoints not represented by any source.

Return JSON:
{{
  "perspectives": [
    {{
      "label": "Brief label for this angle",
      "angle": "What this perspective emphasizes or how it frames the story",
      "sources": ["Source Name 1", "Source Name 2"]
    }}
  ],
  "missing": [
    "Description of a viewpoint not represented by any source and why it matters"
  ]
}}

Rules:
- Base perspectives on what sources ACTUALLY say, not theoretical axes
- Don't force left/right if that's not the real axis of difference
- Group sources with genuinely similar angles, don't make each source its own perspective
- Include ALL meaningfully different angles — no artificial limit
- Missing perspectives should be genuinely important gaps, not padding""".format(
        title=cluster.lead_title,
        sources=source_list)

    # Use 2 LLMs for perspective diversity
    all_perspectives = []
    all_missing = []

    available = [k for k in llm_caller.get_available_llms() if k != "gemini_pro"][:2]
    for llm_id in available:
        report.llm_calls += 1
        result = llm_caller.call_by_id(llm_id,
            "You analyze news perspectives. Return only JSON.",
            prompt, 2000)
        time.sleep(1)

        if not result:
            report.llm_failures += 1
            continue

        try:
            cleaned = re.sub(r'```json\s*', '', result)
            cleaned = re.sub(r'```\s*', '', cleaned).strip()
            m = re.search(r'\{.*\}', cleaned, re.DOTALL)
            data = json.loads(m.group() if m else cleaned)
            report.llm_successes += 1

            for p in data.get("perspectives", []):
                p["identified_by"] = LLM_CONFIGS[llm_id]["label"]
                all_perspectives.append(p)
            all_missing.extend(data.get("missing", []))
        except (json.JSONDecodeError, ValueError, AttributeError):
            report.llm_failures += 1

    # Merge similar perspectives
    merged = _merge_perspectives(all_perspectives)

    # Select one source per perspective (diversity-weighted)
    selected, missing_perspectives = _select_sources(cluster, merged)

    # Add LLM-identified missing perspectives
    for m in all_missing:
        if isinstance(m, str) and m not in missing_perspectives:
            missing_perspectives.append(m)

    # Deduplicate missing
    missing_perspectives = list(dict.fromkeys(missing_perspectives))

    report.items_out = len(selected)
    report.notes.append("{} perspectives, {} sources, {} missing".format(
        len(merged), len(selected), len(missing_perspectives)))

    return selected, missing_perspectives, report


def _merge_perspectives(perspectives):
    """Merge perspectives with similar labels."""
    if not perspectives:
        return []
    merged = []
    for p in perspectives:
        label = p.get("label", "").lower().strip()
        is_dup = False
        for existing in merged:
            ex_label = existing.get("label", "").lower().strip()
            words_a = set(label.split())
            words_b = set(ex_label.split())
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            if overlap > 0.4:
                # Merge sources
                ex_sources = set(existing.get("sources", []))
                new_sources = set(p.get("sources", []))
                existing["sources"] = list(ex_sources | new_sources)
                existing["identified_by"] = existing.get("identified_by", "") + ", " + p.get("identified_by", "")
                is_dup = True
                break
        if not is_dup:
            merged.append(p)
    return merged


def _select_sources(cluster, perspectives):
    """Pick one source per perspective, maximizing diversity."""
    available = {a.source_name: a for a in cluster.articles}
    selected = []
    used = set()
    used_regions = set()
    used_biases = set()
    missing = []

    for persp in perspectives:
        recommended = persp.get("sources", [])
        candidates = []
        for src in recommended:
            if src in available and src not in used:
                a = available[src]
                score = 1.0
                region = a.source_region.split("-")[0]
                bias = a.source_bias.lower()
                if region not in used_regions:
                    score += 0.5
                if bias not in used_biases:
                    score += 0.3
                candidates.append((src, a, score, region, bias))

        if candidates:
            candidates.sort(key=lambda x: x[2], reverse=True)
            src, article, _, region, bias = candidates[0]
            used.add(src)
            used_regions.add(region)
            used_biases.add(bias)
            selected.append(SelectedSource(
                article=article,
                perspective=persp.get("label", ""),
                angle=persp.get("angle", ""),
            ))
        else:
            missing.append(persp.get("label", "Unknown perspective"))

    # Ensure at least one source
    if not selected and cluster.articles:
        selected.append(SelectedSource(
            article=cluster.articles[0],
            perspective="Primary report",
            angle="Lead coverage",
        ))

    return selected, missing
