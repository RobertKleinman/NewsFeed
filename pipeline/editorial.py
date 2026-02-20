"""
Step 9e: Editorial Analysis — deep analytical essays on the most important stories.

Selects the top 1-2 stories and produces editorial analysis that goes beyond
surface reporting to examine:
  - Real motivations of actors (personal, political, financial, ideological)
  - Gap between stated and actual goals
  - What's theater vs substance
  - Historical patterns this fits
  - What actors expect/want to happen
  - What is real and what is not

Uses a writer/editor feedback loop:
  - Writer (strongest available model) drafts the editorial
  - Editor (different model) reviews: challenges assertions, asks pointed
    questions, fact-checks claims
  - Writer revises based on editor feedback
  - Max 2 revision rounds to cap cost

~4-6 LLM calls per editorial, 1-2 editorials per run = 4-12 calls total.
"""

import json
import re

import llm as llm_caller
from config import LLM_CONFIGS
from models import StepReport


# Model preference order for writer vs editor roles
# Writer: want the strongest reasoning model
WRITER_PREFERENCE = ["claude", "chatgpt", "gemini_pro", "grok", "gemini"]
# Editor: want a different model that's good at critique
EDITOR_PREFERENCE = ["gemini_pro", "claude", "chatgpt", "grok", "gemini"]

MAX_EDITORIALS = 2
MAX_REVISION_ROUNDS = 2


def run(topic_cards):
    """Generate editorials for top stories. Modifies cards in place. Returns report."""
    print("\n>>> EDITORIAL: selecting top stories...")
    report = StepReport("editorial", items_in=len(topic_cards))

    available = llm_caller.get_available_llms()
    if len(available) < 2:
        print("    Need 2+ LLMs for writer/editor. Skipping editorials.")
        report.notes.append("skipped: fewer than 2 LLMs available")
        return report

    # Select writer and editor (must be different models)
    writer_id = next((m for m in WRITER_PREFERENCE if m in available), available[0])
    editor_id = next((m for m in EDITOR_PREFERENCE if m in available and m != writer_id), None)
    if not editor_id:
        editor_id = [m for m in available if m != writer_id][0] if len(available) > 1 else None
    if not editor_id:
        print("    Cannot assign different editor. Skipping.")
        return report

    writer_label = LLM_CONFIGS.get(writer_id, {}).get("label", writer_id)
    editor_label = LLM_CONFIGS.get(editor_id, {}).get("label", editor_id)
    print("    Writer: {} | Editor: {}".format(writer_label, editor_label))

    # Select top stories: DEEP tier, highest importance, most sources
    candidates = [
        c for c in topic_cards
        if c.depth_tier == "deep" and c.source_count >= 3
    ]
    if not candidates:
        # Fall back to top standard cards
        candidates = [
            c for c in topic_cards
            if c.depth_tier in ("deep", "standard") and c.source_count >= 3
        ]

    # Sort by importance descending, then source count
    candidates.sort(key=lambda c: (c.importance, c.source_count), reverse=True)
    selected = candidates[:MAX_EDITORIALS]

    if not selected:
        print("    No suitable stories for editorial")
        report.notes.append("no candidates met criteria")
        return report

    print("    {} stories selected for editorial".format(len(selected)))

    for card in selected:
        print("\n    EDITORIAL: {}".format(card.title[:60]))
        editorial, rounds = _write_editorial(card, writer_id, editor_id, report)
        if editorial:
            card.editorial = editorial
            card.editorial_writer = writer_label
            card.editorial_editor = editor_label
            card.editorial_rounds = rounds
            report.items_out += 1
            print("      Done ({} rounds, writer: {}, editor: {})".format(
                rounds, writer_label, editor_label))

    report.notes.append("{} editorials written".format(report.items_out))
    return report


def _build_card_context(card):
    """Build the context the writer/editor sees about the story."""
    facts = "\n".join("- {}".format(f) for f in card.key_facts[:8]) if card.key_facts else "None"
    spin = ""
    if card.spin_positions:
        spin = "\n".join(
            "- {who}: {pos} (claim: {claim}, verified: {v})".format(
                who=p.get("who", "?"), pos=p.get("position", "?"),
                claim=p.get("key_claim", "?"), v=p.get("verified", "?"))
            for p in card.spin_positions[:4])

    return """STORY: {title}

WHAT'S HAPPENING:
{whats}

WHY THIS MATTERS:
{why}

KEY FACTS:
{facts}

BIGGER PICTURE:
{bigger}

{spin_section}

MISSING PERSPECTIVES: {missing}
SOURCES: {src_count} total ({indep} independent)""".format(
        title=card.title,
        whats=card.whats_happening or card.what_happened or "",
        why=card.why_matters or card.so_what or "",
        facts=facts,
        bigger=card.bigger_picture or "",
        spin_section="COMPETING POSITIONS:\n{}".format(spin) if spin else "",
        missing=", ".join(card.missing_perspectives[:5]) if card.missing_perspectives else "None identified",
        src_count=card.source_count,
        indep=card.independent_count)


