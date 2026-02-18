# Global Briefing v3 — Architecture

## Design Principles
1. **Importance drives depth** — not every story gets the same treatment
2. **Perspectives come from data, not invention** — look at what's in the cluster
3. **Noise filtering at every stage** — remove clutter, not just at the end
4. **Modular** — each step is a self-contained module with clean interfaces
5. **No artificial limits** — materiality cutoff, not hard story count

## Pipeline Flow

```
FETCH → TRIAGE → CLUSTER → SELECT → [per story: DEPTH ROUTING]
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼          ▼
                           BRIEF      STANDARD    DEEP
                          (1-2★)      (3★)       (4-5★)
                              │          │          │
                              ▼          ▼          ▼
                          summary    perspectives  perspectives
                          + facts    extract       extract
                                     compare       compare
                                     write         investigate
                                                   write (full)
                              │          │          │
                              └──────────┼──────────┘
                                         ▼
                              SYNTHESIZE → QUICKSCAN → PUBLISH
```

## Step Interfaces

Every step module exports a `run()` function with typed inputs/outputs.
Every step returns a `StepReport` for observability.

### Step 1: FETCH
- Input: source list [(name, url, region, bias, language)]
- Output: list[Article]
- Change: sources now include language tag; non-English sources added

### Step 2: TRIAGE  
- Input: list[Article], topics dict
- Output: list[Article] with topics + relevance scores
- Change: LLM-based batched classification replaces keyword matching
- Batch size: 20 articles per LLM call (~40-50 calls)

### Step 3: CLUSTER
- Input: list[Article]  
- Output: list[StoryCluster]
- Change: mechanical first pass + LLM merge/split second pass
- StoryCluster includes: articles, cluster_id, size, topic spread

### Step 4: SELECT
- Input: list[StoryCluster], topics
- Output: list[RankedStory] — sorted by importance, no hard limit
- Change: LLMs rate importance 1-10 (not just pick/skip)
- Materiality cutoff: drop stories below threshold (e.g., avg score < 4)
- Diversity is soft nudge on final ordering, not hard gate

### Step 5: PERSPECTIVES (per story, standard/deep only)
- Input: StoryCluster (the actual articles in the cluster)
- Output: list[Perspective], list[str] missing
- Change: LLM looks at ACTUAL sources in cluster, identifies what angle
  each source takes, groups similar angles, flags what's missing
- No artificial limit on perspective count

### Step 6: EXTRACT (per story, standard/deep only)
- Input: selected sources with perspectives
- Output: list[ClaimSet]
- Change: hallucination check — verify extracted claims trace to source text

### Step 7: COMPARE (per story, standard/deep only)
- Input: list[ClaimSet], lead title
- Output: ComparisonResult (agreed, disputed, framing, unknowns, contention_level)

### Step 8: INVESTIGATE (per story, deep only)
- Input: ComparisonResult, story title
- Output: InvestigationResult — framed as "what changes the story"
- Change: output explicitly states what the investigation adds
- If nothing new: returns "coverage is accurate, no additional context"

### Step 9: WRITE (per story, all tiers)
- Input: varies by tier
- Brief: cluster summary only → 1-2 sentence card
- Standard: comparison + perspectives → news card or contested card  
- Deep: comparison + investigation → full analysis card
- Output: TopicCard

### Step 10: SYNTHESIZE
- Input: all TopicCards
- Output: executive summary

### Step 11: QUICKSCAN  
- Input: all TopicCards
- Output: scannable overview

### Step 12: PUBLISH
- Input: everything
- Output: HTML

## Depth Tiers

| Tier | Stars | Steps Run | LLM Calls | Use Case |
|------|-------|-----------|-----------|----------|
| BRIEF | 1-2★ | write only | 1-2 | Minor story, "also noteworthy" |
| STANDARD | 3★ | perspectives→extract→compare→write | 8-15 | Important news, clear coverage |
| DEEP | 4-5★ | perspectives→extract→compare→investigate→write | 12-20 | Major event, contested, complex |

## Source Language Handling
- English sources: used as-is
- Non-English sources with English editions: fetch English edition
- Key non-English sources: translate title+summary during fetch (1 LLM call per article)
