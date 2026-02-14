"""
Step 11: Publish as HTML.
Input: topic cards, synthesis, run reports, run time
Output: HTML string

Design: layered reading experience.
- Quick scan: comparison grid, key facts as bullets, color-coded sections
- Detail: expandable prose, raw comparisons, investigation findings
Every source is labeled with its perspective.
"""

from datetime import datetime, timezone

import llm as llm_caller
from config import TOPICS, LLM_CONFIGS


def run(topic_cards, synthesis, quickscan_data, reports, run_time):
    """Generate HTML. Returns html string."""
    stories_html = ""
    for i, card in enumerate(topic_cards):
        stories_html += _render_card(card, i)

    quickscan_html = _render_quickscan(quickscan_data)
    synthesis_html = _render_synthesis(synthesis)
    filter_buttons = _render_filters()
    run_report_html = _render_run_report(reports, run_time)
    llms_used = ", ".join(LLM_CONFIGS[k]["label"] for k in llm_caller.get_available_llms())
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    return HTML_TEMPLATE.format(
        date=now,
        num_stories=len(topic_cards),
        llms=llms_used,
        quickscan=quickscan_html,
        synthesis=synthesis_html,
        filters=filter_buttons,
        stories=stories_html,
        run_report=run_report_html,
        runtime=run_time)


def _esc(text):
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lines_to_items(text):
    """Convert newline-separated text into list items."""
    if not text:
        return ""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    items = ""
    for line in lines:
        items += '<li class="scan-item">{}</li>'.format(_esc(line))
    return items


