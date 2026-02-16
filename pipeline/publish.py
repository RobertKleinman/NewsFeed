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


def run(topic_cards, synthesis, quickscan_data, reports, run_time, quality_review=None):
    """Generate HTML. Returns html string."""
    stories_html = ""
    for i, card in enumerate(topic_cards):
        stories_html += _render_card(card, i)

    quickscan_html = _render_quickscan(quickscan_data)
    synthesis_html = _render_synthesis(synthesis)
    filter_buttons = _render_filters()
    run_report_html = _render_run_report(reports, run_time)
    review_panel_html = _render_review_panel(quality_review)
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
        review_panel=review_panel_html,
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

    # Coverage spectrum bar (computed from data, no LLM)
    type_counts = card.get("source_type_counts", {})
    spectrum_html = ""
    if type_counts:
        parts = []
        for stype in ["wire", "mainstream", "regional", "niche", "think_tank", "opinion", "advocacy"]:
            count = type_counts.get(stype, 0)
            if count > 0:
                parts.append('<span class="spectrum-item"><span class="spectrum-label">{}</span> {}</span>'.format(
                    stype.replace("_", " ").title(), count))
        if parts:
            spectrum_html = '<div class="coverage-spectrum">Coverage: {}</div>'.format(" ".join(parts))

    # Source pills with perspective + type
    source_pills = ""
    for s in card.get("sources", []):
        stype = s.get("source_type", "mainstream")
        source_pills += '<span class="source-pill"><strong>{name}</strong> <span class="perspective-label">{persp}</span> <span class="source-type-tag type-{stype}">{stype}</span></span>'.format(
            name=s["name"], persp=s["perspective"], stype=stype)

    # === SCANNABLE LAYER (always visible) ===

    # What happened (tight, no prose)
    what_happened = '<div class="what-happened"><p>{}</p></div>'.format(
        _esc(card.get("what_happened", "")))

    # Agreed facts as tight bullets with source tags
    facts_html = ""
    agreed = card.get("agreed_facts", [])
    if isinstance(agreed, list) and agreed:
        items = ""
        for fact in agreed[:5]:
            if isinstance(fact, str) and fact.strip():
                items += '<li class="scan-item">{}</li>'.format(_esc(fact))
        if items:
            facts_html = '<div class="scan-section section-agreed"><div class="scan-label">Confirmed Facts</div><ul class="scan-list">{}</ul></div>'.format(items)
    elif isinstance(agreed, str) and agreed:
        items = _lines_to_items(agreed)
        if items:
            facts_html = '<div class="scan-section section-agreed"><div class="scan-label">Confirmed Facts</div><ul class="scan-list">{}</ul></div>'.format(items)

    # Disputes as paired side-by-side comparisons
    disputes_html = ""
    disputes = card.get("disputes", [])
    if isinstance(disputes, list) and disputes:
        dispute_blocks = ""
        for d in disputes[:4]:
            if isinstance(d, dict):
                dtype = d.get("type", "framing").upper()
                side_a = _esc(d.get("side_a", ""))
                side_b = _esc(d.get("side_b", ""))
                if side_a or side_b:
                    dispute_blocks += """<div class="dispute-pair">
                        <span class="dispute-type-tag">{dtype}</span>
                        <div class="dispute-sides">
                            <div class="dispute-side side-a">{side_a}</div>
                            <div class="dispute-vs">vs</div>
                            <div class="dispute-side side-b">{side_b}</div>
                        </div>
                    </div>""".format(dtype=dtype, side_a=side_a, side_b=side_b)
        if dispute_blocks:
            disputes_html = '<div class="scan-section section-disagree"><div class="scan-label">What\'s Disputed</div>{}</div>'.format(dispute_blocks)

    # Framing as quoted blocks
    framing_html = ""
    framing = card.get("framing", [])
    if isinstance(framing, list) and framing:
        framing_blocks = ""
        for f in framing[:5]:
            if isinstance(f, dict):
                source = _esc(f.get("source", ""))
                quote = _esc(f.get("quote", ""))
                frame = _esc(f.get("frame", ""))
                if quote or frame:
                    framing_blocks += '<div class="framing-quote"><span class="framing-source">{src}</span>{q}{f}</div>'.format(
                        src=source,
                        q=' <span class="framing-quoted">&ldquo;{}&rdquo;</span>'.format(quote) if quote else "",
                        f=' <span class="framing-desc">{}</span>'.format(frame) if frame else "")
        if framing_blocks:
            framing_html = '<div class="scan-section section-framing"><div class="scan-label">How Sources Frame It</div>{}</div>'.format(framing_blocks)

    # Perspective grid (promoted — key visual element)
    grid_html = _render_perspective_grid(card)

    # === COLLAPSED DETAIL LAYER ===
    detail_sections = ""

    # Implications
    implications = card.get("implications", "")
    if implications:
        detail_sections += '<div class="detail-section section-implications"><div class="detail-label">Implications</div><div class="detail-text">{}</div></div>'.format(
            _esc(implications).replace("\n", "<br>"))

    # Watch items (structured)
    watch_items = card.get("watch_items", [])
    if isinstance(watch_items, list) and watch_items:
        items_html = ""
        for w in watch_items[:4]:
            if isinstance(w, dict):
                event = _esc(w.get("event", ""))
                horizon = w.get("time_horizon", "")
                driver = _esc(w.get("driver", ""))
                badge = ""
                if horizon:
                    badge = '<span class="horizon-badge badge-developing">{}</span> '.format(_esc(horizon))
                items_html += '<li class="scan-item">{}{}{}</li>'.format(
                    badge, event,
                    ' <span class="watch-driver">If: {}</span>'.format(driver) if driver else "")
            elif isinstance(w, str):
                items_html += '<li class="scan-item">{}</li>'.format(_esc(w))
        if items_html:
            detail_sections += '<div class="detail-section section-watch"><div class="detail-label">What to Watch</div><ul class="scan-list">{}</ul></div>'.format(items_html)

    # Predictions (structured)
    predictions = card.get("predictions", [])
    if isinstance(predictions, list) and predictions:
        pred_html = ""
        for p in predictions[:3]:
            if isinstance(p, dict):
                scenario = _esc(p.get("scenario", ""))
                likelihood = p.get("likelihood", "")
                condition = _esc(p.get("condition", ""))
                lclass = "pred-" + likelihood if likelihood in ("likely", "possible", "unlikely") else ""
                pred_html += '<div class="prediction {lc}"><span class="pred-likelihood">{like}</span> {scen}{cond}</div>'.format(
                    lc=lclass, like=likelihood.upper() if likelihood else "",
                    scen=scenario,
                    cond=' <span class="pred-condition">Condition: {}</span>'.format(condition) if condition else "")
            elif isinstance(p, str):
                pred_html += '<div class="prediction">{}</div>'.format(_esc(p))
        if pred_html:
            detail_sections += '<div class="detail-section section-predictions"><div class="detail-label">Predictions</div>{}</div>'.format(pred_html)

    # Key unknowns
    unknowns = card.get("key_unknowns", [])
    if isinstance(unknowns, list) and unknowns:
        items = "".join('<li class="scan-item">{}</li>'.format(_esc(u)) for u in unknowns if isinstance(u, str) and u.strip())
        if items:
            detail_sections += '<div class="detail-section section-unknowns"><div class="detail-label">Key Unknowns</div><ul class="scan-list">{}</ul></div>'.format(items)
    elif isinstance(unknowns, str) and unknowns:
        detail_sections += '<div class="detail-section section-unknowns"><div class="detail-label">Key Unknowns</div><div class="detail-text">{}</div></div>'.format(
            _esc(unknowns).replace("\n", "<br>"))

    # Missing viewpoints
    missing = card.get("missing_viewpoints", "")
    if missing and "all identified" not in missing.lower() and not missing.strip() == "":
        detail_sections += '<div class="detail-section section-missing"><div class="detail-label">Missing Viewpoints</div><div class="detail-text">{}</div></div>'.format(
            _esc(missing).replace("\n", "<br>"))

    # Investigation - now concise, but still collapsible for safety
    investigation = card.get("investigation", "")
    if investigation:
        # Only show the concise version, not raw essay prose
        inv_text = _esc(investigation).replace("\n", "<br>")
        # If it's still very long, truncate and note
        if len(investigation) > 1000:
            detail_sections += '<details class="raw-comp"><summary>Background Research (Gemini Web Search)</summary><div class="detail-section section-investigation"><div class="detail-text">{}</div></div></details>'.format(inv_text)
        else:
            detail_sections += '<div class="detail-section section-investigation"><div class="detail-label">Background Research</div><div class="detail-text">{}</div></div>'.format(inv_text)

    # Raw comparisons
    comp_html = ""
    comparisons = card.get("comparisons", {})
    if comparisons:
        comp_blocks = ""
        for model, text in comparisons.items():
            comp_blocks += '<div class="comp-block"><div class="comp-model">{}</div><div class="comp-text">{}</div></div>'.format(
                model, _esc(text).replace("\n", "<br>"))
        comp_html = '<details class="raw-comp"><summary>Raw Model Comparisons ({} models)</summary>{}</details>'.format(
            len(comparisons), comp_blocks)

    written_by = card.get("written_by", "")
    writer_html = ""
    if written_by:
        writer_html = '<div class="written-by">Card written by {}</div>'.format(written_by)

    return """
    <article class="story-card" id="topic-card-{card_idx}" data-topics="{topic_ids}">
        <div class="card-header">
            <div class="topic-tags">{tags}</div>
            <h2 class="story-title">{title}</h2>
            <div class="story-meta">
                <span>{src_count} sources</span>
                <span>{persp_count} perspectives</span>
            </div>
            {spectrum}
        </div>
        <div class="sources-row">{pills}</div>

        {what_happened}
        {facts}
        {disputes}
        {framing}

        <details class="detail-expand">
            <summary>Deep Analysis</summary>
            {grid}
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
        spectrum=spectrum_html,
        pills=source_pills,
        what_happened=what_happened,
        facts=facts_html,
        disputes=disputes_html,
        framing=framing_html,
        grid=grid_html,
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
            return line.strip()
    return ""


def _render_quickscan(data):
    """Render Today in 60 Seconds grouped by topic."""
    if not data:
        return ""

    # Group stories by topic
    topic_groups = {}
    for story in data.get("top_stories", [])[:12]:
        topic_id = story.get("topic", "general")
        if topic_id not in topic_groups:
            topic_groups[topic_id] = []
        topic_groups[topic_id].append(story)

    # Render grouped stories
    stories_html = ""
    for topic_id, stories in topic_groups.items():
        topic_info = TOPICS.get(topic_id, {"icon": "", "name": topic_id})
        stories_html += '<div class="qs-topic-group"><div class="qs-topic-label">{icon} {name}</div>'.format(
            icon=topic_info.get("icon", ""), name=topic_info.get("name", topic_id))

        for story in stories:
            consensus = story.get("consensus", "split")
            if consensus == "consensus":
                icon = '<span class="consensus-dot dot-green" title="Sources agree"></span>'
            elif consensus == "contested":
                icon = '<span class="consensus-dot dot-red" title="Highly contested"></span>'
            else:
                icon = '<span class="consensus-dot dot-yellow" title="Sources split"></span>'

            card_idx = story.get("card_index", 0)
            sources = story.get("key_sources", "")
            fault = story.get("fault_line", "")
            stories_html += '<a href="#topic-card-{idx}" class="qs-story">{icon}<div class="qs-story-content"><span class="qs-headline">{headline}</span><span class="qs-fault">{fault}</span><span class="qs-sources">{sources}</span></div></a>'.format(
                idx=card_idx, icon=icon,
                headline=_esc(story.get("headline", "")),
                fault=_esc(fault),
                sources=_esc(sources))
        stories_html += '</div>'

    # Key tensions with type tags
    tensions_items = ""
    for t in data.get("key_tensions", [])[:4]:
        ttype = t.get("type", "")
        type_tag = ""
        if ttype:
            type_tag = '<span class="tension-type">{}</span> '.format(_esc(ttype.upper()))
        tensions_items += '<div class="qs-tension">{tag}{text}</div>'.format(
            tag=type_tag, text=_esc(t.get("tension", "")))

    # Watch list
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
    </div>""".format(stories=stories_html, tensions=tensions_section, watch=watch_section)


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


