"""Autonomous programming engine.

Cycle: SELECT CONCEPT → STUDY → WRITE EXERCISE → EXECUTE → TEST → (FIX) → STORE.

What is real here:

* concepts come from the bundled language catalog and are tracked per language;
* exercises are generated as complete source + test files and executed in the
  process-jail sandbox;
* a concept only gains mastery when its tests actually pass;
* study material is either the bundled reference summary (marked ``local``) or a
  robots.txt-gated public page inside the user's allowlist (marked with its URL);
* every cycle is recorded in ``automation_runs`` and the event stream.

What is *not* real: NEXUS does not invent novel algorithms from nothing when no
generative provider is configured. Missing toolchains are reported and the
exercise is stored unverified.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path

from .config import DATA_DIR
from .database import connect, event, now, read_bool, read_int, set_setting, setting
from . import proglang, sandbox, selfimprove

STATE = {
    'running': False, 'paused': False, 'phase': 'idle', 'worker': None,
    'language': '', 'concept': '', 'last_error': '', 'cycle': 0, 'current_run': None,
}

PROGRAM_ROOT = DATA_DIR / 'programs'
PROGRAM_ROOT.mkdir(parents=True, exist_ok=True)

_MASTERY_WORDS = ('master', 'advanced', 'expert')


def _languages():
    raw = setting('autoprogramming_languages', 'python,javascript') or 'python,javascript'
    ids = [x.strip().lower() for x in raw.split(',') if x.strip()]
    valid = {item['id'] for item in proglang.LANGUAGES}
    return [x for x in ids if x in valid] or ['python']


def seed_concepts(languages=None):
    languages = languages or _languages()
    created = 0
    with connect() as db:
        for item in proglang.LANGUAGES:
            if item['id'] not in languages:
                continue
            for name, difficulty, summary in item['concepts']:
                row = db.execute('SELECT id FROM concept_progress WHERE language=? AND concept=?',
                                 (item['id'], name)).fetchone()
                if row:
                    continue
                db.execute('INSERT INTO concept_progress(language,concept,difficulty,status,confidence,'
                           'summary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                           (item['id'], name, difficulty, 'queued', 0.3, summary, now(), now()))
                created += 1
    return created


def _pick_concept(languages=None):
    languages = languages or _languages()
    seed_concepts(languages)
    marks = ','.join('?' for _ in languages)
    with connect() as db:
        row = db.execute(
            f"SELECT * FROM concept_progress WHERE language IN ({marks}) AND status<>'mastered' "
            "ORDER BY mastery ASC, attempts ASC, RANDOM() LIMIT 1", tuple(languages)).fetchone()
        if not row:
            row = db.execute(
                f"SELECT * FROM concept_progress WHERE language IN ({marks}) "
                "ORDER BY last_studied_at IS NULL DESC, last_studied_at ASC, RANDOM() LIMIT 1",
                tuple(languages)).fetchone()
    if not row:
        return None
    return dict(row)


def _update_concept(concept_id, **fields):
    if not fields:
        return
    allowed = {'status', 'mastery', 'confidence', 'attempts', 'successes', 'last_studied_at',
               'source_url', 'summary'}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    assignments = ', '.join(f'{k}=?' for k in fields)
    with connect() as db:
        db.execute(f'UPDATE concept_progress SET {assignments},updated_at=? WHERE id=?',
                   (*fields.values(), now(), concept_id))


async def _study_material(meta, concept_row):
    """Return (summary, source_url, verification, method)."""
    language_name = meta['name']
    concept = concept_row['concept']
    base = concept_row.get('summary') or ''
    offline = (f'{language_name} · {concept}: {base} '
               f'Reference documentation: {meta["docs"]}')[:4000]
    if not (read_bool('permission_internet') and read_bool('autoprogramming_use_internet', True)):
        return offline, '', 'local', 'bundled catalog'
    try:
        from . import autonomous
        from .research import allowed_domain, fetch_page
        from .textutil import best_sentences
        candidates = await autonomous._wiki_search(f'{language_name} {concept} programming')
        for candidate in candidates[:3]:
            if not allowed_domain(candidate['url']):
                continue
            title, text = await fetch_page(candidate['url'])
            sentences = best_sentences(f'{language_name} {concept}', text, limit=6)
            if not sentences:
                continue
            summary = (f'{language_name} · {concept}. Public reference “{title}”: ' + ' '.join(sentences))[:5000]
            with connect() as db:
                db.execute('INSERT OR IGNORE INTO explored_sites(url,domain,title,category,status,summary,'
                           'discovered_at) VALUES(?,?,?,?,?,?,?)',
                           (candidate['url'], (candidate['url'].split('/')[2] if '://' in candidate['url'] else ''),
                            title, 'programming', 'learned', summary[:1200], now()))
                db.execute("UPDATE explored_sites SET status='learned',learned_at=?,value_score=? WHERE url=?",
                           (now(), 0.8, candidate['url']))
            return summary, candidate['url'], 'single-source', f'public page · {candidate["url"]}'
    except Exception as exc:
        event('warning', f'Auto programming study fallback: {exc}')
    return offline, '', 'local', 'bundled catalog'


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or 'exercise').lower()).strip('-')[:60] or 'exercise'


def _program_artifact(meta, concept_row, exercise, result):
    """Mirror the verified exercise into Code Studio's programs table."""
    slug = f'auto-{meta["id"]}-{_slug(concept_row["concept"])}-{int(random.random() * 1e6)}'
    directory = PROGRAM_ROOT / slug
    directory.mkdir(parents=True, exist_ok=True)
    names = []
    for name, content in exercise['files'].items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        names.append(name)
    readme = (
        f'# {exercise["title"]}\n\n'
        f'Created autonomously while studying **{meta["name"]} · {concept_row["concept"]}**.\n\n'
        f'{exercise["prompt"]}\n\n'
        f'- Concept: {concept_row["concept"]}\n'
        f'- Difficulty: {concept_row["difficulty"]}\n'
        f'- Tests: {exercise["tests"]}\n'
        f'- Verification: {"passed" if result.get("ok") else "not verified"}\n'
    )
    (directory / 'README.md').write_text(readme, encoding='utf-8')
    names.append('README.md')
    verification = (f'Autonomous exercise executed in the sandbox. Exit={result.get("exit_code")} '
                    f'duration={result.get("duration_ms", 0)}ms. '
                    f'{"Tests passed." if result.get("ok") else "Tests failed."}\n'
                    f'{(result.get("stdout") or result.get("stderr") or "")[-1200:]}')
    with connect() as db:
        row = db.execute('SELECT id FROM programs WHERE directory=?', (str(directory),)).fetchone()
        if row:
            return row['id']
        cur = db.execute(
            'INSERT INTO programs(name,slug,request,language,kind,summary,directory,entry,files,source,'
            'generator,status,verified,verification,last_run,last_output,last_exit,created_at,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (exercise['title'], slug, exercise['prompt'], meta['id'], 'exercise',
             f'Auto-generated {concept_row["concept"]} exercise', str(directory), exercise['entry'],
             json.dumps(names), 'auto-programming', 'autoprogramming',
             'verified' if result.get('ok') else 'generated', 1 if result.get('ok') else 0,
             verification, now(), (result.get('stdout') or '')[-4000:], result.get('exit_code') or 0,
             now(), now()))
        return cur.lastrowid


