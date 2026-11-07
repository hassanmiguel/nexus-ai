"""Repository learning engine.

Supports GitHub URLs (public or token-authenticated) and local folders/zips.
A repository is read with strict size/count limits, indexed into SQLite as
files + line-addressed chunks, embedded with the offline local embedder, and
summarised into long-term knowledge. No git binary is required.
"""
import asyncio
import hashlib
import json
import math
import os
import re
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

import httpx

from .database import connect, now, event, read_int, setting
from .llm import local_embed
from .memory import store_knowledge
from .textutil import (extract_symbols, language_from_path, lexical_score,
                       parse_version_files, summarize_text, clip)

IGNORE_DIRS = {
    '.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', 'env', '__pycache__',
    '.next', '.nuxt', 'dist', 'build', 'out', 'target', 'bin', 'obj', 'vendor',
    'Pods', '.idea', '.vscode', 'coverage', '.pytest_cache', '.mypy_cache',
    'site-packages', 'bower_components', '.gradle', '.cache', '.tox', 'venv-win',
}
IGNORE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'composer.lock', 'poetry.lock',
    'Cargo.lock', 'Gemfile.lock', 'pipfile.lock',
}
TEXT_EXTENSIONS = {
    '.py', '.pyw', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.java', '.cs',
    '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.go', '.rs', '.rb', '.php', '.swift',
    '.kt', '.kts', '.scala', '.sh', '.ps1', '.bat', '.cmd', '.html', '.htm', '.css',
    '.scss', '.sass', '.less', '.vue', '.svelte', '.sql', '.json', '.yaml', '.yml',
    '.toml', '.ini', '.xml', '.md', '.mdx', '.rst', '.txt', '.dockerfile', '.env',
    '.gitignore', '.lua', '.dart', '.r', '.ex', '.exs', '.zig', '.nim', '.sol', '.tf',
    '.graphql', '.gql', '.proto', '.cmake', '.make', '.mk', '.lock', '.conf', '.cfg',
}
SPECIAL_TEXT_NAMES = {
    'dockerfile', 'makefile', 'rakefile', 'gemfile', 'procfile', 'license', 'readme',
    'cmakelists.txt', '.gitignore', '.env.example', '.editorconfig', 'go.mod', 'go.sum',
}

ENTRY_POINTS = {
    'main.py', 'app.py', 'server.py', 'manage.py', 'wsgi.py', 'asgi.py',
    'index.js', 'index.ts', 'main.js', 'main.ts', 'server.js', 'server.ts', 'app.js', 'app.tsx',
    'main.go', 'main.rs', 'program.cs', 'main.java', 'index.php', 'app.rb',
}


def parse_github(source: str):
    s = (source or '').strip().rstrip('/')
    s = re.sub(r'\.git$', '', s)
    m = re.match(r'https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:/tree/(.+))?$', s, re.I)
    if m:
        return m.group(1), m.group(2), (m.group(3) or '').strip('/') or None
    m = re.match(r'^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$', s)
    if m:
        return m.group(1), m.group(2), None
    return None


def _should_skip_path(path: str):
    parts = [p for p in path.replace('\\', '/').split('/') if p]
    if any(p in IGNORE_DIRS for p in parts[:-1]):
        return True
    if parts and parts[-1] in IGNORE_FILES:
        return True
    low = (parts[-1] if parts else '').lower()
    if low.endswith(('.min.js', '.min.css', '.map', '.png', '.jpg', '.jpeg', '.gif',
                     '.webp', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.pdf',
                     '.zip', '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so', '.dylib',
                     '.bin', '.class', '.jar', '.pyc', '.db', '.sqlite', '.mp4', '.mp3')):
        return True
    return False


def _looks_text(path: str, data: bytes):
    ext = Path(path).suffix.lower()
    name = Path(path).name.lower()
    if ext in TEXT_EXTENSIONS or name in SPECIAL_TEXT_NAMES:
        if b'\x00' in data[:4096]:
            return False
        return True
    if ext or name in SPECIAL_TEXT_NAMES:
        return False
    if not data:
        return False
    sample = data[:4096]
    if b'\x00' in sample:
        return False
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127)
    return printable / max(1, len(sample)) > 0.86


def _decode(data: bytes):
    for enc in ('utf-8', 'utf-16', 'latin-1'):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode('utf-8', errors='replace')


