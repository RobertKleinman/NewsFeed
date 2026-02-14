# Global Briefing Architecture v2

## What This Is
AI-powered news intelligence system. Pulls from 70+ RSS sources globally, clusters stories by event, maps meaningful perspectives using multiple LLMs, extracts structured claims, cross-compares sources for agreements/disagreements/framing, investigates gaps, and publishes a layered briefing (quick-scan + deep-read) to GitHub Pages twice daily.

## Owner
Rob — solo operator. All changes go through LLM-assisted development (Claude, ChatGPT). This document exists so any LLM session can immediately understand the project without re-explaining.

## How to Use This Document
When starting a conversation about this project, paste this file plus the specific module file you want to change. You do NOT need to share the whole codebase. Each module is self-contained with defined inputs and outputs.

## Pipeline (strict order)

```
Fetch -> Triage -> Cluster -> Select -> Perspectives -> Extract -> Compare -> Investigate -> Write -> Synthesize -> Publish
```

| Step | Module | Input | Output | LLM? |
|------|--------|-------|--------|------|
| 1. Fetch | pipeline/fetch.py | RSS source list | list of Article | No |
| 2. Triage | pipeline/triage.py | Articles, topics dict | Articles with topics + scores | No |
| 3. Cluster | pipeline/cluster.py | Articles | list of StoryGroups (list of list) | No |
| 4. Select | pipeline/select.py | StoryGroups, topics | top StoryGroups (max 12) | Yes: multi-model voting |
| 5. Perspectives | pipeline/perspectives.py | one StoryGroup | selected_sources, missing, perspectives | Yes: multi-model (diversity matters here) |
| 6. Extract | pipeline/extract.py | selected_sources | list of claim dicts | Yes: one cheap model |
| 7. Compare | pipeline/compare.py | claims, title | dict of {model: comparison_text} | Yes: 2 models (bias detection) |
| 8. Investigate | pipeline/investigate.py | comparisons, claims, title | investigation text | Yes: different model than comparators |
| 9. Write | pipeline/write.py | comparisons, investigation, sources | structured card dict (JSON) | Yes: different model than compare/investigate |
| 10. Synthesize | pipeline/synthesize.py | all topic cards | synthesis text | Yes: one model |
| 11. Publish | pipeline/publish.py | cards, synthesis, reports | HTML string | No |

Steps 5-9 run once per selected story. Steps 1-4 and 10-11 run once per briefing.

## Key Design Principles
1. LLMs advise, code decides. Source selection is deterministic (step 5b). LLMs identify perspectives, code picks the sources.
2. Multi-model diversity is concentrated where editorial judgment matters: story selection (step 4) and perspective mapping (step 5). Models do DIFFERENT jobs, not the same job three times.
3. Each model in the analysis chain has a distinct role (extractor, comparator, investigator, writer). The writer is always a model NOT used for comparison to avoid compounding bias.
4. Output is layered: quick-scan (grid, bullets, key facts) first, expandable detail (full analysis, raw comparisons) underneath.
5. Every module has a run() function with defined inputs/outputs. Modules don't import each other (only models.py, config.py, llm.py).

## File Structure

```
global-briefing/
├── runner.py              # Entry point. Calls pipeline steps in order. (165 lines)
├── config.py              # Topics, RSS sources, LLM configs. Query pack support. (200 lines)
├── models.py              # Article, StepReport dataclasses. (44 lines)
├── llm.py                 # All LLM API calls. Retry, caching. (122 lines)
├── requirements.txt       # feedparser, requests
├── ARCHITECTURE.md        # This file
├── pipeline/
│   ├── __init__.py
│   ├── fetch.py           # Step 1: RSS fetching (63 lines)
│   ├── triage.py          # Step 2: Keyword classification (32 lines)
│   ├── cluster.py         # Step 3: Event grouping (81 lines)
│   ├── select.py          # Step 4: Multi-model story voting (99 lines)
│   ├── perspectives.py    # Step 5: Perspective mapping + source selection (146 lines)
│   ├── extract.py         # Step 6: Claim extraction (74 lines)
│   ├── compare.py         # Step 7: Cross-source comparison (77 lines)
│   ├── investigate.py     # Step 8: Gap filling + forecast (99 lines)
│   ├── write.py           # Step 9: Topic card assembly (182 lines)
│   ├── synthesize.py      # Step 10: Executive synthesis (61 lines)
│   └── publish.py         # Step 11: HTML generation (437 lines)
└── .github/
    └── workflows/
        └── briefing.yml   # Scheduled + manual trigger
```

## Data Models (models.py)

### Article
```
title, url, source_name, source_region, source_bias,
summary, published, topics[], importance_score
```

### StepReport
```
step_name, items_in, items_out, llm_calls, llm_successes, llm_failures, notes[]
```

