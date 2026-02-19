# Global Briefing — Suggestions Tracker
Last updated: 2026-02-19 (Sprint 1 complete)

## Status Key
- 🔴 Not started
- 🟡 In progress
- 🟢 Done
- ⬜ Rejected / Not pursuing
- 💡 Worth exploring later

---

## BUGS & FIXES (do first)

| # | Issue | Source | Status | Notes |
|---|-------|--------|--------|-------|
| B1 | Quickscan topic grouping is wrong — Iran under "Tech & AI", South Korea under "US Politics" | Claude review | 🟢 | Fixed: match by headline word overlap instead of position index |
| B2 | Filter bug: `.includes(f)` substring matching — "politics" catches "us_politics" | LLM-1 | 🟢 | Fixed: `.split(' ').includes(f)` |
| B3 | Importance dots all red — tier differentiation not working | Claude review | 🟢 | Fixed: dots now use depth_tier (percentile-based) instead of raw stars |
| B4 | 10/11 cards are DEEP ANALYSIS — materiality cutoff too generous | Claude review | 🟢 | Fixed: percentile-based tiers — top 25% deep, middle 50% standard, bottom 25% brief |
| B5 | "How It's Being Used" showing on 8/11 cards — too many | Claude review | 🟢 | Fixed: removed topic-based fallback, now only triggers when compare step detects real contention |

---

## HIGH PRIORITY — Card & Content Structure

| # | Suggestion | Source | Status | Assessment |
|---|-----------|--------|--------|------------|
| H1 | Bold one-sentence TL;DR at top of every card | LLM-3 | 🔴 | **Strong yes.** Pairs well with our "Why This Matters" — could be a single bolded sentence above it |
| H2 | Collapse card details by default — keep Why This Matters + What's Happening visible, rest collapsed | LLM-3 | 🔴 | **Strong yes.** Biggest readability win. Reader scans title + why + situation, clicks to expand |
| H3 | Cap "What We Still Don't Know" to 3 items max | LLM-1 | 🔴 | **Yes.** Current output has 5+ Q&As per card — too many. 2-3 synthesized is enough |
| H4 | Reformat Executive Synthesis into buckets: 3 calls / 3 risks / 3 watch items | LLM-3 | 🔴 | **Good idea.** Current synthesis is paragraph prose — structured buckets scan faster |
| H5 | Rewrite "Today in 60 Seconds" / Quickscan into tighter one-line bullets | LLM-3 | 🔴 | **Yes.** Current quickscan entries are 2-3 sentences each — should be headline + one-liner |
| H6 | More breathing room between card sections | LLM-1 | 🟢 | Done: increased margin and padding on .card-section |

---

## MEDIUM PRIORITY — Features & Intelligence

| # | Suggestion | Source | Status | Assessment |
|---|-----------|--------|--------|------------|
| M1 | Action Layer at top: "If you only do 1 thing today..." | LLM-3 | 🔴 | **Very strong.** Single most useful addition for a busy reader. Could be 3 lines max above quickscan |
| M2 | Confidence × Impact 2×2 matrix — let users filter Act/Watch | LLM-3 | 💡 | **Interesting but complex.** Requires reliable confidence scoring. Park for later — the importance dots are a simpler version of this |
| M3 | Prediction hooks + disconfirming signals + expiry windows | LLM-3 | 💡 | **Strong concept, hard execution.** Per-card predictions exist but tracking outcomes requires state across runs. Worth exploring after core is solid |
| M4 | One contrarian take per day | LLM-3 | 💡 | **Creative.** Could be a synthesis-level addition — "Why smart people disagree about [top story]" — adds real value |
| M5 | Source profile line per card (primary vs secondary, proximity, diversity) | LLM-3 | 🔴 | **Partial yes.** We have source pills already. Could add a one-line summary: "Based on 14 sources across 6 regions, 3 contested" |
| M6 | Reader modes: Operator / Narrative / Briefing | LLM-3 | 💡 | **Overkill for now.** Collapse-by-default (H2) achieves 80% of this. Revisit later |
| M7 | Dependency threads: upstream drivers → downstream consequences | LLM-3 | 💡 | **Conceptually great, very hard.** Requires cross-card relationship mapping. The "Bigger Picture" section partially does this. Park |
| M8 | "Make my brief" button (30s / 2m / 5m personalized output) | LLM-3 | 💡 | **Cool but requires client-side LLM or API.** Not feasible for static HTML. Park for future interactive version |
| M9 | Epistemic Heatmap toggle — highlight uncertain claims, dim verified | LLM-1 | 🔴 | **High bang for buck.** We already have the CSS classes. ~10 lines of CSS + 1 button. Do it |
| M10 | URL State Management — filters update URL for sharing/bookmarking | LLM-1 | 🔴 | **Yes.** ~15 lines of JS. Easy win for shareability |
| M11 | Perspective Gap Fill — after mapping perspectives, LLM identifies expected positions, finds gaps, does targeted web search to find missing viewpoints, integrates as labeled research sources | Rob | 🔴 | **Strong yes.** Solves the "we only see what our feeds give us" problem. Deep-tier cards only, cap 2-3 gaps per story. New pipeline step 5b after perspectives.py |

