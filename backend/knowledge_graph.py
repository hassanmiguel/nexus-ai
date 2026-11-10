"""Knowledge graph projection built from real SQLite knowledge records.

The graph is deterministic: every node maps to a stored knowledge item, a topic
that appears in the database, a source domain, or a concept keyword extracted
from a stored title. Nothing is generated or randomised for display.
"""
from __future__ import annotations

from urllib.parse import urlparse

from .database import connect, now
from .textutil import keywords

MAX_NODES = 700


def _clip(value, size):
    value = str(value or '')
    return value if len(value) <= size else value[:size - 1].rstrip() + '…'


def build_graph(limit: int = 160, topic: str = '', verification: str = '') -> dict:
    limit = max(20, min(int(limit or 160), 400))
    where = []
    params = []
    if topic:
        where.append('topic=?')
        params.append(topic)
    if verification:
        where.append('verification_status=?')
        params.append(verification)
    sql = ('SELECT id,title,topic,source_url,source_domain,verification_status,confidence,created_at '
           'FROM knowledge')
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    with connect() as db:
        rows = [dict(r) for r in db.execute(sql, params).fetchall()]

    nodes = {}
    edges = {}
    topic_concepts = {}

    def add_node(node_id, label, kind, **extra):
        if node_id in nodes or len(nodes) >= MAX_NODES:
            return
        nodes[node_id] = {'id': node_id, 'label': _clip(label, 46), 'type': kind, **extra}

    def add_edge(source, target, relation, weight=1.0):
        if source not in nodes or target not in nodes or source == target:
            return
        key = (source, target, relation)
        if key not in edges:
            edges[key] = {'source': source, 'target': target, 'relation': relation, 'weight': round(weight, 3)}

    for row in rows:
        kid = f"k:{row['id']}"
        row_topic = (row.get('topic') or 'uncategorized').strip() or 'uncategorized'
        confidence = float(row.get('confidence') or 0.5)
        add_node(kid, row.get('title') or f"Knowledge {row['id']}", 'knowledge',
                 topic=row_topic, verification=row.get('verification_status') or 'unverified',
                 source_url=row.get('source_url') or '', created_at=row.get('created_at') or '',
                 value=row['id'], size=round(5 + confidence * 7, 2))
        topic_id = 't:' + row_topic
        add_node(topic_id, row_topic, 'topic', size=8)
        add_edge(kid, topic_id, 'in_topic', 1.0)
        domain = (row.get('source_domain') or '').strip().lower()
        if not domain and row.get('source_url'):
            domain = (urlparse(row['source_url']).hostname or '').lower()
        if domain:
            host_id = 'd:' + domain
            add_node(host_id, domain, 'source', size=7)
            add_edge(kid, host_id, 'from_source', 1.0)
        for concept in keywords(row.get('title') or '', 3):
            cid = 'c:' + concept
            add_node(cid, concept, 'concept', size=6)
            add_edge(kid, cid, 'mentions', 0.7)
            topic_concepts.setdefault(row_topic, set()).add(concept)

    # Topic-to-topic relationships from shared title concepts (real co-occurrence).
    topics = sorted(topic_concepts)
    for i, left in enumerate(topics):
        for right in topics[i + 1:]:
            shared = topic_concepts[left] & topic_concepts[right]
            if len(shared) >= 2:
                lid, rid = 't:' + left, 't:' + right
                if lid in nodes and rid in nodes:
                    add_edge(lid, rid, 'related', len(shared) / 6.0)

    counts = {'knowledge': 0, 'topic': 0, 'source': 0, 'concept': 0}
    for node in nodes.values():
        counts[node['type']] = counts.get(node['type'], 0) + 1
    verified = sum(1 for row in rows
                   if (row.get('verification_status') or '') in ('corroborated', 'verified'))
    topic_counts = {}
    for row in rows:
        key = (row.get('topic') or 'uncategorized').strip() or 'uncategorized'
        topic_counts[key] = topic_counts.get(key, 0) + 1
    return {
        'nodes': list(nodes.values()),
        'edges': list(edges.values()),
        'stats': {
            'records': len(rows), 'nodes': len(nodes), 'edges': len(edges),
            'verified': verified, 'counts': counts,
            'topics': sorted(({'topic': k, 'count': v} for k, v in topic_counts.items()),
                             key=lambda x: x['count'], reverse=True),
        },
        'generated_at': now(),
    }


def knowledge_history(q: str = '', topic: str = '', verification: str = '', source: str = '',
                      status: str = '', limit: int = 200, offset: int = 0) -> dict:
    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))
    where = []
    params = []
    if q:
        where.append('(title LIKE ? OR content LIKE ? OR source_url LIKE ? OR topic LIKE ?)')
        like = f'%{q}%'
        params.extend([like, like, like, like])
    if topic:
        where.append('topic=?')
        params.append(topic)
    if verification:
        where.append('verification_status=?')
        params.append(verification)
    if source:
        where.append('(source_domain LIKE ? OR source_url LIKE ?)')
        params.extend([f'%{source}%', f'%{source}%'])
    if status == 'learned':
        where.append("source_url IS NOT NULL AND source_url<>''")
    elif status == 'user':
        where.append("(verification_status='user-reported' OR source_url LIKE 'user:%')")
    elif status == 'local':
        where.append("(source_url IS NULL OR source_url='')")
    else:
        status = ''
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM knowledge' + clause, params).fetchone()['n']
        rows = [dict(r) for r in db.execute(
            'SELECT id,title,content,source_url,source_domain,topic,confidence,verification_status,'
            'session_id,created_at FROM knowledge' + clause + ' ORDER BY id DESC LIMIT ? OFFSET ?',
            params + [limit, offset]).fetchall()]
        topics = [r['topic'] for r in db.execute(
            "SELECT DISTINCT topic FROM knowledge WHERE topic IS NOT NULL AND topic<>'' ORDER BY topic").fetchall()]
        verifications = [r['verification_status'] for r in db.execute(
            "SELECT DISTINCT verification_status FROM knowledge WHERE verification_status IS NOT NULL "
            "ORDER BY verification_status").fetchall()]
    return {'items': rows, 'total': total, 'limit': limit, 'offset': offset,
            'has_more': offset + len(rows) < total,
            'topics': topics, 'verifications': verifications, 'status': status}