def _render_card(card, card_index=0):
    # Topic tags
    topic_tags = ""
    for t in card.get("topics", [])[:3]:
        if t in TOPICS:
            topic_tags += '<span class="topic-tag" data-topic="{}">{} {}</span>'.format(
                t, TOPICS[t]["icon"], TOPICS[t]["name"])

    # Source pills with perspective labels
    source_pills = ""
    for s in card.get("sources", []):
        source_pills += '<span class="source-pill"><strong>{name}</strong> <span class="perspective-label">{persp}</span> <span class="bias-label">{bias}</span></span>'.format(
            name=s["name"], persp=s["perspective"], bias=s["bias"])

    # === QUICK SCAN LAYER ===
    # What happened (always visible)
    what_happened = '<div class="what-happened"><p>{}</p></div>'.format(
        _esc(card.get("what_happened", "")))

    # Perspective comparison grid
    grid_html = _render_perspective_grid(card)

    # Key facts as scannable items
    facts_html = ""
    facts_items = _lines_to_items(card.get("agreed_facts", ""))
    if facts_items:
        facts_html = '<div class="scan-section section-agreed"><div class="scan-label">Agreed Facts</div><ul class="scan-list">{}</ul></div>'.format(facts_items)

    # Disagreements as scannable items
    disagree_html = ""
    disagree_items = _lines_to_items(card.get("disagreements", ""))
    if disagree_items and "no substantive" not in card.get("disagreements", "").lower():
        disagree_html = '<div class="scan-section section-disagree"><div class="scan-label">Points of Disagreement</div><ul class="scan-list">{}</ul></div>'.format(disagree_items)

    # What to watch
    watch_html = ""
    watch_items = _lines_to_items(card.get("what_to_watch", ""))
    if watch_items:
        watch_html = '<div class="scan-section section-watch"><div class="scan-label">What to Watch</div><ul class="scan-list">{}</ul></div>'.format(watch_items)

    # === EXPANDABLE DETAIL LAYER ===
    detail_sections = ""

    # Framing differences (detail)
    framing = card.get("framing_differences", "")
    if framing:
        detail_sections += '<div class="detail-section section-framing"><div class="detail-label">Framing & Perspective Detail</div><div class="detail-text">{}</div></div>'.format(
            _esc(framing).replace("\n", "<br>"))

    # Implications
    implications = card.get("implications", "")
    if implications:
        detail_sections += '<div class="detail-section section-implications"><div class="detail-label">Implications</div><div class="detail-text">{}</div></div>'.format(
            _esc(implications).replace("\n", "<br>"))

    # Predictions
    predictions = card.get("predictions", "")
    if predictions:
        pred_items = _lines_to_items(predictions)
        if pred_items:
            detail_sections += '<div class="detail-section section-predictions"><div class="detail-label">Predictions</div><ul class="scan-list">{}</ul></div>'.format(pred_items)

    # Key unknowns
    unknowns = card.get("key_unknowns", "")
    if unknowns:
        detail_sections += '<div class="detail-section section-unknowns"><div class="detail-label">Key Unknowns</div><div class="detail-text">{}</div></div>'.format(
            _esc(unknowns).replace("\n", "<br>"))

    # Missing viewpoints
    missing = card.get("missing_viewpoints", "")
    if missing and "all identified" not in missing.lower() and "none" not in missing.lower():
        detail_sections += '<div class="detail-section section-missing"><div class="detail-label">Missing Viewpoints</div><div class="detail-text">{}</div></div>'.format(
            _esc(missing).replace("\n", "<br>"))

    # Investigation (background + context)
    investigation = card.get("investigation", "")
    if investigation:
        detail_sections += '<div class="detail-section section-investigation"><div class="detail-label">Background & Context (AI Analysis)</div><div class="detail-text">{}</div></div>'.format(
            _esc(investigation).replace("\n", "<br>"))

    # Raw comparisons (always collapsed)
    comp_html = ""
    comparisons = card.get("comparisons", {})
    if comparisons:
        comp_blocks = ""
        for model, text in comparisons.items():
            comp_blocks += '<div class="comp-block"><div class="comp-model">{}</div><div class="comp-text">{}</div></div>'.format(
                model, _esc(text).replace("\n", "<br>"))
        comp_html = '<details class="raw-comp"><summary>Raw Model Comparisons ({} models)</summary>{}</details>'.format(
            len(comparisons), comp_blocks)

    # Written by
    written_by = card.get("written_by", "")
    writer_html = ""
    if written_by:
        writer_html = '<div class="written-by">Card written by {}</div>'.format(written_by)

    return """
    <article class="story-card" id="topic-card-{card_idx}" data-topics="{topic_ids}">
        <div class="topic-tags">{tags}</div>
        <h2 class="story-title">{title}</h2>
        <div class="story-meta">
            <span>{src_count} sources</span>
            <span>{persp_count} perspectives</span>
        </div>
        <div class="sources-row">{pills}</div>

        {what_happened}
        {grid}
        {facts}
        {disagree}
        {watch}

        <details class="detail-expand">
            <summary>Full Analysis</summary>
            {detail_sections}
            {comp}
            {writer}
        </details>
    </article>""".format(
        topic_ids=" ".join(card.get("topics", [])[:3]),
        card_idx=card_index,
        tags=topic_tags,
        title=card.get("title", ""),
        src_count=card.get("source_count", 0),
        persp_count=card.get("perspectives_used", 0),
        pills=source_pills,
        what_happened=what_happened,
        grid=grid_html,
        facts=facts_html,
        disagree=disagree_html,
        watch=watch_html,
        detail_sections=detail_sections,
        comp=comp_html,
        writer=writer_html)


def _render_perspective_grid(card):
    """Render a visual comparison grid showing each source's position."""
    sources = card.get("sources", [])
    framing = card.get("framing_differences", "")
    if len(sources) < 2:
        return ""

    rows = ""
    for s in sources:
        # Try to find this source's specific framing from the framing text
        source_framing = _extract_source_framing(s["name"], framing)
        if not source_framing:
            source_framing = "See full analysis"

        rows += """<div class="grid-row">
            <div class="grid-source">
                <div class="grid-source-name">{name}</div>
                <div class="grid-source-meta">{perspective}</div>
            </div>
            <div class="grid-position">{framing}</div>
        </div>""".format(
            name=s["name"],
            perspective=s["perspective"],
            framing=_esc(source_framing))

    return '<div class="perspective-grid"><div class="grid-header">How Each Source Frames This Story</div>{}</div>'.format(rows)