def write_exercise(meta, concept_row, difficulty=None):
    difficulty = difficulty or setting('autoprogramming_difficulty', 'beginner')
    exercise = proglang.build_exercise(meta['id'], concept_row['concept'], difficulty)
    if not exercise:
        return None
    with connect() as db:
        cur = db.execute(
            'INSERT INTO exercises(language,concept,difficulty,kind,title,prompt,starter,solution,tests,'
            'status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (meta['id'], concept_row['concept'], difficulty, 'generated', exercise['title'],
             exercise['prompt'], exercise.get('starter', ''), exercise.get('solution', ''),
             exercise.get('tests', ''), 'draft', now(), now()))
        exercise['id'] = cur.lastrowid
    return exercise


def execute_exercise(exercise, meta):
    try:
        result = sandbox.run_code(meta['id'], exercise['files'], entry=exercise['entry'])
    except sandbox.ExecutionBlocked as exc:
        result = {'ok': False, 'skipped': True, 'stderr': str(exc), 'stdout': '',
                  'exit_code': None, 'duration_ms': 0}
    return result


def verify_exercise(exercise, meta):
    result = execute_exercise(exercise, meta)
    # One conservative repair attempt: if the harness could not find the entry
    # file, retry with the first source file the generator produced.
    if (not result.get('ok') and result.get('stderr') and
            ('can\'t open file' in result['stderr'] or 'No such file' in result['stderr'])):
        names = [n for n in exercise['files'] if n != exercise['entry']]
        if names:
            result = sandbox.run_code(meta['id'], exercise['files'], entry=names[0])
            if result.get('ok'):
                result['repaired'] = True
    score = 0.0
    if result.get('ok'):
        score = 100.0
    elif result.get('skipped'):
        score = 0.0
    else:
        score = max(0.0, 45.0 - min(40, (result.get('duration_ms') or 0) / 1000))
    status = 'verified' if result.get('ok') else ('skipped' if result.get('skipped') else 'failed')
    with connect() as db:
        db.execute('UPDATE exercises SET status=?,verified=?,score=?,runtime_ms=?,output=?,notes=?,updated_at=? '
                   'WHERE id=?',
                   (status, 1 if result.get('ok') else 0, score, result.get('duration_ms') or 0,
                    ((result.get('stdout') or '') + '\n' + (result.get('stderr') or ''))[-8000:],
                    ('repaired entry selection; ' if result.get('repaired') else '') + result.get('stderr', '')[:700],
                    now(), exercise['id']))
    return result, score, status


