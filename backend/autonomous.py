"""Autonomous web-learning engine.

NEXUS discovers its own topics, searches public sources, learns pages through the
same robots.txt/allow-list-gated pipeline used by URL Learn, verifies source
diversity, and stores everything in SQLite.

Safety model:
- internet permission must be enabled;
- only public HTTPS URLs inside the allow-list are fetched (delegated to
  ``research.allowed_domain`` / ``web_learn``);
- robots.txt is enforced by ``research.fetch_page``;
- one fetch at a time with the configured politeness delay;
- page text is treated as evidence, never as instructions.
"""
from __future__ import annotations

import asyncio
import random
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx

from .config import USER_AGENT
from .database import connect, event, now, read_bool, read_int, setting, set_setting
from .providers import generate
from .research import allowlist, allowed_domain, search_web
from . import web_learn

CURATED_TOPICS = [
    'Python programming language',
    'history of the internet',
    'machine learning fundamentals',
    'retrieval-augmented generation',
    'large language models',
    'SQLite database internals',
    'HTTP protocol and REST APIs',
    'computer networking basics',
    'cybersecurity fundamentals',
    'cryptography basics',
    'world history timeline',
    'human biology overview',
    'climate science basics',
    'astronomy solar system',
    'mathematics linear algebra',
    'statistics and probability',
    'philosophy of science',
    'economics supply and demand',
    'psychology of learning',
    'linguistics and language',
    'open-source software governance',
    'web accessibility guidelines',
    'version control with git',
    'operating systems overview',
    'data structures and algorithms',
    'public health fundamentals',
    'renewable energy technologies',
    'oceanography overview',
]

SPEED_PRESETS = {
    'slow': {'delay': 8, 'interval': 300, 'labels': 'Slow · 8s between pages'},
    'normal': {'delay': 3, 'interval': 120, 'labels': 'Normal · 3s between pages'},
    'fast': {'delay': 1, 'interval': 45, 'labels': 'Fast · 1s between pages'},
}

STATE = {
    'running': False,
    'paused': False,
    'phase': 'idle',
    'topic': '',
    'current_url': '',
    'session_id': None,
    'mode': 'topic',
    'requested_topic': '',
    'last_error': '',
    'worker': None,
}


# --------------------------------------------------------------------------- #
# Topics
# --------------------------------------------------------------------------- #
def _clean_topic(topic: str) -> str:
    topic = re.sub(r'\s+', ' ', str(topic or '')).strip().strip('"\'')
    return topic[:140]


def add_topic(topic, source='user', priority=8, status='pending'):
    topic = _clean_topic(topic)
    if len(topic) < 3:
        raise ValueError('A learning topic needs at least 3 characters.')
    with connect() as db:
        db.execute(
            'INSERT INTO learning_topics(topic,status,priority,source,created_at,updated_at) '
            'VALUES(?,?,?,?,?,?) ON CONFLICT(topic) DO UPDATE SET status=excluded.status,'
            'priority=excluded.priority,updated_at=excluded.updated_at',
            (topic, status, int(priority), source, now(), now()))
    return list_topics()


def remove_topic(topic_id):
    with connect() as db:
        db.execute('DELETE FROM learning_topics WHERE id=?', (topic_id,))
    return list_topics()


def list_topics():
    with connect() as db:
        return [dict(r) for r in db.execute(
            'SELECT * FROM learning_topics ORDER BY CASE status WHEN \'pending\' THEN 0 '
            'WHEN \'learning\' THEN 1 ELSE 2 END, priority DESC, id LIMIT 300').fetchall()]


def _seed_topics():
    with connect() as db:
        count = db.execute('SELECT COUNT(*) n FROM learning_topics').fetchone()['n']
    if count:
        return 0
    with connect() as db:
        for index, topic in enumerate(CURATED_TOPICS[:12]):
            db.execute(
                'INSERT OR IGNORE INTO learning_topics(topic,status,priority,source,created_at,updated_at) '
                'VALUES(?,?,?,?,?,?)', (topic, 'pending', 6 if index < 6 else 4, 'curated', now(), now()))
    return 12