def _extract_source_framing(source_name, framing_text):
    """Try to pull out the framing note specific to one source."""
    if not framing_text:
        return ""
    for line in framing_text.split("\n"):
        if source_name.lower() in line.lower():
            # Clean up the line - remove the source name prefix if present
            return line.strip()[:200]
    return ""


def _render_quickscan(data):
    """Render the Today in 60 Seconds section."""
    if not data:
        return ""

    stories_items = ""
    for story in data.get("top_stories", [])[:10]:
        consensus = story.get("consensus", "split")
        if consensus == "consensus":
            icon = '<span class="consensus-dot dot-green" title="Sources agree"></span>'
        elif consensus == "contested":
            icon = '<span class="consensus-dot dot-red" title="Highly contested"></span>'
        else:
            icon = '<span class="consensus-dot dot-yellow" title="Sources split"></span>'

        card_idx = story.get("card_index", 0)
        sources = story.get("key_sources", "")
        stories_items += '<a href="#topic-card-{idx}" class="qs-story">{icon}<div class="qs-story-content"><span class="qs-headline">{headline}</span><span class="qs-summary">{summary}</span><span class="qs-sources">{sources}</span></div></a>'.format(
            idx=card_idx, icon=icon,
            headline=_esc(story.get("headline", "")),
            summary=_esc(story.get("summary_line", "")),
            sources=_esc(sources))

    tensions_items = ""
    for t in data.get("key_tensions", [])[:4]:
        tensions_items += '<div class="qs-tension">{}</div>'.format(_esc(t.get("tension", "")))

    watch_items = ""
    for w in data.get("watch_list", [])[:4]:
        horizon = w.get("time_horizon", "developing")
        if horizon == "imminent":
            badge = '<span class="horizon-badge badge-imminent">IMMINENT</span>'
        elif horizon == "this_week":
            badge = '<span class="horizon-badge badge-week">THIS WEEK</span>'
        else:
            badge = '<span class="horizon-badge badge-developing">DEVELOPING</span>'
        watch_items += '<div class="qs-watch">{badge} {item}</div>'.format(
            badge=badge, item=_esc(w.get("item", "")))

    tensions_section = ""
    if tensions_items:
        tensions_section = '<div class="qs-box qs-tensions"><div class="qs-box-title">Key Tensions</div>{}</div>'.format(tensions_items)

    watch_section = ""
    if watch_items:
        watch_section = '<div class="qs-box qs-watchlist"><div class="qs-box-title">Watch List</div>{}</div>'.format(watch_items)

    return """<div class="quickscan">
        <div class="qs-header">Today in 60 Seconds</div>
        <div class="qs-legend">
            <span><span class="consensus-dot dot-green"></span> Consensus</span>
            <span><span class="consensus-dot dot-yellow"></span> Split</span>
            <span><span class="consensus-dot dot-red"></span> Contested</span>
        </div>
        <div class="qs-stories">{stories}</div>
        <div class="qs-bottom-row">{tensions}{watch}</div>
    </div>""".format(stories=stories_items, tensions=tensions_section, watch=watch_section)


def _render_synthesis(synthesis):
    if not synthesis:
        return ""

    # Try to parse sections
    sections = {}
    for label in ["THEMES:", "NOTABLE DISAGREEMENTS:", "LOOKING AHEAD:"]:
        if label in synthesis:
            start = synthesis.index(label) + len(label)
            # Find end
            end = len(synthesis)
            for next_label in ["THEMES:", "NOTABLE DISAGREEMENTS:", "LOOKING AHEAD:"]:
                if next_label != label and next_label in synthesis[start:]:
                    candidate = start + synthesis[start:].index(next_label)
                    if candidate < end:
                        end = candidate
            sections[label] = synthesis[start:end].strip()

    if sections:
        html = ""
        if "THEMES:" in sections:
            html += '<div class="synth-section"><div class="synth-label">Key Themes</div><p>{}</p></div>'.format(
                _esc(sections["THEMES:"]).replace("\n\n", "</p><p>").replace("\n", "<br>"))
        if "NOTABLE DISAGREEMENTS:" in sections:
            html += '<div class="synth-section synth-disagree"><div class="synth-label">Notable Disagreements</div><p>{}</p></div>'.format(
                _esc(sections["NOTABLE DISAGREEMENTS:"]).replace("\n\n", "</p><p>").replace("\n", "<br>"))
        if "LOOKING AHEAD:" in sections:
            items = _lines_to_items(sections["LOOKING AHEAD:"])
            if items:
                html += '<div class="synth-section synth-ahead"><div class="synth-label">Looking Ahead</div><ul class="scan-list">{}</ul></div>'.format(items)
        return html

    # Fallback: plain paragraphs
    escaped = _esc(synthesis)
    return "<p>{}</p>".format(escaped.replace("\n\n", "</p><p>").replace("\n", "<br>"))


