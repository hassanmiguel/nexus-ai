"""Programming assessment engine.

Challenges are generated from the same catalog used by Auto Programming, then
actually executed. Scores reflect whether the hidden test harness passed; the
efficiency figure is a wall-clock comparison between two implementations and is
labelled as noisy for sub-millisecond runs.

No challenge is marked solved unless its tests ran and passed in the sandbox.
"""
from __future__ import annotations

import json

from .database import connect, event, now
from . import proglang, sandbox

DIFFICULTIES = ('beginner', 'intermediate', 'advanced', 'expert')


def generate(language, concept='', difficulty='beginner'):
    language = (language or 'python').lower()
    difficulty = difficulty if difficulty in DIFFICULTIES else 'beginner'
    spec = proglang.assessment_spec(language, concept, difficulty)
    if not spec:
        raise ValueError(f'No executable assessment template for {language}. '
                         'That language is still studied conceptually.')
    with connect() as db:
        cur = db.execute(
            'INSERT INTO assessments(language,concept,difficulty,question,solution,alternative,tests,'
            'status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (language, concept, difficulty,
             f'{spec["title"]}\n\n{spec["question"]}\n\nExpected complexity: {spec.get("complexity", "n/a")}',
             spec['solution'], json.dumps(spec['alternative_files']), spec['tests'], 'open', now()))
        return cur.lastrowid


def _run(files, language, entry):
    try:
        return sandbox.run_code(language, files, entry=entry)
    except sandbox.ExecutionBlocked as exc:
        return {'ok': False, 'skipped': True, 'stderr': str(exc), 'stdout': '',
                'exit_code': None, 'duration_ms': 0}
    except sandbox.SandboxError as exc:
        return {'ok': False, 'skipped': True, 'stderr': str(exc), 'stdout': '',
                'exit_code': None, 'duration_ms': 0}


def solve(assessment_id, compare=True):
    with connect() as db:
        row = db.execute('SELECT * FROM assessments WHERE id=?', (assessment_id,)).fetchone()
        if not row:
            raise LookupError('Assessment not found')
        record = dict(row)
    language = record['language']
    entry = proglang.assessment_spec(language, record['concept'], record['difficulty'])
    if not entry:
        raise ValueError('Assessment template is unavailable.')
    result = _run(entry['files'], language, entry['entry'])
    alt_runtime = 0
    if compare:
        try:
            alt_files = json.loads(record.get('alternative') or '{}')
            if alt_files:
                alt = _run(alt_files, language, entry['entry'])
                alt_runtime = alt.get('duration_ms') or 0
        except Exception:
            alt_runtime = 0
    runtime = result.get('duration_ms') or 0
    if result.get('ok'):
        score = 100.0
        status = 'solved'
        efficiency = 100.0 if not alt_runtime else round(min(100.0, 100.0 * alt_runtime / max(1, runtime)), 1)
    elif result.get('skipped'):
        score = 0.0
        status = 'skipped'
        efficiency = 0.0
    else:
        score = 25.0
        status = 'failed'
        efficiency = 0.0
    explanation = explain_solution(record, result)
    with connect() as db:
        db.execute('UPDATE assessments SET status=?,score=?,efficiency=?,runtime_ms=?,alt_runtime_ms=?,'
                   'output=?,explanation=?,finished_at=? WHERE id=?',
                   (status, score, efficiency, runtime, alt_runtime,
                    ((result.get('stdout') or '') + '\n' + (result.get('stderr') or ''))[-8000:],
                    explanation, now(), assessment_id))
    event('assessment', f'{language} · {record["concept"] or record["difficulty"]}: '
                        f'{status} (score {score:.0f}, {runtime} ms).')
    return {'id': assessment_id, 'status': status, 'score': score, 'efficiency': efficiency,
            'runtime_ms': runtime, 'alt_runtime_ms': alt_runtime,
            'execution': {k: result.get(k) for k in ('ok', 'skipped', 'exit_code', 'stdout', 'stderr',
                                                     'duration_ms', 'toolchain_missing')},
            'explanation': explanation}


