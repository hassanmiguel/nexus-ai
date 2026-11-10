"""URL learning engine.

Mirrors repository learning for public web pages: fetch a page (HTTPS only,
robots.txt enforced, domain allow-list respected), extract readable text, split
it into overlapping chunks, embed the chunks locally and store them in SQLite.
Learned pages are also summarised into the shared knowledge base so the offline
NEXUS Core brain can answer from them.

URL learning is an internet capability, so it is gated by the ``internet``
permission switch. Pages are never trusted as instructions: their text is stored
as evidence only.
"""
import asyncio
import json
import re
from urllib.parse import urljoin, urlparse

from .database import connect, event, now, read_bool, read_int, setting
from .llm import local_embed
from .memory import store_knowledge
from .research import allowed_domain, fetch_page
from .textutil import clip, keywords, lexical_score, summarize_text

# One polite fetcher at a time: learning packs queue several pages at once, and
# concurrent hits against the same site invite rate limits / robots violations.
_FETCH_LOCK = asyncio.Lock()
_ACTIVE_URLS = set()


async def _fetch_page_throttled(url, with_links=False, delay=None):
    """Fetch one page at a time, then wait the configured politeness delay."""
    async with _FETCH_LOCK:
        try:
            return await fetch_page(url, with_links=with_links)
        finally:
            wait = delay if delay is not None else setting('request_delay_seconds', '3')
            await asyncio.sleep(max(1, int(wait or 3)))

LEARNING_PACKS = [
    {
        'id': 'greetings',
        'label': 'Greetings & social language',
        'topic': 'language',
        'description': 'How humans greet, open conversations and manage social tone.',
        'urls': [
            'https://en.wikipedia.org/wiki/Greeting',
            'https://en.wikipedia.org/wiki/Salutation',
            'https://en.wikipedia.org/wiki/Conversation',
        ],
    },
    {
        'id': 'programming',
        'label': 'Programming foundations',
        'topic': 'programming',
        'description': 'Core ideas behind code, languages and algorithms.',
        'urls': [
            'https://en.wikipedia.org/wiki/Computer_programming',
            'https://en.wikipedia.org/wiki/Programming_language',
            'https://en.wikipedia.org/wiki/Algorithm',
        ],
    },
    {
        'id': 'python',
        'label': 'Python essentials',
        'topic': 'programming',
        'description': 'Official Python tutorial and language reference pages.',
        'urls': [
            'https://docs.python.org/3/tutorial/index.html',
            'https://docs.python.org/3/tutorial/introduction.html',
            'https://docs.python.org/3/tutorial/controlflow.html',
        ],
    },
    {
        'id': 'ai',
        'label': 'AI & local models',
        'topic': 'ai',
        'description': 'Machine learning, language models and retrieval basics.',
        'urls': [
            'https://en.wikipedia.org/wiki/Artificial_intelligence',
            'https://en.wikipedia.org/wiki/Large_language_model',
            'https://en.wikipedia.org/wiki/Retrieval-augmented_generation',
        ],
    },
]

SKIP_EXTENSIONS = (
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.zip',
    '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so', '.dylib', '.bin',
    '.mp4', '.mp3', '.wav', '.woff', '.woff2', '.ttf', '.css', '.js', '.json',
    '.xml', '.rss', '.atom',
)


def permission_enabled():
    return read_bool('permission_internet')


def _require_internet():
    if not permission_enabled():
        raise PermissionError(
            'Internet permission is off. Open Permissions and enable “Internet access” before learning URLs.')


def validate_url(url):
    url = (url or '').strip()
    if not url:
        raise ValueError('A URL is required.')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('Only public HTTPS URLs can be learned (http://, file:// and localhost are blocked).')
    if not allowed_domain(url):
        raise ValueError('That URL is outside the configured public HTTPS / domain allow-list.')
    return url