def _write_editorial(card, writer_id, editor_id, report):
    """Run the writer/editor loop. Returns (editorial_text, num_rounds)."""
    context = _build_card_context(card)

    # === WRITER: First draft ===
    writer_prompt = """You are writing an editorial analysis for an intelligence briefing. This is NOT a summary — the reader has already seen the facts. Your job is to go DEEPER.

STORY CONTEXT:
{context}

Write an editorial analysis (400-600 words) that addresses:

1. REAL MOTIVATIONS: What are the key actors actually trying to achieve? Distinguish between stated goals and likely actual motivations (personal power, domestic politics, financial interests, ideology, legacy, desperation, etc.). Be specific about which actors and which motivations.

2. THEATER VS SUBSTANCE: What in this story is performative (for domestic audiences, for allies, for opponents) vs what represents genuine shifts in position or capability? What signals should a sophisticated reader pay attention to vs ignore?

3. PATTERN RECOGNITION: What historical precedent or recurring pattern does this fit? Has this playbook been used before, and how did it turn out? What does the pattern predict?

4. WHAT ACTORS EXPECT: What outcome does each key actor think they're working toward? Are these expectations realistic? Where is there a dangerous gap between expectation and likely reality?

5. THE UNCOMFORTABLE TRUTH: What's the thing that reporting tends to dance around or frame diplomatically? State it plainly.

RULES:
- Be specific. Name actors, cite evidence, reference concrete facts from the story.
- Distinguish clearly between what you know from the evidence and what you're inferring.
- Don't hedge everything. Take analytical positions and defend them.
- Write in a clear, direct style. No throat-clearing, no "it remains to be seen."
- This should read like the analysis a veteran correspondent would give off the record.""".format(context=context)

    report.llm_calls += 1
    draft = llm_caller.call_by_id(writer_id,
        "You are a veteran intelligence analyst writing editorial analysis. Be direct, specific, and analytical.",
        writer_prompt, 3000)

    if not draft:
        report.llm_failures += 1
        return None, 0

    report.llm_successes += 1

    # === EDITOR: Review ===
    rounds = 0
    current_draft = draft

    for round_num in range(MAX_REVISION_ROUNDS):
        editor_prompt = """You are the editor reviewing an editorial analysis for an intelligence briefing.

STORY CONTEXT:
{context}

CURRENT DRAFT:
{draft}

Review this editorial critically. Check for:

1. UNSUPPORTED ASSERTIONS: Does the writer claim motivations or intentions without evidence? Flag specific sentences.
2. MISSING ANGLES: Is there an obvious analytical angle the writer missed? A key actor whose motivations aren't examined?
3. FACTUAL CONSISTENCY: Do the writer's claims match the facts provided in the story context?
4. HEDGING vs BOLDNESS: Is the writer being too cautious (saying nothing) or too bold (overclaiming)?
5. SPECIFICITY: Are there vague generalizations that should be grounded in specific evidence?

If the draft is GOOD ENOUGH — analytically sound, well-evidenced, insightful — respond with exactly:
APPROVED

If it needs revision, respond with:
REVISION NEEDED

[Your specific editorial feedback — be pointed and direct. Ask questions the writer must answer. Challenge weak reasoning. No more than 5 bullet points.]""".format(context=context, draft=current_draft)

        report.llm_calls += 1
        editor_response = llm_caller.call_by_id(editor_id,
            "You are a demanding editor. Only approve work that meets a high analytical standard. Be specific in your critique.",
            editor_prompt, 1500)

        if not editor_response:
            report.llm_failures += 1
            break

        report.llm_successes += 1
        rounds += 1

        if "APPROVED" in editor_response[:50]:
            print("      Editor approved (round {})".format(rounds))
            break

        # Editor wants revision
        print("      Editor requested revision (round {})".format(rounds))

        revision_prompt = """Your editor has reviewed your editorial and requested changes.

ORIGINAL STORY CONTEXT:
{context}

YOUR PREVIOUS DRAFT:
{draft}

EDITOR'S FEEDBACK:
{feedback}

Revise your editorial to address the editor's concerns. Maintain your analytical voice but strengthen the weak points identified. 400-600 words.""".format(
            context=context, draft=current_draft, feedback=editor_response)

        report.llm_calls += 1
        revised = llm_caller.call_by_id(writer_id,
            "You are revising your editorial based on editor feedback. Address every concern specifically.",
            revision_prompt, 3000)

        if not revised:
            report.llm_failures += 1
            break

        report.llm_successes += 1
        current_draft = revised

    return current_draft, rounds