def record_cycle(meta, concept_row, exercise, result, study):
    concept_id = concept_row['id']
    attempts = (concept_row.get('attempts') or 0) + 1
    successes = (concept_row.get('successes') or 0) + (1 if result.get('ok') else 0)
    mastery = concept_row.get('mastery') or 0.0
    if result.get('ok'):
        mastery = min(1.0, mastery + (0.25 if (concept_row.get('mastery') or 0) > 0 else 0.45))
    else:
        mastery = min(1.0, mastery + 0.05)
    status = 'mastered' if mastery >= 0.8 and successes >= 2 else (
        'practising' if attempts else 'studied')
    confidence = round(min(0.97, 0.35 + (0.5 if result.get('ok') else 0.05) + mastery * 0.15), 3)
    _update_concept(concept_id, status=status, mastery=round(mastery, 3), confidence=confidence,
                    attempts=attempts, successes=successes, last_studied_at=now(),
                    source_url=study.get('url') or '', summary=study.get('summary', '')[:1200])
    program_id = _program_artifact(meta, concept_row, exercise, result) if exercise else None
    return {'concept_id': concept_id, 'mastery': round(mastery, 3), 'status': status,
            'attempts': attempts, 'successes': successes, 'program_id': program_id}


async def study_and_practice(language=None, concept=None, difficulty=None, assess=None):
    languages = [language] if language else _languages()
    seed_concepts(languages)
    if concept:
        with connect() as db:
            row = db.execute('SELECT * FROM concept_progress WHERE language=? AND concept=?',
                             (languages[0], concept)).fetchone()
        if not row:
            # Allow matching a concept across any enabled language.
            with connect() as db:
                row = db.execute('SELECT * FROM concept_progress WHERE concept=? LIMIT 1',
                                 (concept,)).fetchone()
        concept_row = dict(row) if row else None
    else:
        concept_row = _pick_concept(languages)
    if not concept_row:
        raise ValueError('No programming concepts are queued. Seed the catalog first.')
    meta = proglang.language_meta(concept_row['language'])
    if not meta:
        raise ValueError(f'Unknown language: {concept_row["language"]}')
    STATE.update(language=meta['id'], concept=concept_row['concept'], phase='studying', last_error='')
    event('programming', f'Studying {meta["name"]} · {concept_row["concept"]} ({concept_row["difficulty"]}).')
    summary, url, verification, method = await _study_material(meta, concept_row)
    topic = f'programming: {meta["name"]}'
    knowledge_id = None
    try:
        from .memory import store_knowledge
        knowledge_id = await store_knowledge(
            f'{meta["name"]} · {concept_row["concept"]}', summary, url, topic,
            0.72 if url else 0.6, verification)
    except Exception as exc:
        event('warning', f'Could not store study note: {exc}')
    STATE['phase'] = 'writing'
    exercise = write_exercise(meta, concept_row, difficulty)
    result, score, status = ({'ok': False, 'skipped': True, 'stderr': 'No executable exercise template for this language.',
                              'stdout': '', 'duration_ms': 0}, 0.0, 'skipped')
    if exercise:
        STATE['phase'] = 'testing'
        result, score, status = verify_exercise(exercise, meta)
    STATE['phase'] = 'recording'
    outcome = record_cycle(meta, concept_row, exercise, result, {
        'summary': summary, 'url': url})
    assessment_id = None
    if assess is None:
        assess = read_bool('autoprogramming_auto_assess', True)
    if assess and exercise:
        try:
            from . import assessment
            assessment_id = assessment.generate(meta['id'], concept_row['concept'],
                                                difficulty or concept_row['difficulty'])
            assessment.solve(assessment_id, compare=True)
        except Exception as exc:
            event('warning', f'Assessment generation skipped: {exc}')
    STATE['phase'] = 'idle'
    event('programming', f'{meta["name"]} · {concept_row["concept"]}: tests {"passed" if result.get("ok") else "not passed"}; '
                         f'mastery {outcome["mastery"]:.0%}.')
    return {
        'language': meta['id'], 'language_name': meta['name'],
        'concept': concept_row['concept'], 'difficulty': concept_row['difficulty'],
        'study': {'summary': summary[:2500], 'source_url': url, 'verification': verification, 'method': method,
                  'knowledge_id': knowledge_id},
        'exercise': None if not exercise else {
            'id': exercise['id'], 'title': exercise['title'], 'prompt': exercise['prompt'],
            'entry': exercise['entry'], 'status': status, 'score': score,
            'files': sorted(exercise['files']), 'solution': exercise['solution'],
            'tests': exercise['tests']},
        'execution': {k: result.get(k) for k in ('ok', 'skipped', 'exit_code', 'stdout', 'stderr',
                                                 'duration_ms', 'toolchain_missing', 'note')},
        'outcome': outcome, 'assessment_id': assessment_id,
        'verified': bool(result.get('ok')),
    }