def _render_filters():
    html = '<button class="filter-btn active" data-filter="all">All</button>'
    for tid, info in TOPICS.items():
        html += '<button class="filter-btn" data-filter="{}">{} {}</button>'.format(
            tid, info["icon"], info["name"])
    return html


def _render_run_report(reports, run_time):
    lines = []
    total_llm = 0
    total_ok = 0
    for r in reports:
        total_llm += r.llm_calls
        total_ok += r.llm_successes
        notes = " | ".join(r.notes) if r.notes else ""
        lines.append("{}: {} in / {} out{}".format(
            r.step_name, r.items_in, r.items_out,
            " | " + notes if notes else ""))
    summary = " | ".join(lines)
    return "Pipeline: {} | LLM calls: {}/{} succeeded | Runtime: {}s".format(
        summary, total_ok, total_llm, run_time)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Intelligence Briefing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #0a0e17; --card-bg: #111827; --border: #1e293b;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #f59e0b;
    --blue: #3b82f6; --green: #10b981; --red: #ef4444;
    --purple: #a78bfa; --slate: #64748b; --section-bg: #0f172a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; padding: 0 1rem; max-width: 900px; margin: 0 auto; }}

.masthead {{ text-align: center; padding: 2rem 0 1rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }}
.masthead h1 {{ font-family: 'Newsreader', serif; font-size: 2rem; color: var(--accent); }}
.masthead .meta {{ font-size: 0.85rem; color: var(--muted); margin-top: 0.3rem; }}