async def _download_github_zip(owner, repo, branch, token, max_mb):
    headers = {'User-Agent': 'NexusAI-RepoIndexer/1.0', 'Accept': 'application/vnd.github+json'}
    env_token = token or os.getenv('GITHUB_TOKEN') or ''
    if env_token:
        headers['Authorization'] = f'Bearer {env_token}'
    branch = branch or ''
    async with httpx.AsyncClient(timeout=None, follow_redirects=True, headers=headers) as client:
        if not branch:
            try:
                r = await client.get(f'https://api.github.com/repos/{owner}/{repo}', timeout=20)
                if r.status_code == 200:
                    branch = r.json().get('default_branch') or 'main'
            except Exception:
                branch = ''
        candidates = [branch] if branch else []
        for extra in ('main', 'master'):
            if extra not in candidates:
                candidates.append(extra)
        urls = []
        for b in candidates:
            urls.append((f'https://api.github.com/repos/{owner}/{repo}/zipball/{quote(b, safe="")}', b))
            urls.append((f'https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{quote(b, safe="")}', b))
        last_error = None
        tmp = tempfile.NamedTemporaryFile(prefix='nexus_repo_', suffix='.zip', delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        for url, candidate_branch in urls:
            try:
                downloaded = 0
                async with client.stream('GET', url) as response:
                    if response.status_code >= 400:
                        last_error = f'HTTP {response.status_code} for branch {candidate_branch}'
                        continue
                    with open(tmp_path, 'wb') as fh:
                        async for chunk in response.aiter_bytes(65536):
                            downloaded += len(chunk)
                            if downloaded > max_mb * 1024 * 1024:
                                raise RuntimeError(f'Repository archive exceeds {max_mb} MB limit.')
                            fh.write(chunk)
                if downloaded == 0:
                    last_error = 'Empty repository archive.'
                    continue
                return tmp_path, candidate_branch
            except Exception as e:
                last_error = str(e)
                continue
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(f'Could not download repository: {last_error or "unknown error"}')


def _iter_zip_files(zip_path: Path, max_files, max_file_bytes, max_total_chars):
    files = []
    total_chars = 0
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        if not names:
            return files
        roots = {n.replace('\\', '/').split('/', 1)[0] for n in names}
        strip_root = len(roots) == 1 and all('/' in n.replace('\\', '/') for n in names)
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace('\\', '/')
            parts = [p for p in name.split('/') if p not in ('', '.')]
            if not parts or any(p == '..' for p in parts):
                continue
            if strip_root and len(parts) > 1:
                parts = parts[1:]
            rel = '/'.join(parts)
            if not rel or _should_skip_path(rel):
                continue
            if info.file_size > max_file_bytes:
                continue
            # skip symlinks
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                continue
            try:
                data = z.read(info)
            except Exception:
                continue
            if not _looks_text(rel, data):
                continue
            content = _decode(data)
            if len(content) > max_total_chars:
                content = content[:max_total_chars]
            total_chars += len(content)
            files.append({'path': rel, 'content': content, 'size': len(data)})
            if len(files) >= max_files or total_chars >= max_total_chars:
                break
    return files


def _iter_local_files(root: Path, max_files, max_file_bytes, max_total_chars):
    files = []
    total_chars = 0
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for filename in sorted(filenames):
            if len(files) >= max_files or total_chars >= max_total_chars:
                return files
            fp = Path(dirpath) / filename
            try:
                rel = fp.relative_to(root).as_posix()
            except ValueError:
                continue
            if _should_skip_path(rel):
                continue
            try:
                size = fp.stat().st_size
            except Exception:
                continue
            if size > max_file_bytes:
                continue
            try:
                data = fp.read_bytes()
            except Exception:
                continue
            if not _looks_text(rel, data):
                continue
            content = _decode(data)
            if len(content) > max_total_chars:
                content = content[:max_total_chars]
            total_chars += len(content)
            files.append({'path': rel, 'content': content, 'size': len(data)})
    return files


def _chunk_lines(content: str, target_lines: int, overlap: int):
    lines = content.splitlines()
    if not lines:
        return []
    target_lines = max(20, target_lines)
    overlap = max(0, min(overlap, target_lines // 2))
    chunks = []
    i = 0
    while i < len(lines):
        end = min(len(lines), i + target_lines)
        text = '\n'.join(lines[i:end]).strip()
        if text:
            if len(text) > 6000:
                text = text[:6000]
            chunks.append((i + 1, end, text))
        if end >= len(lines):
            break
        i = max(i + 1, end - overlap)
    return chunks


def _structural_summary(name, source, files, languages, deps, readme):
    top = {}
    for f in files:
        first = f['path'].split('/', 1)[0]
        top[first] = top.get(first, 0) + 1
    top_dirs = ', '.join(f'{k} ({v})' for k, v in sorted(top.items(), key=lambda x: -x[1])[:12]) or 'flat repository'
    entries = [f['path'] for f in files if Path(f['path']).name.lower() in ENTRY_POINTS][:14]
    lang_text = ', '.join(f'{k} ({v})' for k, v in sorted(languages.items(), key=lambda x: -x[1])[:8]) or 'unknown'
    lines = [
        f'# Repository: {name}',
        f'Source: {source}',
        f'Indexed files: {len(files)}',
        f'Languages: {lang_text}',
        f'Top-level areas: {top_dirs}',
        f'Entry points: {", ".join(entries) if entries else "not detected"}',
        f'Dependencies: {", ".join(deps[:40]) if deps else "not detected"}',
    ]
    if readme:
        lines.append('')
        lines.append('## README excerpt')
        lines.append(clip(readme, 2600))
    return '\n'.join(lines)


async def _architecture_summary(name, files, deps, readme):
    """Use a configured generative provider when available; otherwise return a
    structural map. Never fails ingestion if the model is offline."""
    tree = '\n'.join(f['path'] for f in files[:420])
    prompt = (
        f'You are indexing a code repository named {name} for a local AI memory.\n'
        f'Produce a precise architecture brief with sections: Purpose, Stack, Module map, '
        f'Key entry points, Data flow, Testing/build, Risks and gotchas. Cite file paths. '
        f'Do not invent files. Keep under 700 words.\n\nFILE TREE:\n{tree}\n\n'
        f'DEPENDENCIES: {", ".join(deps[:60])}\n\nREADME:\n{clip(readme, 5000)}'
    )
    try:
        from .providers import current_provider, generate
        if current_provider() != 'nexus':
            return await asyncio.wait_for(generate(prompt, system='You are a code archaeologist. Be factual and cite paths.'), timeout=150)
    except Exception:
        pass
    return ''


async def start_ingest(source, branch=None, token=None, name=None):
    source = (source or '').strip()
    if not source:
        raise ValueError('Repository source is required.')
    gh = parse_github(source)
    if gh:
        owner, repo, url_branch = gh
        kind = 'github'
        branch = branch or url_branch
        name = name or repo
        normalized = f'https://github.com/{owner}/{repo}'
    else:
        path = Path(os.path.expandvars(os.path.expanduser(source)))
        if not path.exists():
            raise ValueError('Not a GitHub repository or an existing local path.')
        kind = 'local'
        path = path.resolve()
        name = name or path.name
        normalized = str(path)
    with connect() as db:
        cur = db.execute(
            'INSERT INTO repos(name,source,kind,branch,status,created_at,updated_at,meta) VALUES(?,?,?,?,?,?,?,?)',
            (name, normalized, kind, branch or '', 'queued', now(), now(), '{}'))
        repo_id = cur.lastrowid
    event('repo', f'Queued repository learning: {name} ({normalized})')
    asyncio.create_task(_ingest_task(repo_id, normalized, kind, branch, token, name))
    return repo_id


async def _set_progress(repo_id, phase, processed=0, total=0, status=None):
    meta = json.dumps({'phase': phase, 'processed': processed, 'total': total})
    with connect() as db:
        if status:
            db.execute('UPDATE repos SET status=?,meta=?,updated_at=? WHERE id=?', (status, meta, now(), repo_id))
        else:
            db.execute('UPDATE repos SET meta=?,updated_at=? WHERE id=?', (meta, now(), repo_id))


async def _ingest_task(repo_id, source, kind, branch, token, name):
    max_files = max(50, min(read_int('max_repo_files', 1500), 5000))
    max_file_bytes = max(32, min(read_int('max_repo_file_kb', 256), 2048)) * 1024
    max_mb = max(10, min(read_int('max_repo_mb', 300), 1000))
    max_total_chars = 24_000_000
    zip_path = None
    try:
        await _set_progress(repo_id, 'downloading' if kind == 'github' else 'scanning', status='ingesting')
        if kind == 'github':
            owner, repo, _ = parse_github(source)
            zip_path, used_branch = await _download_github_zip(owner, repo, branch, token, max_mb)
            branch = used_branch
            event('repo', f'Downloaded archive for {name} (branch {used_branch}); indexing files…')
            files = await asyncio.to_thread(_iter_zip_files, zip_path, max_files, max_file_bytes, max_total_chars)
        else:
            path = Path(source)
            if path.is_file() and path.suffix.lower() == '.zip':
                files = await asyncio.to_thread(_iter_zip_files, path, max_files, max_file_bytes, max_total_chars)
            elif path.is_dir():
                files = await asyncio.to_thread(_iter_local_files, path, max_files, max_file_bytes, max_total_chars)
            else:
                raise ValueError('Local source must be a folder or .zip file.')
        if not files:
            raise ValueError('No readable text/code files were found under the size and ignore limits.')

        await _set_progress(repo_id, 'indexing', 0, len(files))
        target_lines = max(30, min(read_int('repo_chunk_lines', 80), 300))
        overlap = max(0, min(read_int('repo_chunk_overlap', 12), 100))
        languages = {}
        deps = {}
        readme = ''
        chunk_count = 0
        for index, file in enumerate(files):
            path = file['path']
            content = file['content']
            language = language_from_path(path)
            languages[language] = languages.get(language, 0) + 1
            if Path(path).name.lower().startswith('readme') and not readme:
                readme = content
            if not path.startswith(('node_modules/', 'vendor/')) and Path(path).suffix.lower() in (
                    '.json', '.txt', '.toml', '.mod'):
                deps.update({d: content for d in [path]})
            symbols = extract_symbols(path, content)
            summary = summarize_text(content, 4)
            sha = hashlib.sha256(content.encode('utf-8', errors='ignore')).hexdigest()[:24]
            chunks = _chunk_lines(content, target_lines, overlap)
            with connect() as db:
                db.execute('DELETE FROM repo_chunks WHERE repo_id=? AND path=?', (repo_id, path))
                cur = db.execute(
                    'INSERT INTO repo_files(repo_id,path,language,size,sha,content,summary,symbols,created_at) '
                    'VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(repo_id,path) DO UPDATE SET '
                    'language=excluded.language,size=excluded.size,sha=excluded.sha,content=excluded.content,'
                    'summary=excluded.summary,symbols=excluded.symbols,created_at=excluded.created_at',
                    (repo_id, path, language, file.get('size', len(content)), sha, content,
                     summary, json.dumps(symbols), now()))
                file_id = cur.lastrowid
                rows = []
                for start, end, text in chunks:
                    vector = json.dumps(local_embed(text))
                    rows.append((repo_id, file_id, path, start, end, text, vector, 'local', now()))
                if rows:
                    db.executemany(
                        'INSERT INTO repo_chunks(repo_id,file_id,path,start_line,end_line,content,embedding,embedding_kind,created_at) '
                        'VALUES(?,?,?,?,?,?,?,?,?)', rows)
                chunk_count += len(rows)
            if index % 15 == 0 or index == len(files) - 1:
                await _set_progress(repo_id, 'indexing', index + 1, len(files))
                await asyncio.sleep(0)

        dep_map = {}
        for f in files:
            if Path(f['path']).name.lower() in {'package.json', 'requirements.txt', 'pyproject.toml',
                                                'cargo.toml', 'go.mod', 'gemfile', 'composer.json'}:
                dep_map[f['path']] = f['content']
        dependencies = parse_version_files(dep_map)
        structural = _structural_summary(name, source, files, languages, dependencies, readme)
        await _set_progress(repo_id, 'reasoning', len(files), len(files))
        architecture = await _architecture_summary(name, files, dependencies, readme)
        if architecture:
            structural += '\n\n## Model architecture brief\n' + architecture
        languages_text = ', '.join(f'{k}:{v}' for k, v in sorted(languages.items(), key=lambda x: -x[1]))
        with connect() as db:
            db.execute('UPDATE repos SET status=?,branch=?,file_count=?,chunk_count=?,languages=?,summary=?,'
                       'architecture=?,meta=?,updated_at=? WHERE id=?',
                       ('ready', branch or '', len(files), chunk_count, languages_text, structural,
                        architecture, json.dumps({'dependencies': dependencies[:80]}), now(), repo_id))
        # Persist what was learned into the shared long-term memory so NEXUS Core
        # can answer questions even without any generative model.
        await store_knowledge(f'Repository: {name}', structural, source, 'repository', 0.92, 'repository')
        if readme:
            await store_knowledge(f'{name} — README', clip(readme, 6000), source, 'repository', 0.8, 'repository')
        if architecture:
            await store_knowledge(f'{name} — architecture', architecture, source, 'repository', 0.86, 'repository')
        event('repo', f'Repository ready: {name} — {len(files)} files, {chunk_count} chunks, {len(languages)} languages.')
        await _set_progress(repo_id, 'ready', len(files), len(files), status='ready')
    except Exception as e:
        with connect() as db:
            db.execute('UPDATE repos SET status=?,meta=?,updated_at=? WHERE id=?',
                       ('failed', json.dumps({'phase': 'failed', 'error': str(e)[:800]}), now(), repo_id))
        event('warning', f'Repository ingestion failed for {name}: {e}')
    finally:
        if zip_path:
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def list_repos():
    with connect() as db:
        rows = db.execute('SELECT id,name,source,kind,branch,status,file_count,chunk_count,languages,'
                          'summary,architecture,meta,created_at,updated_at FROM repos ORDER BY id DESC').fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item['meta'] = json.loads(item.get('meta') or '{}')
        except Exception:
            item['meta'] = {}
        out.append(item)
    return out


def get_repo(repo_id):
    with connect() as db:
        row = db.execute('SELECT * FROM repos WHERE id=?', (repo_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item['meta'] = json.loads(item.get('meta') or '{}')
    except Exception:
        item['meta'] = {}
    return item


def list_files(repo_id, limit=3000):
    with connect() as db:
        rows = db.execute('SELECT id,path,language,size,summary,symbols FROM repo_files WHERE repo_id=? '
                          'ORDER BY path LIMIT ?', (repo_id, max(1, min(limit, 8000)))).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item['symbols'] = json.loads(item.get('symbols') or '[]')
        except Exception:
            item['symbols'] = []
        out.append(item)
    return out


def get_file(repo_id, path):
    with connect() as db:
        row = db.execute('SELECT * FROM repo_files WHERE repo_id=? AND path=?', (repo_id, path)).fetchone()
    return dict(row) if row else None


def build_tree(repo_id):
    files = list_files(repo_id, 8000)
    root = []
    index = {}
    for f in files:
        parts = f['path'].split('/')
        current = root
        key_prefix = ''
        for i, part in enumerate(parts):
            key_prefix = (key_prefix + '/' + part) if key_prefix else part
            node = index.get(key_prefix)
            if not node:
                node = {'name': part, 'path': key_prefix, 'type': 'file' if i == len(parts) - 1 else 'dir',
                        'size': f['size'] if i == len(parts) - 1 else 0,
                        'language': f['language'] if i == len(parts) - 1 else None, 'children': []}
                index[key_prefix] = node
                current.append(node)
            current = node['children']
    def sort_tree(nodes):
        nodes.sort(key=lambda n: (n['type'] == 'file', n['name'].lower()))
        for n in nodes:
            sort_tree(n['children'])
        return nodes
    return sort_tree(root)


async def search_chunks(query, repo_id=None, limit=8):
    qvec = local_embed(query)
    sql = 'SELECT rc.id,rc.repo_id,rc.path,rc.start_line,rc.end_line,rc.content,rc.embedding,rc.embedding_kind,r.name repo_name ' \
          'FROM repo_chunks rc JOIN repos r ON r.id=rc.repo_id'
    params = []
    if repo_id:
        sql += ' WHERE rc.repo_id=?'
        params.append(repo_id)
    sql += ' ORDER BY rc.id DESC LIMIT 16000'
    with connect() as db:
        rows = [dict(r) for r in db.execute(sql, params).fetchall()]
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
        score = semantic * 0.68 + min(lexical, 1.2) * 0.32 if semantic else lexical
        if score > 0.002:
            row['score'] = round(score, 4)
            row.pop('embedding', None)
            scored.append(row)
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:max(1, min(limit, 30))]


def repo_context_text(query, repo_id=None, limit=7):
    """Synchronous-safe wrapper is awkward because search is async; callers await
    search_chunks then format with this helper."""
    pass


def format_chunks(chunks):
    blocks = []
    for c in chunks:
        blocks.append(f"[{c.get('repo_name', 'repo')}] {c['path']}:{c['start_line']}-{c['end_line']} (score {c.get('score')})\n{c['content'][:2200]}")
    return '\n\n'.join(blocks)


def delete_repo(repo_id):
    with connect() as db:
        chunks = db.execute('DELETE FROM repo_chunks WHERE repo_id=?', (repo_id,)).rowcount
        db.execute('DELETE FROM repo_files WHERE repo_id=?', (repo_id,))
        db.execute('DELETE FROM repos WHERE id=?', (repo_id,))
    event('repo', f'Deleted repository index {repo_id} ({chunks} chunks).')
    return {'ok': True, 'chunks_deleted': chunks}