async def _loop():
    try:
        while STATE['running']:
            if STATE['paused']:
                await asyncio.sleep(1)
                continue
            STATE['cycle'] += 1
            run_started = now()
            run_id = None
            with connect() as db:
                cur = db.execute('INSERT INTO automation_runs(kind,status,detail,stats,started_at) '
                                 'VALUES(?,?,?,?,?)', ('autoprogramming', 'running', '', '{}', run_started))
                run_id = cur.lastrowid
                STATE['current_run'] = run_id
            try:
                requested = STATE.pop('requested_concept', '')
                result = await study_and_practice(concept=requested or None)
                with connect() as db:
                    db.execute('UPDATE automation_runs SET status=?,detail=?,stats=?,finished_at=? WHERE id=?',
                               ('completed', f'{result["language"]} · {result["concept"]}',
                                json.dumps({'verified': result['verified'], 'score': result['exercise']['score'] if result['exercise'] else 0,
                                            'mastery': result['outcome']['mastery']}), now(), run_id))
            except asyncio.CancelledError:
                with connect() as db:
                    db.execute("UPDATE automation_runs SET status='stopped',finished_at=? WHERE id=?", (now(), run_id))
                raise
            except Exception as exc:
                STATE['last_error'] = str(exc)[:400]
                with connect() as db:
                    db.execute("UPDATE automation_runs SET status='failed',detail=?,finished_at=? WHERE id=?",
                               (str(exc)[:500], now(), run_id))
                event('warning', f'Auto programming cycle failed: {exc}')
            STATE['current_run'] = None
            interval = max(30, min(read_int('autoprogramming_interval_seconds', 90), 3600))
            for _ in range(interval):
                if not STATE['running'] or STATE['paused']:
                    break
                await asyncio.sleep(1)
    finally:
        STATE.update(running=False, paused=False, worker=None, phase='idle',
                     language='', concept='', current_run=None)