def sync_setting_topics():
    raw = setting('learning_topics', '') or ''
    with connect() as db:
        for part in raw.split(','):
            topic = _clean_topic(part)
            if len(topic) >= 3:
                db.execute(
                    'INSERT OR IGNORE INTO learning_topics(topic,status,priority,source,created_at,updated_at) '
                    'VALUES(?,?,?,?,?,?)', (topic, 'pending', 7, 'settings', now(), now()))
    return len(list_topics())


async def discover_topics(count=3):
    """Ask the active provider for a new topic and add it to the queue."""
    with connect() as db:
        recent = db.execute('SELECT topic,title FROM knowledge ORDER BY id DESC LIMIT 24').fetchall()
        known = '\n'.join(f"{r['topic']}: {r['title']}" for r in recent)
        queued = [r['topic'] for r in db.execute('SELECT topic FROM learning_topics LIMIT 40').fetchall()]
    created = []
    for index in range(max(1, min(int(count), 6))):
        prompt = (
            'Create ONE novel, useful web-learning topic to expand this knowledge, prioritizing gaps '
            'and avoiding repetition. Return only the topic under 14 words. Existing knowledge:\n'
            f"{known or 'No prior knowledge.'}\nQueued topics:\n{', '.join(queued) or 'None.'}"
        )
        try:
            topic = _clean_topic(await generate(prompt))
        except Exception:
            topic = ''
        if len(topic) < 3 or topic.lower() in {q.lower() for q in queued}:
            topic = CURATED_TOPICS[(len(known) + index) % len(CURATED_TOPICS)]
        add_topic(topic, source='auto', priority=5)
        created.append(topic)
    return created


async def _pick_topic(mode):
    _seed_topics()
    sync_setting_topics()
    # Retry cooldown: a pending topic that just failed waits before another try.
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM learning_topics WHERE status='pending' "
            "AND (attempts=0 OR updated_at<?) ORDER BY priority DESC, id LIMIT 1", (cutoff,)).fetchone()
    if row:
        with connect() as db:
            db.execute("UPDATE learning_topics SET status='learning',updated_at=?,attempts=attempts+1 WHERE id=?",
                       (now(), row['id']))
        return row['topic']
    if mode == 'random' or read_bool('learning_random', True):
        with connect() as db:
            existing = {r['topic'].lower(): dict(r) for r in
                        db.execute('SELECT * FROM learning_topics').fetchall()}
        # Never reset a learned or in-progress curated topic just to learn it
        # again; that caused an endless failure loop on an offline machine.
        candidates = []
        for topic in CURATED_TOPICS:
            item = existing.get(topic.lower())
            if item is None:
                candidates.append(topic)
            elif (item['status'] == 'failed' and int(item['attempts'] or 0) < 3
                  and (item['updated_at'] or '') < cutoff):
                candidates.append(topic)
        if not candidates:
            return None
        topic = random.choice(candidates)
        add_topic(topic, source='random', priority=5)
        return topic
    created = await discover_topics(1)
    return created[0] if created else None


def _mark_topic_failure(topic, detail=''):
    """Record a failed session and stop retrying a topic after three tries."""
    with connect() as db:
        row = db.execute('SELECT id,attempts FROM learning_topics WHERE topic=?', (topic,)).fetchone()
        if not row:
            return
        attempts = int(row['attempts'] or 0)
        status = 'failed' if attempts >= 3 else 'pending'
        db.execute('UPDATE learning_topics SET status=?,detail=?,updated_at=? WHERE id=?',
                   (status, str(detail)[:500], now(), row['id']))
    event('learning', f'Learning topic “{topic}” marked {status} after {attempts} attempt(s).')


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
async def _wiki_search(topic):
    if not allowed_domain('https://en.wikipedia.org/'):
        return []
    query = urllib.parse.quote_plus(topic)
    url = ('https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=8&srsearch=' + query)
    try:
        async with httpx.AsyncClient(timeout=20, headers={'User-Agent': USER_AGENT}) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        event('warning', f'Wikipedia discovery failed for “{topic}”: {exc}')
        return []
    out = []
    for item in (data.get('query') or {}).get('search') or []:
        title = item.get('title') or ''
        if not title:
            continue
        page = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'))
        out.append({'url': page, 'title': title, 'snippet': re.sub(r'<[^>]+>', '', item.get('snippet') or '')})
    return out


