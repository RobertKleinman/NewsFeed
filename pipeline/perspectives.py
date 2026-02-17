"""
Step 5: Map perspectives (multi-model) and select sources (code).
Input: story group (list of Article)
Output: (selected_sources, missing_perspectives, perspectives, report)

Multiple LLMs independently identify the meaningful viewpoint axes for the story
and map them to available sources. Their divergence expands the lens.
Code then deterministically picks one source per perspective.
"""

import json
import re
import time

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


def map_perspectives(story_group):
    """Ask multiple LLMs what perspectives matter for this story."""
    lead = story_group[0]
    source_lines = []
    for a in story_group[:10]:
        source_lines.append("- {} (region: {}, leaning: {}): \"{}\"".format(
            a.source_name, a.source_region, a.source_bias, a.title))
    source_list = "\n".join(source_lines)

    prompt = """This story is about: {title}

Here are the sources covering it:
{sources}

Identify 3-5 meaningfully different perspectives or stakeholder positions on this story.
These could be political (left/right), regional (Western/Global South), institutional
(government/industry/civil society), ideological, religious, economic, or any other axis
that matters for THIS specific story.

Don't default to generic left/right if other axes are more relevant.
For each perspective, name which of the available sources above would best represent it.

Return ONLY a JSON array like:
[
  {{"perspective": "US administration position", "sources": ["Fox News", "AP News"], "reasoning": "brief why"}},
  {{"perspective": "Canadian sovereignty concern", "sources": ["CBC News"], "reasoning": "brief why"}}
]""".format(title=lead.title, sources=source_list)

    all_perspectives = []
    report = StepReport("perspectives", items_in=len(story_group))

    for llm_id in [k for k in llm_caller.get_available_llms() if k != "gemini_pro"][:3]:
        config = LLM_CONFIGS[llm_id]
        report.llm_calls += 1
        result = llm_caller.call_by_id(llm_id,
            "You are a media analyst who understands editorial perspectives globally. Return only JSON.",
            prompt, 1200)
        time.sleep(1)
        if result:
            try:
                json_match = re.search(r'\[.*\]', result, re.DOTALL)
                if json_match:
                    perspectives = json.loads(json_match.group())
                    for p in perspectives:
                        p["identified_by"] = config["label"]
                    all_perspectives.extend(perspectives)
                    report.llm_successes += 1
            except Exception:
                report.llm_failures += 1
        else:
            report.llm_failures += 1

    merged = _merge_perspectives(all_perspectives, len(story_group[:10]))
    report.items_out = len(merged)
    return merged, report


def _merge_perspectives(perspectives, source_count=5):
    if not perspectives:
        return []
    merged = []
    for p in perspectives:
        name = p.get("perspective", "").lower().strip()
        is_dup = False
        for existing in merged:
            ex_name = existing.get("perspective", "").lower().strip()
            words_a = set(name.split())
            words_b = set(ex_name.split())
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            if overlap > 0.4:
                existing["identified_by"] = existing.get("identified_by", "") + ", " + p.get("identified_by", "")
                existing_s = set(existing.get("sources", []))
                new_s = set(p.get("sources", []))
                existing["sources"] = list(existing_s | new_s)
                is_dup = True
                break
        if not is_dup:
            merged.append(p)
    max_persp = min(7, max(5, source_count))
    return merged[:max_persp]


def select_sources(story_group, perspectives):
    """Deterministic: pick one source per perspective, favoring diversity."""
    available = {a.source_name: a for a in story_group}
    selected = []
    used = set()
    used_regions = set()
    used_biases = set()
    missing = []

    for persp in perspectives:
        recommended = persp.get("sources", [])
        picked = None
        # Score candidates: prefer sources from new regions and different biases
        candidates = []
        for src in recommended:
            if src in available and src not in used:
                a = available[src]
                score = 1.0
                region = a.source_region.lower().split("-")[0]
                bias = a.source_bias.lower()
                # Bonus for new region
                if region not in used_regions:
                    score += 0.5
                # Bonus for different political leaning
                if bias not in used_biases:
                    score += 0.3
                candidates.append((src, a, score, region, bias))
        if candidates:
            candidates.sort(key=lambda x: x[2], reverse=True)
            src, picked, _, region, bias = candidates[0]
            used_regions.add(region)
            used_biases.add(bias)

        if picked:
            used.add(picked.source_name)
            selected.append({
                "article": picked,
                "perspective": persp.get("perspective", ""),
                "identified_by": persp.get("identified_by", ""),
            })
        else:
            missing.append(persp.get("perspective", "Unknown"))

    # Always include lead if nothing matched
    if not selected and story_group:
        selected.append({
            "article": story_group[0],
            "perspective": "Primary report",
            "identified_by": "system",
        })

    return selected, missing


def run(story_group):
    """Full step: map perspectives then select sources. Returns (selected, missing, perspectives, report)."""
    perspectives, report = map_perspectives(story_group)

    if not perspectives:
        perspectives = [{"perspective": "General coverage",
                        "sources": [a.source_name for a in story_group[:3]]}]

    selected, missing = select_sources(story_group, perspectives)
    report.notes.append("{} sources, {} missing".format(len(selected), len(missing)))
    return selected, missing, perspectives, report
