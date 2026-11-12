import json
import math
from urllib.parse import urlparse

from .database import connect, now
from .llm import embed_both
from .textutil import lexical_score, clip


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _load_vector(raw, kind):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _vector_kind(row):
    # Old rows were written by nomic-embed-text through Ollama.
    return row.get('embedding_kind') or ('ollama' if row.get('embedding') else None)


def _semantic(qvectors, row):
    stored_kind = _vector_kind(row)
    if not stored_kind or stored_kind not in qvectors:
        return 0.0
    stored = _load_vector(row.get('embedding'), stored_kind)
    return cosine(qvectors[stored_kind], stored)


async def store_knowledge(title, content, url, topic, confidence, verification='unverified'):
    try:
        vectors = await embed_both(f'{title}\n{topic}\n{clip(content, 3000)}')
    except Exception:
        vectors = {}
    kind = 'ollama' if 'ollama' in vectors else ('local' if 'local' in vectors else None)
    vector = json.dumps(vectors[kind]) if kind else None
    domain = urlparse(url).netloc.lower() if url else ''
    with connect() as db:
        cur = db.execute(
            'INSERT INTO knowledge(title,content,source_url,topic,confidence,created_at,embedding,verification_status,source_domain,embedding_kind) '
            'VALUES(?,?,?,?,?,?,?,?,?,?)',
            (title, content, url, topic, confidence, now(), vector, verification, domain, kind))
        knowledge_id = cur.lastrowid
    # Curate: version snapshot, duplicate link, confidence, category.
    try:
        from . import selfimprove
        selfimprove.after_store(knowledge_id)
    except Exception:
        pass
    return knowledge_id


async def retrieve(query, limit=8):
    vectors = await embed_both(query)
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM knowledge ORDER BY id DESC LIMIT 2500').fetchall()]
    scored = []
    for row in rows:
        lexical = lexical_score(query, (row['title'] + ' ' + (row['topic'] or '') + ' ' + (row['content'] or ''))[:6000])
        semantic = _semantic(vectors, row)
        if semantic and lexical:
            score = semantic * 0.74 + min(lexical, 1.0) * 0.26
        elif semantic:
            score = semantic * 0.9
        else:
            score = lexical
        if score > 0.001:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{'score': round(s, 4), **row} for s, row in scored[:limit]]


async def save_experience(kind, content, importance=.5):
    try:
        vectors = await embed_both(content)
    except Exception:
        vectors = {}
    vector_kind = 'ollama' if 'ollama' in vectors else ('local' if 'local' in vectors else None)
    vector = json.dumps(vectors[vector_kind]) if vector_kind else None
    with connect() as db:
        db.execute('INSERT INTO memories(kind,content,importance,created_at,embedding,embedding_kind) VALUES(?,?,?,?,?,?)',
                   (kind, content, importance, now(), vector, vector_kind))


async def retrieve_experiences(query, limit=5):
    vectors = await embed_both(query)
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM memories ORDER BY id DESC LIMIT 800').fetchall()]
    ranked = []
    for row in rows:
        semantic = _semantic(vectors, row)
        lexical = lexical_score(query, row['content'])
        score = (semantic * 0.7 + min(lexical, 1) * 0.3) if semantic else lexical
        score += (row.get('importance') or 0) * 0.02
        if score > 0.001:
            ranked.append((score, row))
    return [row for _, row in sorted(ranked, key=lambda x: x[0], reverse=True)[:limit]]


def knowledge_stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM knowledge').fetchone()['n']
        repos = db.execute('SELECT COUNT(*) n FROM repos').fetchone()['n']
        chunks = db.execute('SELECT COUNT(*) n FROM repo_chunks').fetchone()['n']
        memories = db.execute('SELECT COUNT(*) n FROM memories').fetchone()['n']
    return {'knowledge': total, 'repos': repos, 'repo_chunks': chunks, 'memories': memories}