async def _candidates(topic, limit=12):
    results = []
    try:
        results.extend(await search_web(topic, limit=limit))
    except Exception as exc:
        event('warning', f'Web search unavailable for “{topic}”: {exc}')
    results.extend(await _wiki_search(topic))
    with connect() as db:
        visited = {r['url'] for r in db.execute("SELECT url FROM visits WHERE status LIKE 'analyzed%'").fetchall()}
        ready = {r['url'] for r in db.execute("SELECT url FROM web_sources WHERE status='ready'").fetchall()}
    out = []
    seen = set()
    domains = {}
    for item in results:
        url = (item or {}).get('url') or ''
        if not url or url in seen or url in visited or url in ready:
            continue
        if not allowed_domain(url):
            continue
        domain = urllib.parse.urlparse(url).hostname or ''
        if domains.get(domain, 0) >= 2:
            continue
        seen.add(url)
        domains[domain] = domains.get(domain, 0) + 1
        out.append({'url': url, 'title': item.get('title') or '', 'snippet': item.get('snippet') or ''})
    return out[:limit]


# --------------------------------------------------------------------------- #
# Learning + verification
# --------------------------------------------------------------------------- #
def _create_session(topic, mode):
    with connect() as db:
        cur = db.execute(
            'INSERT INTO learning_sessions(topic,mode,status,started_at,updated_at) VALUES(?,?,?,?,?)',
            (topic, mode, 'running', now(), now()))
        session_id = cur.lastrowid
    event('learning', f'Autonomous learning session #{session_id} started · {topic} ({mode}).')
    return session_id


def _update_session(session_id, **fields):
    if not fields or not session_id:
        return
    allowed = {'status', 'pages_visited', 'pages_learned', 'knowledge_added', 'errors', 'detail'}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    assignments = ', '.join(f'{k}=?' for k in fields)
    with connect() as db:
        db.execute(f'UPDATE learning_sessions SET {assignments},updated_at=? WHERE id=?',
                   (*fields.values(), now(), session_id))


def _finish_session(session_id, status, detail=''):
    if not session_id:
        return
    with connect() as db:
        db.execute('UPDATE learning_sessions SET status=?,detail=?,updated_at=?,finished_at=? WHERE id=?',
                   (status, (detail or '')[:800], now(), now(), session_id))


def _verify_topic(topic):
    """Mark knowledge as corroborated when independent source domains agree.

    This is source-diversity verification, not semantic fact checking; the UI
    labels it explicitly so it is never presented as more than it is.
    """
    if not read_bool('learning_auto_verify', True):
        return {'status': 'skipped', 'domains': 0}
    minimum = max(2, read_int('verification_sources', 2))
    with connect() as db:
        rows = db.execute(
            "SELECT COALESCE(NULLIF(source_domain,''),'') domain, COUNT(*) n FROM knowledge "
            "WHERE topic=? AND source_url IS NOT NULL AND source_url<>'' GROUP BY domain", (topic,)).fetchall()
        domains = [r['domain'] for r in rows if r['domain']]
        status = 'corroborated' if len(domains) >= minimum else 'single-source'
        db.execute(
            "UPDATE knowledge SET verification_status=? WHERE topic=? AND source_url IS NOT NULL "
            "AND source_url<>'' AND verification_status IN ('unverified','web-learned','single-source')",
            (status, topic))
    event('verification', f'Topic “{topic}”: {len(domains)} independent domain(s) → {status}.')
    return {'status': status, 'domains': len(domains)}


