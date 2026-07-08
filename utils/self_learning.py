"""Self-learning engine for KB auto-enrichment (AgentForge-inspired).

Pipeline: Observer → Extractor → Generator
- Observer: logs user questions to Redis
- Extractor: clusters similar questions via Jaccard (threshold 0.7)
- Generator: proposes new KB articles for clusters ≥ 5 questions

This runs periodically (cron trigger or on-demand).
"""

import json
import logging
import time

import redis

from config import settings
from utils.jaccard_search import tokenize, jaccard

logger = logging.getLogger(__name__)

OBSERVER_KEY = "learn:questions"
CLUSTER_KEY = "learn:clusters"
MIN_CLUSTER_SIZE = 5
SIMILARITY_THRESHOLD = 0.7
MAX_OBSERVED = 1000


class Observer:
    """Records user questions for later clustering."""

    def __init__(self, r: redis.Redis):
        self.r = r

    def observe(self, agent: str, user_id: int, question: str):
        entry = json.dumps({
            'agent': agent,
            'user_id': user_id,
            'text': question,
            'tokens': tokenize(question),
            'ts': int(time.time()),
        })
        self.r.rpush(OBSERVER_KEY, entry)
        self.r.ltrim(OBSERVER_KEY, -MAX_OBSERVED, -1)

    def drain(self) -> list[dict]:
        """Get all observed questions and clear the buffer."""
        raw = self.r.lrange(OBSERVER_KEY, 0, -1)
        entries = [json.loads(m) for m in raw]
        self.r.delete(OBSERVER_KEY)
        return entries


class Extractor:
    """Clusters similar questions via Jaccard similarity."""

    def cluster(self, entries: list[dict]) -> list[dict]:
        """Group entries into clusters by question similarity."""
        clusters: list[list[dict]] = []

        for entry in entries:
            placed = False
            for cluster in clusters:
                # Compare with cluster centroid (first entry)
                centroid_tokens = cluster[0]['tokens']
                score = jaccard(entry['tokens'], centroid_tokens)
                if score >= SIMILARITY_THRESHOLD:
                    cluster.append(entry)
                    placed = True
                    break
            if not placed:
                clusters.append([entry])

        # Filter: only clusters with ≥ MIN_CLUSTER_SIZE
        result = []
        for cluster in clusters:
            if len(cluster) >= MIN_CLUSTER_SIZE:
                # Compute cluster keywords (most common tokens)
                all_tokens = []
                for e in cluster:
                    all_tokens.extend(e['tokens'])
                # Top keywords by frequency
                from collections import Counter
                freq = Counter(all_tokens)
                top_keywords = [t for t, c in freq.most_common(10) if c >= 2]

                result.append({
                    'size': len(cluster),
                    'keywords': top_keywords,
                    'agents': list(set(e['agent'] for e in cluster)),
                    'sample_questions': [e['text'] for e in cluster[:3]],
                    'avg_similarity': self._avg_similarity(cluster),
                })

        return result

    def _avg_similarity(self, cluster: list[dict]) -> float:
        if len(cluster) < 2:
            return 1.0
        scores = []
        for i in range(len(cluster)):
            for j in range(i + 1, min(i + 5, len(cluster))):
                s = jaccard(cluster[i]['tokens'], cluster[j]['tokens'])
                scores.append(s)
        return sum(scores) / len(scores) if scores else 0.0


class Generator:
    """Proposes KB articles from clusters (requires LLM for article generation)."""

    def __init__(self, r: redis.Redis, llm_client=None, kb_dir: str = ''):
        self.r = r
        self.llm = llm_client
        self.kb_dir = kb_dir or settings.kb_dir

    async def generate(self, clusters: list[dict]) -> list[dict]:
        """Generate KB article proposals from clusters."""
        proposals = []

        for cluster in clusters:
            # Check if similar KB article already exists
            if self._is_covered(cluster):
                logger.info(f"Cluster covered by existing KB: {cluster['keywords']}")
                continue

            if not self.llm:
                # Store cluster for manual review
                self._store_cluster(cluster)
                proposals.append({
                    'status': 'pending_review',
                    'keywords': cluster['keywords'],
                    'size': cluster['size'],
                    'sample_questions': cluster['sample_questions'],
                })
                continue

            # Generate KB article via LLM
            article = await self._generate_article(cluster)
            if article:
                proposals.append({
                    'status': 'generated',
                    'keywords': cluster['keywords'],
                    'size': cluster['size'],
                    'article': article,
                })

        return proposals

    def _is_covered(self, cluster: dict) -> bool:
        """Check if existing KB already covers this cluster."""
        # Load existing KB index keywords
        from knowledge_base import Retriever
        try:
            retriever = Retriever(settings.knowledge_index_path, '')
            results = retriever.retrieve(' '.join(cluster['keywords']), top_k=1)
            if results and results[0].score >= 0.3:
                return True
        except Exception:
            pass
        return False

    def _store_cluster(self, cluster: dict):
        """Store cluster info for manual review in Redis."""
        key = f"{CLUSTER_KEY}:{int(time.time())}"
        self.r.set(key, json.dumps(cluster), ex=86400 * 30)

    async def _generate_article(self, cluster: dict) -> str | None:
        """Use LLM to draft a KB article from cluster."""
        prompt = (
            f"Напиши статью для базы знаний туристического бота на основе частых вопросов.\n"
            f"Ключевые слова: {', '.join(cluster['keywords'])}\n"
            f"Агенты: {', '.join(cluster['agents'])}\n"
            f"Примеры вопросов:\n"
        )
        for q in cluster['sample_questions']:
            prompt += f"- {q}\n"
        prompt += (
            "\nФормат статьи:\n"
            "## Заголовок раздела\n"
            "- Ключевые факты (цены, сроки, правила)\n"
            "- Рекомендации\n\n"
            "Статья: 5-7 строк, по-русски, факты без выдумывания."
        )

        try:
            content = await self.llm.chat(
                [{'role': 'system', 'content': prompt}],
                temperature=0.3,
                max_tokens=512,
            )
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            logger.warning(f"KB article generation failed: {e}")
            return None


class SelfLearningEngine:
    """Full pipeline: Observer → Extractor → Generator."""

    def __init__(self, r: redis.Redis, llm_client=None):
        self.observer = Observer(r)
        self.extractor = Extractor()
        self.generator = Generator(r, llm_client)

    def observe(self, agent: str, user_id: int, question: str):
        self.observer.observe(agent, user_id, question)

    async def run_cycle(self) -> list[dict]:
        """Run one extraction cycle: drain → cluster → generate proposals."""
        entries = self.observer.drain()
        if not entries:
            return []
        logger.info(f"Self-learning: processing {len(entries)} observations")
        clusters = self.extractor.cluster(entries)
        logger.info(f"Self-learning: found {len(clusters)} clusters")
        proposals = await self.generator.generate(clusters)
        logger.info(f"Self-learning: generated {len(proposals)} proposals")
        return proposals
