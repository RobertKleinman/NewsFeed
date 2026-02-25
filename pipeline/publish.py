"""Step 11: Publish as HTML."""

from datetime import datetime, timezone

import llm as llm_caller
from config import TOPICS, LLM_CONFIGS


def run(topic_cards, synthesis, quickscan_data, reports, run_time, quality_review=None, predictions_data=None, action_data=None):
    """Generate HTML. Returns html string."""
    try:
        card_dicts = []
        for card in topic_cards:
            if hasattr(card, "to_dict"):
                d = card.to_dict()
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
                card_dicts.append(d)
            else:
                card_dicts.append(card)

        stories_html = "".join(_render_card(card, i) for i, card in enumerate(card_dicts))
        brief_html = _render_the_brief(card_dicts, predictions_data or {}, action_data or {})
        featured_editorial_html = _render_featured_editorial(card_dicts)
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
            the_brief=brief_html,
            featured_editorial=featured_editorial_html,
            synthesis=synthesis_html,
            filters=filter_buttons,
            stories=stories_html,
            run_report=run_report_html,
            review_panel=review_panel_html,
            runtime=run_time,
        )
    except Exception:
        return ""


def _esc(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _normalize_action_data(action_data):
    """Accept old flat list or new watch/prepare/ignore object."""
    try:
        out = {"watch": [], "prepare": [], "ignore": []}
        if isinstance(action_data, dict):
            for k in out:
                items = action_data.get(k, [])
                if isinstance(items, list):
                    out[k] = [i for i in items if isinstance(i, dict)]
            return out
        if isinstance(action_data, list):
            for i, item in enumerate(action_data[:6]):
                if not isinstance(item, dict):
                    continue
                target = "watch" if i < 2 else ("prepare" if i < 4 else "ignore")
                out[target].append(item)
            return out
        return out
    except Exception:
        return {"watch": [], "prepare": [], "ignore": []}


def _get_why_today(card):
    try:
        why_today = card.get("why_today", "")
        if why_today:
            return why_today
        why = card.get("why_matters", card.get("so_what", ""))
        if not why:
            return ""
        first = why.split(".")[0].strip()
        return first + "." if first else ""
    except Exception:
        return ""


def _has_substantive_unknowns(card):
    try:
        unknowns = card.get("unknowns", card.get("key_unknowns", []))
        if not isinstance(unknowns, list):
            return False
        for u in unknowns:
            if isinstance(u, dict):
                q = (u.get("q") or u.get("question") or "").strip()
                if len(q) >= 20:
                    return True
        return False
    except Exception:
        return False


def _render_the_brief(cards, predictions_data, action_data):
    try:
        if not cards:
            return ""
        top = sorted(cards, key=lambda c: c.get("heat_score", 0), reverse=True)[:8]
        headlines = ""
        for card in top:
            idx = cards.index(card)
            mode = card.get("card_mode", "straight_news")
            contested = '<span class="qs-contested-tag">CONTESTED</span>' if mode == "contested" else ""
            why_today = _esc(_get_why_today(card))
            why_today_html = '<div class="brief-why">{}</div>'.format(why_today) if why_today else ""
            headlines += '<a class="brief-item" href="#topic-card-{idx}"><div class="brief-head">{title}</div>{contested}{why}</a>'.format(
                idx=idx,
                title=_esc(card.get("title", "")),
                contested=contested,
                why=why_today_html,
            )

        actions = _normalize_action_data(action_data)
        action_html = ""
        for bucket, label in [("watch", "Watch"), ("prepare", "Prepare"), ("ignore", "Ignore")]:
            items = ""
            for item in actions.get(bucket, [])[:2]:
                txt = _esc(item.get("action", ""))
                idx = item.get("card_index", 0)
                if txt:
                    items += '<a href="#topic-card-{idx}" class="brief-action-item">{txt}</a>'.format(idx=idx, txt=txt)
            if items:
                action_html += '<div class="brief-action-col"><div class="brief-action-label">{}</div>{}</div>'.format(label, items)

        pred_html = _render_predictions(predictions_data)
        return '<section class="the-brief"><h2>The Brief</h2><div class="brief-grid">{}</div><div class="brief-actions">{}</div>{}</section>'.format(
            headlines,
            action_html,
            pred_html,
        )
    except Exception:
        return ""


def _render_featured_editorial(cards):
    try:
        for idx, card in enumerate(cards):
            editorial = card.get("editorial", "")
            if editorial:
                writer = _esc(card.get("editorial_writer", ""))
                editor = _esc(card.get("editorial_editor", ""))
                body = "".join("<p>{}</p>".format(_esc(p.strip())) for p in editorial.split("\n\n") if p.strip())
                meta = "{} · {}".format(writer, editor).strip(" ·")
                return '<section class="featured-editorial"><h2>Featured Editorial</h2><a href="#topic-card-{idx}" class="featured-title">{title}</a><div class="editorial-meta">{meta}</div><div class="editorial-body">{body}</div></section>'.format(
                    idx=idx, title=_esc(card.get("title", "")), meta=meta, body=body
                )
        return ""
    except Exception:
        return ""


def _render_card(card, card_index=0):
    try:
        topic_tags = ""
        for t in card.get("topics", [])[:3]:
            if t in TOPICS:
                topic_tags += '<span class="topic-tag" data-topic="{}">{} {}</span>'.format(t, TOPICS[t]["icon"], TOPICS[t]["name"])

        tldr_source = card.get("why_matters", card.get("so_what", ""))
        tldr = ""
        if tldr_source:
            first_sentence = tldr_source.split(".")[0].strip()
            if first_sentence:
                tldr = first_sentence + "."

        source_count = card.get("source_count", 0)
        why_today = _get_why_today(card)

        # gated details
        spin_html = ""
        if card.get("card_mode") == "contested":
            positions = card.get("spin_positions", [])
            preds = card.get("spin_predictions", [])
            items = ""
            for p in positions[:3]:
                if isinstance(p, dict):
                    items += '<div class="spin-position"><div>{}</div><div class="muted">{} · {}</div></div>'.format(_esc(p.get("position", "")), _esc(p.get("who", "")), _esc(p.get("verified", "")))
            for p in preds[:2]:
                if isinstance(p, dict):
                    items += '<div class="spin-watch">{}</div>'.format(_esc(p.get("prediction", "")))
            if items:
                spin_html = '<div class="card-section"><div class="section-label">How Sources Frame This</div>{}</div>'.format(items)

        unknown_html = ""
        if _has_substantive_unknowns(card):
            qas = ""
            for u in card.get("unknowns", card.get("key_unknowns", []))[:3]:
                if isinstance(u, dict):
                    q = _esc(u.get("q", u.get("question", "")))
                    a = _esc(u.get("a", u.get("answer", "Not yet reported.")))
                    if q:
                        qas += '<details class="unknown-qa"><summary>{}</summary><div>{}</div></details>'.format(q, a)
            if qas:
                unknown_html = '<div class="card-section"><div class="section-label">Decision Blockers</div>{}</div>'.format(qas)

        bigger_html = ""
        bigger = card.get("bigger_picture", "")
        if bigger:
            bigger_html = '<div class="card-section"><div class="section-label">What Changes Next</div><p>{}</p></div>'.format(_esc(bigger))

        facts_html = ""
        facts = card.get("key_facts", [])
        if isinstance(facts, list) and facts:
            items = "".join('<li>{}</li>'.format(_esc(f)) for f in facts[:5] if isinstance(f, str) and f.strip())
            if items:
                facts_html = '<div class="card-section"><div class="section-label">Sources & Evidence</div><ul>{}</ul></div>'.format(items)

        sources_html = ""
        for s in card.get("sources", []):
            if isinstance(s, dict):
                nm = _esc(s.get("name", ""))
                url = s.get("url", "")
                nm = '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(url, nm) if url else nm
                sources_html += '<span class="source-pill">{} <span class="muted">{}</span></span>'.format(nm, _esc(s.get("perspective", "")))

        details = ""
        if spin_html or unknown_html or bigger_html or facts_html or sources_html:
            details = '<details class="card-expand"><summary class="card-expand-summary">Go Deeper</summary>{spin}{unknown}{bigger}{facts}<div class="card-section"><div class="section-label">Sources & Evidence</div><div class="source-pills">{sources}</div></div></details>'.format(
                spin=spin_html, unknown=unknown_html, bigger=bigger_html, facts=facts_html, sources=sources_html
            )

        return '<article class="story-card" id="topic-card-{idx}" data-topics="{topics}"><div class="topic-tags">{tags}</div><h2 class="story-title">{title}</h2><div class="card-tldr"><strong>{tldr}</strong></div><div class="why-today">{why_today}</div><div class="story-meta"><span>{count} sources</span></div>{details}</article>'.format(
            idx=card_index,
            topics=" ".join(card.get("topics", [])[:3]),
            tags=topic_tags,
            title=_esc(card.get("title", "")),
            tldr=_esc(tldr),
            why_today=_esc(why_today),
            count=source_count,
            details=details,
        )
    except Exception:
        return ""


def _render_quickscan(data):
    """Legacy dead code kept for compatibility."""
    try:
        if not data:
            return ""
        return '<div class="quickscan" style="display:none"></div>'
    except Exception:
        return ""


def _render_synthesis(synthesis):
    try:
        if not synthesis:
            return ""
        return "<p>{}</p>".format(_esc(synthesis).replace("\n\n", "</p><p>").replace("\n", "<br>"))
    except Exception:
        return ""


def _render_filters():
    try:
        html = '<button class="filter-btn active" data-filter="all">All</button>'
        for tid, info in TOPICS.items():
            html += '<button class="filter-btn" data-filter="{}">{} {}</button>'.format(tid, info["icon"], info["name"])
        return html
    except Exception:
        return ""


def _render_action_layer(actions):
    """Legacy dead code kept for compatibility."""
    try:
        if not actions:
            return ""
        return '<div class="action-layer" style="display:none"></div>'
    except Exception:
        return ""


def _render_predictions(data):
    try:
        if not data:
            return ""
        categories = [
            ("cross_story", "Cross-Story"),
            ("near_term", "Next 48 Hours"),
            ("medium_term", "This Week / This Month"),
        ]
        blocks = ""
        for key, label in categories:
            items = ""
            for p in data.get(key, [])[:3]:
                if not isinstance(p, dict):
                    continue
                signal = p.get("disconfirming_signal") or p.get("disconfirm")
                if not signal:
                    continue
                items += '<div class="pred-item"><div class="pred-text">{}</div><div class="pred-disconfirm">Would be wrong if: {}</div></div>'.format(
                    _esc(p.get("prediction", "")), _esc(signal)
                )
            if items:
                blocks += '<div class="pred-category"><div class="pred-category-label">{}</div>{}</div>'.format(label, items)
        if not blocks:
            return ""
        return '<div class="predictions-box">{}</div>'.format(blocks)
    except Exception:
        return ""


def _render_run_report(reports, run_time):
    try:
        lines = []
        total_llm = 0
        total_ok = 0
        for r in reports:
            total_llm += r.llm_calls
            total_ok += r.llm_successes
            notes = " | ".join(r.notes) if r.notes else ""
            lines.append("{}: {} in / {} out{}".format(r.step_name, r.items_in, r.items_out, " | " + notes if notes else ""))
        summary = " | ".join(lines)
        return "Pipeline: {} | LLM calls: {}/{} succeeded | Runtime: {}s".format(summary, total_ok, total_llm, run_time)
    except Exception:
        return ""


def _render_review_panel(quality_review):
    try:
        if not quality_review or not quality_review.get("reviews"):
            return ""
        return '<div class="analyst-only"><details><summary>Quality Review</summary><pre>{}</pre></details></div>'.format(_esc(str(quality_review)))
    except Exception:
        return ""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Global Intelligence Briefing</title>
<style>
:root {{--bg:#0a0e17;--card-bg:#111827;--border:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#f59e0b;--purple:#a78bfa;}}
* {{box-sizing:border-box}} body {{font-family:Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:0 1rem;max-width:900px;margin:0 auto;}}
.masthead {{text-align:center;padding:1.5rem 0 1rem;border-bottom:1px solid var(--border);margin-bottom:1rem;}}
.mode-toggle {{display:inline-flex;gap:.4rem;margin-top:.8rem}} .mode-btn {{background:var(--card-bg);color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:.28rem .8rem;cursor:pointer}} .mode-btn.active {{background:var(--accent);color:#000}}
.the-brief {{background:var(--card-bg);border:1px solid var(--border);border-radius:10px;padding:1rem;margin:1rem 0 1.2rem;}}
.brief-grid {{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;}} .brief-item {{display:block;padding:.5rem;border:1px solid var(--border);border-radius:6px;color:var(--text);text-decoration:none}} .brief-head {{font-size:.9rem;font-weight:600}} .brief-why {{font-size:.78rem;color:var(--muted)}}
.brief-actions {{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem;margin-top:.8rem}} .brief-action-label {{font-size:.72rem;color:var(--accent);text-transform:uppercase}} .brief-action-item {{display:block;font-size:.83rem;color:var(--text);text-decoration:none;margin:.2rem 0}}
.featured-editorial {{background:var(--card-bg);border-left:3px solid var(--purple);border-radius:8px;padding:1rem;margin-bottom:1rem}}
.filter-bar {{display:flex;flex-wrap:wrap;gap:.4rem;margin:1rem 0}} .filter-btn {{background:var(--card-bg);color:var(--muted);border:1px solid var(--border);padding:.3rem .7rem;border-radius:999px;cursor:pointer}} .filter-btn.active {{background:var(--accent);color:#000}}
.heatmap-btn {{font-size:.75rem;padding:.3rem .7rem;background:transparent;border:1px solid var(--purple);color:var(--purple);border-radius:4px;cursor:pointer}} .heatmap-btn.active {{background:var(--purple);color:#000}}
.story-card {{background:var(--card-bg);border:1px solid var(--border);border-radius:10px;padding:1rem;margin-bottom:.8rem}}
.story-title {{font-size:1.1rem;margin:.2rem 0}} .card-tldr {{margin:.25rem 0 .2rem}} .why-today {{color:var(--muted);font-size:.85rem;margin-bottom:.2rem}}
.topic-tag {{display:inline-block;font-size:.7rem;background:#1e293b;padding:.15rem .45rem;border-radius:999px;margin-right:.25rem}}
.story-meta {{font-size:.75rem;color:var(--muted)}}
.card-expand {{margin-top:.4rem}} .card-expand-summary {{cursor:pointer;color:var(--purple);font-size:.82rem;font-weight:600}}
.card-section {{margin-top:.6rem;padding:.55rem;background:#0f172a;border-radius:6px}} .section-label {{font-size:.72rem;text-transform:uppercase;color:var(--accent);margin-bottom:.3rem}}
.source-pill {{display:inline-block;margin:.2rem .3rem .2rem 0;padding:.2rem .5rem;border:1px solid var(--border);border-radius:999px;font-size:.74rem}} .muted {{color:var(--muted)}}
.pred-category-label {{font-size:.72rem;color:var(--purple);text-transform:uppercase}} .pred-item {{margin:.3rem 0}} .pred-disconfirm {{font-size:.75rem;color:var(--muted)}}
.run-report {{margin:1.3rem 0;padding:.8rem;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;font-size:.75rem;color:var(--muted);text-align:center}}
.analyst-only {{}} .mode-brief .analyst-only {{display:none!important}} .mode-analyst .analyst-only {{display:initial}}
.qs-contested-tag {{font-size:.66rem;color:#fca5a5}}
@media (max-width:700px) {{ .brief-grid,.brief-actions {{grid-template-columns:1fr}} }}
</style>
</head>
<body class=\"mode-brief\">
<div class=\"masthead\"><h1>Global Intelligence Briefing</h1><div class=\"meta\">{date} | {num_stories} stories | Models: {llms}</div><div class=\"meta\" style=\"font-size:.75rem\">Updated every 2 hours · Runtime: {runtime}s</div><div class=\"mode-toggle\" role=\"group\" aria-label=\"View mode\"><button class=\"mode-btn active\" id=\"mode-brief-btn\" type=\"button\">Morning Brief</button><button class=\"mode-btn\" id=\"mode-analyst-btn\" type=\"button\">Analyst View</button></div></div>
{the_brief}
{featured_editorial}
<details class=\"synthesis-expand\"><summary class=\"synthesis-toggle\">Executive Synthesis (full analysis)</summary><div class=\"synthesis-box\"><h2>Executive Synthesis</h2>{synthesis}</div></details>
<div class=\"filter-bar\">{filters}<button class=\"heatmap-btn\" id=\"heatmap-toggle\" title=\"Highlight uncertain claims\">🔍 Uncertainty</button></div>
{stories}
<div class=\"run-report\">{run_report}</div>
{review_panel}
<script>
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
        const url = new URL(window.location);
        if (f === 'all') {{ url.searchParams.delete('filter'); }}
        else {{ url.searchParams.set('filter', f); }}
        history.replaceState(null, '', url);
    }});
    if (btn.dataset.filter === initialFilter) {{ btn.click(); }}
}});
document.getElementById('heatmap-toggle').addEventListener('click', function() {{
    document.body.classList.toggle('heatmap-mode');
    this.classList.toggle('active');
    if (document.body.classList.contains('heatmap-mode')) {{
        document.querySelectorAll('.card-expand').forEach(d => d.open = true);
    }}
}});
if (window.location.hash) {{
    const target = document.querySelector(window.location.hash);
    if (target) {{
        const expand = target.querySelector('.card-expand');
        if (expand) expand.open = true;
        setTimeout(() => target.scrollIntoView({{behavior: 'smooth'}}), 100);
    }}
}}
document.querySelectorAll('a[href^="#topic-card"]').forEach(a => {{
    a.addEventListener('click', () => {{
        const hash = a.getAttribute('href').replace(/.*#/, '#');
        const target = document.querySelector(hash);
        if (target) {{
            const expand = target.querySelector('.card-expand');
            if (expand) expand.open = true;
        }}
    }});
}});
(function () {{
    const briefBtn = document.getElementById('mode-brief-btn');
    const analystBtn = document.getElementById('mode-analyst-btn');
    if (!briefBtn || !analystBtn) return;
    function applyMode(mode) {{
        if (mode === 'analyst') {{
            document.body.classList.remove('mode-brief');
            document.body.classList.add('mode-analyst');
            briefBtn.classList.remove('active');
            analystBtn.classList.add('active');
        }} else {{
            document.body.classList.remove('mode-analyst');
            document.body.classList.add('mode-brief');
            analystBtn.classList.remove('active');
            briefBtn.classList.add('active');
        }}
    }}
    briefBtn.addEventListener('click', function() {{ applyMode('brief'); try {{ localStorage.setItem('gib-view-mode', 'brief'); }} catch (e) {{}} }});
    analystBtn.addEventListener('click', function() {{ applyMode('analyst'); try {{ localStorage.setItem('gib-view-mode', 'analyst'); }} catch (e) {{}} }});
    let savedMode = 'brief';
    try {{ const storedMode = localStorage.getItem('gib-view-mode'); if (storedMode === 'brief' || storedMode === 'analyst') savedMode = storedMode; }} catch (e) {{}}
    applyMode(savedMode);
}})();
</script>
</body></html>"""
