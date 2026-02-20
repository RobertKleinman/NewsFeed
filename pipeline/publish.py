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


def run(topic_cards, synthesis, quickscan_data, reports, run_time, quality_review=None, predictions_data=None, action_data=None):
    """Generate HTML. Returns html string."""
    # Convert TopicCard objects to dicts if needed
    card_dicts = []
    for card in topic_cards:
        if hasattr(card, 'to_dict'):
            d = card.to_dict()
            # Map new field names to legacy names for template compatibility
            d.setdefault("what_happened", d.get("what_happened", ""))
            d.setdefault("implications", d.get("so_what", ""))
            d.setdefault("missing_viewpoints", ", ".join(d.get("missing_perspectives", [])))
            d.setdefault("_political_balance", d.get("political_balance", ""))
            d.setdefault("_coverage_depth", d.get("coverage_depth", ""))
            d.setdefault("_bias_breakdown", {})
            d.setdefault("source_type_counts", {})
            d.setdefault("perspectives_used", len(d.get("sources", [])))
            d.setdefault("comparisons", d.get("comparisons", {}))
            d.setdefault("investigation", d.get("investigation_raw", ""))
            d.setdefault("disagreements",
                "\n".join("{}: {} vs {}".format(
                    dd.get("type", ""), dd.get("side_a", ""), dd.get("side_b", ""))
                    for dd in d.get("disputes", [])) or "No substantive contradictions identified.")
            d.setdefault("framing_differences",
                "\n".join('{}: "{}" - {}'.format(
                    f.get("source", ""), f.get("quote", ""), f.get("frame", ""))
                    for f in d.get("framing", [])))
            card_dicts.append(d)
        else:
            card_dicts.append(card)

    stories_html = ""
    for i, card in enumerate(card_dicts):
        stories_html += _render_card(card, i)

    quickscan_html = _render_quickscan(quickscan_data)
    synthesis_html = _render_synthesis(synthesis)
    predictions_html = _render_predictions(predictions_data or {})
    action_html_top = _render_action_layer(action_data or [])
    filter_buttons = _render_filters()
    run_report_html = _render_run_report(reports, run_time)
    review_panel_html = _render_review_panel(quality_review)
    llms_used = ", ".join(LLM_CONFIGS[k]["label"] for k in llm_caller.get_available_llms())
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    return HTML_TEMPLATE.format(
        date=now,
        num_stories=len(topic_cards),
        llms=llms_used,
        action_layer=action_html_top,
        quickscan=quickscan_html,
        synthesis=synthesis_html,
        predictions=predictions_html,
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
    # Importance dot — color based on depth tier (which is percentile-based)
    importance_reason = _esc(card.get("importance_reason", ""))
    tier = card.get("depth_tier", "standard")
    if tier == "deep":
        importance_html = '<span class="importance-dot dot-red" title="{}" aria-label="High importance" role="img"></span>'.format(importance_reason)
    elif tier == "standard":
        importance_html = '<span class="importance-dot dot-yellow" title="{}" aria-label="Standard importance" role="img"></span>'.format(importance_reason)
    else:
        importance_html = '<span class="importance-dot dot-green" title="{}" aria-label="Brief" role="img"></span>'.format(importance_reason)

    # Card mode badge — only show for contested stories
    card_mode = card.get("card_mode", "straight_news")
    mode_html = '<span class="card-mode-badge mode-contested">CONTESTED</span>' if card_mode == "contested" else ""

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
            spectrum_html = '<div class="coverage-spectrum">Coverage: {}'.format(" ".join(parts))
            # Add enrichment badges
            balance = card.get("_political_balance", "")
            depth = card.get("_coverage_depth", "")
            bias = card.get("_bias_breakdown", {})
            if balance:
                bal_class = "bal-" + balance.replace("_", "-")
                bias_str = "L:{} C:{} R:{}".format(bias.get("left", 0), bias.get("center", 0), bias.get("right", 0))
                spectrum_html += ' <span class="balance-badge {bc}" title="{bs}">{bal}</span>'.format(
                    bc=bal_class, bs=bias_str, bal=balance.replace("_", " ").title())
            if depth:
                spectrum_html += ' <span class="depth-badge depth-{d}">{d}</span>'.format(d=depth)
            spectrum_html += '</div>'

    # Source pills with perspective + type + date
    source_pills = ""
    for s in card.get("sources", []):
        stype = s.get("source_type", "mainstream")
        pub_date = s.get("pub_date", "")
        date_tag = ""
        if pub_date:
            short_date = pub_date[:10] if len(pub_date) >= 10 else pub_date
            date_tag = ' <span class="source-date">{}</span>'.format(short_date)
        url = s.get("url", "")
        name_html = '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(url, s["name"]) if url else s["name"]
        source_pills += '<span class="source-pill"><strong>{name}</strong> <span class="perspective-label">{persp}</span> <span class="source-type-tag type-{stype}">{stype}</span>{date}</span>'.format(
            name=name_html, persp=s["perspective"], stype=stype, date=date_tag)

    # === WHY THIS MATTERS ===
    why_html = ""
    why_matters = card.get("why_matters", card.get("so_what", ""))
    if why_matters:
        why_html = '<div class="card-section section-why"><div class="section-label">Why This Matters</div><p>{}</p></div>'.format(_esc(why_matters))

    # === WHAT'S HAPPENING ===
    whats_html = ""
    whats = card.get("whats_happening", card.get("what_happened", ""))
    if whats:
        whats_html = '<div class="card-section section-whats"><div class="section-label">What\'s Happening</div><p>{}</p></div>'.format(_esc(whats))

    # === HOW IT'S BEING USED (contested/political only) ===
    spin_html = ""
    positions = card.get("spin_positions", [])
    spin_preds = card.get("spin_predictions", [])
    if positions or spin_preds:
        spin_content = ""

        # Current framing positions
        if positions:
            spin_content += '<div class="spin-subsection"><div class="spin-sublabel">Current Framing</div>'
            for p in positions[:3]:
                if isinstance(p, dict):
                    position = _esc(p.get("position", ""))
                    who = _esc(p.get("who", ""))
                    claim = _esc(p.get("key_claim", ""))
                    verified = _esc(p.get("verified", ""))
                    # Color the verified tag
                    v_class = "verified-yes" if verified.lower().startswith("verified") else (
                        "verified-partial" if "partial" in verified.lower() else "verified-no")
                    spin_content += '<div class="spin-position"><div class="spin-stance">{}</div><div class="spin-who">Who: {}</div>'.format(position, who)
                    if claim:
                        spin_content += '<div class="spin-claim">Key claim: {}</div>'.format(claim)
                    if verified:
                        spin_content += '<div class="spin-verified {}">Verdict: {}</div>'.format(v_class, verified)
                    spin_content += '</div>'
            spin_content += '</div>'

        # Predicted spin
        if spin_preds:
            spin_content += '<div class="spin-subsection"><div class="spin-sublabel">Watch For</div>'
            for sp in spin_preds[:3]:
                if isinstance(sp, dict):
                    pred = _esc(sp.get("prediction", ""))
                    conf = sp.get("confidence", "likely")
                    conf_class = "conf-likely" if conf == "likely" else "conf-speculative"
                    spin_content += '<div class="spin-prediction {cc}"><span class="spin-conf">{conf}</span> {pred}</div>'.format(
                        cc=conf_class, conf=conf.upper(), pred=pred)
            spin_content += '</div>'

        if spin_content:
            spin_html = '<div class="card-section section-spin"><div class="section-label">How It\'s Being Used</div>{}</div>'.format(spin_content)

    # === WHAT YOU NEED TO KNOW ===
    know_content = ""

    # Key facts from coverage
    key_facts = card.get("key_facts", card.get("agreed_facts", []))
    if isinstance(key_facts, list) and key_facts:
        items = ""
        for f in key_facts[:5]:
            if isinstance(f, str) and f.strip():
                items += '<li class="know-item">{}</li>'.format(_esc(f))
        if items:
            know_content += '<div class="know-subsection"><div class="know-sublabel">Key Facts</div><ul class="know-list">{}</ul></div>'.format(items)

    # Context from research
    context_items = card.get("context", [])
    if isinstance(context_items, list) and context_items:
        items = ""
        for c in context_items[:3]:
            if isinstance(c, str) and c.strip():
                items += '<li class="know-item know-research">{}</li>'.format(_esc(c))
        if items:
            know_content += '<div class="know-subsection"><div class="know-sublabel">Context (from research)</div><ul class="know-list">{}</ul></div>'.format(items)

    # Historical context
    history_items = card.get("history", [])
    if isinstance(history_items, list) and history_items:
        items = ""
        for h in history_items[:3]:
            if isinstance(h, str) and h.strip():
                items += '<li class="know-item know-history">{}</li>'.format(_esc(h))
        if items:
            know_content += '<div class="know-subsection"><div class="know-sublabel">Historical Context</div><ul class="know-list">{}</ul></div>'.format(items)

    # What we still don't know (Q&A)
    unknowns = card.get("unknowns", card.get("key_unknowns", []))
    if isinstance(unknowns, list) and unknowns:
        qa_items = ""
        for u in unknowns:
            if isinstance(u, dict):
                q = _esc(u.get("q", u.get("question", "")))
                a = _esc(u.get("a", u.get("answer", "Not yet reported.")))
                if q:
                    qa_items += '<details class="unknown-qa"><summary class="unknown-q">{}</summary><div class="unknown-a">{}</div></details>'.format(q, a)
        if qa_items:
            know_content += '<div class="know-subsection"><div class="know-sublabel">What We Still Don\'t Know</div>{}</div>'.format(qa_items)

    know_html = ""
    if know_content:
        know_html = '<div class="card-section section-know"><div class="section-label">What You Need to Know</div>{}</div>'.format(know_content)

    # === BIGGER PICTURE ===
    bigger_html = ""
    bigger = card.get("bigger_picture", "")
    if bigger:
        bigger_html = '<div class="card-section section-bigger"><div class="section-label">Bigger Picture</div><p>{}</p></div>'.format(_esc(bigger))

    # === WHAT YOU CAN DO ===
    action_html = ""
    actions = card.get("actions", [])
    if isinstance(actions, list) and actions:
        items = ""
        for a in actions[:3]:
            if isinstance(a, str) and a.strip():
                items += '<li class="action-item">{}</li>'.format(_esc(a))
        if items:
            action_html = '<div class="card-section section-actions"><div class="section-label">What You Can Do</div><ul class="action-list">{}</ul></div>'.format(items)

    # === COLLAPSED: raw data ===
    collapsed_content = ""

    # Investigation raw
    investigation = card.get("investigation_raw", card.get("investigation", ""))
    if investigation:
        inv_text = _esc(investigation).replace("\n", "<br>")
        collapsed_content += '<details class="raw-comp"><summary>Background Research (Gemini Web Search)</summary><div class="detail-section section-investigation"><div class="detail-text">{}</div></div></details>'.format(inv_text)

    # Raw comparisons
    comparisons = card.get("comparisons", {})
    if comparisons:
        comp_blocks = ""
        for model, text in comparisons.items():
            comp_blocks += '<div class="comp-block"><div class="comp-model">{}</div><div class="comp-text">{}</div></div>'.format(
                model, _esc(text).replace("\n", "<br>"))
        collapsed_content += '<details class="raw-comp"><summary>Raw Model Comparisons ({} models)</summary>{}</details>'.format(
            len(comparisons), comp_blocks)

    written_by = card.get("written_by", "")
    writer_html = ""
    if written_by:
        writer_html = '<div class="written-by">Card written by {}</div>'.format(written_by)

    # TL;DR — single bold sentence
    tldr_html = ""
    # Use why_matters as TL;DR source, take just the first sentence
    tldr_source = card.get("why_matters", card.get("so_what", ""))
    if tldr_source:
        first_sentence = tldr_source.split(".")[0].strip()
        if first_sentence and len(first_sentence) > 20:
            tldr_html = '<div class="card-tldr"><strong>{}</strong></div>'.format(_esc(first_sentence + "."))

    # Tier badge
    tier = card.get("depth_tier", "standard")
    tier_html = ""
    if tier == "deep":
        tier_html = '<span class="tier-badge tier-deep">DEEP ANALYSIS</span>'
    elif tier == "brief":
        tier_html = '<span class="tier-badge tier-brief">BRIEF</span>'

    # Editorial analysis
    editorial_html = ""
    editorial_text = card.get("editorial", "")
    if editorial_text:
        writer_model = _esc(card.get("editorial_writer", ""))
        editor_model = _esc(card.get("editorial_editor", ""))
        rounds = card.get("editorial_rounds", 0)
        meta = "Written by {} · Edited by {} · {} revision rounds".format(
            writer_model, editor_model, rounds) if writer_model else ""

        # Convert paragraphs
        paras = editorial_text.strip().split("\n\n")
        body = "".join("<p>{}</p>".format(_esc(p.strip()).replace("\n", "<br>")) for p in paras if p.strip())

        editorial_html = """
        <div class="card-section section-editorial">
            <div class="section-label">Editorial Analysis</div>
            <div class="editorial-meta">{meta}</div>
            <div class="editorial-body">{body}</div>
            <div class="editorial-disclaimer">This is analytical opinion, not reported fact. It represents one interpretation of the available evidence.</div>
        </div>""".format(meta=meta, body=body)

    # Build the expandable detail sections (everything after why + whats)
    card_details = ""
    if spin_html or know_html or bigger_html or action_html or editorial_html:
        card_details = """
        <details class="card-expand"{open_attr}>
            <summary class="card-expand-summary">{expand_label}</summary>
            {spin}
            {know}
            {bigger}
            {actions}
            {editorial}
        </details>""".format(
            spin=spin_html, know=know_html, bigger=bigger_html,
            actions=action_html, editorial=editorial_html,
            open_attr=' open' if editorial_html else '',
            expand_label='Full Analysis + Editorial' if editorial_html else 'Full Analysis')

    # Source profile line (M5)
    src_count = card.get("source_count", 0)
    indep_count = card.get("independent_count", src_count)
    region_count = card.get("region_count", 0)
    if indep_count < src_count:
        source_profile = '<span>{} independent sources ({} total)</span>'.format(indep_count, src_count)
    else:
        source_profile = '<span>{} sources</span>'.format(src_count)
    if region_count > 1:
        source_profile += '<span>{} regions</span>'.format(region_count)
    source_profile += '<span>{} perspectives</span>'.format(card.get("perspectives_used", 0))

    # Contested reason (P0-6)
    contested_reason_html = ""
    contested_reason = card.get("contested_reason", "")
    if contested_reason and card.get("card_mode") == "contested":
        contested_reason_html = '<div class="contested-reason">{}</div>'.format(_esc(contested_reason))

    # QA warnings (P1-2)
    qa_html = ""
    qa_warnings = card.get("qa_warnings", [])
    if qa_warnings:
        warning_items = "".join('<div class="qa-warning">⚠️ {}</div>'.format(_esc(w)) for w in qa_warnings[:3])
        qa_html = '<div class="qa-warnings">{}</div>'.format(warning_items)

    return """
    <article class="story-card" id="topic-card-{card_idx}" data-topics="{topic_ids}">
        <div class="card-header">
            <div class="topic-tags">{importance} {mode} {tier} {tags}</div>
            <h2 class="story-title">{title}</h2>
            {tldr}
            {contested_reason}
            <div class="story-meta">
                {source_profile}
            </div>
            {spectrum}
        </div>

        {why}
        {whats}

        {card_details}

        {qa}

        <details class="detail-expand">
            <summary>Full Sources & Research</summary>
            {collapsed}
            {writer}
        </details>
    </article>""".format(
        topic_ids=" ".join(card.get("topics", [])[:3]),
        card_idx=card_index,
        importance=importance_html,
        mode=mode_html,
        tier=tier_html,
        tags=topic_tags,
        title=card.get("title", ""),
        tldr=tldr_html,
        contested_reason=contested_reason_html,
        source_profile=source_profile,
        spectrum=spectrum_html,
        why=why_html,
        whats=whats_html,
        card_details=card_details,
        qa=qa_html,
        collapsed=collapsed_content,
        writer=writer_html)


def _render_perspective_grid(card):
    """Render a visual comparison grid showing each source's position."""
    sources = card.get("sources", [])
    framing = card.get("framing_differences", "")
    if len(sources) < 2:
        return ""

    rows = ""
    for s in sources:
        source_framing = _extract_source_framing(s["name"], framing)
        if not source_framing:
            # Also try the structured framing data
            for f in card.get("framing", []):
                if isinstance(f, dict) and f.get("source", "").lower() == s["name"].lower():
                    quote = f.get("quote", "")
                    frame = f.get("frame", "")
                    source_framing = '{}: "{}" - {}'.format(s["name"], quote, frame) if quote else frame
                    break
        if not source_framing:
            continue  # Skip sources with no framing data instead of showing placeholder

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
            # Color dot based on depth tier (percentile-based)
            card_mode = story.get("card_mode", "straight_news")
            tier = story.get("depth_tier", "standard")
            if tier == "deep":
                dot = '<span class="importance-dot dot-red" title="High importance"></span>'
            elif tier == "standard":
                dot = '<span class="importance-dot dot-yellow" title="Notable"></span>'
            else:
                dot = '<span class="importance-dot dot-green" title="Background"></span>'

            # Add contested indicator
            mode_tag = ""
            if card_mode == "contested":
                mode_tag = ' <span class="qs-contested-tag">CONTESTED</span>'

            card_idx = story.get("card_index", 0)
            one_liner = story.get("one_liner", story.get("summary", ""))
            why_care = story.get("why_care", "")
            why_html = ""
            if why_care:
                why_html = '<span class="qs-why">{}</span>'.format(_esc(why_care))

            stories_html += '<a href="#topic-card-{idx}" class="qs-story">{dot}<div class="qs-story-content"><span class="qs-headline">{headline}{mode}</span><span class="qs-summary">{one_liner}</span>{why}</div></a>'.format(
                idx=card_idx, dot=dot,
                headline=_esc(story.get("headline", "")),
                mode=mode_tag,
                one_liner=_esc(one_liner),
                why=why_html)
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

    # Try JSON format first (new bucketed structure)
    import json as _json
    import re as _re
    try:
        if isinstance(synthesis, str):
            cleaned = _re.sub(r'```json\s*', '', synthesis)
            cleaned = _re.sub(r'```\s*', '', cleaned).strip()
            m = _re.search(r'\{.*\}', cleaned, _re.DOTALL)
            data = _json.loads(m.group() if m else cleaned)
        else:
            data = synthesis

        html = ""

        # Action Calls bucket
        calls = data.get("action_calls", [])
        if calls:
            items = "".join('<li class="synth-item synth-call">{}</li>'.format(_esc(c)) for c in calls[:3])
            html += '<div class="synth-bucket"><div class="synth-bucket-label">🎯 Action Calls</div><ul class="synth-list">{}</ul></div>'.format(items)

        # Risks bucket
        risks = data.get("risks", [])
        if risks:
            items = "".join('<li class="synth-item synth-risk">{}</li>'.format(_esc(r)) for r in risks[:3])
            html += '<div class="synth-bucket"><div class="synth-bucket-label">⚠️ Risks</div><ul class="synth-list">{}</ul></div>'.format(items)

        # Watch Items bucket
        watch = data.get("watch_items", [])
        if watch:
            items = "".join('<li class="synth-item synth-watch">{}</li>'.format(_esc(w)) for w in watch[:3])
            html += '<div class="synth-bucket"><div class="synth-bucket-label">👁️ Watch</div><ul class="synth-list">{}</ul></div>'.format(items)

        # Themes + Disagreements as prose below buckets
        themes = data.get("themes", "")
        disagree = data.get("disagreements", "")
        if themes:
            html += '<div class="synth-section"><div class="synth-label">Themes</div><p>{}</p></div>'.format(_esc(themes))
        if disagree:
            html += '<div class="synth-section synth-disagree"><div class="synth-label">Disagreements</div><p>{}</p></div>'.format(_esc(disagree))

        if html:
            return html
    except (ValueError, AttributeError, KeyError):
        pass

    # Fallback: old text-based format
    sections = {}
    for label in ["THEMES:", "NOTABLE DISAGREEMENTS:", "LOOKING AHEAD:"]:
        if label in synthesis:
            start = synthesis.index(label) + len(label)
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

    escaped = _esc(synthesis)
    return "<p>{}</p>".format(escaped.replace("\n\n", "</p><p>").replace("\n", "<br>"))


def _render_filters():
    html = '<button class="filter-btn active" data-filter="all">All</button>'
    for tid, info in TOPICS.items():
        html += '<button class="filter-btn" data-filter="{}">{} {}</button>'.format(
            tid, info["icon"], info["name"])
    return html


def _render_action_layer(actions):
    """Render 'If you only do 1 thing today' section."""
    if not actions:
        return ""
    items = ""
    for a in actions[:3]:
        if isinstance(a, dict):
            action_text = _esc(a.get("action", ""))
            card_idx = a.get("card_index", 0)
            items += '<a href="#topic-card-{}" class="action-item">{}</a>'.format(card_idx, action_text)
    if not items:
        return ""
    return '<div class="action-layer"><div class="action-layer-label">If you only do 1 thing today</div>{}</div>'.format(items)


def _render_predictions(data):
    """Render What's Coming predictions section."""
    if not data:
        return ""

    cross = data.get("cross_story", [])
    near = data.get("near_term", [])
    medium = data.get("medium_term", [])
    titles = data.get("story_titles", {})

    if not cross and not near and not medium:
        return ""

    html = ""

    # Cross-story predictions (most valuable)
    if cross:
        items = ""
        for p in cross[:3]:
            if isinstance(p, dict):
                pred = _esc(p.get("prediction", ""))
                conf = p.get("confidence", "possible")
                disconfirm = _esc(p.get("disconfirm", ""))
                stories = p.get("stories", [])
                timeframe = p.get("timeframe", "this_week")

                conf_class = "pred-" + conf
                tf_class = "badge-" + timeframe.replace("_", "-")

                # Map story numbers to titles
                story_refs = ""
                if stories:
                    refs = []
                    for s in stories[:3]:
                        title = titles.get(str(s), "Story {}".format(s))
                        refs.append('<a href="#topic-card-{}" class="pred-story-ref">{}</a>'.format(
                            s - 1, _esc(title[:40])))
                    story_refs = '<div class="pred-stories">Connects: {}</div>'.format(" + ".join(refs))

                disconfirm_html = ""
                if disconfirm:
                    disconfirm_html = '<div class="pred-disconfirm">Would be wrong if: {}</div>'.format(disconfirm)

                items += '<div class="pred-item {cc}"><span class="pred-badge {tc}">{tf}</span> <span class="pred-conf-badge">{conf}</span> <span class="pred-text">{pred}</span>{stories}{dis}</div>'.format(
                    cc=conf_class, tc=tf_class, tf=timeframe.replace("_", " ").upper(),
                    conf=conf.upper(), pred=pred, stories=story_refs, dis=disconfirm_html)
        if items:
            html += '<div class="pred-category"><div class="pred-category-label">Cross-Story Predictions</div>{}</div>'.format(items)

    # Near-term predictions
    if near:
        items = ""
        for p in near[:3]:
            if isinstance(p, dict):
                pred = _esc(p.get("prediction", ""))
                conf = p.get("confidence", "likely")
                disconfirm = _esc(p.get("disconfirm", ""))
                conf_class = "pred-" + conf
                dis_html = '<div class="pred-disconfirm">Would be wrong if: {}</div>'.format(disconfirm) if disconfirm else ""
                items += '<div class="pred-item {cc}"><span class="pred-badge badge-48-hours">48 HOURS</span> <span class="pred-conf-badge">{conf}</span> <span class="pred-text">{pred}</span>{dis}</div>'.format(
                    cc=conf_class, conf=conf.upper(), pred=pred, dis=dis_html)
        if items:
            html += '<div class="pred-category"><div class="pred-category-label">Next 48 Hours</div>{}</div>'.format(items)

    # Medium-term predictions
    if medium:
        items = ""
        for p in medium[:3]:
            if isinstance(p, dict):
                pred = _esc(p.get("prediction", ""))
                conf = p.get("confidence", "possible")
                disconfirm = _esc(p.get("disconfirm", ""))
                timeframe = p.get("timeframe", "this_week")
                conf_class = "pred-" + conf
                tf_class = "badge-" + timeframe.replace("_", "-")
                dis_html = '<div class="pred-disconfirm">Would be wrong if: {}</div>'.format(disconfirm) if disconfirm else ""
                items += '<div class="pred-item {cc}"><span class="pred-badge {tc}">{tf}</span> <span class="pred-conf-badge">{conf}</span> <span class="pred-text">{pred}</span>{dis}</div>'.format(
                    cc=conf_class, tc=tf_class, tf=timeframe.replace("_", " ").upper(),
                    conf=conf.upper(), pred=pred, dis=dis_html)
        if items:
            html += '<div class="pred-category"><div class="pred-category-label">This Week / This Month</div>{}</div>'.format(items)

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
.qs-summary {{ font-size: 0.82rem; color: var(--text); display: block; margin-top: 0.15rem; }}
.qs-fault {{ font-size: 0.78rem; color: var(--accent); display: block; margin-top: 0.1rem; font-style: italic; }}
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

/* Predictions section */
.predictions-expand {{ margin-bottom: 1.5rem; }}
.predictions-toggle {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: var(--purple); cursor: pointer; padding: 0.5rem 0; font-weight: 600; }}
.predictions-box {{ background: var(--card-bg); border-left: 3px solid var(--purple); border-radius: 8px; padding: 1.2rem; margin-top: 0.5rem; }}
.pred-category {{ margin-bottom: 1rem; }}
.pred-category-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--purple); font-weight: 700; margin-bottom: 0.5rem; }}
.pred-item {{ padding: 0.6rem 0.8rem; background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 0.5rem; font-size: 0.88rem; line-height: 1.6; }}
.pred-badge {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.35rem; border-radius: 3px; margin-right: 0.3rem; }}
.badge-48-hours {{ background: var(--red); color: #fff; }}
.badge-this-week {{ background: var(--accent); color: #000; }}
.badge-this-month {{ background: var(--blue); color: #fff; }}
.pred-conf-badge {{ font-family: 'JetBrains Mono', monospace; font-size: 0.55rem; padding: 0.1rem 0.3rem; border-radius: 3px; margin-right: 0.4rem; border: 1px solid var(--border); color: var(--muted); }}
.pred-likely .pred-conf-badge {{ border-color: var(--green); color: var(--green); }}
.pred-possible .pred-conf-badge {{ border-color: var(--accent); color: var(--accent); }}
.pred-speculative .pred-conf-badge {{ border-color: var(--muted); color: var(--muted); }}
.pred-text {{ color: var(--text); }}
.pred-stories {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.3rem; }}
.pred-story-ref {{ color: var(--purple); text-decoration: none; }}
.pred-story-ref:hover {{ text-decoration: underline; }}
.pred-disconfirm {{ font-size: 0.75rem; color: var(--slate); margin-top: 0.2rem; font-style: italic; }}
.synth-section {{ margin-bottom: 1rem; padding: 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.synth-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); margin-bottom: 0.4rem; font-weight: 600; }}
.synth-disagree .synth-label {{ color: var(--red); }}
.synth-ahead .synth-label {{ color: var(--blue); }}
.synth-section p {{ font-size: 0.9rem; margin-bottom: 0.5rem; }}

/* Filters */
.filter-bar {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.5rem; padding: 0.8rem 0; }}
@media (max-width: 600px) {{ .filter-bar {{ flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 0.5rem; }} .filter-btn {{ white-space: nowrap; flex-shrink: 0; }} }}
.filter-btn {{ background: var(--card-bg); color: var(--muted); border: 1px solid var(--border); border-radius: 20px; padding: 0.3rem 0.8rem; font-size: 0.78rem; cursor: pointer; font-family: 'DM Sans', sans-serif; }}
.filter-btn.active {{ background: var(--accent); color: #000; border-color: var(--accent); font-weight: 600; }}

/* Story cards */
.story-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.card-header {{ margin-bottom: 0.5rem; }}
.topic-tags {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; align-items: center; }}
.topic-tag {{ font-size: 0.73rem; padding: 0.15rem 0.5rem; border-radius: 12px; border: 1px solid var(--border); color: var(--muted); }}
.importance-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; flex-shrink: 0; cursor: help; }}
.dot-red {{ background: #e53935; }}
.dot-yellow {{ background: #ffa726; }}
.dot-green {{ background: #66bb6a; }}
.qs-why {{ display: block; font-size: 0.78rem; color: #555; font-style: italic; margin-top: 2px; }}
.qs-contested-tag {{ font-size: 0.6rem; background: #fff3e0; color: #e65100; padding: 1px 5px; border-radius: 3px; margin-left: 6px; font-weight: 600; vertical-align: middle; }}
.card-mode-badge {{ font-size: 0.65rem; font-weight: 600; padding: 0.1rem 0.45rem; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.5px; }}
.mode-news {{ background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }}
.mode-contested {{ background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }}
.so-what {{ font-size: 0.92rem; color: var(--text); margin: 0.6rem 0; padding: 0.5rem 0.8rem; background: rgba(100, 149, 237, 0.06); border-left: 3px solid cornflowerblue; border-radius: 0 4px 4px 0; }}
.inv-impact {{ font-size: 0.88rem; color: var(--text); margin: 0.5rem 0; padding: 0.5rem 0.8rem; background: rgba(255, 152, 0, 0.06); border-left: 3px solid #ff9800; border-radius: 0 4px 4px 0; }}
.coverage-note {{ font-size: 0.8rem; color: var(--muted); font-style: italic; margin: 0.4rem 0; }}
.tier-badge {{ font-size: 0.6rem; font-weight: 600; padding: 0.1rem 0.4rem; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.5px; }}
.tier-deep {{ background: #e8eaf6; color: #283593; border: 1px solid #9fa8da; }}
.tier-brief {{ background: #f5f5f5; color: #757575; border: 1px solid #e0e0e0; }}
.story-title {{ font-family: 'Newsreader', serif; font-size: 1.25rem; line-height: 1.4; margin-bottom: 0.4rem; }}
.story-meta {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 0.3rem; display: flex; gap: 1rem; }}

/* Coverage spectrum */
.coverage-spectrum {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: var(--muted); padding: 0.3rem 0; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
.spectrum-item {{ padding: 0.1rem 0.4rem; background: var(--section-bg); border-radius: 3px; }}
.spectrum-label {{ color: var(--purple); }}

/* Balance and depth badges */
.balance-badge {{ padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.6rem; margin-left: 0.3rem; }}
.bal-balanced {{ background: var(--green); color: #fff; }}
.bal-leans-left {{ background: #3b82f6; color: #fff; }}
.bal-leans-right {{ background: #ef4444; color: #fff; }}
.depth-badge {{ padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.6rem; margin-left: 0.3rem; }}
.depth-deep {{ background: var(--green); color: #fff; }}
.depth-moderate {{ background: var(--accent); color: #000; }}
.depth-thin {{ background: var(--slate); color: #fff; }}

/* Source pills */
.sources-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1rem; }}
.source-pill {{ font-size: 0.73rem; padding: 0.25rem 0.6rem; background: var(--section-bg); border-radius: 10px; color: var(--text); border: 1px solid var(--border); }}
.source-pill strong {{ color: var(--text); }}
.perspective-label {{ color: var(--purple); font-style: italic; }}
.perspective-label::before {{ content: "— "; }}
.source-pill a {{ color: var(--purple); text-decoration: none; }}
.source-pill a:hover {{ text-decoration: underline; }}
.source-date {{ font-size: 0.65rem; color: var(--slate); margin-left: 0.3rem; }}
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

/* Key unknowns Q&A */
.unknown-qa {{ margin-bottom: 0.3rem; }}
.unknown-q {{ font-size: 0.85rem; cursor: pointer; padding: 0.3rem 0; color: var(--text); }}
.unknown-q:hover {{ color: var(--purple); }}
.unknown-q::marker {{ color: var(--purple); }}
.unknown-a {{ font-size: 0.82rem; color: var(--muted); padding: 0.3rem 0 0.3rem 1rem; border-left: 2px solid var(--purple); margin: 0.2rem 0 0.4rem 0.5rem; }}

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

/* New card section styles */
.card-section {{ margin-bottom: 1.2rem; padding: 0.9rem 1.1rem; background: var(--section-bg); border-radius: 8px; border-left: 3px solid var(--border); }}
.section-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.6rem; font-weight: 700; }}
.section-why {{ border-left-color: var(--accent); }}
.section-why .section-label {{ color: var(--accent); }}
.section-whats {{ border-left-color: var(--blue); }}
.section-whats .section-label {{ color: var(--blue); }}
.section-spin {{ border-left-color: var(--red); }}
.section-spin .section-label {{ color: var(--red); }}
.section-know {{ border-left-color: var(--green); }}
.section-know .section-label {{ color: var(--green); }}
.section-bigger {{ border-left-color: var(--purple); }}
.section-bigger .section-label {{ color: var(--purple); }}
.section-actions {{ border-left-color: var(--accent); background: rgba(245, 158, 11, 0.05); }}
.section-actions .section-label {{ color: var(--accent); }}
.card-section p {{ font-size: 0.9rem; line-height: 1.7; color: var(--text); }}

/* Spin section */
.spin-subsection {{ margin-bottom: 0.6rem; }}
.spin-sublabel {{ font-size: 0.7rem; font-weight: 600; color: var(--muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.03em; }}
.spin-position {{ padding: 0.6rem; background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 0.4rem; }}
.spin-stance {{ font-weight: 600; font-size: 0.88rem; margin-bottom: 0.2rem; }}
.spin-who {{ font-size: 0.78rem; color: var(--muted); }}
.spin-claim {{ font-size: 0.82rem; margin-top: 0.3rem; font-style: italic; }}
.spin-verified {{ font-size: 0.75rem; margin-top: 0.2rem; padding: 0.15rem 0.4rem; border-radius: 4px; display: inline-block; }}
.verified-yes {{ background: rgba(16, 185, 129, 0.15); color: var(--green); }}
.verified-partial {{ background: rgba(245, 158, 11, 0.15); color: var(--accent); }}
.verified-no {{ background: rgba(239, 68, 68, 0.15); color: var(--red); }}
.spin-prediction {{ padding: 0.4rem 0.6rem; font-size: 0.82rem; border-left: 2px solid var(--red); margin-bottom: 0.3rem; }}
.spin-conf {{ font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.3rem; border-radius: 3px; margin-right: 0.4rem; }}
.conf-likely .spin-conf {{ background: var(--red); color: #fff; }}
.conf-speculative .spin-conf {{ background: var(--slate); color: #fff; }}

/* Know section */
.know-subsection {{ margin-bottom: 0.6rem; }}
.know-sublabel {{ font-size: 0.7rem; font-weight: 600; color: var(--muted); margin-bottom: 0.3rem; }}
.know-list {{ list-style: none; padding-left: 1rem; }}
.know-item {{ position: relative; font-size: 0.85rem; padding: 0.2rem 0; }}
.know-item::before {{ content: "\\2022"; position: absolute; left: -0.8rem; color: var(--green); }}
.know-research::before {{ content: "\\1F50D"; }}
.know-history::before {{ content: "\\1F4DC"; }}

/* Action section */
.action-list {{ list-style: none; padding-left: 1rem; }}
.action-item {{ position: relative; font-size: 0.85rem; padding: 0.3rem 0; }}
.action-item::before {{ content: "\\2794"; position: absolute; left: -1rem; color: var(--accent); }}

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

/* TL;DR */
.card-tldr {{ font-size: 0.92rem; color: var(--accent); margin: 0.3rem 0 0.5rem 0; line-height: 1.5; }}

/* Action Layer */
.action-layer {{ background: linear-gradient(135deg, rgba(234,179,8,0.08), rgba(234,179,8,0.03)); border: 1px solid rgba(234,179,8,0.2); border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 1.5rem; }}
.action-layer-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); font-weight: 700; margin-bottom: 0.5rem; }}
.action-item {{ display: block; color: var(--text); text-decoration: none; font-size: 0.88rem; padding: 0.3rem 0; line-height: 1.5; }}
.action-item:hover {{ color: var(--accent); }}
.action-item::before {{ content: '→ '; color: var(--accent); }}

/* Contested reason */
.contested-reason {{ font-size: 0.78rem; color: var(--red); font-style: italic; margin: 0.2rem 0 0.4rem 0; }}

/* Editorial Analysis */
.section-editorial {{ border-left: 3px solid var(--purple); }}
.editorial-meta {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--muted); margin-bottom: 0.8rem; }}
.editorial-body p {{ font-size: 0.92rem; line-height: 1.7; margin-bottom: 0.8rem; color: var(--text); }}
.editorial-disclaimer {{ font-size: 0.7rem; color: var(--muted); font-style: italic; margin-top: 0.8rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }}

/* QA Warnings */
.qa-warnings {{ margin-top: 0.5rem; padding: 0.5rem 0.8rem; background: rgba(239,68,68,0.05); border-radius: 6px; border-left: 3px solid var(--red); }}
.qa-warning {{ font-size: 0.78rem; color: var(--red); line-height: 1.5; margin-bottom: 0.2rem; }}

/* Synthesis buckets */
.synth-bucket {{ margin-bottom: 0.8rem; }}
.synth-bucket-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; font-weight: 700; margin-bottom: 0.3rem; }}
.synth-list {{ list-style: none; padding: 0; margin: 0; }}
.synth-item {{ font-size: 0.88rem; padding: 0.25rem 0; line-height: 1.5; }}
.synth-call {{ color: var(--accent); }}
.synth-risk {{ color: var(--red); }}
.synth-watch {{ color: var(--blue); }}

/* Card collapse — Full Analysis toggle */
.card-expand {{ margin-top: 0.3rem; }}
.card-expand-summary {{ font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--purple); cursor: pointer; padding: 0.5rem 0; font-weight: 600; letter-spacing: 0.03em; }}
.card-expand-summary:hover {{ color: var(--accent); }}
.card-expand-summary::marker {{ color: var(--purple); }}

/* Epistemic heatmap mode */
.heatmap-mode .verified-yes {{ opacity: 0.3; }}
.heatmap-mode .verified-partial {{ box-shadow: 0 0 8px rgba(234, 179, 8, 0.5); background: rgba(234, 179, 8, 0.08); }}
.heatmap-mode .verified-no {{ box-shadow: 0 0 10px rgba(239, 68, 68, 0.6); background: rgba(239, 68, 68, 0.1); }}
.heatmap-mode .mode-contested {{ box-shadow: 0 0 8px rgba(239, 68, 68, 0.4); }}
.heatmap-mode .spin-position {{ border-left: 3px solid var(--red); padding-left: 0.6rem; }}
.heatmap-mode .pred-disconfirm {{ background: rgba(239, 68, 68, 0.08); padding: 0.2rem 0.4rem; border-radius: 4px; }}
.heatmap-btn {{ font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; padding: 0.3rem 0.7rem; background: transparent; border: 1px solid var(--purple); color: var(--purple); border-radius: 4px; cursor: pointer; margin-left: 0.5rem; }}
.heatmap-btn.active {{ background: var(--purple); color: #000; }}
.heatmap-btn:hover {{ background: var(--purple); color: #000; }}
.detail-section {{ margin-top: 0.8rem; padding: 0.8rem; background: var(--section-bg); border-radius: 6px; }}
.detail-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; font-weight: 600; }}
.section-framing .detail-label {{ color: var(--purple); }}
.section-notable .scan-label {{ color: var(--blue); }}
.notable-item {{ font-size: 0.85rem; color: var(--muted); padding: 0.2rem 0; border-left: 2px solid var(--blue); padding-left: 0.6rem; margin-bottom: 0.3rem; }}
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
    <div class="meta" style="font-size: 0.75rem; margin-top: 0.2rem;">Updated every 2 hours · Runtime: {runtime}s</div>
</div>

{action_layer}

{quickscan}

<details class="synthesis-expand">
<summary class="synthesis-toggle">Executive Synthesis (full analysis)</summary>
<div class="synthesis-box">
    <h2>Executive Synthesis</h2>
    {synthesis}
</div>
</details>

<details class="predictions-expand" open>
<summary class="predictions-toggle">What's Coming (Predictions)</summary>
<div class="predictions-box">
    {predictions}
</div>
</details>

<div class="filter-bar">{filters}<button class="heatmap-btn" id="heatmap-toggle" title="Highlight uncertain claims">🔍 Uncertainty</button></div>

{stories}

<div class="run-report">{run_report}</div>

<button onclick="var p=document.getElementById('review-panel');p.style.display=p.style.display==='none'?'block':'none'" class="review-toggle-btn">Quality Review</button>
{review_panel}

<script>
// Filter buttons with URL state
const params = new URLSearchParams(window.location.search);
const initialFilter = params.get('filter') || 'all';

document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const f = btn.dataset.filter;
        document.querySelectorAll('.story-card').forEach(c => {{
            c.style.display = (f === 'all' || c.dataset.topics.split(' ').includes(f)) ? '' : 'none';
        }});
        // URL state management
        const url = new URL(window.location);
        if (f === 'all') {{ url.searchParams.delete('filter'); }}
        else {{ url.searchParams.set('filter', f); }}
        history.replaceState(null, '', url);
    }});
    // Apply initial filter from URL
    if (btn.dataset.filter === initialFilter) {{
        btn.click();
    }}
}});

// Epistemic heatmap toggle
document.getElementById('heatmap-toggle').addEventListener('click', function() {{
    document.body.classList.toggle('heatmap-mode');
    this.classList.toggle('active');
    // When heatmap is on, expand all cards so uncertain content is visible
    if (document.body.classList.contains('heatmap-mode')) {{
        document.querySelectorAll('.card-expand').forEach(d => d.open = true);
    }}
}});

// Hash navigation — open card details when clicking quickscan links
if (window.location.hash) {{
    const target = document.querySelector(window.location.hash);
    if (target) {{
        const expand = target.querySelector('.card-expand');
        if (expand) expand.open = true;
        setTimeout(() => target.scrollIntoView({{behavior: 'smooth'}}), 100);
    }}
}}
document.querySelectorAll('a[href^="#topic-card"]').forEach(a => {{
    a.addEventListener('click', (e) => {{
        const hash = a.getAttribute('href').replace(/.*#/, '#');
        const target = document.querySelector(hash);
        if (target) {{
            const expand = target.querySelector('.card-expand');
            if (expand) expand.open = true;
        }}
    }});
}});
</script>
</body>
</html>"""
