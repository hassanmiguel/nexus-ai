"""Deterministic tool router for chat.

Local models are unreliable at emitting structured tool calls, so NEXUS also
supports explicit natural-language intents. Every action goes through the same
permission + audit layer as the Tools page.
"""
import json
import re

from .textutil import clip
from .tools import run_tool


def _match(pattern, text, flags=re.I):
    return re.search(pattern, text, flags)


def _unquote(value):
    return (value or '').strip().strip('"').strip("'")


async def execute_intents(message: str):
    text = (message or '').strip()
    if not text:
        return []
    jobs = []

    m = _match(r'(?:^|\b)(?:search(?:\s+the)?\s+web(?:\s+for)?|web\s+search|google)\s+(.+)', text)
    if m:
        jobs.append(('web_search', {'query': _unquote(m.group(1))[:300], 'limit': 5}))

    for m in re.finditer(r'https?://[^\s<>"\']+', text):
        url = m.group(0).rstrip('.,);')
        if re.search(r'(?:fetch|open|visit|summarize|summarise|read)\s+(?:the\s+)?(?:url\s+)?' + re.escape(url), text, re.I):
            jobs.append(('web_fetch', {'url': url}))

    m = _match(r'(?:learn|index|ingest|study|import|add)\s+(?:this\s+)?(?:repo(?:sitory)?\s*)?(https?://github\.com/[^\s]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', text)
    if m:
        jobs.append(('learn_repo', {'source': _unquote(m.group(1))}))

    m = _match(r'(?:read|cat)\s+(?:the\s+)?(?:file\s+)?["\']([^"\']+)["\']', text)
    if not m:
        m = _match(r'(?:read|cat)\s+(?:the\s+)?(?:file\s+)?([A-Za-z]:\\[^\n]+|~[/\\][^\n]+)', text)
    if m:
        jobs.append(('read_file', {'path': _unquote(m.group(1)), 'end_line': 240}))

    m = _match(r'(?:list|ls|dir)\s+(?:the\s+)?(?:files\s+in\s+|folder\s+|directory\s+)?["\']([^"\']+)["\']', text)
    if not m:
        m = _match(r'(?:list|ls|dir)\s+(?:the\s+)?(?:files\s+in\s+|folder\s+|directory\s+)?([A-Za-z]:\\[^\n]+|~[/\\][^\n]+)', text)
    if m:
        jobs.append(('list_dir', {'path': _unquote(m.group(1))}))

    m = _match(r'(?:find|search\s+files?|glob)\s+(.+?)\s+(?:in|under)\s+["\']?(.+?)["\']?$', text)
    if m:
        jobs.append(('search_files', {'pattern': _unquote(m.group(1)), 'root': _unquote(m.group(2))}))

    m = _match(r'(?:run|execute)\s+(?:the\s+)?(?:command|shell|powershell)\s*[:\-]?\s*(.+)', text)
    if m:
        jobs.append(('run_command', {'command': _unquote(m.group(1))}))

    if _match(r'\b(?:system info|pc specs|hardware info|hardware profile|my specs)\b', text):
        jobs.append(('system_info', {}))

    # De-duplicate and cap work per message.
    unique = []
    seen = set()
    for name, args in jobs:
        key = name + json.dumps(args, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append((name, args))
    results = []
    for name, args in unique[:4]:
        try:
            result = await run_tool(name, args)
        except Exception as e:
            result = {'ok': False, 'tool': name, 'error': str(e)}
        results.append(result)
    return results


def format_results(results):
    if not results:
        return ''
    blocks = []
    for item in results:
        status = 'OK' if item.get('ok') else 'DENIED/ERROR'
        body = item.get('output') or item.get('error') or ''
        blocks.append(f'[{item.get("tool")} · {status}]\n{clip(body, 6000)}')
    return '\n\n'.join(blocks)


def intent_names(results):
    return [item.get('tool') for item in results if item.get('tool')]
