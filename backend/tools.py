"""Permission-gated local tools.

Every capability is closed by default. Calls are checked against explicit
permission switches, path allow-roots and a destructive-command deny-list, then
written to an audit trail. This is deliberately conservative: the assistant can
only touch what the user has granted.
"""
import asyncio
import glob
import json
import os
import re
import subprocess
from pathlib import Path

from .database import connect, now, setting, read_bool, audit, event
from .textutil import clip

MAX_OUTPUT = 20000
MAX_READ = 600_000

TOOL_SPECS = [
    {'name': 'web_search', 'permission': 'internet', 'args': {'query': 'string', 'limit': 'int (1-8)'},
     'description': 'Search the public web with the research crawler.'},
    {'name': 'web_fetch', 'permission': 'internet', 'args': {'url': 'https url'},
     'description': 'Fetch a public HTTPS page and return readable text.'},
    {'name': 'system_info', 'permission': 'pc_read', 'args': {},
     'description': 'Read CPU, RAM, GPU and platform information.'},
    {'name': 'list_dir', 'permission': 'pc_read', 'args': {'path': 'string'},
     'description': 'List a directory inside an allowed root.'},
    {'name': 'read_file', 'permission': 'pc_read', 'args': {'path': 'string', 'start_line': 'int?', 'end_line': 'int?'},
     'description': 'Read a text file inside an allowed root.'},
    {'name': 'search_files', 'permission': 'pc_read', 'args': {'root': 'string', 'pattern': 'glob'},
     'description': 'Find files by glob inside an allowed root.'},
    {'name': 'write_file', 'permission': 'pc_write', 'args': {'path': 'string', 'content': 'string', 'overwrite': 'bool'},
     'description': 'Write a text file inside an allowed root.'},
    {'name': 'run_command', 'permission': 'shell', 'args': {'command': 'string', 'cwd': 'string?', 'timeout': 'int?'},
     'description': 'Run a PowerShell command inside an allowed root (destructive commands blocked).'},
    {'name': 'learn_repo', 'permission': 'internet', 'args': {'source': 'github url / owner/repo / local path', 'branch': 'string?'},
     'description': 'Clone-index a repository into NEXUS long-term memory.'},
]

PERMISSION_LABELS = {
    'internet': 'Internet access',
    'pc_read': 'Read local files',
    'pc_write': 'Write local files',
    'shell': 'Run shell commands',
}

DANGEROUS = [
    r'\brm\s+-rf\s+/(?:\s|$)', r'\brm\s+-rf\s+[a-z]:\\?\s*$', r'\brd\s+/s\s+/q\s+[a-z]:\\?\s*$',
    r'\bdel\s+/f\s+/s\s+/q\s+[a-z]:\\?\s*$', r'\bformat\s+[a-z]:', r'\bmkfs(?:\.|\s)',
    r'\bshutdown\b', r'\breboot\b', r'\bdiskpart\b', r'\bbcdedit\b',
    r'\breg\s+delete\s+hklm', r'\btakeown\s+/f\s+[a-z]:\\?\s*$',
    r'\b(?:iwr|invoke-webrequest|curl|wget)\b[^\n|]*\|\s*(?:iex|invoke-expression|sh|bash|powershell)\b',
    r'\bcipher\s+/w\b', r'\bnet\s+user\s+\S+\s+\S+\s+/add\b',
    r':\(\)\s*\{\s*:\|:&\s*\};:',  # fork bomb
]


def permissions():
    return {
        'internet': read_bool('permission_internet'),
        'pc_read': read_bool('permission_pc_read'),
        'pc_write': read_bool('permission_pc_write'),
        'shell': read_bool('permission_shell'),
        'allowed_roots': [str(p) for p in allowed_roots()],
        'allowed_commands': [x.strip() for x in (setting('allowed_commands', '') or '').splitlines() if x.strip()],
    }


def update_permissions(data: dict):
    mapping = {
        'internet': 'permission_internet',
        'pc_read': 'permission_pc_read',
        'pc_write': 'permission_pc_write',
        'shell': 'permission_shell',
    }
    from .database import set_setting
    for key, setting_key in mapping.items():
        if key in data and data[key] is not None:
            set_setting(setting_key, 'true' if data[key] else 'false')
    if data.get('allowed_roots') is not None:
        set_setting('allowed_roots', data['allowed_roots'])
    if data.get('allowed_commands') is not None:
        set_setting('allowed_commands', data['allowed_commands'])
    audit('permissions.update', json.dumps({k: v for k, v in data.items() if v is not None})[:2000])
    return permissions()