def explain_solution(record, result):
    concept = record.get('concept') or record.get('difficulty') or 'programming'
    meta = proglang.language_meta(record.get('language'))
    name = meta['name'] if meta else record.get('language')
    concept_summary = ''
    for item in proglang.concepts(record.get('language')):
        if item['concept'] == concept:
            concept_summary = item['summary']
            break
    lines = [f'{name} · {concept}', concept_summary,
             f'Approach: a reference implementation was executed against an assertion harness.',
             f'Tests: {"passed" if result.get("ok") else "did not pass"} '
             f'(exit {result.get("exit_code")}, {result.get("duration_ms", 0)} ms).']
    if result.get('skipped'):
        lines.append('Execution was skipped, so this challenge is not marked solved.')
    tail = (result.get('stdout') or result.get('stderr') or '').strip().splitlines()[-4:]
    if tail:
        lines.append('Output: ' + ' | '.join(tail)[:600])
    return '\n'.join(x for x in lines if x)


def compare(assessment_id):
    with connect() as db:
        row = db.execute('SELECT * FROM assessments WHERE id=?', (assessment_id,)).fetchone()
        if not row:
            raise LookupError('Assessment not found')
        record = dict(row)
    spec = proglang.assessment_spec(record['language'], record['concept'], record['difficulty'])
    if not spec:
        raise ValueError('Assessment template is unavailable.')
    primary = _run(spec['files'], record['language'], spec['entry'])
    alternative = json.loads(record.get('alternative') or '{}')
    alt = _run(alternative, record['language'], spec['entry']) if alternative else None
    return {
        'primary': {'ok': primary.get('ok'), 'runtime_ms': primary.get('duration_ms'),
                    'exit_code': primary.get('exit_code'),
                    'output': ((primary.get('stdout') or '') + (primary.get('stderr') or ''))[-2000:]},
        'alternative': None if alt is None else {
            'ok': alt.get('ok'), 'runtime_ms': alt.get('duration_ms'), 'exit_code': alt.get('exit_code'),
            'output': ((alt.get('stdout') or '') + (alt.get('stderr') or ''))[-2000:]},
        'note': 'Wall-clock comparison only. Timing differences under 1 ms are noise.',
    }


def list_assessments(limit=60, language=''):
    with connect() as db:
        if language:
            rows = db.execute('SELECT * FROM assessments WHERE language=? ORDER BY id DESC LIMIT ?',
                              (language, max(1, min(limit, 200)))).fetchall()
        else:
            rows = db.execute('SELECT * FROM assessments ORDER BY id DESC LIMIT ?',
                              (max(1, min(limit, 200)),)).fetchall()
    return [dict(r) for r in rows]


def stats():
    with connect() as db:
        overall = db.execute('SELECT COUNT(*) n,AVG(score) s,AVG(efficiency) e FROM assessments').fetchone()
        by_diff = db.execute('SELECT difficulty,COUNT(*) n,AVG(score) score,SUM(CASE WHEN status=\'solved\' '
                             'THEN 1 ELSE 0 END) solved FROM assessments GROUP BY difficulty').fetchall()
        by_lang = db.execute('SELECT language,COUNT(*) n,AVG(score) score FROM assessments '
                             'GROUP BY language ORDER BY n DESC').fetchall()
        solved = db.execute("SELECT COUNT(*) n FROM assessments WHERE status='solved'").fetchone()['n']
    return {'total': overall['n'] or 0, 'solved': solved,
            'avg_score': round(overall['s'] or 0, 1), 'avg_efficiency': round(overall['e'] or 0, 1),
            'by_difficulty': [dict(r) for r in by_diff], 'by_language': [dict(r) for r in by_lang]}