---

## LOWER PRIORITY — Design & Accessibility

| # | Suggestion | Source | Status | Assessment |
|---|-----------|--------|--------|------------|
| L1 | Sticky filter bar | LLM-1 | 🟢 | Done: position sticky + dark bg + border |
| L2 | Mobile horizontal scrolling filters | LLM-1 | 🔴 | **Good.** `overflow-x: auto; white-space: nowrap; flex-wrap: nowrap;` |
| L3 | Color contrast improvements (dark red/purple on dark bg) | LLM-1 | 🔴 | Worth testing with contrast checker |
| L4 | Bigger touch targets for details toggles (44px min) | LLM-1 | 🔴 | Accessibility standard |
| L5 | Screen reader friendly emojis (aria-hidden) | LLM-1 | 🔴 | Easy fix |
| L6 | Keyboard navigation / aria-expanded on dropdowns | LLM-1 | 🔴 | Accessibility standard |
| L7 | Extract CSS to external file | LLM-1 | ⬜ | **No — single-file HTML is intentional.** Static site generated by pipeline, external CSS adds deployment complexity for no user benefit |
| L8 | Decouple to JSON data + JS renderer | LLM-1 | ⬜ | **Not now.** Same reason — static HTML from pipeline is the whole point. Would be a full rewrite |
| L9 | Split-pane desktop UI (pin quickscan left, cards right) | LLM-1 | 💡 | **Interesting.** Would require significant layout rework. Park |
| L10 | Visualize spin as horizontal spectrum bar | LLM-1 | 💡 | **Cool visual but current text format is more informative.** The positions + verified claims convey more than a bar |

---

## REJECTED / NOT APPLICABLE

| # | Suggestion | Source | Reason |
|---|-----------|--------|--------|
| R1 | AI-Driven "Truth Decay Alerts" with X/Community Notes integration | LLM-2 | Requires live X API, real-time infrastructure. Not applicable to static briefing |
| R2 | "Shadow Briefings" — alternate left/right/neutral versions | LLM-2 | Would 3x LLM costs per run. The spin section already shows different positions |
| R3 | "Infinite Insight Feed" single-column | LLM-2 | Already essentially what we have — cards in a column |
| R4 | "User Intel Uploads" — citizen journalism submissions | LLM-2 | Requires auth, moderation, backend. Way out of scope |
| R5 | Musk/X alignment anything | LLM-2 | LLM-2 response was clearly Grok — the Musk framing is irrelevant to our product |

---

## IMPLEMENTATION ORDER (my recommendation)

### Sprint 1 — Bugs & Quick Wins (next deploy)
1. B2: Fix filter substring bug
2. B1: Fix quickscan topic grouping
3. B3+B4: Fix importance scoring / tier distribution
4. B5: Tighten spin section threshold
5. H6: Add breathing room between sections (CSS)
6. L1: Sticky filter bar (CSS)

### Sprint 2 — Card Readability
7. H2: Collapse cards by default (keep title + why + whats visible)
8. H1: Add TL;DR sentence at top of each card
9. H3: Cap unknowns at 3
10. H5: Tighten quickscan to one-liners
11. M9: Epistemic heatmap toggle
12. M10: URL state management

### Sprint 3 — Intelligence Features
13. M1: Action Layer at top of briefing
14. H4: Restructure executive synthesis
15. M5: Source profile summary line
16. M4: Contrarian take section
17. M11: Perspective Gap Fill module (step 5b)

### Future / Exploration
- M2: Confidence × Impact matrix
- M3: Prediction tracking across runs
- M6: Reader modes
- M7: Dependency threads
- M8: "Make my brief" button
- L9: Split-pane layout
- L10: Spin visualization
