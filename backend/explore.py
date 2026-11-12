"""Categorised autonomous exploration.

This is the DISCOVER → EXPLORE → EXTRACT → ANALYZE → VERIFY → STORE slice of the
continuous cycle, kept separate from Auto Programming (which owns the programming
practice loop).

Hard rules, enforced in code and surfaced in the UI:

* every fetch goes through :func:`research.fetch_page`, which requires HTTPS, a
  public IP, a robots.txt allowance and the user's domain allowlist;
* no paywall, CAPTCHA or login bypass is attempted; a blocked page is recorded as
  ``blocked`` and never retried aggressively;
* one host is rate-limited by the existing crawler plus a per-cycle cap here;
* programming documentation domains are only fetched after the user explicitly
  adds them to the allowlist; until then discovery falls back to Wikipedia.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from .database import connect, event, now, read_bool, setting, set_setting
from . import proglang

CATEGORIES = {
    'programming': 'Programming languages, algorithms and software engineering',
    'ai': 'Artificial intelligence, machine learning and agents',
    'ml': 'Machine learning methods and evaluation',
    'cybersecurity': 'Defensive security, privacy and secure coding',
    'science': 'Physics, astronomy, biology, chemistry and climate',
    'mathematics': 'Algebra, calculus, statistics and discrete mathematics',
    'webdev': 'HTML, CSS, JavaScript, accessibility and the web platform',
    'gamedev': 'Game design, engines, rendering and graphics',
    'robotics': 'Robotics, control systems and sensors',
    'general': 'Cross-cutting reference material',
}

TOPIC_HINTS = {
    'programming': 'programming language tutorial',
    'ai': 'artificial intelligence overview',
    'ml': 'machine learning overview',
    'cybersecurity': 'computer security defensive',
    'science': 'scientific discipline overview',
    'mathematics': 'mathematics overview',
    'webdev': 'web development overview',
    'gamedev': 'video game development overview',
    'robotics': 'robotics overview',
    'general': 'technology overview',
}

BLOCK_MARKERS = ('paywall', 'subscribe to continue', 'captcha', 'enable javascript to continue',
                 'sign in to continue', 'access denied')


def _domain(url):
    return (urlparse(url).hostname or '').lower()


def _clean(value):
    return re.sub(r'\s+', ' ', (value or '').strip())


def _ensure_category(category):
    category = (category or 'general').lower()
    return category if category in CATEGORIES else 'general'


def _record_site(url, title='', category='general', status='discovered', summary='', value=0.0):
    _ensure_category(category)
    with connect() as db:
        db.execute('INSERT INTO explored_sites(url,domain,title,category,status,value_score,summary,'
                   'discovered_at) VALUES(?,?,?,?,?,?,?,?) '
                   'ON CONFLICT(url) DO UPDATE SET title=COALESCE(NULLIF(excluded.title,\'\'),title), '
                   'category=excluded.category,summary=CASE WHEN excluded.summary<>\'\' '
                   'THEN excluded.summary ELSE summary END,value_score=MAX(value_score,excluded.value_score)',
                   (url, _domain(url), title[:300], category, status, float(value or 0),
                    summary[:1200], now()))
        return db.execute('SELECT * FROM explored_sites WHERE url=?', (url,)).fetchone()['id']


def _mark(url, status, summary='', value=None):
    with connect() as db:
        if value is not None:
            db.execute('UPDATE explored_sites SET status=?,summary=?,value_score=?,learned_at=? WHERE url=?',
                       (status, summary[:1200], float(value), now(), url))
        else:
            db.execute('UPDATE explored_sites SET status=?,learned_at=? WHERE url=?',
                       (status, now(), url))


def allowlist_status():
    """Which programming doc domains are already allowed, and which need approval."""
    from .research import allowlist

    allowed = allowlist()
    domains = proglang.docs_domains()
    if not allowed:
        return {'open': True, 'allowed': [], 'missing': [], 'domains': domains,
                'note': 'The allowlist is empty, so every public HTTPS site is permitted. '
                        'Consider restricting it for safer exploration.'}
    missing = [d for d in domains if not any(d == a or d.endswith('.' + a) for a in allowed)]
    return {'open': False, 'allowed': allowed, 'missing': missing, 'domains': domains,
            'note': ('Programming documentation domains are blocked until you approve them. '
                     'Until then exploration uses Wikipedia and any allowed domains.') if missing else
                    'All programming documentation domains are permitted.'}


def approve_docs_domains(domains=None):
    """Explicit user-approved allowlist extension. Never called automatically."""
    status = allowlist_status()
    current = status['allowed']
    targets = [d.strip().lower() for d in (domains or status['missing']) if d.strip()]
    merged = sorted({*current, *targets})
    set_setting('allowed_domains', ','.join(merged))
    event('exploration', f'User approved {len(targets)} documentation domain(s) for exploration.')
    return allowlist_status()


async def discover(category='general', limit=6):
    """Find candidate pages for a category without fetching their bodies."""
    category = _ensure_category(category)
    if not read_bool('permission_internet'):
        return {'category': category, 'candidates': [], 'errors': ['Internet permission is disabled.']}
    from .autonomous import _wiki_search
    from .research import allowed_domain, search_web

    errors = []
    found = []
    query = TOPIC_HINTS.get(category, 'technology overview')
    try:
        for item in await search_web(query, limit=limit * 2):
            if allowed_domain(item['url']):
                found.append(item)
    except Exception as exc:
        errors.append(f'Search failed: {exc}'[:300])
    try:
        found.extend(await _wiki_search(f'{category} {query}'))
    except Exception as exc:
        errors.append(f'Wikipedia discovery failed: {exc}'[:300])

    out = []
    seen = set()
    per_domain = {}
    for item in found:
        url = item.get('url') or ''
        if not url or url in seen or not allowed_domain(url):
            continue
        host = _domain(url)
        if per_domain.get(host, 0) >= 2:
            continue
        seen.add(url)
        per_domain[host] = per_domain.get(host, 0) + 1
        _record_site(url, item.get('title', ''), category, 'discovered', item.get('snippet', ''))
        out.append({'url': url, 'title': _clean(item.get('title')), 'snippet': _clean(item.get('snippet')),
                    'domain': host, 'category': category})
        if len(out) >= limit:
            break
    event('exploration', f'Discovery for {category}: {len(out)} candidate(s) inside the allowlist.')
    return {'category': category, 'candidates': out, 'errors': errors, 'allowlist': allowlist_status()}


async def explore_url(url, category='general', store=True):
    """Fetch, extract, verify and store one page. Respects every safety gate."""
    category = _ensure_category(category)
    if not read_bool('permission_internet'):
        raise PermissionError('Internet exploration requires the internet permission.')
    from .research import allowed_domain, fetch_page
    from .textutil import best_sentences

    if not allowed_domain(url):
        _record_site(url, '', category, 'blocked', 'Outside the allowlist or not public HTTPS.')
        raise PermissionError('That URL is not HTTPS, not public, or outside the allowlist.')
    _record_site(url, '', category, 'fetching')
    try:
        title, text = await fetch_page(url)
    except PermissionError as exc:
        _mark(url, 'blocked', str(exc)[:500])
        return {'ok': False, 'url': url, 'status': 'blocked', 'error': str(exc),
                'note': 'robots.txt or the allowlist refused this page. Nothing was stored.'}
    except Exception as exc:
        _mark(url, 'failed', str(exc)[:500])
        return {'ok': False, 'url': url, 'status': 'failed', 'error': str(exc),
                'note': 'The page could not be fetched safely; nothing was stored.'}

    lowered = text.lower()
    if any(marker in lowered for marker in BLOCK_MARKERS) and len(text) < 1200:
        _mark(url, 'blocked', 'Paywall, CAPTCHA or login wall detected; not bypassed.')
        return {'ok': False, 'url': url, 'status': 'blocked',
                'error': 'Paywall, CAPTCHA or login wall detected.',
                'note': 'NEXUS does not bypass access controls.'}

    sentences = best_sentences(f'{category} {title}', text, limit=10)
    summary = _clean(' '.join(sentences) or text[:1200])[:5000]
    knowledge_id = None
    if store and summary:
        from .memory import store_knowledge
        knowledge_id = await store_knowledge(title or url, summary, url,
                                             f'exploration: {category}', 0.66, 'single-source')
    _mark(url, 'learned', summary, 0.75 if summary else 0.3)
    event('exploration', f'Explored “{title or url}” ({category}); '
                         f'{"stored" if knowledge_id else "no new knowledge"}.')
    return {'ok': True, 'url': url, 'status': 'learned', 'title': title, 'summary': summary,
            'sentences': len(sentences), 'knowledge_id': knowledge_id, 'category': category}


async def explore(category='general', limit=3, store=True):
    """Discover then explore up to ``limit`` pages for one category."""
    limit = max(1, min(int(limit), 6))
    discovered = await discover(category, limit=limit + 2)
    results = []
    for candidate in discovered['candidates'][:limit]:
        result = await explore_url(candidate['url'], category, store=store)
        results.append(result)
        await asyncio.sleep(1)
    learned = sum(1 for r in results if r.get('ok'))
    return {'category': category, 'attempted': len(results), 'learned': learned,
            'results': results, 'errors': discovered.get('errors', []),
            'allowlist': discovered.get('allowlist')}


def queue_categories():
    raw = setting('exploration_categories', '') or ''
    chosen = [c.strip().lower() for c in raw.split(',') if c.strip()]
    valid = [c for c in chosen if c in CATEGORIES]
    return valid or ['programming', 'ai', 'science']


def sites(limit=100, status='', category=''):
    with connect() as db:
        clauses, params = [], []
        if status:
            clauses.append('status=?')
            params.append(status)
        if category:
            clauses.append('category=?')
            params.append(category)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = db.execute(f'SELECT * FROM explored_sites {where} ORDER BY id DESC LIMIT ?',
                          (*params, max(1, min(limit, 500)))).fetchall()
    return [dict(r) for r in rows]


def stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM explored_sites').fetchone()['n']
        learned = db.execute("SELECT COUNT(*) n FROM explored_sites WHERE status='learned'").fetchone()['n']
        blocked = db.execute("SELECT COUNT(*) n FROM explored_sites WHERE status='blocked'").fetchone()['n']
        by_category = [dict(r) for r in db.execute(
            'SELECT category,COUNT(*) n,SUM(CASE WHEN status=\'learned\' THEN 1 ELSE 0 END) learned '
            'FROM explored_sites GROUP BY category ORDER BY n DESC').fetchall()]
        by_domain = [dict(r) for r in db.execute(
            "SELECT domain,COUNT(*) n FROM explored_sites WHERE domain<>'' GROUP BY domain "
            'ORDER BY n DESC LIMIT 12').fetchall()]
    return {'total': total, 'learned': learned, 'blocked': blocked,
            'success_rate': round(100 * learned / total, 1) if total else 0,
            'by_category': by_category, 'by_domain': by_domain,
            'categories': CATEGORIES, 'queue': queue_categories(),
            'allowlist': allowlist_status()}