### Topic Card (dict returned by write.py)
```
title, topics[], source_count, perspectives_used,
sources: [{name, region, bias, perspective, url}],
missing_perspective_list[], comparisons: {model: text},
investigation: text, written_by: model_label,
what_happened, agreed_facts, disagreements, framing_differences,
key_unknowns, implications, what_to_watch, predictions, missing_viewpoints
```

## LLM Model Assignments

| Role | Where | Model | Why |
|------|-------|-------|-----|
| Triage voting | select.py | All available (up to 3) | Reduces selection bias |
| Perspective mapping | perspectives.py | All available (up to 3) | Divergence expands the lens |
| Claim extraction | extract.py | First available (cheapest) | Mechanical task, cost efficiency |
| Cross-source comparison | compare.py | 2 models | Bias detection needs multiple eyes |
| Gap investigation + forecast | investigate.py | Model NOT used for comparison | Avoids compounding |
| Topic card writing | write.py | Model NOT used for compare/investigate | Avoids compounding |
| Executive synthesis | synthesize.py | First available | Single coherent voice |

### Current Models (as of Feb 2026)
- Gemini: gemini-3-flash-preview (Google)
- ChatGPT: gpt-4.1 (OpenAI)
- Grok: grok-3-fast (xAI)
- Claude: claude-sonnet-4-20250514 (Anthropic, if key provided)

## API Keys (GitHub Secrets)
- GOOGLE_API_KEY — required
- OPENAI_API_KEY — recommended
- XAI_API_KEY — recommended
- ANTHROPIC_API_KEY — optional

## Hosting & Cost
- GitHub Actions free tier: scheduled 2x/day (6 AM, 5 PM Eastern)
- GitHub Pages free tier: static HTML, public repo
- Target: under $15/month in LLM API calls
- Cost control: funnel approach (free keyword triage, cheap extraction, expensive analysis only on final 12 stories)
- In-memory LLM response cache avoids duplicate calls within same run

## HTML Output Design
Layered reading experience:
1. Quick scan: headline, source pills with perspective labels, "what happened" box, perspective comparison grid, agreed facts (green checkmarks), disagreements (red X), what to watch (blue arrows)
2. Expandable detail: framing analysis, implications, predictions, key unknowns, missing viewpoints, background/context from investigation, raw model comparisons
3. Synthesis at top with structured sections: themes, notable disagreements, looking ahead
4. Topic filter buttons, run report at bottom

## Rules for LLM-Assisted Development
1. Don't change models.py schemas without updating this document.
2. All LLM calls go through llm.py. No direct API calls anywhere else.
3. Pipeline modules only import from models.py, config.py, and llm.py. Never from each other.
4. Each module's run() function signature is its contract. Change with care.
5. Prompts say "plain text only, no markdown" to avoid raw formatting in HTML.
6. Temperature is 0.3 everywhere for reproducibility.
7. Max 12 stories per run to stay within budget.
8. Every step returns a StepReport for observability.

## Query Packs (config-driven runs)
Place JSON files in a config/ directory. Runner loads them via --config flag.
```json
{
  "name": "Canadian Insurance & Privacy Focus",
  "sources": ["Canadian Underwriter", "Insurance Business Canada", "IAPP", "CBC News"],
  "topics": ["insurance_canada", "data_privacy_governance", "canada_politics"]
}
```
Use "sources": "all" for the full source list.

## How to Iterate on a Specific Module
1. Open a new conversation with Claude or ChatGPT.
2. Paste this ARCHITECTURE.md.
3. Paste the specific module file you want to change.
4. Describe what you want. The LLM has full context from the architecture doc.
5. Test the change. Commit.

## Removing or Replacing a Step
To remove a step (e.g., investigate.py):
1. Delete the import in runner.py
2. In runner.py's process_story(), remove the call and pass None to write.py for investigation
3. No other files change

To replace a step (e.g., swap cluster.py for an embedding-based version):
1. Rewrite cluster.py
2. Ensure run() still takes list of Article and returns list of list[Article]
3. No other files change

## Known Limitations
- RSS summaries are often thin (1-2 sentences). Analysis quality depends on feed quality.
- No full article scraping. Working with headlines and RSS snippets only.
- Clustering uses title word overlap + entity overlap. Can merge unrelated or split related stories.
- No translation. Non-English sources without English RSS are invisible.
- No social media ingestion. Investigation step uses LLM training knowledge, not live social data.
- Investigation step clearly labeled as AI inference, distinct from source-reported facts.

## Version History
- v0.1 — Single-file MVP. RSS + keyword triage + single-model analysis + HTML.
- v0.2 — Multi-LLM analysis. Rate limiting, retry. Multi-model story voting.
- v1.0 — Extract-compare-write pipeline. Multi-model perspective mapping. Structured topic cards.
- v2.0 — Modular architecture (current). 12 pipeline modules. Investigation + forecast step. Layered HTML output with scan + detail. Config-driven query packs. Run reports. LLM response caching.