async def _learn_one(session_id, topic, candidate):
    STATE['phase'] = 'fetching'
    STATE['current_url'] = candidate['url']
    try:
        result = await web_learn.learn_page_now(candidate['url'], title=candidate.get('title'), topic=topic,
                                                depth=0, pace=_speed()['delay'])
    except Exception as exc:
        with connect() as db:
            db.execute('INSERT OR IGNORE INTO visits(url,title,visited_at,status) VALUES(?,?,?,?)',
                       (candidate['url'], candidate.get('title') or '', now(), f'skipped: {str(exc)[:180]}'))
        raise
    with connect() as db:
        db.execute('UPDATE web_sources SET session_id=? WHERE url=?', (session_id, candidate['url']))
        db.execute('UPDATE knowledge SET session_id=? WHERE source_url=?', (session_id, candidate['url']))
        db.execute('INSERT OR IGNORE INTO visits(url,title,visited_at,status) VALUES(?,?,?,?)',
                   (candidate['url'], result.get('title') or candidate.get('title') or '', now(), 'analyzed'))
        db.execute("UPDATE visits SET status='analyzed',title=? WHERE url=?",
                   (result.get('title') or candidate.get('title') or '', candidate['url']))
    event('discovery', f'Learned “{result.get("title") or candidate["url"]}” for topic {topic}.')
    return result


async def _run_session(session_id, topic, mode):
    pages_limit = max(1, min(read_int('learning_pages_per_session', 5), 20))
    candidates = await _candidates(topic, limit=max(pages_limit * 2, 10))
    if not candidates:
        restrictions = allowlist()
        hint = (f' The domain allowlist is restricted to: {", ".join(restrictions)}.' if restrictions else '')
        raise RuntimeError('No new eligible public pages were found for this topic.' + hint)
    STATE['phase'] = 'discovering'
    visited = learned = errors = 0
    queue = list(candidates)
    while queue and learned < pages_limit:
        if not STATE['running']:
            break
        if STATE['paused']:
            await asyncio.sleep(1)
            continue
        candidate = queue.pop(0)
        visited += 1
        try:
            result = await _learn_one(session_id, topic, candidate)
            learned += 1
            # Follow at most one same-site link per learned page, if budget remains.
            if learned < pages_limit:
                links = result.get('links') or []
                followed = web_learn.same_site_links(candidate['url'], links)[:2]
                known = {c['url'] for c in queue}
                for link in followed:
                    if learned + len(queue) >= pages_limit + 2:
                        break
                    if link not in known and allowed_domain(link):
                        queue.append({'url': link, 'title': '', 'snippet': ''})
                        known.add(link)
        except Exception as exc:
            errors += 1
            STATE['last_error'] = str(exc)[:300]
            event('warning', f'Autonomous learning skipped {candidate["url"]}: {exc}')
        with connect() as db:
            knowledge_added = db.execute(
                'SELECT COUNT(*) n FROM knowledge WHERE session_id=?', (session_id,)).fetchone()['n']
        _update_session(session_id, pages_visited=visited, pages_learned=learned,
                        knowledge_added=knowledge_added, errors=errors)
    _update_session(session_id, pages_visited=visited, pages_learned=learned, errors=errors)
    if not learned:
        raise RuntimeError(f'All {visited} discovered page(s) were skipped or failed.')
    if read_bool('learning_auto_verify', True):
        _verify_topic(topic)
    with connect() as db:
        db.execute("UPDATE learning_topics SET status='learned',last_learned_at=?,updated_at=? WHERE topic=?",
                   (now(), now(), topic))
        knowledge_added = db.execute(
            'SELECT COUNT(*) n FROM knowledge WHERE session_id=?', (session_id,)).fetchone()['n']
    return {'pages_visited': visited, 'pages_learned': learned,
            'knowledge_added': knowledge_added, 'errors': errors}


def _speed():
    name = (setting('learning_speed', 'normal') or 'normal').lower()
    preset = SPEED_PRESETS.get(name, SPEED_PRESETS['normal'])
    interval = read_int('learning_session_interval_seconds', preset['interval'])
    return {'name': name if name in SPEED_PRESETS else 'normal', **preset,
            'interval': max(30, int(interval))}