def _split_roots(raw=None):
    raw = setting('allowed_roots', '') if raw is None else raw
    parts = [p.strip().strip('"') for p in re.split(r'[;\n\r]+', raw or '') if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(Path(os.path.expandvars(os.path.expanduser(p))).resolve())
        except Exception:
            continue
    return out


def allowed_roots():
    return _split_roots()


def _inside_allowed(path: Path, must_exist=True):
    if not allowed_roots():
        return False, 'No allowed roots configured. Add a folder in Permissions first.'
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        return False, 'Invalid path.'
    for root in allowed_roots():
        try:
            resolved.relative_to(root)
            if must_exist and not resolved.exists():
                return False, f'Path does not exist: {resolved}'
            return True, str(resolved)
        except ValueError:
            continue
    return False, f'Path is outside the allowed roots: {resolved}'


def _deny_command(command: str):
    text = (command or '').strip()
    if not text:
        return 'Empty command.'
    for pattern in DANGEROUS:
        if re.search(pattern, text, re.I):
            return 'Command blocked by the destructive-command policy.'
    allow = [x.strip() for x in (setting('allowed_commands', '') or '').splitlines() if x.strip()]
    if allow and not any(text.startswith(prefix) for prefix in allow):
        return 'Command is not in the configured command allow-list.'
    return None


def _record(tool, args, result, status='ok'):
    try:
        with connect() as db:
            db.execute('INSERT INTO tool_runs(tool,args,result,status,created_at) VALUES(?,?,?,?,?)',
                       (tool, clip(json.dumps(args, default=str), 3000), clip(result, 12000), status, now()))
    except Exception:
        pass


async def _web_search(args):
    from .research import search_web
    query = str(args.get('query', '')).strip()
    limit = max(1, min(int(args.get('limit', 5) or 5), 8))
    if not query:
        return False, 'A query is required.'
    results = await search_web(query, limit=limit)
    return True, json.dumps(results, indent=2)


async def _web_fetch(args):
    from .research import fetch_page
    url = str(args.get('url', '')).strip()
    if not url:
        return False, 'A URL is required.'
    title, text = await fetch_page(url)
    return True, f'# {title}\nURL: {url}\n\n{clip(text, 12000)}'


def _system_info(args):
    from .optimization import hardware_profile
    import platform
    profile = hardware_profile()
    profile['python'] = platform.python_version()
    profile['user_home'] = str(Path.home())
    profile['allowed_roots'] = [str(p) for p in allowed_roots()]
    return True, json.dumps(profile, indent=2)


def _list_dir(args):
    ok, resolved = _inside_allowed(Path(str(args.get('path', ''))))
    if not ok:
        return False, resolved
    root = Path(resolved)
    if not root.is_dir():
        return False, 'Path is not a directory.'
    rows = []
    try:
        for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:500]:
            try:
                size = child.stat().st_size if child.is_file() else 0
            except Exception:
                size = 0
            rows.append({'name': child.name, 'type': 'dir' if child.is_dir() else 'file', 'size': size})
    except PermissionError as e:
        return False, f'Permission denied: {e}'
    return True, json.dumps({'path': str(root), 'entries': rows}, indent=2)


def _read_file(args):
    ok, resolved = _inside_allowed(Path(str(args.get('path', ''))))
    if not ok:
        return False, resolved
    path = Path(resolved)
    if not path.is_file():
        return False, 'Path is not a file.'
    if path.stat().st_size > MAX_READ:
        return False, f'File is larger than {MAX_READ // 1000} KB limit.'
    try:
        data = path.read_bytes()
    except PermissionError as e:
        return False, f'Permission denied: {e}'
    if b'\x00' in data[:4096]:
        return False, 'Refusing to read a binary file.'
    text = data.decode('utf-8', errors='replace')
    lines = text.splitlines()
    start = max(1, int(args.get('start_line', 1) or 1))
    end = min(len(lines), int(args.get('end_line', min(len(lines), 400)) or min(len(lines), 400)))
    snippet = '\n'.join(f'{i:>5} | {lines[i - 1]}' for i in range(start, end + 1))
    return True, f'{path} (lines {start}-{end} of {len(lines)})\n\n{clip(snippet, MAX_OUTPUT)}'


def _search_files(args):
    root_arg = str(args.get('root', '')).strip()
    pattern = str(args.get('pattern', '*')).strip() or '*'
    ok, resolved = _inside_allowed(Path(root_arg))
    if not ok:
        return False, resolved
    root = Path(resolved)
    if not root.is_dir():
        return False, 'Root is not a directory.'
    if '..' in pattern or pattern.startswith(('/', '\\')):
        return False, 'Invalid glob pattern.'
    matches = []
    try:
        for p in glob.iglob(str(root / '**' / pattern), recursive=True):
            matches.append(p)
            if len(matches) >= 250:
                break
    except Exception as e:
        return False, str(e)
    return True, '\n'.join(matches) if matches else 'No matches.'


