# Global Briefing Architecture

## What This Is
AI-powered news intelligence system. Pulls from 70+ RSS sources globally, triages by topic relevance, clusters stories by event, gathers multiple perspectives, analyzes with multiple LLMs, and publishes a clean briefing to GitHub Pages twice daily.

## Owner
Rob — solo operator. No team. All changes go through LLM-assisted development (Claude, ChatGPT). This document exists so any LLM session can immediately understand the project without re-explaining.

## Pipeline (strict order)
1. **FETCH**: Pull RSS feeds in parallel (20 workers, 15s timeout per feed) → list of Articles. Bad feeds are skipped gracefully.
2. **TRIAGE**: Keyword-based topic classification (free, local) → relevant Articles with topics and importance scores.
3. **CLUSTER**: Group articles about the same event using title similarity (Jaccard) → StoryGroups. Multi-source stories flagged.
4. **SELECT**: Multi-LLM voting — each available LLM independently picks top stories, votes are tallied, highest-voted stories win. Reduces single-model selection bias.
5. **ANALYZE**: Each selected StoryGroup sent to all available LLMs for independent analysis (2-3 paragraphs each) → dict of {llm_name: analysis_text}.
6. **SYNTHESIZE**: One LLM writes an executive overview of all stories and analyses → string.
7. **PUBLISH**: Generate static HTML briefing page → output/index.html, deployed to GitHub Pages.

## Data Models
- **Article**: title, url, source_name, source_region, source_bias, summary, published, topics[], importance_score, is_perspective_story, related_articles[], llm_analyses{}
- **StoryGroup**: list of Articles about the same event. Lead article is group[0]. Properties derived from group: source_count, is_multi_perspective.
- **Analysis result**: dict of {llm_label: analysis_text} per StoryGroup.

## Topics
1. World Politics & Geopolitics
2. Canadian Politics & Policy
3. US Politics
4. Economics & Business
5. Technology & AI
6. Canadian Insurance Industry
7. Data, Privacy & AI Governance (includes breaches, political commentary, regulation — not just formal legal developments)
8. Culture, Joy & Good News

## Sources
70+ RSS feeds across: Canada, USA, UK, Europe, Middle East, Asia-Pacific, Africa, Latin America, plus specialized tech/AI, insurance, privacy/security, and good news sources. Full list in RSS_SOURCES in briefing.py.

## LLM Models (as of Feb 2026)
| Role | Provider | Model String | Notes |
|------|----------|-------------|-------|
| Triage voting | Google | gemini-3-flash-preview | Also used for analysis |
| Triage voting | OpenAI | gpt-4.1 | Also used for analysis |
| Triage voting | xAI | grok-3-fast | Also used for analysis |
| Analysis | Google | gemini-3-flash-preview | |
| Analysis | OpenAI | gpt-4.1 | |
| Analysis | Anthropic | claude-sonnet-4-20250514 | Only if ANTHROPIC_API_KEY provided |
| Analysis | xAI | grok-3-fast | |
| Synthesis | Whichever is available | First available key wins | Gemini preferred |

## API Keys (GitHub Secrets)
- `GOOGLE_API_KEY` — required (Gemini, paid tier)
- `OPENAI_API_KEY` — optional but recommended
- `XAI_API_KEY` — optional but recommended
- `ANTHROPIC_API_KEY` — optional

## Hosting & Cost
- **GitHub Actions** (free tier): scheduled runs at 6 AM and 5 PM Eastern
- **GitHub Pages** (free): static HTML, public repo required
- **LLM API costs**: target <$15/month
- **Cost control**: funnel approach — free keyword triage first, cheap LLM voting on top 50 candidates, expensive multi-LLM analysis only on final 12 stories

## Current File Structure
```
global-briefing/
├── briefing.py          # Everything (fetch, triage, cluster, analyze, publish)
├── requirements.txt     # feedparser, requests
├── README.md
├── ARCHITECTURE.md      # This file
└── .github/
    └── workflows/
        └── briefing.yml # Scheduled + manual trigger
```

## Planned File Structure (Phase 1 Refactor)
```
global-briefing/
├── config/
│   ├── broad.json
│   └── sources.json
├── prompts/
│   ├── triage.txt
│   ├── analysis.txt
│   └── synthesis.txt
├── pipeline/
│   ├── fetch.py
│   ├── triage.py
│   ├── cluster.py
│   ├── analyze.py
│   ├── synthesize.py
│   └── publish.py
├── models.py
├── llm.py
├── runner.py
├── requirements.txt
├── ARCHITECTURE.md
├── CHANGELOG.md
└── .github/workflows/briefing.yml
```

## Rules for LLM-Assisted Development
1. **Don't change data models** without updating this document.
2. **All LLM API calls** go through the unified caller (call_llm / _call_llm_once) with retry logic.
3. **Prompts** should explicitly say "plain text only, no markdown" to avoid raw formatting in HTML output.
4. **Rate limiting**: 5-second delay between LLM calls, automatic retry with backoff on 429 errors.
5. **Fail gracefully**: if a feed or LLM fails, skip it and continue. Never crash the whole pipeline.
6. **Max 12 stories** per run to stay within budget.
7. **Multi-model voting** for story selection to avoid single-model bias.
8. **Don't over-engineer**: this is an MVP. Add complexity only when the simple approach demonstrably fails.

## Known Limitations
- RSS summaries are often thin (1-2 sentences). Analysis quality depends on what the feed provides.
- No full article scraping — we work with headlines and RSS summaries only.
- Clustering uses simple title word overlap (Jaccard similarity). Can merge unrelated stories or split one event.
- No translation — non-English sources that don't provide English RSS are effectively invisible.
- No social media ingestion — LLM "counter-narrative" analysis would be speculative without actual social data.
- GitHub Actions free tier allows ~2000 minutes/month. Current usage is ~10 min/day.

## Version History
- **v0.1** — Initial single-file MVP. RSS fetch + keyword triage + single-model (Gemini) analysis + HTML output.
- **v0.2** — Multi-LLM analysis (Gemini, ChatGPT, Grok). Rate limiting and retry logic. Multi-model story voting.
- **v0.3 (planned)** — Structural split into modules. Config-driven query packs. Improved clustering.
