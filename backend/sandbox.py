"""Hardened local execution sandbox for generated code.

This is *process-level* isolation, not a virtual machine. It provides:

* an explicit interpreter/compiler allow-list (argv arrays, never ``shell=True``);
* a fresh temporary working directory under ``data/sandbox``;
* path traversal and size validation for written files;
* a scrubbed environment (API keys, tokens and secrets are removed);
* wall-clock timeouts, output caps and a resident-memory watchdog;
* process-tree termination on timeout or memory pressure.

Known limitations, reported honestly by the UI:

* generated code runs as the same OS user, so it can read files that user can
  read and can open outbound sockets. NEXUS does not run untrusted third-party
  binaries; it runs code it generated, gated behind ``permission_shell``.
* Windows has no cgroup/rlimit equivalent here; the memory watchdog kills the
  process after the fact instead of preventing allocation.

Any code that needs stronger isolation should run inside a container or VM
managed outside NEXUS.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .config import DATA_DIR
from .database import read_bool, read_int

SANDBOX_ROOT = DATA_DIR / 'sandbox'
SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)

MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 200_000
DEFAULT_TIMEOUT = 20
DEFAULT_MEMORY_MB = 768

# Files are only ever written with these names. Anything else is rejected.
SAFE_NAME = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/')

SPEC = {
    'python': {'ext': 'py', 'kind': 'interpreted', 'label': 'Python',
               'which': None, 'run': lambda entry: [sys.executable, '-B', entry]},
    'javascript': {'ext': 'js', 'kind': 'interpreted', 'label': 'JavaScript', 'which': 'node',
                   'run': lambda entry: [shutil.which('node'), entry]},
    'typescript': {'ext': 'ts', 'kind': 'compiled', 'label': 'TypeScript', 'which': 'tsc',
                   'compile': lambda entry: [shutil.which('tsc'), '--target', 'es2020', '--outDir', 'dist', entry],
                   'run': lambda entry: [shutil.which('node'), str(Path('dist') / (Path(entry).stem + '.js'))]},
    'php': {'ext': 'php', 'kind': 'interpreted', 'label': 'PHP', 'which': 'php',
            'run': lambda entry: [shutil.which('php'), entry]},
    'sql': {'ext': 'sql', 'kind': 'interpreted', 'label': 'SQL (SQLite)', 'which': None,
            'run': lambda entry: [sys.executable, '-I', '-B', '_sql_runner.py', entry]},
    'c': {'ext': 'c', 'kind': 'compiled', 'label': 'C', 'which': 'gcc',
          'compile': lambda entry: [shutil.which('gcc'), '-O2', '-std=c11', entry, '-o', 'program.exe'],
          'run': lambda entry: [str(Path('program.exe'))]},
    'cpp': {'ext': 'cpp', 'kind': 'compiled', 'label': 'C++', 'which': 'g++',
            'compile': lambda entry: [shutil.which('g++'), '-O2', '-std=c++17', entry, '-o', 'program.exe'],
            'run': lambda entry: [str(Path('program.exe'))]},
    'rust': {'ext': 'rs', 'kind': 'compiled', 'label': 'Rust', 'which': 'rustc',
             'compile': lambda entry: [shutil.which('rustc'), '-O', entry, '-o', 'program.exe'],
             'run': lambda entry: [str(Path('program.exe'))]},
    'go': {'ext': 'go', 'kind': 'compiled', 'label': 'Go', 'which': 'go',
           'compile': lambda entry: [shutil.which('go'), 'build', '-o', 'program.exe', entry],
           'run': lambda entry: [str(Path('program.exe'))]},
    'java': {'ext': 'java', 'kind': 'compiled', 'label': 'Java', 'which': 'javac',
             'compile': lambda entry: [shutil.which('javac'), entry],
             'run': lambda entry: [shutil.which('java'), '-cp', '.', Path(entry).stem]},
    'csharp': {'ext': 'cs', 'kind': 'compiled', 'label': 'C#', 'which': 'dotnet',
               'compile': lambda entry: [shutil.which('dotnet'), 'build', '-v', 'q'],
               'run': lambda entry: [shutil.which('dotnet'), 'run', '--no-build']},
    'html': {'ext': 'html', 'kind': 'static', 'label': 'HTML', 'which': None},
    'css': {'ext': 'css', 'kind': 'static', 'label': 'CSS', 'which': None},
}

SQL_RUNNER = '''import sqlite3, sys, pathlib
sql = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
db = sqlite3.connect(":memory:")
try:
    db.executescript(sql)
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        print("table:", row[0])
    print("SQL OK")
except Exception as exc:
    print("SQL ERROR:", exc)
    sys.exit(1)
'''


class ExecutionBlocked(RuntimeError):
    """Raised when the user has not granted shell execution."""


class SandboxError(ValueError):
    """Raised for invalid file names, sizes or unsupported languages."""


_TOOLCHAIN_CACHE = None


def _which(name):
    return shutil.which(name) if name else None


def toolchains():
    """Report which real compilers/interpreters exist on this machine."""
    global _TOOLCHAIN_CACHE
    if _TOOLCHAIN_CACHE is not None:
        return _TOOLCHAIN_CACHE
    out = {}
    for lang, spec in SPEC.items():
        if lang == 'python':
            out[lang] = {'available': True, 'path': sys.executable, 'executable': spec['kind'] != 'static',
                         'label': spec['label'], 'kind': spec['kind']}
            continue
        if spec['kind'] == 'static':
            out[lang] = {'available': True, 'path': '', 'executable': False, 'label': spec['label'], 'kind': 'static'}
            continue
        path = _which(spec.get('which'))
        # SQL is executed through the bundled Python runner, so it is available whenever Python is.
        if lang == 'sql':
            path = sys.executable
        out[lang] = {'available': bool(path), 'path': path or '', 'executable': bool(path),
                     'label': spec['label'], 'kind': spec['kind']}
    _TOOLCHAIN_CACHE = out
    return out


def refresh_toolchains():
    global _TOOLCHAIN_CACHE
    _TOOLCHAIN_CACHE = None
    return toolchains()


def _safe_relpath(name):
    if not name or len(name) > 160:
        raise SandboxError(f'Invalid file name: {name!r}')
    normalized = str(name).replace('\\', '/').strip('/')
    if normalized.startswith('/') or ':' in normalized:
        raise SandboxError(f'Absolute paths are not allowed: {name!r}')
    parts = [p for p in normalized.split('/') if p]
    if not parts or any(p in ('..', '.') for p in parts):
        raise SandboxError(f'Path traversal is not allowed: {name!r}')
    if any(ch not in SAFE_NAME for ch in normalized):
        raise SandboxError(f'Unsafe characters in file name: {name!r}')
    if normalized.endswith(('.exe', '.dll', '.bat', '.cmd', '.ps1')):
        raise SandboxError(f'Executable artefacts cannot be supplied: {name!r}')
    return '/'.join(parts)


def _scrub_env(workspace):
    keep = {'PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
            'LANG', 'LC_ALL', 'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE',
            'RUSTUP_HOME', 'CARGO_HOME', 'GOPATH', 'GOROOT', 'HOME', 'USERPROFILE'}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({
        'TMP': str(workspace), 'TEMP': str(workspace),
        'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1',
        'NODE_OPTIONS': '--no-warnings', 'NEXUS_SANDBOX': '1',
    })
    # Belt and braces: never pass anything that looks like a credential.
    for key in list(env):
        upper = key.upper()
        if any(word in upper for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')):
            env.pop(key, None)
    return env


def _kill_tree(proc):
    try:
        import psutil
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _monitor_memory(proc, limit_mb, flag, stop):
    try:
        import psutil
    except Exception:
        return
    try:
        parent = psutil.Process(proc.pid)
    except Exception:
        return
    while not stop.is_set():
        try:
            total = parent.memory_info().rss
            for child in parent.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except Exception:
                    pass
            if total > limit_mb * 1024 * 1024:
                flag['exceeded'] = True
                _kill_tree(proc)
                return
        except Exception:
            return
        stop.wait(0.15)


def _run_argv(argv, workspace, timeout, memory_mb, stdin=''):
    if not argv or not argv[0]:
        raise SandboxError('The required interpreter or compiler is not installed.')
    stdout_path = workspace / '.stdout.log'
    stderr_path = workspace / '.stderr.log'
    env = _scrub_env(workspace)
    started = time.perf_counter()
    with open(stdout_path, 'wb') as out, open(stderr_path, 'wb') as err:
        try:
            proc = subprocess.Popen(
                argv, cwd=str(workspace), env=env, stdin=subprocess.PIPE,
                stdout=out, stderr=err, shell=False, close_fds=True,
            )
        except FileNotFoundError:
            return {'ok': False, 'exit_code': None, 'stdout': '', 'stderr': f'Tool not found: {argv[0]}',
                    'timed_out': False, 'memory_exceeded': False, 'duration_ms': 0, 'command': argv}
    stop = threading.Event()
    flag = {'exceeded': False}
    watchdog = threading.Thread(target=_monitor_memory, args=(proc, memory_mb, flag, stop), daemon=True)
    watchdog.start()
    timed_out = False
    try:
        if stdin:
            try:
                proc.stdin.write(stdin.encode('utf-8'))
            except Exception:
                pass
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    finally:
        stop.set()
    duration = int((time.perf_counter() - started) * 1000)
    stdout = stdout_path.read_bytes()[:MAX_OUTPUT_BYTES].decode('utf-8', 'replace')
    stderr = stderr_path.read_bytes()[:MAX_OUTPUT_BYTES].decode('utf-8', 'replace')
    return {'ok': proc.returncode == 0 and not timed_out and not flag['exceeded'],
            'exit_code': proc.returncode, 'stdout': stdout, 'stderr': stderr,
            'timed_out': timed_out, 'memory_exceeded': flag['exceeded'],
            'duration_ms': duration, 'command': argv}


def run_code(language, files, entry=None, args=None, stdin='', timeout=None, memory_mb=None,
             require_permission=True, keep=False):
    """Write ``files`` into a fresh jailed directory and execute ``entry``.

    Returns a JSON-safe dict. Never raises for ordinary program failure; raises
    :class:`ExecutionBlocked` when the shell permission is disabled and
    :class:`SandboxError` for malformed input.
    """
    language = (language or 'python').lower()
    if language not in SPEC:
        raise SandboxError(f'Unsupported language: {language}')
    if require_permission and not read_bool('permission_shell'):
        raise ExecutionBlocked('Running code requires the “Run shell commands” permission. '
                               'Enable it in Permissions first.')
    if not isinstance(files, dict) or not files:
        raise SandboxError('No files supplied.')
    spec = SPEC[language]
    clean = {}
    total = 0
    for name, content in files.items():
        safe = _safe_relpath(name)
        if not isinstance(content, str):
            raise SandboxError(f'File {name!r} must be text.')
        raw = content.encode('utf-8')
        if len(raw) > MAX_FILE_BYTES:
            raise SandboxError(f'File {name!r} exceeds {MAX_FILE_BYTES} bytes.')
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise SandboxError('Project exceeds the sandbox size limit.')
        clean[safe] = content
    entry = _safe_relpath(entry) if entry else None
    if not entry:
        candidates = [n for n in clean if n.endswith('.' + spec['ext'])]
        entry = candidates[0] if candidates else None
    if language not in ('html', 'css') and not entry:
        raise SandboxError('No entry file found for this language.')
    timeout = int(timeout if timeout is not None else read_int('code_exec_timeout', DEFAULT_TIMEOUT))
    timeout = max(2, min(timeout, 120))
    memory_mb = int(memory_mb if memory_mb is not None else DEFAULT_MEMORY_MB)
    workspace = Path(tempfile.mkdtemp(prefix=f'{language}_', dir=str(SANDBOX_ROOT)))
    try:
        for name, content in clean.items():
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        if language == 'sql':
            # SQL exercises bundle their own Python test harness that executes
            # the SQL; prefer running it directly. Otherwise fall back to the
            # bundled SQL syntax runner on the .sql entry.
            py_files = [n for n in clean if n.endswith('.py')]
            if py_files:
                argv = [sys.executable, '-B', py_files[0]]
                if args:
                    argv = list(argv) + [str(a)[:200] for a in args[:20]]
                result = _run_argv(argv, workspace, timeout, memory_mb, stdin)
                result['stdout'] = result.get('stdout', '')
                result['stderr'] = result.get('stderr', '')
                result['stage'] = 'run'
                result['language'] = language
                result['files'] = sorted(clean)
                result['entry'] = py_files[0]
                result['sandbox'] = 'process-jail'
                return result
            clean['_sql_runner.py'] = SQL_RUNNER
            sql_entry = entry if entry and entry.endswith('.sql') else \
                (next((n for n in clean if n.endswith('.sql')), None))
            entry = sql_entry
            target = workspace / '_sql_runner.py'
            target.write_text(SQL_RUNNER, encoding='utf-8')
        if language in ('html', 'css'):
            return {'ok': True, 'skipped': True, 'exit_code': 0, 'stdout': '',
                    'stderr': '', 'timed_out': False, 'memory_exceeded': False,
                    'duration_ms': 0, 'command': [],
                    'note': 'HTML/CSS is reviewed statically and rendered in Review Studio; it is not executed.'}
        available = toolchains().get(language, {})
        if not available.get('available'):
            return {'ok': False, 'skipped': True, 'exit_code': None, 'stdout': '',
                    'stderr': f'{spec["label"]} toolchain is not installed on this machine '
                              f'({spec.get("which") or "interpreter"} not found). Code was stored but not executed.',
                    'timed_out': False, 'memory_exceeded': False, 'duration_ms': 0,
                    'command': [], 'toolchain_missing': True}
        combined = {'stdout': '', 'stderr': '', 'duration_ms': 0}
        build = None
        if spec['kind'] == 'compiled':
            # Compilation can legitimately take much longer than a run on a
            # cold compiler/antivirus cache (Rust and C++ especially).
            build_timeout = max(timeout, 90)
            build = _run_argv(spec['compile'](entry), workspace, build_timeout, memory_mb)
            combined['stdout'] += build['stdout']
            combined['stderr'] += build['stderr']
            combined['duration_ms'] += build['duration_ms']
            if not build['ok']:
                return {'ok': False, 'stage': 'build', 'exit_code': build['exit_code'],
                        'stdout': combined['stdout'], 'stderr': combined['stderr'],
                        'timed_out': build['timed_out'], 'memory_exceeded': build['memory_exceeded'],
                        'duration_ms': combined['duration_ms'], 'command': build['command']}
        argv = spec['run'](entry)
        # On Windows a bare "program.exe" is not resolved against cwd by
        # CreateProcess(shell=False), so use an absolute path for the simple
        # compiled toolchains (c, cpp, rust, go).
        if spec['kind'] == 'compiled' and argv and argv[0] == str(Path('program.exe')):
            argv = [str(workspace / 'program.exe')]
        if args:
            argv = list(argv) + [str(a)[:200] for a in args[:20]]
        result = _run_argv(argv, workspace, timeout, memory_mb, stdin)
        result['stdout'] = (combined['stdout'] + result['stdout'])[:MAX_OUTPUT_BYTES]
        result['stderr'] = (combined['stderr'] + result['stderr'])[:MAX_OUTPUT_BYTES]
        result['duration_ms'] += combined['duration_ms']
        result['stage'] = 'run'
        result['language'] = language
        result['files'] = sorted(clean)
        result['entry'] = entry
        result['sandbox'] = 'process-jail'
        return result
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)


def self_check():
    """Run a tiny real program to prove the sandbox works."""
    result = run_code('python', {'main.py': 'print("sandbox-ok", 6 * 7)\n'}, entry='main.py', timeout=10)
    result['ok'] = result.get('ok') and 'sandbox-ok 42' in (result.get('stdout') or '')
    result['toolchains'] = toolchains()
    return result