/* Quickscan */
.quickscan {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid var(--accent); border-radius: 10px; padding: 1.5rem; margin-bottom: 2rem; }}
.qs-header {{ font-family: 'Newsreader', serif; font-size: 1.4rem; color: var(--accent); margin-bottom: 0.5rem; }}
.qs-legend {{ display: flex; gap: 1rem; font-size: 0.75rem; color: var(--muted); margin-bottom: 1rem; align-items: center; }}
.consensus-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}
.dot-green {{ background: var(--green); }}
.dot-yellow {{ background: var(--accent); }}
.dot-red {{ background: var(--red); }}
.qs-stories {{ display: flex; flex-direction: column; gap: 0.4rem; }}
.qs-story {{ display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.5rem 0.6rem; background: rgba(255,255,255,0.03); border-radius: 6px; text-decoration: none; color: var(--text); transition: background 0.15s; cursor: pointer; }}
.qs-story:hover {{ background: rgba(255,255,255,0.07); }}
.qs-story .consensus-dot {{ margin-top: 0.45rem; flex-shrink: 0; }}
.qs-story-content {{ flex: 1; }}
.qs-headline {{ font-weight: 600; font-size: 0.9rem; display: block; }}
.qs-summary {{ font-size: 0.82rem; color: var(--muted); display: block; margin-top: 0.15rem; }}
.qs-sources {{ font-size: 0.72rem; color: var(--purple); display: block; margin-top: 0.15rem; }}
.qs-bottom-row {{ display: flex; gap: 1rem; margin-top: 1rem; }}
.qs-box {{ flex: 1; padding: 0.8rem; background: rgba(255,255,255,0.03); border-radius: 6px; }}
.qs-box-title {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; font-weight: 600; }}
.qs-tensions .qs-box-title {{ color: var(--red); }}
.qs-watchlist .qs-box-title {{ color: var(--blue); }}
.qs-tension {{ font-size: 0.82rem; padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.qs-tension:last-child {{ border-bottom: none; }}
.qs-watch {{ font-size: 0.82rem; padding: 0.3rem 0; display: flex; align-items: flex-start; gap: 0.4rem; }}
.horizon-badge {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.4rem; border-radius: 3px; font-weight: 600; flex-shrink: 0; }}
.badge-imminent {{ background: var(--red); color: #fff; }}
.badge-week {{ background: var(--accent); color: #000; }}
.badge-developing {{ background: var(--slate); color: #fff; }}
@media (max-width: 600px) {{ .qs-bottom-row {{ flex-direction: column; }} }}

/* Synthesis */
.synthesis-expand {{ margin-bottom: 1.5rem; }}
.synthesis-toggle {{ font-size: 0.9rem; color: var(--muted); cursor: pointer; padding: 0.5rem 0; font-weight: 500; }}
.synthesis-toggle:hover {{ color: var(--text); }}
.synthesis-box {{ background: var(--card-bg); border-left: 3px solid var(--accent); border-radius: 8px; padding: 1.5rem; margin-top: 0.5rem; }}
.synthesis-box h2 {{ font-family: 'Newsreader', serif; color: var(--accent); font-size: 1.3rem; margin-bottom: 1rem; }}
.synth-section {{ margin-bottom: 1rem; padding: 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.synth-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); margin-bottom: 0.4rem; font-weight: 600; }}
.synth-disagree .synth-label {{ color: var(--red); }}
.synth-ahead .synth-label {{ color: var(--blue); }}
.synth-section p {{ font-size: 0.9rem; margin-bottom: 0.5rem; }}

/* Filters */
.filter-bar {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.5rem; }}
.filter-btn {{ background: var(--card-bg); color: var(--muted); border: 1px solid var(--border); border-radius: 20px; padding: 0.3rem 0.8rem; font-size: 0.78rem; cursor: pointer; font-family: 'DM Sans', sans-serif; }}
.filter-btn.active {{ background: var(--accent); color: #000; border-color: var(--accent); font-weight: 600; }}

/* Story cards */
.story-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.topic-tags {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }}
.topic-tag {{ font-size: 0.73rem; padding: 0.15rem 0.5rem; border-radius: 12px; border: 1px solid var(--border); color: var(--muted); }}
.story-title {{ font-family: 'Newsreader', serif; font-size: 1.25rem; line-height: 1.4; margin-bottom: 0.4rem; }}
.story-meta {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 0.5rem; display: flex; gap: 1rem; }}

/* Source pills */
.sources-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1rem; }}
.source-pill {{ font-size: 0.73rem; padding: 0.25rem 0.6rem; background: var(--section-bg); border-radius: 10px; color: var(--text); border: 1px solid var(--border); }}
.source-pill strong {{ color: var(--text); }}
.perspective-label {{ color: var(--purple); font-style: italic; }}
.perspective-label::before {{ content: "— "; }}
.bias-label {{ color: var(--muted); font-size: 0.68rem; }}

/* What happened */
.what-happened {{ margin-bottom: 1rem; padding: 0.8rem; background: var(--section-bg); border-left: 3px solid var(--blue); border-radius: 0 6px 6px 0; }}
.what-happened p {{ font-size: 0.95rem; }}

/* Perspective grid */
.perspective-grid {{ margin-bottom: 1rem; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
.grid-header {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--purple); padding: 0.5rem 0.8rem; background: var(--section-bg); border-bottom: 1px solid var(--border); }}
.grid-row {{ display: flex; border-bottom: 1px solid var(--border); }}
.grid-row:last-child {{ border-bottom: none; }}
.grid-source {{ width: 35%; padding: 0.5rem 0.8rem; background: var(--section-bg); border-right: 1px solid var(--border); }}
.grid-source-name {{ font-size: 0.85rem; font-weight: 600; }}
.grid-source-meta {{ font-size: 0.7rem; color: var(--purple); font-style: italic; }}
.grid-position {{ width: 65%; padding: 0.5rem 0.8rem; font-size: 0.85rem; color: var(--text); }}

/* Scan sections (quick read) */
.scan-section {{ margin-bottom: 0.8rem; padding: 0.6rem 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.scan-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; font-weight: 600; }}
.section-agreed .scan-label {{ color: var(--green); }}
.section-disagree .scan-label {{ color: var(--red); }}
.section-watch .scan-label {{ color: var(--blue); }}
.scan-list {{ list-style: none; padding: 0; }}
.scan-item {{ font-size: 0.87rem; padding: 0.25rem 0; padding-left: 1rem; position: relative; border-bottom: 1px solid rgba(255,255,255,0.03); }}
.scan-item:last-child {{ border-bottom: none; }}
.section-agreed .scan-item::before {{ content: "\\2713"; position: absolute; left: 0; color: var(--green); font-weight: bold; }}
.section-disagree .scan-item::before {{ content: "\\2717"; position: absolute; left: 0; color: var(--red); font-weight: bold; }}
.section-watch .scan-item::before {{ content: "\\25B6"; position: absolute; left: 0; color: var(--blue); font-size: 0.7rem; top: 0.35rem; }}

/* Detail layer (expandable) */
.detail-expand {{ margin-top: 0.8rem; border-top: 1px solid var(--border); }}
.detail-expand summary {{ font-size: 0.85rem; color: var(--muted); cursor: pointer; padding: 0.6rem 0; font-weight: 500; }}
.detail-expand summary:hover {{ color: var(--text); }}
.detail-section {{ margin-top: 0.8rem; padding: 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.detail-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; font-weight: 600; }}
.section-framing .detail-label {{ color: var(--purple); }}
.section-implications .detail-label {{ color: var(--blue); }}
.section-predictions .detail-label {{ color: var(--accent); }}
.section-unknowns .detail-label {{ color: var(--slate); }}
.section-missing .detail-label {{ color: var(--red); }}
.section-investigation .detail-label {{ color: var(--muted); }}
.detail-text {{ font-size: 0.87rem; line-height: 1.6; }}

/* Raw comparisons */
.raw-comp {{ margin-top: 0.8rem; }}
.raw-comp summary {{ font-size: 0.78rem; color: var(--muted); cursor: pointer; }}
.comp-block {{ margin-top: 0.6rem; padding: 0.6rem; background: var(--section-bg); border-radius: 6px; }}
.comp-model {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: var(--accent); margin-bottom: 0.2rem; }}
.comp-text {{ font-size: 0.78rem; color: var(--muted); line-height: 1.5; }}

.written-by {{ font-size: 0.7rem; color: var(--muted); text-align: right; margin-top: 0.5rem; font-style: italic; }}

/* Run report */
.run-report {{ margin-top: 2rem; padding: 1rem; background: var(--card-bg); border-radius: 8px; font-size: 0.75rem; color: var(--muted); text-align: center; border: 1px solid var(--border); line-height: 1.8; }}

@media (max-width: 600px) {{
    body {{ padding: 0 0.5rem; }}
    .story-card {{ padding: 1rem; }}
    .masthead h1 {{ font-size: 1.5rem; }}
    .grid-source {{ width: 40%; }}
    .grid-position {{ width: 60%; }}
}}
</style>
</head>
<body>
<div class="masthead">
    <h1>Global Intelligence Briefing</h1>
    <div class="meta">{date} | {num_stories} stories | Models: {llms}</div>
</div>

{quickscan}

<details class="synthesis-expand">
<summary class="synthesis-toggle">Executive Synthesis (full analysis)</summary>
<div class="synthesis-box">
    <h2>Executive Synthesis</h2>
    {synthesis}
</div>
</details>

<div class="filter-bar">{filters}</div>

{stories}

<div class="run-report">{run_report}</div>

<script>
document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const f = btn.dataset.filter;
        document.querySelectorAll('.story-card').forEach(c => {{
            c.style.display = (f === 'all' || c.dataset.topics.includes(f)) ? '' : 'none';
        }});
    }});
}});
</script>
</body>
</html>"""
