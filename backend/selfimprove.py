"""Self-improvement layer: versioning, duplicate detection, confidence, organisation.

Nothing here rewrites NEXUS instructions or production code. It curates the
knowledge store that the rest of the system reads:

* every stored record gets a version snapshot;
* near-duplicates are linked instead of silently duplicated;
* confidence is derived from source verification, corroboration and recency;
* records are labelled outdated when newer evidence supersedes them;
* topics are normalised and categorised for retrieval and dashboard charts.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .database import connect, now, event
from .textutil import keywords

CATEGORIES = {
    'programming': ('programming', 'python', 'javascript', 'typescript', 'java', 'c++', 'rust',
                    'go', 'php', 'sql', 'html', 'css', 'algorithm', 'software', 'code', 'database'),
    'ai': ('artificial intelligence', 'machine learning', 'neural', 'deep learning', 'llm',
           'transformer', 'model', 'agent', 'nlp', 'computer vision'),
    'cybersecurity': ('security', 'cryptography', 'vulnerability', 'malware', 'encryption',
                      'authentication', 'privacy', 'cyber', 'exploit', 'penetration'),
    'science': ('science', 'physics', 'astronomy', 'chemistry', 'biology', 'climate', 'space',
                'oceanography', 'geology', 'medicine', 'health'),
    'mathematics': ('mathematics', 'statistics', 'probability', 'algebra', 'calculus', 'geometry',
                    'number theory', 'optimization'),
    'webdev': ('web development', 'html', 'css', 'react', 'frontend', 'backend', 'http',
               'browser', 'accessibility', 'api'),
    'gamedev': ('game', 'unity', 'godot', 'rendering', 'graphics', 'shader', 'physics engine'),
    'robotics': ('robot', 'robotics', 'control system', 'sensor', 'actuator', 'autonomous vehicle'),
    'general': (),
}


def _words(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


def fingerprint(title, content):
    """Word bigrams from title + first 800 characters of content."""
    words = _words(f'{title} {content[:800]}')
    return {f'{words[i]} {words[i + 1]}' for i in range(len(words) - 1)} if len(words) > 1 else set(words)


def similarity(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def normalize_topic(topic):
    topic = re.sub(r'\s+', ' ', (topic or '').strip())
    topic = topic.replace(' · ', ': ').replace('·', ':')
    if topic.lower() in ('', 'web', 'general'):
        return 'general'
    return topic[:120]


def categorize(title, content, topic=''):
    haystack = f'{topic} {title} {content[:2000]}'.lower()
    scores = {}
    for category, words in CATEGORIES.items():
        if not words:
            continue
        scores[category] = sum(1 for word in words if word in haystack)
    if not scores:
        return 'general'
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'


def _verification_base(status):
    return {'corroborated': 0.86, 'single-source': 0.66, 'web-learned': 0.58,
            'user-reported': 0.72, 'local': 0.6, 'unverified': 0.38,
            'outdated': 0.25, 'disputed': 0.2}.get(status or 'unverified', 0.4)


def confidence_for(row):
    score = _verification_base(row.get('verification_status'))
    src = (row.get('source_url') or '').strip()
    if not src:
        score -= 0.1
    created = row.get('created_at') or now()
    try:
        stamp = datetime.fromisoformat(created)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - stamp).days
        if age_days > 365:
            score -= 0.12
        elif age_days < 7:
            score += 0.03
    except Exception:
        pass
    score += min(0.08, (row.get('confirmations') or 0) * 0.02)
    return round(max(0.05, min(0.97, score)), 3)


def snapshot(knowledge_id, change='created'):
    with connect() as db:
        row = db.execute('SELECT * FROM knowledge WHERE id=?', (knowledge_id,)).fetchone()
        if not row:
            return None
        version = db.execute('SELECT COALESCE(MAX(version),0)+1 v FROM knowledge_versions WHERE knowledge_id=?',
                             (knowledge_id,)).fetchone()['v']
        db.execute('INSERT INTO knowledge_versions(knowledge_id,version,title,content,source_url,topic,'
                   'confidence,verification_status,change,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (knowledge_id, version, row['title'], row['content'], row['source_url'], row['topic'],
                    row['confidence'], row['verification_status'], change, now()))
        db.execute('UPDATE knowledge SET version=? WHERE id=?', (version, knowledge_id))
        return version


def after_store(knowledge_id):
    """Curate a freshly stored record. Safe to call for every insert."""
    try:
        with connect() as db:
            row = dict(db.execute('SELECT * FROM knowledge WHERE id=?', (knowledge_id,)).fetchone())
        topic = normalize_topic(row.get('topic'))
        category = categorize(row.get('title'), row.get('content'), topic)
        status = row.get('verification_status') or 'unverified'
        if not (row.get('source_url') or '').strip() and status in ('unverified', 'web-learned', ''):
            status = 'user-reported'
        fp = fingerprint(row.get('title'), row.get('content'))
        duplicate_id = None
        best = 0.0
        with connect() as db:
            candidates = db.execute(
                'SELECT id,title,content,supersedes_id FROM knowledge WHERE id<>? AND '
                'COALESCE(topic,\'\')=? ORDER BY id DESC LIMIT 60', (knowledge_id, topic)).fetchall()
        for candidate in candidates:
            score = similarity(fp, fingerprint(candidate['title'], candidate['content']))
            if score > best:
                best, duplicate_id = score, candidate['id']
        linked = bool(duplicate_id and best >= 0.82)
        with connect() as db:
            db.execute('UPDATE knowledge SET topic=?,category=?,verification_status=? WHERE id=?',
                       (topic, category, status, knowledge_id))
            if linked:
                db.execute('UPDATE knowledge SET supersedes_id=? WHERE id=?', (duplicate_id, knowledge_id))
                db.execute("UPDATE knowledge SET verification_status='outdated' WHERE id=? AND "
                           "verification_status NOT IN ('corroborated','user-reported')", (duplicate_id,))
        if linked:
            # Keep this write on its own connection: event() must never be
            # called while the connection above still holds a write lock.
            event('knowledge', f'Duplicate detected ({best:.0%} overlap): #{knowledge_id} supersedes #{duplicate_id}.')
        snapshot(knowledge_id, 'created')
        recompute_confidence(knowledge_id)
        return {'duplicate_of': duplicate_id if best >= 0.82 else None,
                'similarity': round(best, 3), 'category': category, 'status': status}
    except Exception as exc:
        event('warning', f'Knowledge curation skipped for #{knowledge_id}: {exc}')
        return {'error': str(exc)}


def recompute_confidence(knowledge_id):
    with connect() as db:
        row = dict(db.execute('SELECT * FROM knowledge WHERE id=?', (knowledge_id,)).fetchone() or {})
        if not row:
            return None
        confirmations = db.execute('SELECT COUNT(*) n FROM knowledge_versions WHERE knowledge_id=?',
                                   (knowledge_id,)).fetchone()['n']
        score = confidence_for({**row, 'confirmations': max(0, confirmations - 1)})
        db.execute('UPDATE knowledge SET confidence=? WHERE id=?', (score, knowledge_id))
        return score


def organize(limit=400):
    """Normalise topics, categorise records and label stale/duplicate knowledge."""
    changed = 0
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT * FROM knowledge ORDER BY id DESC LIMIT ?', (max(1, min(limit, 2000)),)).fetchall()]
    for row in rows:
        topic = normalize_topic(row.get('topic'))
        category = categorize(row.get('title'), row.get('content'), topic)
        if topic != (row.get('topic') or '') or category != (row.get('category') or ''):
            with connect() as db:
                db.execute('UPDATE knowledge SET topic=?,category=? WHERE id=?', (topic, category, row['id']))
            changed += 1
    outdated = mark_outdated()
    superseded = mark_duplicates()
    event('knowledge', f'Organisation pass: {changed} normalised, {outdated} outdated, {superseded} duplicates linked.')
    return {'normalised': changed, 'outdated': outdated, 'duplicates_linked': superseded, 'scanned': len(rows)}


def mark_outdated(days=365):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect() as db:
        cur = db.execute(
            "UPDATE knowledge SET verification_status='outdated' "
            "WHERE created_at < ? AND verification_status IN ('single-source','web-learned','unverified') "
            "AND EXISTS (SELECT 1 FROM knowledge k2 WHERE k2.topic=knowledge.topic AND k2.id>knowledge.id)",
            (cutoff,))
        return cur.rowcount


def mark_duplicates(threshold=0.9, limit=300):
    """Link most recent near-duplicates without deleting evidence."""
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT id,title,content,topic FROM knowledge ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]
    linked = 0
    seen = []
    for row in rows:
        fp = fingerprint(row['title'], row['content'])
        for newer_id, newer_fp in seen:
            if similarity(fp, newer_fp) >= threshold:
                with connect() as db:
                    db.execute('UPDATE knowledge SET supersedes_id=? WHERE id=? AND supersedes_id IS NULL',
                               (newer_id, row['id']))
                linked += 1
                break
        seen.append((row['id'], fp))
    return linked


def stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM knowledge').fetchone()['n']
        cats = db.execute('SELECT category,COUNT(*) n FROM knowledge GROUP BY category ORDER BY n DESC').fetchall()
        status = db.execute('SELECT verification_status s,COUNT(*) n FROM knowledge GROUP BY s ORDER BY n DESC').fetchall()
        versions = db.execute('SELECT COUNT(*) n FROM knowledge_versions').fetchone()['n']
        superseded = db.execute('SELECT COUNT(*) n FROM knowledge WHERE supersedes_id IS NOT NULL').fetchone()['n']
        avg = db.execute('SELECT AVG(confidence) a FROM knowledge').fetchone()['a']
        duplicate_topics = db.execute(
            'SELECT topic,COUNT(*) n FROM knowledge WHERE topic IS NOT NULL AND topic<>\'\' '
            'GROUP BY topic HAVING n>1 ORDER BY n DESC LIMIT 10').fetchall()
    return {
        'total': total,
        'categories': [dict(r) for r in cats],
        'verification': [dict(r) for r in status],
        'versions': versions,
        'superseded': superseded,
        'avg_confidence': round(avg or 0, 3),
        'top_topics': [dict(r) for r in duplicate_topics],
    }


def versions(knowledge_id):
    with connect() as db:
        return [dict(r) for r in db.execute(
            'SELECT * FROM knowledge_versions WHERE knowledge_id=? ORDER BY version DESC',
            (knowledge_id,)).fetchall()]


def explain(knowledge_id):
    with connect() as db:
        row = db.execute('SELECT * FROM knowledge WHERE id=?', (knowledge_id,)).fetchone()
        if not row:
            return None
        versions_count = db.execute('SELECT COUNT(*) n FROM knowledge_versions WHERE knowledge_id=?',
                                    (knowledge_id,)).fetchone()['n']
        newer = db.execute('SELECT id,title FROM knowledge WHERE supersedes_id=? ORDER BY id DESC LIMIT 3',
                           (knowledge_id,)).fetchall()
    data = dict(row)
    data['category'] = data.get('category') or categorize(data.get('title'), data.get('content'), data.get('topic'))
    data['confidence_breakdown'] = {
        'verification': _verification_base(data.get('verification_status')),
        'has_source': bool((data.get('source_url') or '').strip()),
        'versions': versions_count,
        'computed': data.get('confidence'),
    }
    data['superseded_by'] = [dict(r) for r in newer]
    return data
