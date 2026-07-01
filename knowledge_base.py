"""Retriever: loads precomputed chunk index, provides retrieve() and format_context()."""

from utils.jaccard_search import load_chunks, retrieve, format_context
from utils.wiki_chunk import WikiChunk, RetrievedChunk


class Retriever:
    def __init__(self, index_path: str, base_url: str = ''):
        self.chunks: list[WikiChunk] = load_chunks(index_path)
        self.base_url = base_url

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        return retrieve(self.chunks, query, top_k)

    def format_context(self, entries: list[RetrievedChunk]) -> str:
        return format_context(entries, self.base_url)
