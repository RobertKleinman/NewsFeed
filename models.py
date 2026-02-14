"""
Data models shared across the pipeline.
These are the contracts between modules. Change with care and update ARCHITECTURE.md.
"""

from dataclasses import dataclass, field
import hashlib


@dataclass
class Article:
    """A single article from an RSS feed."""
    title: str
    url: str
    source_name: str
    source_region: str
    source_bias: str
    summary: str = ""
    published: str = ""
    topics: list = field(default_factory=list)
    importance_score: float = 0.0

    def uid(self):
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def source_label(self):
        return "{} ({}, {})".format(self.source_name, self.source_region, self.source_bias)


@dataclass
class StepReport:
    """Metadata from a pipeline step for the run report."""
    step_name: str
    items_in: int = 0
    items_out: int = 0
    llm_calls: int = 0
    llm_successes: int = 0
    llm_failures: int = 0
    notes: list = field(default_factory=list)

    def summary(self):
        return "{}: {} in -> {} out | LLM: {}/{} ok".format(
            self.step_name, self.items_in, self.items_out,
            self.llm_successes, self.llm_calls)
