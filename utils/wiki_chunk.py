"""WikiChunk data model — precomputed keyword index for Jaccard search."""

from dataclasses import dataclass, field


@dataclass
class WikiChunk:
    id: str
    title: str
    source_path: str
    section: str
    text: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class RetrievedChunk:
    chunk: WikiChunk
    score: float