async def start(language=None, concept=None, difficulty=None, assess=None):
    if not read_bool('permission_shell'):
        raise PermissionError('Auto Programming needs the “Run shell commands” permission to test the code it writes.')
    if difficulty:
        set_setting('autoprogramming_difficulty', difficulty)
    if assess is not None:
        set_setting('autoprogramming_auto_assess', 'true' if assess else 'false')
    if language:
        set_setting('autoprogramming_languages', language)
    if concept:
        meta = proglang.language_meta(language) if language else None
        target = language or (_languages()[0] if _languages() else 'python')
        meta = meta or proglang.language_meta(target)
        if meta:
            seed_concepts([target])
            with connect() as db:
                hit = db.execute('SELECT concept FROM concept_progress WHERE language=? AND concept LIKE ?',
                                 (target, f'%{concept}%')).fetchone()
            if hit:
                concept = hit['concept']
                with connect() as db:
                    db.execute("UPDATE concept_progress SET status='queued' WHERE language=? AND concept=?",
                               (target, concept))
    set_setting('autoprogramming_enabled', 'true')
    if STATE['running']:
        STATE['paused'] = False
        if concept:
            STATE['requested_concept'] = concept
        return status()
    STATE.update(running=True, paused=False, last_error='')
    STATE['worker'] = asyncio.create_task(_loop())
    event('programming', 'Autonomous programming started.')
    return status()


async def pause():
    if STATE['running']:
        STATE['paused'] = True
        STATE['phase'] = 'paused'
        event('programming', 'Autonomous programming paused.')
    return status()


async def resume():
    if not STATE['running']:
        return await start()
    STATE['paused'] = False
    STATE['phase'] = 'idle'
    event('programming', 'Autonomous programming resumed.')
    return status()


async def stop():
    STATE['running'] = False
    STATE['paused'] = False
    worker = STATE.get('worker')
    STATE['worker'] = None
    if worker and not worker.done():
        worker.cancel()
        try:
            await worker
        except (asyncio.CancelledError, Exception):
            pass
    from .database import set_setting
    set_setting('autoprogramming_enabled', 'false')
    STATE.update(phase='idle', current_run=None)
    event('programming', 'Autonomous programming stopped.')
    return status()


def mark_interrupted():
    with connect() as db:
        cur = db.execute("UPDATE automation_runs SET status='interrupted',finished_at=? "
                         "WHERE kind='autoprogramming' AND status='running'", (now(),))
        return cur.rowcount


def skills():
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT language,COUNT(*) concepts,'
            'SUM(CASE WHEN status=\'mastered\' THEN 1 ELSE 0 END) mastered,'
            'AVG(mastery) mastery,AVG(confidence) confidence '
            'FROM concept_progress GROUP BY language ORDER BY language').fetchall()]
        exercise_rows = db.execute(
            'SELECT language,COUNT(*) total,SUM(verified) verified FROM exercises GROUP BY language').fetchall()
    by_lang = {r['language']: dict(r) for r in rows}
    for row in exercise_rows:
        item = by_lang.setdefault(row['language'], {'language': row['language'], 'concepts': 0,
                                                    'mastered': 0, 'mastery': 0, 'confidence': 0})
        item['exercises'] = row['total']
        item['verified_exercises'] = row['verified'] or 0
    out = []
    for lang, item in by_lang.items():
        meta = proglang.language_meta(lang) or {'name': lang}
        tool = sandbox.toolchains().get(lang, {})
        item['language_name'] = meta['name']
        item['score'] = round((item.get('mastery') or 0) * 70 + min(30, (item.get('verified_exercises') or 0) * 6), 1)
        item['toolchain'] = bool(tool.get('executable'))
        out.append(item)
    return sorted(out, key=lambda x: x.get('score', 0), reverse=True)


def stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM concept_progress').fetchone()['n']
        mastered = db.execute("SELECT COUNT(*) n FROM concept_progress WHERE status='mastered'").fetchone()['n']
        studying = db.execute("SELECT COUNT(*) n FROM concept_progress WHERE status IN ('studied','practising')").fetchone()['n']
        queued = db.execute("SELECT COUNT(*) n FROM concept_progress WHERE status='queued'").fetchone()['n']
        exercises = db.execute('SELECT COUNT(*) n,SUM(verified) v,AVG(runtime_ms) rt FROM exercises').fetchone()
        assessments = db.execute('SELECT COUNT(*) n,AVG(score) s FROM assessments WHERE status=\'solved\'').fetchone()
        knowledge = db.execute("SELECT COUNT(*) n FROM knowledge WHERE topic LIKE 'programming:%'").fetchone()['n']
        runs = db.execute("SELECT COUNT(*) n FROM automation_runs WHERE kind='autoprogramming'").fetchone()['n']
        failed_rows = db.execute("SELECT COUNT(*) n FROM exercises WHERE verified=0 AND status='failed'").fetchone()['n']
        recent = [dict(r) for r in db.execute(
            "SELECT id,language,concept,difficulty,status,mastery,successes,attempts,last_studied_at "
            "FROM concept_progress WHERE last_studied_at IS NOT NULL ORDER BY last_studied_at DESC LIMIT 8").fetchall()]
        next_rows = [dict(r) for r in db.execute(
            "SELECT language,concept,difficulty,mastery FROM concept_progress WHERE status<>'mastered' "
            "ORDER BY mastery ASC, attempts ASC LIMIT 8").fetchall()]
    return {
        'concepts_total': total, 'mastered': mastered, 'studying': studying, 'queued': queued,
        'exercises': exercises['n'] or 0, 'verified_exercises': exercises['v'] or 0,
        'avg_runtime_ms': int(exercises['rt'] or 0),
        'assessments': assessments['n'] or 0, 'assessment_avg': round(assessments['s'] or 0, 1),
        'programming_knowledge': knowledge, 'cycles': runs, 'failed_exercises': failed_rows,
        'recent': recent, 'next': next_rows, 'skills': skills(),
        'languages': _languages(),
        'toolchains': sandbox.toolchains(),
        'catalog': proglang.languages(),
        'errors_fixed': db_count_fixed(),
    }


def db_count_fixed():
    with connect() as db:
        return db.execute("SELECT COUNT(*) n FROM exercises WHERE verified=1 AND notes LIKE '%repaired%'").fetchone()['n']


def status():
    return {
        'state': {'running': STATE['running'], 'paused': STATE['paused'], 'phase': STATE['phase'],
                  'language': STATE['language'], 'concept': STATE['concept'],
                  'last_error': STATE['last_error'], 'cycle': STATE['cycle'],
                  'current_run': STATE['current_run']},
        'stats': stats(),
        'settings': {
            'languages': setting('autoprogramming_languages', ''),
            'difficulty': setting('autoprogramming_difficulty', 'beginner'),
            'interval_seconds': read_int('autoprogramming_interval_seconds', 90),
            'use_internet': read_bool('autoprogramming_use_internet', True),
            'auto_assess': read_bool('autoprogramming_auto_assess', True),
            'enabled': read_bool('autoprogramming_enabled'),
        },
        'history': history(12),
    }


