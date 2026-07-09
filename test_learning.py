#!/usr/bin/env python3
"""Test self-learning with threshold=0.3 and min_cluster=3."""
import asyncio
import redis
import json
from utils.self_learning import SelfLearningEngine, Observer, Extractor, Generator
from utils.llm import LLMClient

r = redis.Redis(host='redis', port=6379, decode_responses=True)

# Add diverse questions about wellness/spa (not in existing KB)
obs = Observer(r=r)
questions = [
    'wellness и спа туры цены',
    'спа тур для женщин стоимость',
    'wellness программа в отеле',
    'хочу wellness тур с массажем',
    'туры с йогой и медитацией',
    'wellness отдых на море цены',
    'спа и wellness тур куда поехать',
    'экологичный тур что это',
    'eco туризм destinations',
    'зеленый тур для семьи',
    'устойчивый туризм варианты',
    'eco tour куда поехать',
]
for i, q in enumerate(questions):
    obs.observe('consultant', 5000+i, q)

# Drain and cluster
entries = obs.drain()
print(f'Drained: {len(entries)} entries')

ext = Extractor()
clusters = ext.cluster(entries)
print(f'\n=== Found {len(clusters)} clusters ===')
for c in clusters:
    print(f'  size={c["size"]}, keywords={c["keywords"]}, avg_sim={c["avg_similarity"]:.2f}')
    for q in c['sample_questions']:
        print(f'    - "{q}"')

# Check coverage
gen = Generator(r=r, llm_client=None)
for c in clusters:
    covered = gen._is_covered(c)
    print(f'  Covered by existing KB: {covered}')

# Generate articles (if not covered)
if clusters:
    llm = LLMClient()
    gen_with_llm = Generator(r=r, llm_client=llm)
    
    async def run_gen():
        proposals = await gen_with_llm.generate(clusters)
        print(f'\n=== Generated {len(proposals)} proposals ===')
        for p in proposals:
            print(f'  Status: {p["status"]}')
            print(f'  Keywords: {p["keywords"]}')
            if 'article' in p:
                print(f'  Article:')
                print(f'    {p["article"][:300]}')
                # Show full article if available
                if len(p["article"]) > 300:
                    print(f'    ...({len(p["article"])} chars total)')
            if 'sample_questions' in p:
                for q in p['sample_questions']:
                    print(f'    Q: "{q}"')
    
    asyncio.run(run_gen())
