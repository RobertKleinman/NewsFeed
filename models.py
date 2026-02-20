"""
Data models for the pipeline. Clean interfaces between steps.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class Article:
    """A single news article from an RSS feed."""
    title: str
    url: str
    source_name: str
    source_region: str
    source_bias: str
    summary: str = ""
    published: str = ""
    language: str = "en"
    # Set by triage
    topics: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    # Set by syndication detection
    wire_origin: Optional[str] = None  # e.g., "AP", "Reuters" or None
    is_independent: bool = True  # False if republished wire content

    def source_label(self):
        return "{} ({}, {})".format(self.source_name, self.source_region, self.source_bias)


@dataclass
class StoryCluster:
    """A group of articles about the same event."""
    articles: List[Article]
    cluster_id: str = ""
    lead_title: str = ""
    topic_spread: List[str] = field(default_factory=list)

    @property
    def size(self):
        return len(self.articles)

    @property
    def lead(self):
        return self.articles[0] if self.articles else None

    def source_names(self):
        return [a.source_name for a in self.articles]

    def unique_regions(self):
        return list(set(a.source_region.split("-")[0] for a in self.articles))


@dataclass
class RankedStory:
    """A story cluster with importance scoring from selection."""
    cluster: StoryCluster
    importance_score: float = 0.0  # 1-10 average from LLM voters
    vote_count: int = 0  # how many voters picked it
    importance_reason: str = ""
    depth_tier: str = "standard"  # brief, standard, deep

    @property
    def stars(self):
        """Convert 1-10 score to 1-5 stars."""
        if self.importance_score >= 8:
            return 5
        elif self.importance_score >= 6:
            return 4
        elif self.importance_score >= 4:
            return 3
        elif self.importance_score >= 2:
            return 2
        return 1


@dataclass
class Perspective:
    """A perspective identified from actual cluster sources."""
    label: str  # e.g., "Western security framing"
    angle: str  # what this source emphasizes
    sources: List[str] = field(default_factory=list)  # source names
    identified_by: str = ""


@dataclass
class SelectedSource:
    """A source chosen to represent a perspective."""
    article: Article
    perspective: str
    angle: str = ""


@dataclass
class ClaimSet:
    """Extracted claims from one source."""
    source_name: str
    source_region: str
    source_bias: str
    perspective: str
    headline: str
    url: str
    extracted_text: str
    hallucination_flags: List[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Output of cross-source comparison."""
    comparisons: Dict[str, str] = field(default_factory=dict)  # model -> text
    contention_level: str = "straight_news"  # straight_news or contested
    agreed_facts_summary: str = ""
    has_real_disputes: bool = False


@dataclass
class InvestigationResult:
    """Output of investigation step."""
    raw_text: str = ""
    story_impact: str = ""  # how this changes the story
    adds_value: bool = False  # whether investigation found anything new


@dataclass
class TopicCard:
    """The final card for one story — restructured around reader questions."""
    title: str = ""

    # WHY THIS MATTERS
    why_matters: str = ""  # 2-3 sentences: direct impact, world-shaping, cultural gravity

    # WHAT'S HAPPENING
    whats_happening: str = ""  # concrete situation right now

    # HOW IT'S BEING USED (only when contested)
    spin_positions: List[Dict] = field(default_factory=list)
    # Each: {"position": str, "who": str, "key_claim": str, "verified": str}
    spin_predictions: List[Dict] = field(default_factory=list)
    # Each: {"prediction": str, "confidence": "likely"|"speculative"}

    # WHAT YOU NEED TO KNOW
    key_facts: List[str] = field(default_factory=list)  # from coverage
    context: List[str] = field(default_factory=list)  # from research, labeled
    history: List[str] = field(default_factory=list)  # historical context
    unknowns: List[Dict] = field(default_factory=list)  # Q&A: {"q": str, "a": str}

    # BIGGER PICTURE
    bigger_picture: str = ""  # where this is heading, second/third order effects

    # WHAT YOU CAN DO (only when applicable)
    actions: List[str] = field(default_factory=list)

    # === Legacy fields (kept for backward compat during transition) ===
    what_happened: str = ""
    so_what: str = ""
    agreed_facts: List[str] = field(default_factory=list)
    disputes: List[Dict] = field(default_factory=list)
    framing: List[Dict] = field(default_factory=list)
    coverage_note: str = ""
    investigation_impact: str = ""
    key_unknowns: List[Dict] = field(default_factory=list)
    predictions: List[Dict] = field(default_factory=list)
    notable_details: List[str] = field(default_factory=list)

    # Metadata
    card_mode: str = "straight_news"  # straight_news or contested
    contested_reason: str = ""  # 1-sentence explanation of why contested
    depth_tier: str = "standard"  # brief, standard, deep
    importance: int = 3  # 1-5 stars
    importance_reason: str = ""
    topics: List[str] = field(default_factory=list)
    source_count: int = 0
    independent_count: int = 0  # sources with original reporting (not wire republishers)
    region_count: int = 0  # number of distinct geographic regions
    sources: List[Dict] = field(default_factory=list)
    missing_perspectives: List[str] = field(default_factory=list)
    comparisons: Dict[str, str] = field(default_factory=dict)
    investigation_raw: str = ""
    written_by: str = ""
    qa_warnings: List[str] = field(default_factory=list)  # from QA reviewer
    # Enrichment (computed, no LLM)
    political_balance: str = ""
    geo_diversity: int = 0
    coverage_depth: str = "thin"
    heat_score: int = 0

    def to_dict(self):
        """Convert to dict for JSON serialization and template rendering."""
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class StepReport:
    """Observability for each pipeline step."""
    step_name: str
    items_in: int = 0
    items_out: int = 0
    llm_calls: int = 0
    llm_successes: int = 0
    llm_failures: int = 0
    notes: List[str] = field(default_factory=list)

    def summary(self):
        success_rate = ""
        if self.llm_calls > 0:
            pct = int(100 * self.llm_successes / self.llm_calls)
            success_rate = " ({}% success)".format(pct)
        return "{}: {} in -> {} out | {} LLM calls{}{}".format(
            self.step_name, self.items_in, self.items_out,
            self.llm_calls, success_rate,
            " | " + "; ".join(self.notes) if self.notes else "")