# --------------------------------------------------------------------------- #
# Worker lifecycle
# --------------------------------------------------------------------------- #
async def _loop(mode):
    try:
        while STATE['running']:
            if STATE['paused']:
                await asyncio.sleep(1)
                continue
            topic = STATE['requested_topic'] or await _pick_topic(mode)
            STATE['requested_topic'] = ''
            if not topic:
                await asyncio.sleep(max(60, _speed()['interval']))
                continue
            topic = _clean_topic(topic)
            STATE.update(topic=topic, mode=mode, phase='discovering', current_url='', last_error='')
            session_id = _create_session(topic, mode)
            STATE['session_id'] = session_id
            try:
                await _run_session(session_id, topic, mode)
                _finish_session(session_id, 'completed')
                event('learning', f'Autonomous learning session #{session_id} completed · {topic}.')
            except asyncio.CancelledError:
                _finish_session(session_id, 'stopped', 'Stopped by user.')
                raise
            except Exception as exc:
                STATE['last_error'] = str(exc)[:400]
                _finish_session(session_id, 'failed', str(exc)[:600])
                _mark_topic_failure(topic, str(exc))
                event('warning', f'Autonomous learning session #{session_id} failed: {exc}')
            finally:
                STATE.update(session_id=None, current_url='', phase='idle')
            if mode == 'once':
                break
            delay = _speed()['interval']
            for _ in range(max(1, int(delay))):
                if not STATE['running']:
                    break
                await asyncio.sleep(1)
    finally:
        STATE.update(running=False, paused=False, worker=None, session_id=None,
                     current_url='', phase='idle')


async def start(topic=None, mode='topic'):
    if not read_bool('permission_internet'):
        raise PermissionError('Internet permission is off. Enable it in Permissions before autonomous learning.')
    mode = mode if mode in ('topic', 'random', 'once') else 'topic'
    if topic:
        add_topic(topic, source='user', priority=10)
        STATE['requested_topic'] = _clean_topic(topic)
    set_setting('learning_enabled', 'true')
    if STATE['running']:
        if STATE['paused']:
            STATE['paused'] = False
            event('learning', 'Autonomous learning resumed.')
        if topic:
            STATE['requested_topic'] = _clean_topic(topic)
        return status()
    STATE.update(running=True, paused=False, mode=mode, last_error='')
    STATE['worker'] = asyncio.create_task(_loop(mode))
    event('learning', f'Autonomous learning started in {mode} mode.')
    return status()


async def pause():
    if STATE['running']:
        STATE['paused'] = True
        STATE['phase'] = 'paused'
        if STATE['session_id']:
            _update_session(STATE['session_id'], status='paused')
        event('learning', 'Autonomous learning paused after the current page.')
    return status()


async def resume():
    if not STATE['running']:
        return await start()
    STATE['paused'] = False
    STATE['phase'] = 'discovering'
    if STATE['session_id']:
        _update_session(STATE['session_id'], status='running')
    event('learning', 'Autonomous learning resumed.')
    return status()


async def stop():
    STATE['running'] = False
    STATE['paused'] = False
    session_id = STATE.get('session_id')
    worker = STATE.get('worker')
    STATE['worker'] = None
    if worker and not worker.done():
        worker.cancel()
        try:
            await worker
        except (asyncio.CancelledError, Exception):
            pass
    if session_id:
        _finish_session(session_id, 'stopped', 'Stopped by user.')
    STATE.update(session_id=None, current_url='', phase='idle')
    set_setting('learning_enabled', 'false')
    event('learning', 'Autonomous learning stopped.')
    return status()


async def random_explore():
    if not read_bool('permission_internet'):
        raise PermissionError('Internet permission is off. Enable it in Permissions before autonomous learning.')
    topic = random.choice(CURATED_TOPICS)
    add_topic(topic, source='random', priority=9)
    return await start(topic=topic, mode='random')


def mark_interrupted_sessions():
    with connect() as db:
        cur = db.execute(
            "UPDATE learning_sessions SET status='interrupted',updated_at=?,finished_at=?,"
            "detail=CASE WHEN detail='' THEN 'Application stopped during this session.' ELSE detail END "
            "WHERE status IN ('running','paused')", (now(), now()))
        db.execute("UPDATE learning_topics SET status='pending' WHERE status='learning'")
        return cur.rowcount


