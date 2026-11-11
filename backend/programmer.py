"""NEXUS Program Forge — write, save, verify and run programs.

Two honest generation paths:

1. **Offline recipes** (``backend/recipes.py``) — complete, curated programs that
   ship with their own ``--selftest``. When the checks pass the program is marked
   verified; that word means something because the code really ran.
2. **Local generative models** — used only when no recipe matches. The model's
   reply is parsed as JSON, written to the workspace and syntax-checked. It is
   never executed automatically, and the record says it is model-generated.

Programs live in ``data/programs/<slug>/``. Execution of any generated code is
gated behind the existing ``permission_shell`` switch and a timeout.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import DATA_DIR
from .database import audit, connect, event, now, read_bool, read_int, setting
from . import recipes

MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 4_000_000
MAX_PROGRAMS = 400

CODEGEN_SYSTEM = (
    'You are NEXUS Program Forge, a careful senior programmer. Reply with one '
    'JSON object and nothing else. Shape: {"name": str, "language": "python"|'
    '"javascript"|"powershell"|"sql"|"html", "kind": str, "summary": str, '
    '"entry": str, "run": str, "files": {relative_path: content}}. '
    'Write complete, runnable, dependency-light code. Prefer the Python standard '
    'library. Never include secrets, network callbacks, obfuscation or destructive '
    'commands. For Python include a `selftest()` function and a `--selftest` flag, '
    'but do not run the program yourself.'
)

CODE_EXTENSIONS = {'.py', '.js', '.ps1', '.sql', '.html', '.css', '.json', '.md', '.txt'}


class GenerationError(RuntimeError):
    """No honest way to generate the requested program."""


class ExecutionBlocked(RuntimeError):
    """Execution was refused because a permission is disabled."""


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #
def workspace_root():
    root = DATA_DIR / 'programs'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slugify(text, fallback='program'):
    value = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    value = re.sub(r'-{2,}', '-', value)[:48].strip('-')
    return value or fallback


def _unique_folder(slug):
    root = workspace_root()
    candidate = root / slug
    counter = 2
    while candidate.exists():
        candidate = root / f'{slug}-{counter}'
        counter += 1
    return candidate


def _safe_relative(name):
    """Return a safe relative path or raise ValueError."""
    text = str(name or '').replace('\\', '/').strip()
    if not text or text.startswith('/') or re.match(r'^[a-zA-Z]:', text):
        raise ValueError(f'unsafe file name: {name!r}')
    parts = [part for part in text.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' for part in parts):
        raise ValueError(f'unsafe file name: {name!r}')
    for part in parts:
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', part):
            raise ValueError(f'unsafe file name: {name!r}')
    return '/'.join(parts)


def _inside_workspace(path):
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(workspace_root().resolve())
        return resolved
    except (ValueError, OSError):
        return None


def _write_files(folder, files):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    total = 0
    for raw_name, content in (files or {}).items():
        name = _safe_relative(raw_name)
        text = str(content)
        size = len(text.encode('utf-8'))
        if size > MAX_FILE_BYTES:
            raise GenerationError(f'{name} is larger than the {MAX_FILE_BYTES // 1000} KB file limit')
        total += size
        if total > MAX_TOTAL_BYTES:
            raise GenerationError('the generated program exceeds the workspace size limit')
        target = (folder / name).resolve()
        if _inside_workspace(target) is None or folder.resolve() not in target.parents and target.parent != folder.resolve():
            raise GenerationError(f'unsafe output path: {name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8', newline='\n')
        written.append(name)
    if not written:
        raise GenerationError('the program has no files')
    return written


def _interpreter(language):
    language = (language or '').lower()
    if language == 'python':
        return [sys.executable]
    if language == 'javascript':
        return ['node']
    if language == 'powershell':
        return ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    return None


def _shell_enabled():
    return read_bool('permission_shell')


def _timeout():
    return max(5, min(read_int('code_exec_timeout', 20), 120))


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def _run_check(folder, entry, check, language):
    command = _interpreter(language)
    if not command:
        return {'name': check.get('name', 'check'), 'ok': False,
                'output': f'No interpreter is configured for {language}.', 'exit': -1}
    cmd = command + [str(Path(folder) / entry)] + [str(arg) for arg in check.get('args', [])]
    try:
        proc = subprocess.run(
            cmd, cwd=str(folder), input=check.get('stdin') or '',
            capture_output=True, text=True, timeout=_timeout(), shell=False)
    except subprocess.TimeoutExpired:
        return {'name': check.get('name', 'check'), 'ok': False,
                'output': f'Timed out after {_timeout()}s.', 'exit': -1}
    except FileNotFoundError:
        return {'name': check.get('name', 'check'), 'ok': False,
                'output': f'Interpreter not found: {command[0]}', 'exit': -1}
    except OSError as exc:
        return {'name': check.get('name', 'check'), 'ok': False,
                'output': f'Could not run the check: {exc}', 'exit': -1}
    output = (proc.stdout or '') + (proc.stderr or '')
    expect = check.get('expect')
    ok = proc.returncode == 0 and (not expect or expect in output)
    return {'name': check.get('name', 'check'), 'ok': ok,
            'output': output[-4000:], 'exit': proc.returncode}


def _compile_python(folder, files):
    problems = []
    for name in files:
        if not str(name).endswith('.py'):
            continue
        path = Path(folder) / name
        try:
            compile(path.read_text(encoding='utf-8'), name, 'exec')
        except (SyntaxError, ValueError) as exc:
            problems.append(f'{name}: {exc}')
    return problems


def _check_javascript(folder, files):
    if not _shell_enabled():
        return ['JavaScript syntax was not checked: shell permission is off.']
    notes = []
    for name in files:
        if not str(name).endswith('.js'):
            continue
        try:
            proc = subprocess.run(['node', '--check', str(Path(folder) / name)],
                                  cwd=str(folder), capture_output=True, text=True,
                                  timeout=30, shell=False)
            if proc.returncode != 0:
                notes.append(f'{name}: {(proc.stderr or proc.stdout).strip()[:400]}')
        except FileNotFoundError:
            notes.append('Node.js is not installed, so JavaScript was not syntax-checked.')
            break
        except OSError as exc:
            notes.append(f'JavaScript check failed: {exc}')
            break
    return notes


def verify_folder(folder, language, entry, files, checks=None,
                  allow_checks=True, source='recipe'):
    """Verify a written program. Returns (status, verified, report)."""
    folder = Path(folder)
    status = 'ready'
    verified = 0
    lines = []

    if language == 'python':
        problems = _compile_python(folder, files)
        if problems:
            status = 'syntax_error'
            lines.append('Syntax check failed:')
            lines.extend('  ' + problem for problem in problems)
        else:
            lines.append('Python syntax check passed.')
    elif language == 'javascript':
        problems = _check_javascript(folder, files)
        if problems:
            lines.extend(problems)
        else:
            lines.append('JavaScript syntax check passed.')
    elif language in ('html', 'sql'):
        lines.append('No automated syntax check for this language; files were written as-is.')

    if entry and not (folder / entry).exists():
        status = 'syntax_error'
        lines.append(f'Entry file is missing: {entry}')

    checks = list(checks or [])
    if source == 'model' and status == 'ready' and not checks:
        status = 'unverified'
        lines.append('Model-generated: syntax was checked where possible, but NEXUS did not execute it. '
                     'Review the code before running it.')
    if status == 'syntax_error' or not checks:
        if status == 'ready' and not checks:
            lines.append('Ready to run. No automated self-test is defined for this program.')
        return status, verified, '\n'.join(lines)

    if not allow_checks:
        lines.append('Self-tests were skipped: shell permission is off, so no generated code was executed.')
        return 'unverified', 0, '\n'.join(lines)

    if not _shell_enabled():
        lines.append('Self-tests were skipped: enable “Run shell commands” in Permissions to execute them.')
        return 'unverified', 0, '\n'.join(lines)

    results = [_run_check(folder, entry, check, language) for check in checks]
    lines.append('Self-tests:')
    for result in results:
        lines.append(f"  [{'PASS' if result['ok'] else 'FAIL'}] {result['name']} (exit {result['exit']})")
        if not result['ok'] and result['output'].strip():
            lines.extend('    ' + line for line in result['output'].strip().splitlines()[-8:])
    passed = all(result['ok'] for result in results)
    status = 'verified' if passed else 'checks_failed'
    verified = 1 if passed else 0
    return status, verified, '\n'.join(lines)


# --------------------------------------------------------------------------- #
# Model generation
# --------------------------------------------------------------------------- #
async def resolve_codegen_provider():
    choice = (setting('codegen_provider', 'auto') or 'auto').strip().lower()
    if choice in ('off', 'none', 'nexus', 'disabled'):
        return None
    if choice in ('ollama', 'llamacpp', 'openai'):
        return choice
    # auto: first online provider other than the native brain
    try:
        from .providers import provider_catalog
        catalog = await provider_catalog()
    except Exception:
        return None
    for entry in catalog:
        if entry.get('id') != 'nexus' and entry.get('online'):
            return entry['id']
    return None


def _extract_json(text):
    text = (text or '').strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if fenced:
        text = fenced.group(1)
    if not text.startswith('{'):
        start = text.find('{')
        end = text.rfind('}')
        if start < 0 or end <= start:
            raise GenerationError('The model did not return a JSON program.')
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError(f'The model returned invalid JSON: {exc}') from exc


def parse_model_program(text, request):
    data = _extract_json(text)
    files = data.get('files')
    if not isinstance(files, dict) or not files:
        raise GenerationError('The model response has no files.')
    clean = {}
    for name, content in files.items():
        try:
            safe = _safe_relative(name)
        except ValueError as exc:
            raise GenerationError(str(exc)) from exc
        if not isinstance(content, str):
            raise GenerationError(f'The model returned non-text content for {safe}.')
        clean[safe] = content

    language = str(data.get('language') or 'python').strip().lower()
    aliases = {'js': 'javascript', 'node': 'javascript', 'ps1': 'powershell', 'htm': 'html'}
    language = aliases.get(language, language)
    if language not in ('python', 'javascript', 'powershell', 'sql', 'html'):
        language = 'python'

    entry = str(data.get('entry') or '').strip()
    if entry not in clean:
        preferred = [name for name in clean if name.endswith(
            {'python': '.py', 'javascript': '.js', 'powershell': '.ps1',
             'sql': '.sql', 'html': '.html'}[language])]
        entry = preferred[0] if preferred else sorted(clean)[0]

    name = str(data.get('name') or 'Model Program').strip()[:80] or 'Model Program'
    summary = str(data.get('summary') or 'A program generated by a local model.').strip()[:400]
    run = str(data.get('run') or '').strip()[:200]
    kind = str(data.get('kind') or 'script').strip()[:40] or 'script'
    return {
        'id': 'model-' + _slugify(name),
        'title': name,
        'language': language,
        'kind': kind,
        'summary': summary,
        'files': clean,
        'entry': entry,
        'checks': [],
        'run': run,
        'request': request,
    }


async def model_generate(request, provider=None):
    provider = provider or await resolve_codegen_provider()
    if not provider:
        raise GenerationError(
            'No offline recipe matches this request, and no local model is available. '
            'Start Ollama (or select a model in Providers), or ask for one of the built-in programs.')
    prompt = (
        f'Write a program for this request:\n{request}\n\n'
        'Return the JSON object described in the system prompt. Include every file '
        'needed to run it, and keep it small and self-contained.'
    )
    from .providers import chat as provider_chat
    try:
        text = await provider_chat(
            [{'role': 'user', 'content': prompt}],
            system=CODEGEN_SYSTEM, provider=provider)
    except Exception as exc:
        raise GenerationError(f'The {provider} model failed: {exc}') from exc
    built = parse_model_program(text, request)
    built['generator'] = provider
    return built


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _row(row):
    return dict(row) if row is not None else None


def _default_run(record):
    language = record.get('language') or ''
    entry = record.get('entry') or ''
    command = _interpreter(language)
    if command and entry:
        return ' '.join(command + [entry])
    if language == 'html' and entry:
        return f'start {entry}'
    return ''


def _decode(record, hint=False):
    if record and isinstance(record.get('files'), str):
        try:
            record['files'] = json.loads(record['files'])
        except (TypeError, json.JSONDecodeError):
            record['files'] = []
    if record and not record.get('run'):
        run = ''
        if hint:
            try:
                run = (recipes.build(recipe_id=(record.get('generator') or '').split(':', 1)[1])
                       .get('run') or '').strip()
            except Exception:
                run = ''
        record['run'] = run or _default_run(record)
    return record


def list_programs(limit=80):
    with connect() as db:
        rows = db.execute('SELECT * FROM programs ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    return [_decode(_row(row)) for row in rows]


def get_program(program_id):
    with connect() as db:
        row = db.execute('SELECT * FROM programs WHERE id=?', (int(program_id),)).fetchone()
    return _decode(_row(row), hint=True)


def _insert(built, request, source, generator, folder, files, status, verified, report):
    stamp = now()
    entry = built.get('entry', '')
    with connect() as db:
        cur = db.execute(
            'INSERT INTO programs(name,slug,request,language,kind,summary,directory,entry,'
            'files,source,generator,status,verified,verification,last_run,last_output,'
            'last_exit,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (built['title'], folder.name, request, built['language'], built['kind'],
             built.get('summary', ''), str(folder), entry, json.dumps(files),
             source, generator, status, verified, report, '', '', 0, stamp, stamp))
        return cur.lastrowid


def _persist(built, request, source, generator):
    slug = _slugify(built['title'])
    folder = _unique_folder(slug)
    files = _write_files(folder, built['files'])
    checks = built.get('checks') or []
    status, verified, report = verify_folder(
        folder, built['language'], built.get('entry', ''), files, checks,
        allow_checks=(source == 'recipe'), source=source)
    program_id = _insert(built, request, source, generator, folder, files, status, verified, report)
    event('program', f'Program #{program_id} "{built["title"]}" written ({source}, {status}).')
    audit('program.forge', f'id={program_id} source={source} language={built["language"]} status={status}')
    return get_program(program_id)


# --------------------------------------------------------------------------- #
# Public generation entry point
# --------------------------------------------------------------------------- #
async def forge(request, recipe_id=None, provider=None, context=None):
    """Generate, write, verify and store a program. Raises GenerationError."""
    request = (request or '').strip()
    if not request and not recipe_id:
        raise GenerationError('Describe the program you want, or pick a recipe.')

    offline_error = ''
    try:
        built = recipes.build(recipe_id=recipe_id, request=request, context=context)
    except LookupError as exc:
        offline_error = str(exc)
        built = await model_generate(request, provider=provider)
        built['request'] = request
        generator = 'model:' + built.get('generator', 'unknown')
        title = f'Model: {built["title"]}'
        built['title'] = title
        return _persist(dict(built), request, 'model', generator)

    if not request:
        request = f'offline recipe: {built["title"]}'
    generator = 'recipe:' + built['id']
    return _persist(dict(built), request, 'recipe', generator)


def _recipe_for(record):
    generator = record.get('generator') or ''
    if generator.startswith('recipe:'):
        try:
            return recipes.build(recipe_id=generator.split(':', 1)[1])
        except LookupError:
            return None
    return None


def verify_program(program_id):
    record = get_program(program_id)
    if not record:
        raise LookupError(f'no program with id {program_id}')
    folder = _inside_workspace(record['directory'])
    if folder is None:
        raise GenerationError('The program directory is outside the workspace.')
    recipe = _recipe_for(record)
    checks = (recipe or {}).get('checks') or []
    files = record.get('files') or []
    entry = record.get('entry') or (recipe or {}).get('entry') or ''
    status, verified, report = verify_folder(
        folder, record['language'], entry, files, checks,
        allow_checks=(record.get('source') == 'recipe'), source=record.get('source', ''))
    with connect() as db:
        db.execute('UPDATE programs SET status=?,verified=?,verification=?,updated_at=? WHERE id=?',
                   (status, verified, report, now(), program_id))
    audit('program.verify', f'id={program_id} status={status}')
    return get_program(program_id)


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def run_program(program_id, args=None):
    record = get_program(program_id)
    if not record:
        raise LookupError(f'no program with id {program_id}')
    if not _shell_enabled():
        raise ExecutionBlocked(
            'Running generated code needs the “Run shell commands” permission. '
            'Enable it in Permissions, then try again.')
    command = _interpreter(record['language'])
    if not command:
        raise ExecutionBlocked(
            f'This program is {record["language"]}; open its files instead of running it here.')
    folder = _inside_workspace(record['directory'])
    if folder is None or not folder.is_dir():
        raise GenerationError('The program directory is missing from the workspace.')
    entry_path = folder / record['entry']
    if not entry_path.exists():
        raise GenerationError(f'Entry file is missing: {record["entry"]}')
    extra = [str(item)[:200] for item in (args or [])][:20]
    full = command + [str(entry_path)] + extra
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        proc = subprocess.run(full, cwd=str(folder), capture_output=True, text=True,
                              timeout=_timeout(), shell=False)
        output = (proc.stdout or '') + (('\n[stderr]\n' + proc.stderr) if proc.stderr else '')
        exit_code = proc.returncode
        ok = exit_code == 0
    except subprocess.TimeoutExpired:
        output = f'Timed out after {_timeout()} seconds.'
        exit_code = -1
        ok = False
    except OSError as exc:
        output = f'Could not start the program: {exc}'
        exit_code = -1
        ok = False
    output = output[-12000:]
    with connect() as db:
        db.execute('UPDATE programs SET last_run=?,last_output=?,last_exit=?,updated_at=? WHERE id=?',
                   (started, output, exit_code, now(), program_id))
    audit('program.run', f'id={program_id} exit={exit_code}')
    return {'ok': ok, 'exit': exit_code, 'output': output, 'command': ' '.join(full),
            'ran_at': started, 'program': get_program(program_id)}


# --------------------------------------------------------------------------- #
# Files and deletion
# --------------------------------------------------------------------------- #
def read_program_file(program_id, name):
    record = get_program(program_id)
    if not record:
        raise LookupError(f'no program with id {program_id}')
    folder = _inside_workspace(record['directory'])
    if folder is None:
        raise GenerationError('The program directory is outside the workspace.')
    safe = _safe_relative(name)
    target = (folder / safe).resolve()
    if folder.resolve() not in target.parents and target.parent != folder.resolve():
        raise GenerationError('Unsafe file path.')
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(safe)
    data = target.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
    return safe, data.decode('utf-8', errors='replace')


def delete_program(program_id):
    record = get_program(program_id)
    if not record:
        raise LookupError(f'no program with id {program_id}')
    folder = _inside_workspace(record['directory'])
    if folder and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    with connect() as db:
        db.execute('DELETE FROM programs WHERE id=?', (int(program_id),))
    audit('program.delete', f'id={program_id} folder={record.get("directory", "")}')
    event('program', f'Program #{program_id} deleted.')
    return True


def status():
    programs = list_programs(1000)
    verified = sum(1 for item in programs if item.get('verified'))
    return {
        'total': len(programs),
        'verified': verified,
        'recipes': len(recipes.catalog()),
        'languages': recipes.languages(),
        'shell': _shell_enabled(),
        'codegen_provider': setting('codegen_provider', 'auto'),
    }


def capability_summary():
    info = status()
    return (
        f'The Program Forge can write, save, verify and run programs. It ships with '
        f'{info["recipes"]} offline templates across {", ".join(info["languages"])}. '
        'Templates carry real self-tests; a program is only marked verified when they pass. '
        'For other requests it can ask a local model, but those results are syntax-checked '
        'and never executed automatically.'
    )
