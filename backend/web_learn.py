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
from .textutil import clip, lexical_score, summarize_text

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


async def _learn_page(source_id, url, title, topic, depth, root_id=None):
    _set_status(source_id, 'learning', 'fetching')
    if depth > 0:
        page_title, text, links = await fetch_page(url, with_links=True)
    else:
        page_title, text = await fetch_page(url)
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
    event('web', f'Learned page: {page_title} — {len(chunks)} chunks, {len(text)} chars.')
    return page_title, links


async def _learn_task(source_id, url, title, topic, depth):
    root_id = source_id if depth > 0 else None
    try:
        page_title, links = await _learn_page(source_id, url, title, topic, depth, root_id)
        if depth > 0 and links:
            limit = max(1, min(read_int('learn_max_links', 8), 24))
            follow = _same_site_links(url, links)[:limit]
            event('web', f'Following {len(follow)} same-site link(s) from {url}.')
            delay = max(1, int(setting('request_delay_seconds', '3') or 3))
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
                await asyncio.sleep(delay)
    except Exception as e:
        _set_status(source_id, 'failed', 'failed', error=str(e)[:600])
        event('warning', f'URL learning failed for {url}: {e}')


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
        chunks = db.execute(f'DELETE FROM web_chunks WHERE source_id IN ({marks})', ids).rowcount
        db.execute(f'DELETE FROM web_sources WHERE id IN ({marks})', ids)
    event('web', f'Deleted learned URL(s) {ids} ({chunks} chunks).')
    return {'ok': True, 'deleted_sources': len(ids), 'chunks_deleted': chunks}


async def search_web_chunks(query, limit=6):
    import math
    qvec = local_embed(query)
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT wc.id,wc.source_id,wc.url,wc.title,wc.ordinal,wc.content,wc.embedding,wc.embedding_kind,'
            'ws.topic,ws.title source_title FROM web_chunks wc JOIN web_sources ws ON ws.id=wc.source_id '
            "WHERE ws.status='ready' ORDER BY wc.id DESC LIMIT 20000").fetchall()]
    scored = []
    for row in rows:
        semantic = 0.0
        if row.get('embedding') and (row.get('embedding_kind') or 'local') == 'local':
            try:
                vec = json.loads(row['embedding'])
                if len(vec) == len(qvec):
                    dot = sum(a * b for a, b in zip(qvec, vec))
                    na = math.sqrt(sum(a * a for a in qvec)) or 1
                    nb = math.sqrt(sum(b * b for b in vec)) or 1
                    semantic = dot / (na * nb)
            except Exception:
                pass
        lexical = lexical_score(query, row['content'])
        score = semantic * 0.7 + min(lexical, 1.2) * 0.3 if semantic else lexical
        if score > 0.002:
            row['score'] = round(score, 4)
            row.pop('embedding', None)
            row['repo_name'] = None
            scored.append(row)
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:max(1, min(limit, 30))]


def format_web_chunks(chunks):
    blocks = []
    for c in chunks:
        blocks.append(f"[web] {c.get('source_title') or c.get('title') or c.get('url')} "
                      f"(chunk {c.get('ordinal')}, score {c.get('score')})\n{clip(c.get('content'), 1800)}")
    return '\n\n'.join(blocks)