def _write_file(args):
    ok, resolved = _inside_allowed(Path(str(args.get('path', ''))), must_exist=False)
    if not ok:
        return False, resolved
    path = Path(resolved)
    content = str(args.get('content', ''))
    if len(content) > 1_000_000:
        return False, 'Content larger than 1 MB limit.'
    overwrite = bool(args.get('overwrite', False))
    if path.exists() and not overwrite:
        return False, 'File exists. Pass overwrite=true to replace it.'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True, f'Wrote {len(content)} characters to {path}'


def _run_command(args):
    command = str(args.get('command', '')).strip()
    denied = _deny_command(command)
    if denied:
        return False, denied
    cwd_arg = str(args.get('cwd', '') or '').strip()
    cwd = None
    if cwd_arg:
        ok, resolved = _inside_allowed(Path(cwd_arg))
        if not ok:
            return False, resolved
        cwd = resolved
    elif allowed_roots():
        cwd = str(allowed_roots()[0])
    timeout = max(1, min(int(args.get('timeout', 60) or 60), 180))
    try:
        proc = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
            cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=False)
        output = (proc.stdout or '') + (('\n[stderr]\n' + proc.stderr) if proc.stderr else '')
        return proc.returncode == 0, clip(output or f'[exit code {proc.returncode}]', MAX_OUTPUT)
    except subprocess.TimeoutExpired:
        return False, f'Command timed out after {timeout}s.'
    except Exception as e:
        return False, str(e)


async def _learn_repo(args):
    from .repos import start_ingest
    source = str(args.get('source', '')).strip()
    if not source:
        return False, 'A repository URL or local path is required.'
    repo_id = await start_ingest(source, branch=args.get('branch') or None,
                                 token=args.get('token') or None)
    return True, f'Repository ingestion started (repo id {repo_id}). Follow progress in Repo Lab.'


async def run_tool(name: str, args: dict | None = None):
    args = args or {}
    spec = next((s for s in TOOL_SPECS if s['name'] == name), None)
    if not spec:
        return {'ok': False, 'error': f'Unknown tool: {name}', 'tool': name}
    perm = spec['permission']
    if not read_bool(f'permission_{perm}'):
        audit(f'tool.{name}', f'Denied: permission {perm} is off. args={json.dumps(args, default=str)[:1000]}', False)
        _record(name, args, f'Permission denied: {perm}', 'denied')
        return {'ok': False, 'error': f'Permission denied. Enable “{PERMISSION_LABELS.get(perm, perm)}” in Permissions first.',
                'tool': name, 'permission': perm}
    try:
        if name == 'web_search':
            ok, output = await _web_search(args)
        elif name == 'web_fetch':
            ok, output = await _web_fetch(args)
        elif name == 'system_info':
            ok, output = _system_info(args)
        elif name == 'list_dir':
            ok, output = _list_dir(args)
        elif name == 'read_file':
            ok, output = _read_file(args)
        elif name == 'search_files':
            ok, output = _search_files(args)
        elif name == 'write_file':
            ok, output = _write_file(args)
        elif name == 'run_command':
            ok, output = await asyncio.to_thread(_run_command, args)
        elif name == 'learn_repo':
            ok, output = await _learn_repo(args)
        else:
            ok, output = False, 'Tool not implemented.'
    except Exception as e:
        ok, output = False, f'{type(e).__name__}: {e}'
    audit(f'tool.{name}', f'{"ok" if ok else "failed"}: {clip(str(output), 1500)}', ok)
    _record(name, args, output, 'ok' if ok else 'error')
    return {'ok': ok, 'tool': name, 'output': clip(output, MAX_OUTPUT)}


def tool_context_for_prompt():
    perms = permissions()
    enabled = [PERMISSION_LABELS[k] for k in ('internet', 'pc_read', 'pc_write', 'shell') if perms[k]]
    return ('Enabled tools: ' + (', '.join(enabled) if enabled else 'none (all local tools disabled)') +
            '. Allowed roots: ' + (', '.join(perms['allowed_roots']) if perms['allowed_roots'] else 'none') + '.')


def recent_audit(limit=120):
    with connect() as db:
        rows = db.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?', (max(1, min(limit, 500)),)).fetchall()
    return [dict(r) for r in rows]


def recent_tool_runs(limit=80):
    with connect() as db:
        rows = db.execute('SELECT * FROM tool_runs ORDER BY id DESC LIMIT ?', (max(1, min(limit, 300)),)).fetchall()
    return [dict(r) for r in rows]