def _render_review_panel(quality_review):
    """Render hidden quality review panel with copy button."""
    if not quality_review or not quality_review.get("reviews"):
        return '<div class="review-panel" id="review-panel" style="display:none"><div class="review-header">Quality review not available</div></div>'

    summary = quality_review.get("summary", "")
    errors = quality_review.get("error_count", 0)
    warnings = quality_review.get("warning_count", 0)
    notes = quality_review.get("note_count", 0)

    if errors > 2:
        badge_class = "review-badge-error"
    elif errors > 0 or warnings > 3:
        badge_class = "review-badge-warning"
    else:
        badge_class = "review-badge-ok"

    cards_html = ""
    for review in quality_review["reviews"]:
        title = _esc(review.get("card_title", ""))
        score = review.get("quality_score", "?")
        strengths = _esc(review.get("strengths", ""))
        issues = review.get("issues", [])

        issues_html = ""
        for issue in issues:
            sev = issue.get("severity", "note")
            section = _esc(issue.get("section", ""))
            problem = _esc(issue.get("problem", ""))
            suggestion = _esc(issue.get("suggestion", ""))
            issues_html += '<div class="review-issue issue-{sc}"><span class="issue-sev">{sev}</span> <span class="issue-section">[{sect}]</span> {prob}<div class="issue-fix">Fix: {fix}</div></div>'.format(
                sc=sev, sev=sev.upper(), sect=section, prob=problem, fix=suggestion)

        cards_html += '<div class="review-card"><div class="review-card-header">Card {idx}: {title} <span class="quality-score">Score: {score}/10</span></div>{str_html}{issues}</div>'.format(
            idx=review.get("card_index", "?"), title=title, score=score,
            str_html='<div class="review-strengths">{}</div>'.format(strengths) if strengths else "",
            issues=issues_html or '<div class="review-no-issues">No issues found</div>')

    # Copyable plaintext version
    copy_lines = ["QUALITY REVIEW: " + summary, ""]
    for review in quality_review["reviews"]:
        copy_lines.append("Card {}: {} (Score: {}/10)".format(
            review.get("card_index", "?"), review.get("card_title", "")[:60], review.get("quality_score", "?")))
        for issue in review.get("issues", []):
            copy_lines.append("  {} [{}] {} -> Fix: {}".format(
                issue.get("severity", "").upper(), issue.get("section", ""),
                issue.get("problem", ""), issue.get("suggestion", "")))
        copy_lines.append("")
    copy_text = "\n".join(copy_lines)

    return """<div class="review-panel" id="review-panel" style="display:none">
        <div class="review-header">
            <span class="review-badge {badge_class}">{errors}E {warnings}W {notes}N</span>
            Quality Review: {summary}
        </div>
        <div class="review-cards">{cards}</div>
        <div class="review-copy-section">
            <button onclick="navigator.clipboard.writeText(document.getElementById('review-copy-text').textContent).then(function(){{this.textContent='Copied!'}}.bind(this))" class="review-copy-btn">Copy Review for Chat</button>
            <pre id="review-copy-text" class="review-copy-text">{copy_text}</pre>
        </div>
    </div>""".format(
        badge_class=badge_class, errors=errors, warnings=warnings, notes=notes,
        summary=_esc(summary), cards=cards_html, copy_text=_esc(copy_text))


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
html {{ scroll-behavior: smooth; }}
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
.qs-stories {{ display: flex; flex-direction: column; gap: 0.2rem; }}
.qs-topic-group {{ margin-bottom: 0.5rem; }}
.qs-topic-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom: 0.2rem; }}
.qs-story {{ display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.5rem 0.6rem; background: rgba(255,255,255,0.03); border-radius: 6px; text-decoration: none; color: var(--text); transition: background 0.15s; cursor: pointer; }}
.qs-story:hover {{ background: rgba(255,255,255,0.07); }}
.qs-story .consensus-dot {{ margin-top: 0.45rem; flex-shrink: 0; }}
.qs-story-content {{ flex: 1; }}
.qs-headline {{ font-weight: 600; font-size: 0.9rem; display: block; }}
.qs-fault {{ font-size: 0.82rem; color: var(--muted); display: block; margin-top: 0.15rem; font-style: italic; }}
.qs-sources {{ font-size: 0.72rem; color: var(--purple); display: block; margin-top: 0.15rem; }}
.qs-bottom-row {{ display: flex; gap: 1rem; margin-top: 1rem; }}
.qs-box {{ flex: 1; padding: 0.8rem; background: rgba(255,255,255,0.03); border-radius: 6px; }}
.qs-box-title {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; font-weight: 600; }}
.qs-tensions .qs-box-title {{ color: var(--red); }}
.qs-watchlist .qs-box-title {{ color: var(--blue); }}
.qs-tension {{ font-size: 0.82rem; padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.qs-tension:last-child {{ border-bottom: none; }}
.tension-type {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.3rem; border-radius: 3px; background: var(--red); color: #fff; margin-right: 0.3rem; vertical-align: middle; }}
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
.card-header {{ margin-bottom: 0.5rem; }}
.topic-tags {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }}
.topic-tag {{ font-size: 0.73rem; padding: 0.15rem 0.5rem; border-radius: 12px; border: 1px solid var(--border); color: var(--muted); }}
.story-title {{ font-family: 'Newsreader', serif; font-size: 1.25rem; line-height: 1.4; margin-bottom: 0.4rem; }}
.story-meta {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 0.3rem; display: flex; gap: 1rem; }}

/* Coverage spectrum */
.coverage-spectrum {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: var(--muted); padding: 0.3rem 0; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
.spectrum-item {{ padding: 0.1rem 0.4rem; background: var(--section-bg); border-radius: 3px; }}
.spectrum-label {{ color: var(--purple); }}

/* Source pills */
.sources-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1rem; }}
.source-pill {{ font-size: 0.73rem; padding: 0.25rem 0.6rem; background: var(--section-bg); border-radius: 10px; color: var(--text); border: 1px solid var(--border); }}
.source-pill strong {{ color: var(--text); }}
.perspective-label {{ color: var(--purple); font-style: italic; }}
.perspective-label::before {{ content: "— "; }}
.source-type-tag {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.05rem 0.25rem; border-radius: 2px; margin-left: 0.2rem; }}
.type-mainstream {{ background: var(--blue); color: #fff; }}
.type-wire {{ background: var(--green); color: #fff; }}
.type-niche {{ background: var(--purple); color: #fff; }}
.type-opinion {{ background: var(--accent); color: #000; }}
.type-think_tank {{ background: var(--slate); color: #fff; }}
.type-advocacy {{ background: var(--red); color: #fff; }}
.type-regional {{ background: #4a9eff; color: #fff; }}

/* What happened */
.what-happened {{ margin-bottom: 1rem; padding: 0.8rem; background: var(--section-bg); border-left: 3px solid var(--blue); border-radius: 0 6px 6px 0; }}
.what-happened p {{ font-size: 0.95rem; }}

/* Disputes - paired side-by-side */
.dispute-pair {{ margin-bottom: 0.6rem; padding: 0.6rem; background: rgba(239,68,68,0.05); border: 1px solid rgba(239,68,68,0.15); border-radius: 6px; }}
.dispute-type-tag {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.3rem; background: var(--red); color: #fff; border-radius: 3px; display: inline-block; margin-bottom: 0.4rem; }}
.dispute-sides {{ display: flex; gap: 0.5rem; align-items: flex-start; }}
.dispute-side {{ flex: 1; font-size: 0.85rem; padding: 0.4rem; background: var(--section-bg); border-radius: 4px; }}
.side-a {{ border-left: 2px solid var(--accent); }}
.side-b {{ border-left: 2px solid var(--blue); }}
.dispute-vs {{ font-size: 0.7rem; color: var(--red); font-weight: 600; padding-top: 0.4rem; flex-shrink: 0; }}

/* Framing quotes */
.framing-quote {{ padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 0.85rem; }}
.framing-quote:last-child {{ border-bottom: none; }}
.framing-source {{ font-weight: 600; color: var(--purple); }}
.framing-quoted {{ font-style: italic; color: var(--text); }}
.framing-desc {{ color: var(--muted); font-size: 0.8rem; }}

/* Predictions */
.prediction {{ padding: 0.3rem 0; font-size: 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.03); }}
.prediction:last-child {{ border-bottom: none; }}
.pred-likelihood {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.3rem; border-radius: 3px; margin-right: 0.3rem; }}
.pred-likely .pred-likelihood {{ background: var(--green); color: #fff; }}
.pred-possible .pred-likelihood {{ background: var(--accent); color: #000; }}
.pred-unlikely .pred-likelihood {{ background: var(--slate); color: #fff; }}
.pred-condition {{ font-size: 0.78rem; color: var(--muted); font-style: italic; display: block; margin-top: 0.15rem; }}
.watch-driver {{ font-size: 0.78rem; color: var(--muted); font-style: italic; }}

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

/* Quality review panel */
.review-toggle-btn {{ display: block; margin: 1rem auto; padding: 0.4rem 1rem; background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; color: var(--muted); font-size: 0.75rem; cursor: pointer; font-family: 'JetBrains Mono', monospace; }}
.review-toggle-btn:hover {{ border-color: var(--purple); color: var(--text); }}
.review-panel {{ margin: 1rem auto; max-width: 900px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; }}
.review-header {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }}
.review-badge {{ padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.7rem; margin-right: 0.5rem; }}
.review-badge-ok {{ background: var(--green); color: #fff; }}
.review-badge-warning {{ background: var(--accent); color: #000; }}
.review-badge-error {{ background: var(--red); color: #fff; }}
.review-card {{ margin-bottom: 1rem; padding: 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.review-card-header {{ font-weight: 600; font-size: 0.85rem; margin-bottom: 0.5rem; }}
.quality-score {{ float: right; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--muted); }}
.review-strengths {{ font-size: 0.8rem; color: var(--green); margin-bottom: 0.5rem; font-style: italic; }}
.review-issue {{ font-size: 0.8rem; padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.03); }}
.issue-sev {{ font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; padding: 0.1rem 0.25rem; border-radius: 2px; }}
.issue-error .issue-sev {{ background: var(--red); color: #fff; }}
.issue-warning .issue-sev {{ background: var(--accent); color: #000; }}
.issue-note .issue-sev {{ background: var(--slate); color: #fff; }}
.issue-section {{ color: var(--purple); font-size: 0.75rem; }}
.issue-fix {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.15rem; font-style: italic; }}
.review-no-issues {{ font-size: 0.8rem; color: var(--green); }}
.review-copy-section {{ margin-top: 1rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }}
.review-copy-btn {{ padding: 0.4rem 0.8rem; background: var(--purple); color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8rem; font-family: 'DM Sans', sans-serif; }}
.review-copy-btn:hover {{ opacity: 0.9; }}
.review-copy-text {{ font-size: 0.7rem; color: var(--muted); max-height: 300px; overflow-y: auto; white-space: pre-wrap; margin-top: 0.5rem; padding: 0.5rem; background: rgba(0,0,0,0.3); border-radius: 4px; }}

@media (max-width: 600px) {{
    body {{ padding: 0 0.5rem; }}
    .story-card {{ padding: 1rem; }}
    .masthead h1 {{ font-size: 1.5rem; }}
    .grid-source {{ width: 40%; }}
    .grid-position {{ width: 60%; }}
    .dispute-sides {{ flex-direction: column; }}
    .dispute-vs {{ padding: 0; text-align: center; }}
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

<button onclick="var p=document.getElementById('review-panel');p.style.display=p.style.display==='none'?'block':'none'" class="review-toggle-btn">Quality Review</button>
{review_panel}

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
