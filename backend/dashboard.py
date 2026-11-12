"""Real dashboard aggregates.

Every number and series here is computed from SQLite at request time. There are
no seeded or invented statistics. If a table is empty the series is empty and the
UI must say so rather than drawing fake data.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .database import connect, setting, read_bool
from . import sandbox


def _rows(db, sql, params=()):
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def _daily_series(db, table, days=30, date_column='created_at', where=''):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
    clause = f'WHERE substr({date_column},1,10) >= ?'
    if where:
        clause += f' AND ({where})'
    rows = _rows(db,
                 f"SELECT substr({date_column},1,10) day,COUNT(*) n FROM {table} "
                 f"{clause} GROUP BY day ORDER BY day", (cutoff,))
    counts = {r['day']: r['n'] for r in rows}
    series = []
    start = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        series.append({'day': day, 'n': counts.get(day, 0)})
    return series


def _cumulative(series, baseline):
    running = baseline
    out = []
    for item in series:
        running += item['n']
        out.append({'day': item['day'], 'n': running})
    return out


def overview():
    with connect() as db:
        knowledge = db.execute('SELECT COUNT(*) n FROM knowledge').fetchone()['n']
        verified = db.execute("SELECT COUNT(*) n FROM knowledge WHERE verification_status IN "
                              "('corroborated','user-reported')").fetchone()['n']
        web_sources = db.execute('SELECT COUNT(*) n FROM web_sources').fetchone()['n']
        topics = db.execute('SELECT COUNT(DISTINCT topic) n FROM knowledge').fetchone()['n']
        sessions = db.execute('SELECT COUNT(*) n FROM learning_sessions').fetchone()['n']
        concepts = db.execute('SELECT COUNT(*) n FROM concept_progress').fetchone()['n']
        mastered = db.execute("SELECT COUNT(*) n FROM concept_progress WHERE status='mastered'").fetchone()['n']
        exercises = db.execute('SELECT COUNT(*) n FROM exercises').fetchone()['n']
        verified_ex = db.execute('SELECT COUNT(*) n FROM exercises WHERE verified=1').fetchone()['n']
        projects = db.execute('SELECT COUNT(*) n FROM projects').fetchone()['n']
        reviews = db.execute('SELECT COUNT(*) n FROM reviews').fetchone()['n']
        avg_review = db.execute('SELECT AVG(overall) a FROM reviews').fetchone()['a']
        agent_runs = db.execute('SELECT COUNT(*) n FROM agent_runs').fetchone()['n']
        assessments = db.execute('SELECT COUNT(*) n FROM assessments').fetchone()['n']
        solved = db.execute("SELECT COUNT(*) n FROM assessments WHERE status='solved'").fetchone()['n']
        explored = db.execute('SELECT COUNT(*) n FROM explored_sites').fetchone()['n']
        learned_sites = db.execute("SELECT COUNT(*) n FROM explored_sites WHERE status='learned'").fetchone()['n']
        tasks = db.execute('SELECT status,COUNT(*) n FROM tasks GROUP BY status').fetchall()
        programmes = db.execute('SELECT COUNT(*) n FROM programs').fetchone()['n']
        avg_conf = db.execute('SELECT AVG(confidence) a FROM knowledge').fetchone()['a']
    task_counts = {r['status']: r['n'] for r in tasks}
    total_tasks = sum(task_counts.values())
    completed = task_counts.get('done', 0) + task_counts.get('completed', 0)
    return {
        'knowledge': knowledge, 'verified_knowledge': verified, 'avg_confidence': round(avg_conf or 0, 3),
        'web_sources': web_sources, 'topics': topics, 'learning_sessions': sessions,
        'concepts': concepts, 'mastered_concepts': mastered,
        'exercises': exercises, 'verified_exercises': verified_ex,
        'projects': projects, 'reviews': reviews, 'avg_review_score': round(avg_review or 0, 1),
        'agent_runs': agent_runs, 'assessments': assessments, 'solved_assessments': solved,
        'explored_sites': explored, 'learned_sites': learned_sites, 'programs': programmes,
        'tasks_total': total_tasks, 'tasks_completed': completed,
        'task_completion': round(100 * completed / total_tasks, 1) if total_tasks else 0,
        'tasks_by_status': task_counts,
    }


def knowledge_growth(days=30):
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM knowledge').fetchone()['n']
        daily = _daily_series(db, 'knowledge', days)
        categories = _rows(db, "SELECT COALESCE(NULLIF(category,''),'general') category,COUNT(*) n "
                               "FROM knowledge GROUP BY category ORDER BY n DESC")
        verification = _rows(db, 'SELECT verification_status status,COUNT(*) n FROM knowledge '
                                 'GROUP BY status ORDER BY n DESC')
        domains = _rows(db, "SELECT source_domain domain,COUNT(*) n FROM knowledge "
                            "WHERE COALESCE(source_domain,'')<>'' GROUP BY source_domain "
                            "ORDER BY n DESC LIMIT 10")
    baseline = total - sum(item['n'] for item in daily)
    return {'total': total, 'daily': daily, 'cumulative': _cumulative(daily, max(0, baseline)),
            'categories': categories, 'verification': verification, 'domains': domains}


def programming_skills():
    with connect() as db:
        rows = _rows(db,
                     "SELECT language,COUNT(*) concepts,"
                     "SUM(CASE WHEN status='mastered' THEN 1 ELSE 0 END) mastered,"
                     "AVG(mastery) mastery,AVG(confidence) confidence FROM concept_progress "
                     "GROUP BY language ORDER BY mastery DESC")
        exercises = {r['language']: r for r in _rows(
            db, 'SELECT language,COUNT(*) total,SUM(verified) verified,AVG(runtime_ms) runtime '
                'FROM exercises GROUP BY language')}
        assessments = {r['language']: r for r in _rows(
            db, 'SELECT language,COUNT(*) total,AVG(score) score FROM assessments GROUP BY language')}
    tools = sandbox.toolchains()
    from . import proglang
    out = []
    for row in rows:
        lang = row['language']
        meta = proglang.language_meta(lang) or {'name': lang}
        ex = exercises.get(lang, {})
        assess = assessments.get(lang, {})
        tool = tools.get(lang, {})
        mastery = row['mastery'] or 0
        score = round(mastery * 60 + min(25, (ex.get('verified') or 0) * 5) +
                      min(15, (assess.get('score') or 0) * 0.15), 1)
        out.append({'language': lang, 'name': meta.get('name', lang), 'concepts': row['concepts'],
                    'mastered': row['mastered'] or 0, 'mastery': round(mastery, 3),
                    'confidence': round(row['confidence'] or 0, 3), 'exercises': ex.get('total') or 0,
                    'verified_exercises': ex.get('verified') or 0,
                    'avg_runtime_ms': int(ex.get('runtime') or 0),
                    'assessments': assess.get('total') or 0,
                    'assessment_score': round(assess.get('score') or 0, 1),
                    'score': score, 'toolchain': bool(tool.get('executable'))})
    return sorted(out, key=lambda x: x['score'], reverse=True)


def learning_activity(days=30):
    with connect() as db:
        daily = _daily_series(db, 'learning_sessions', days, date_column='started_at')
        knowledge_daily = _daily_series(db, 'knowledge', days)
        session_rows = _rows(db, 'SELECT status,COUNT(*) n FROM learning_sessions GROUP BY status')
        speed = setting('learning_speed', 'normal')
        recent = _rows(db, 'SELECT topic,status,started_at,finished_at,pages_visited,pages_learned,'
                            'knowledge_added FROM learning_sessions ORDER BY id DESC LIMIT 10')
    return {'daily_sessions': daily, 'daily_knowledge': knowledge_daily,
            'by_status': session_rows, 'speed': speed, 'recent': recent}


def exploration_stats(days=30):
    with connect() as db:
        total = db.execute('SELECT COUNT(*) n FROM explored_sites').fetchone()['n']
        daily = _daily_series(db, 'explored_sites', days, date_column='discovered_at')
        by_category = _rows(db, 'SELECT category,COUNT(*) n FROM explored_sites GROUP BY category '
                                'ORDER BY n DESC')
        by_status = _rows(db, 'SELECT status,COUNT(*) n FROM explored_sites GROUP BY status '
                              'ORDER BY n DESC')
        by_domain = _rows(db, "SELECT domain,COUNT(*) n FROM explored_sites WHERE domain<>'' "
                              'GROUP BY domain ORDER BY n DESC LIMIT 10')
        learned = db.execute("SELECT COUNT(*) n FROM explored_sites WHERE status='learned'").fetchone()['n']
    return {'total': total, 'learned': learned, 'daily': daily, 'by_category': by_category,
            'by_status': by_status, 'by_domain': by_domain}


def task_completion(days=30):
    with connect() as db:
        daily_created = _daily_series(db, 'tasks', days)
        status_rows = _rows(db, 'SELECT status,COUNT(*) n FROM tasks GROUP BY status ORDER BY n DESC')
        by_category = _rows(db, "SELECT COALESCE(NULLIF(category,''),'uncategorised') category,"
                                "COUNT(*) n,SUM(CASE WHEN status IN ('done','completed') THEN 1 ELSE 0 END) done "
                                "FROM tasks GROUP BY category ORDER BY n DESC")
        agent_rows = _rows(db, 'SELECT agent,COUNT(*) n FROM tasks WHERE COALESCE(agent,\'\')<>\'\' '
                               'GROUP BY agent ORDER BY n DESC')
    total = sum(r['n'] for r in status_rows)
    done = sum(r['n'] for r in status_rows if r['status'] in ('done', 'completed'))
    return {'total': total, 'done': done,
            'completion': round(100 * done / total, 1) if total else 0,
            'daily_created': daily_created, 'by_status': status_rows,
            'by_category': by_category, 'by_agent': agent_rows}


def automation():
    with connect() as db:
        runs = _rows(db, 'SELECT kind,status,COUNT(*) n FROM automation_runs GROUP BY kind,status '
                         'ORDER BY kind')
        recent = _rows(db, 'SELECT id,kind,status,detail,started_at,finished_at,stats '
                           'FROM automation_runs ORDER BY id DESC LIMIT 10')
    for item in recent:
        try:
            item['stats'] = json.loads(item.get('stats') or '{}')
        except Exception:
            item['stats'] = {}
    return {'by_status': runs, 'recent': recent}


def system_state():
    return {
        'sandbox': sandbox.toolchains(),
        'permissions': {
            'internet': read_bool('permission_internet'),
            'shell': read_bool('permission_shell'),
            'files': read_bool('permission_files'),
            'automation': read_bool('learning_enabled'),
        },
        'allowlist': [d for d in (setting('allowed_domains', '') or '').split(',') if d.strip()],
        'provider': setting('provider', 'nexus'),
    }


def full(days=30):
    return {
        'overview': overview(),
        'knowledge': knowledge_growth(days),
        'skills': programming_skills(),
        'learning': learning_activity(days),
        'exploration': exploration_stats(days),
        'tasks': task_completion(days),
        'automation': automation(),
        'system': system_state(),
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