def chunk_text(text, size=None, overlap=None):
    text = re.sub(r'\s+', ' ', text or '').strip()
    if not text:
        return []
    size = max(240, min(int(size or read_int('web_chunk_chars', 1200)), 4000))
    overlap = max(0, min(int(overlap if overlap is not None else read_int('web_chunk_overlap', 180)), size // 2))
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ''
    for sentence in sentences:
        if len(sentence) > size:
            # hard-split pathological long sentences
            pieces = [sentence[i:i + size] for i in range(0, len(sentence), size)]
        else:
            pieces = [sentence]
        for piece in pieces:
            if current and len(current) + 1 + len(piece) > size:
                chunks.append(current.strip())
                tail = current[-overlap:] if overlap else ''
                current = (tail + ' ' + piece).strip() if tail else piece
            else:
                current = (current + ' ' + piece).strip() if current else piece
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 40][:400]


def _set_status(source_id, status, phase, **extra):
    meta = {'phase': phase}
    meta.update({k: v for k, v in extra.items() if v is not None})
    with connect() as db:
        db.execute('UPDATE web_sources SET status=?,meta=?,updated_at=? WHERE id=?',
                   (status, json.dumps(meta), now(), source_id))


def _insert_source(url, title, topic, depth, root_id=None, status='queued'):
    with connect() as db:
        cur = db.execute(
            'INSERT INTO web_sources(url,final_url,title,topic,status,depth,root_id,meta,created_at,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?)',
            (url, url, title or '', topic or 'web', status, depth, root_id,
             json.dumps({'phase': 'queued'}), now(), now()))
        return cur.lastrowid


def _reset_existing(url, title, topic, depth):
    with connect() as db:
        row = db.execute('SELECT id FROM web_sources WHERE url=? ORDER BY id DESC LIMIT 1', (url,)).fetchone()
        if not row:
            return None
        source_id = row['id']
        db.execute('DELETE FROM web_chunks WHERE source_id=?', (source_id,))
        db.execute('UPDATE web_sources SET title=?,topic=?,status=?,depth=?,summary=?,char_count=0,chunk_count=0,'
                   'meta=?,updated_at=? WHERE id=?',
                   (title or '', topic or 'web', 'queued', depth, '',
                    json.dumps({'phase': 'queued'}), now(), source_id))
        return source_id


async def start_learning(url, title=None, topic=None, depth=None):
    """Queue a URL for learning. Returns the web_sources id."""
    _require_internet()
    url = validate_url(url)
    topic = (topic or 'web').strip()[:60] or 'web'
    depth = read_int('learn_depth', 0) if depth is None else int(depth)
    depth = max(0, min(depth, 1))
    source_id = _reset_existing(url, title, topic, depth) or _insert_source(url, title, topic, depth)
    if depth and source_id:
        with connect() as db:
            db.execute('UPDATE web_sources SET root_id=? WHERE id=?', (source_id, source_id))
    event('web', f'Queued URL learning: {url} (topic {topic}, depth {depth})')
    asyncio.create_task(_learn_task(source_id, url, title, topic, depth))
    return source_id


def _same_site_links(base_url, links):
    host = (urlparse(base_url).hostname or '').lower()
    out = []
    seen = set()
    for href in links:
        try:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme != 'https' or (parsed.hostname or '').lower() != host:
                continue
            if absolute.split('#', 1)[0] in seen:
                continue
            path = (parsed.path or '/').lower()
            if path.endswith(SKIP_EXTENSIONS):
                continue
            if any(x in path for x in ('/login', '/signup', '/signin', '/account', '/cart', '/checkout')):
                continue
            clean = absolute.split('#', 1)[0]
            if not allowed_domain(clean):
                continue
            seen.add(clean)
            out.append(clean)
        except Exception:
            continue
    return out


async def _learn_page(source_id, url, title, topic, depth, root_id=None, with_links=None, pace=None):
    _set_status(source_id, 'learning', 'fetching')
    want_links = (depth > 0) if with_links is None else bool(with_links)
    if want_links:
        page_title, text, links = await _fetch_page_throttled(url, with_links=True, delay=pace)
    else:
        page_title, text = await _fetch_page_throttled(url, delay=pace)
        links = []
    page_title = (title or page_title or url).strip()
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError('No readable text could be chunked from this page.')
    _set_status(source_id, 'learning', 'indexing', total=len(chunks))
    rows = []
    for ordinal, chunk in enumerate(chunks):
        rows.append((source_id, url, page_title, ordinal, chunk,
                     json.dumps(local_embed(chunk)), 'local', now()))
    summary = summarize_text(text, 7) or clip(text, 1200)
    with connect() as db:
        db.execute('DELETE FROM web_chunks WHERE source_id=?', (source_id,))
        db.executemany(
            'INSERT INTO web_chunks(source_id,url,title,ordinal,content,embedding,embedding_kind,created_at) '
            'VALUES(?,?,?,?,?,?,?,?)', rows)
        db.execute('UPDATE web_sources SET final_url=?,title=?,status=?,char_count=?,chunk_count=?,summary=?,'
                   'meta=?,updated_at=? WHERE id=?',
                   (url, page_title, 'ready', len(text), len(chunks), summary,
                    json.dumps({'phase': 'ready', 'links_followed': len(links)}), now(), source_id))
    # Store the page summary in shared long-term memory (deduplicated by URL).
    with connect() as db:
        exists = db.execute('SELECT id FROM knowledge WHERE source_url=? LIMIT 1', (url,)).fetchone()
    if not exists:
        try:
            await store_knowledge(f'Web: {page_title}', summary, url, topic, 0.74, 'web-learned')
        except Exception:
            pass
    else:
        # Re-learning a page should refresh its summary instead of leaving stale text.
        with connect() as db:
            db.execute('UPDATE knowledge SET title=?,content=?,topic=?,confidence=?,created_at=? WHERE id=?',
                       (f'Web: {page_title}', summary, topic, 0.74, now(), exists['id']))
    event('web', f'Learned page: {page_title} — {len(chunks)} chunks, {len(text)} chars.')
    return page_title, links


async def learn_page_now(url, title=None, topic=None, depth=None, pace=None):
    """Learn a URL synchronously (used by the autonomous learning engine)."""
    _require_internet()
    url = validate_url(url)
    topic = (topic or 'web').strip()[:60] or 'web'
    depth = read_int('learn_depth', 0) if depth is None else max(0, min(int(depth), 1))
    source_id = _reset_existing(url, title, topic, depth) or _insert_source(url, title, topic, depth)
    page_title, links = await _learn_page(source_id, url, title, topic, 0, with_links=True, pace=pace)
    return {'id': source_id, 'title': page_title, 'links': links, 'url': url}


def same_site_links(base_url, links):
    return _same_site_links(base_url, links)


async def _learn_task(source_id, url, title, topic, depth):
    if url in _ACTIVE_URLS:
        event('web', f'URL learning already in progress, skipped duplicate: {url}')
        return
    _ACTIVE_URLS.add(url)
    root_id = source_id if depth > 0 else None
    try:
        page_title, links = await _learn_page(source_id, url, title, topic, depth, root_id)
        if depth > 0 and links:
            limit = max(1, min(read_int('learn_max_links', 8), 24))
            follow = _same_site_links(url, links)[:limit]
            event('web', f'Following {len(follow)} same-site link(s) from {url}.')
            for link in follow:
                with connect() as db:
                    exists = db.execute("SELECT 1 FROM web_sources WHERE url=? AND status='ready' LIMIT 1",
                                        (link,)).fetchone()
                if exists:
                    continue
                child_id = _insert_source(link, '', topic, 0, root_id)
                try:
                    await _learn_page(child_id, link, '', topic, 0, root_id)
                except Exception as e:
                    _set_status(child_id, 'failed', 'failed', error=str(e)[:400])
                    event('warning', f'URL learning skipped {link}: {e}')
    except Exception as e:
        _set_status(source_id, 'failed', 'failed', error=str(e)[:600])
        event('warning', f'URL learning failed for {url}: {e}')
    finally:
        _ACTIVE_URLS.discard(url)


async def learn_pack(pack_id, depth=None):
    _require_internet()
    pack = next((p for p in LEARNING_PACKS if p['id'] == pack_id), None)
    if not pack:
        raise ValueError('Unknown learning pack.')
    ids = []
    for url in pack['urls']:
        try:
            ids.append(await start_learning(url, topic=pack['topic'], depth=depth))
        except Exception as e:
            event('warning', f'Pack {pack_id}: could not queue {url}: {e}')
    return {'pack': pack_id, 'queued': len(ids), 'ids': ids}


def list_sources():
    with connect() as db:
        rows = db.execute(
            'SELECT id,url,final_url,title,topic,status,depth,root_id,char_count,chunk_count,summary,meta,'
            'created_at,updated_at FROM web_sources ORDER BY id DESC LIMIT 400').fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item['meta'] = json.loads(item.get('meta') or '{}')
        except Exception:
            item['meta'] = {}
        out.append(item)
    return out


def get_source(source_id):
    with connect() as db:
        row = db.execute('SELECT * FROM web_sources WHERE id=?', (source_id,)).fetchone()
        if not row:
            return None
        chunks = db.execute('SELECT id,source_id,url,title,ordinal,content,created_at FROM web_chunks '
                            'WHERE source_id=? ORDER BY ordinal', (source_id,)).fetchall()
    item = dict(row)
    try:
        item['meta'] = json.loads(item.get('meta') or '{}')
    except Exception:
        item['meta'] = {}
    return {'source': item, 'chunks': [dict(c) for c in chunks]}


def delete_source(source_id):
    with connect() as db:
        row = db.execute('SELECT id,root_id FROM web_sources WHERE id=?', (source_id,)).fetchone()
        if not row:
            return None
        ids = [source_id]
        if row['root_id'] == source_id:
            ids += [r['id'] for r in db.execute('SELECT id FROM web_sources WHERE root_id=? AND id<>?',
                                               (source_id, source_id)).fetchall()]
        marks = ','.join('?' for _ in ids)
        urls = [r['url'] for r in db.execute(
            f'SELECT url FROM web_sources WHERE id IN ({marks})', ids).fetchall()]
        knowledge_deleted = 0
        if urls:
            kmarks = ','.join('?' for _ in urls)
            knowledge_deleted = db.execute(
                f'DELETE FROM knowledge WHERE source_url IN ({kmarks})', urls).rowcount
        chunks = db.execute(f'DELETE FROM web_chunks WHERE source_id IN ({marks})', ids).rowcount
        db.execute(f'DELETE FROM web_sources WHERE id IN ({marks})', ids)
    event('web', f'Deleted learned URL(s) {ids} ({chunks} chunks, {knowledge_deleted} knowledge items).')
    return {'ok': True, 'deleted_sources': len(ids), 'chunks_deleted': chunks,
            'knowledge_deleted': knowledge_deleted}


async def search_web_chunks(query, limit=6):
    """Two-stage retrieval: SQL/lexical shortlist, then semantic rerank.

    Web indexes can grow to tens of thousands of chunks; decoding every embedding
    on each chat turn is slow. Mirror the repository search strategy: use a cheap
    keyword prefilter and only decode vectors for the shortlist.
    """
    import math
    qvec = local_embed(query)
    qnorm = math.sqrt(sum(a * a for a in qvec)) or 1.0
    base_sql = ('SELECT wc.id,wc.source_id,wc.url,wc.title,wc.ordinal,wc.content,wc.embedding,'
                'wc.embedding_kind,ws.topic,ws.title source_title '
                'FROM web_chunks wc JOIN web_sources ws ON ws.id=wc.source_id')
    where = ["ws.status='ready'"]
    params = []
    kws = keywords(query, 8)
    if kws:
        where.append('(' + ' OR '.join(['wc.content LIKE ?'] * len(kws)) + ')')
        params.extend(f'%{k}%' for k in kws)
    sql = base_sql + ' WHERE ' + ' AND '.join(where)
    row_limit = 1000 if kws else 200
    with connect() as db:
        rows = [dict(r) for r in db.execute(sql + f' ORDER BY wc.id DESC LIMIT {row_limit}', params).fetchall()]
        if len(rows) < 40:
            recent = [dict(r) for r in db.execute(
                base_sql + " WHERE ws.status='ready' ORDER BY wc.id DESC LIMIT 200").fetchall()]
            seen = {r['id'] for r in rows}
            rows.extend(r for r in recent if r['id'] not in seen)
    lexical = []
    for row in rows:
        score = lexical_score(query, row['content'])
        if score > 0.002:
            lexical.append((score, row))
    lexical.sort(key=lambda x: x[0], reverse=True)
    shortlist = lexical[:240]
    if len(shortlist) < 60:
        seen = {id(row) for _, row in shortlist}
        for row in rows[:120]:
            if id(row) not in seen:
                shortlist.append((0.0, row))
    scored = []
    for base, row in shortlist:
        semantic = 0.0
        if row.get('embedding') and (row.get('embedding_kind') or 'local') == 'local':
            try:
                vec = json.loads(row['embedding'])
                if len(vec) == len(qvec):
                    dot = sum(a * b for a, b in zip(qvec, vec))
                    nb = math.sqrt(sum(b * b for b in vec)) or 1.0
                    semantic = dot / (qnorm * nb)
            except Exception:
                pass
        score = semantic * 0.7 + min(base, 1.2) * 0.3 if semantic else base
        if score > 0.002:
            row['score'] = round(score, 4)
            row.pop('embedding', None)
            row['repo_name'] = None
            scored.append(row)
    scored.sort(key=lambda x: (x['score'], -x['id']), reverse=True)
    return scored[:max(1, min(limit, 30))]


def format_web_chunks(chunks):
    blocks = []
    for c in chunks:
        blocks.append(f"[web] {c.get('source_title') or c.get('title') or c.get('url')} "
                      f"(chunk {c.get('ordinal')}, score {c.get('score')})\n{clip(c.get('content'), 1800)}")
    return '\n\n'.join(blocks)