async def maybe_resume():
    if not read_bool('learning_resume', True):
        return None
    if (setting('learning_enabled', 'false') or '').lower() != 'true':
        return None
    if not read_bool('permission_internet'):
        return None
    with connect() as db:
        row = db.execute("SELECT topic FROM learning_sessions WHERE status='interrupted' "
                         "ORDER BY id DESC LIMIT 1").fetchone()
    try:
        return await start(topic=row['topic'] if row else None, mode='topic')
    except Exception as exc:
        event('warning', f'Could not resume autonomous learning: {exc}')
        return None


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def stats():
    with connect() as db:
        session_rows = db.execute('SELECT status,COUNT(*) n FROM learning_sessions GROUP BY status').fetchall()
        sessions = {r['status']: r['n'] for r in session_rows}
        pages_learned = db.execute('SELECT COALESCE(SUM(pages_learned),0) n FROM learning_sessions').fetchone()['n']
        knowledge_auto = db.execute('SELECT COUNT(*) n FROM knowledge WHERE session_id IS NOT NULL').fetchone()['n']
        sources = db.execute('SELECT COUNT(*) n FROM web_sources').fetchone()['n']
        ready = db.execute("SELECT COUNT(*) n FROM web_sources WHERE status='ready'").fetchone()['n']
        failed = db.execute("SELECT COUNT(*) n FROM web_sources WHERE status='failed'").fetchone()['n']
        domains = db.execute("SELECT COUNT(DISTINCT source_domain) n FROM knowledge "
                             "WHERE source_domain IS NOT NULL AND source_domain<>''").fetchone()['n']
        topics = db.execute("SELECT COUNT(DISTINCT topic) n FROM knowledge "
                            "WHERE topic IS NOT NULL AND topic<>''").fetchone()['n']
        topic_counts = db.execute("SELECT topic,COUNT(*) n FROM knowledge WHERE topic IS NOT NULL "
                                  "AND topic<>'' GROUP BY topic ORDER BY n DESC LIMIT 12").fetchall()
        last = db.execute('SELECT * FROM learning_sessions ORDER BY id DESC LIMIT 1').fetchone()
        last_knowledge = db.execute('SELECT title,topic,source_url,created_at,verification_status,'
                                    'session_id FROM knowledge WHERE session_id IS NOT NULL '
                                    'ORDER BY id DESC LIMIT 1').fetchone()
    completed = sessions.get('completed', 0)
    attempted = sum(v for k, v in sessions.items() if k in ('completed', 'failed', 'stopped', 'interrupted'))
    return {
        'sessions_total': sum(sessions.values()),
        'sessions_completed': completed,
        'sessions_failed': sessions.get('failed', 0),
        'sessions_stopped': sessions.get('stopped', 0),
        'sessions_interrupted': sessions.get('interrupted', 0),
        'success_rate': round((completed / attempted) * 100, 1) if attempted else 0.0,
        'pages_learned': pages_learned,
        'knowledge_auto': knowledge_auto,
        'sources_discovered': sources,
        'pages_analyzed': ready,
        'pages_failed': failed,
        'domains': domains,
        'topics_explored': topics,
        'topic_counts': [dict(r) for r in topic_counts],
        'last_session': dict(last) if last else None,
        'last_knowledge': dict(last_knowledge) if last_knowledge else None,
    }


def history(limit=40):
    limit = max(1, min(int(limit or 40), 200))
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT * FROM learning_sessions ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]
    return rows


def status():
    current = None
    if STATE['session_id']:
        with connect() as db:
            row = db.execute('SELECT * FROM learning_sessions WHERE id=?', (STATE['session_id'],)).fetchone()
            current = dict(row) if row else None
    return {
        'state': {
            'running': STATE['running'], 'paused': STATE['paused'], 'phase': STATE['phase'],
            'topic': STATE['topic'], 'current_url': STATE['current_url'],
            'session_id': STATE['session_id'], 'mode': STATE['mode'],
            'last_error': STATE['last_error'],
        },
        'current_session': current,
        'speed': _speed(),
        'stats': stats(),
        'topics': list_topics(),
        'sessions': history(12),
        'settings': {
            'pages_per_session': read_int('learning_pages_per_session', 5),
            'topics_of_interest': setting('learning_topics', '') or '',
            'random_exploration': read_bool('learning_random', True),
            'auto_verify': read_bool('learning_auto_verify', True),
            'resume': read_bool('learning_resume', True),
        },
        'allowlist': allowlist(),
    }