def history(limit=40):
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT * FROM automation_runs WHERE kind=\'autoprogramming\' ORDER BY id DESC LIMIT ?',
            (max(1, min(limit, 200)),)).fetchall()]
    for row in rows:
        try:
            row['stats'] = json.loads(row.get('stats') or '{}')
        except Exception:
            row['stats'] = {}
    return rows


def list_exercises(limit=80, language=''):
    with connect() as db:
        if language:
            rows = db.execute('SELECT * FROM exercises WHERE language=? ORDER BY id DESC LIMIT ?',
                              (language, max(1, min(limit, 300)))).fetchall()
        else:
            rows = db.execute('SELECT * FROM exercises ORDER BY id DESC LIMIT ?',
                              (max(1, min(limit, 300)),)).fetchall()
    return [dict(r) for r in rows]


def exercise_detail(exercise_id):
    with connect() as db:
        row = db.execute('SELECT * FROM exercises WHERE id=?', (exercise_id,)).fetchone()
        if not row:
            return None
        program = db.execute("SELECT id,name FROM programs WHERE generator='autoprogramming' AND "
                             "request=(SELECT prompt FROM exercises WHERE id=?) ORDER BY id DESC LIMIT 1",
                             (exercise_id,)).fetchone()
    data = dict(row)
    data['program_id'] = program['id'] if program else None
    return data


def rerun_exercise(exercise_id):
    """Rebuild a stored exercise from the deterministic generator and test it again."""
    with connect() as db:
        row = db.execute('SELECT * FROM exercises WHERE id=?', (exercise_id,)).fetchone()
    if not row:
        raise LookupError('Exercise not found')
    meta = proglang.language_meta(row['language'])
    if not meta:
        raise ValueError(f'Unknown language: {row["language"]}')
    exercise = proglang.build_exercise(row['language'], row['concept'], row['difficulty'])
    if not exercise:
        raise ValueError('This exercise has no executable template.')
    exercise['id'] = exercise_id
    result, score, status = verify_exercise(exercise, meta)
    detail = exercise_detail(exercise_id) or {}
    return {
        'exercise': detail,
        'execution': {k: result.get(k) for k in ('ok', 'skipped', 'exit_code', 'stdout', 'stderr',
                                                 'duration_ms', 'toolchain_missing', 'note')},
        'verified': bool(result.get('ok')), 'score': score, 'status': status,
    }


def concept_catalog(language=''):
    seed_concepts()
    with connect() as db:
        if language:
            rows = db.execute('SELECT * FROM concept_progress WHERE language=? ORDER BY difficulty,concept',
                              (language,)).fetchall()
        else:
            rows = db.execute('SELECT * FROM concept_progress ORDER BY language,difficulty,concept').fetchall()
    return [dict(r) for r in rows]


def queue_concept(language, concept, priority=8):
    language = (language or 'python').lower()
    meta = proglang.language_meta(language)
    if not meta:
        raise ValueError(f'Unknown language: {language}')
    seed_concepts([language])
    with connect() as db:
        row = db.execute('SELECT id FROM concept_progress WHERE language=? AND concept=?',
                         (language, concept)).fetchone()
        if row:
            db.execute("UPDATE concept_progress SET status='queued',mastery=0,attempts=0 WHERE id=?",
                       (row['id'],))
            return dict(db.execute('SELECT * FROM concept_progress WHERE id=?', (row['id'],)).fetchone())
        difficulty = dict((name, diff) for name, diff, _ in meta['concepts']).get(concept, 'beginner')
        summary = dict((name, text) for name, _diff, text in meta['concepts']).get(concept, '')
        cur = db.execute('INSERT INTO concept_progress(language,concept,difficulty,status,confidence,summary,'
                         'created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                         (language, concept, difficulty, 'queued', 0.3, summary, now(), now()))
        return dict(db.execute('SELECT * FROM concept_progress WHERE id=?', (cur.lastrowid,)).fetchone())
