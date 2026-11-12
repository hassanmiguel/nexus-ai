"""Specialised agents that do real, bounded work.

Each agent runs a deterministic tool pipeline and stores its steps, inputs and
outputs in ``agent_runs``. There is no hidden prompting: an agent either has
access to a configured provider or it reports what it could compute from local
data. Agents cannot execute arbitrary shell commands; code execution is routed
through the sandbox permission gate.

Collaboration is an explicit pipeline, not a claim: research gathers evidence,
a builder produces an artefact, testing executes it, and the orchestrator keeps
the transcript.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re

from .database import connect, event, now
from . import sandbox

AGENTS = {
    'programming': {
        'name': 'Programming Agent',
        'description': 'Selects a concept, writes a tested program and records verified results.',
        'capabilities': ['language catalog', 'exercise generation', 'sandboxed tests'],
    },
    'research': {
        'name': 'Research Agent',
        'description': 'Finds public evidence inside the allowlist, extracts findings and stores them with sources.',
        'capabilities': ['robots.txt-gated fetch', 'local retrieval', 'source-linked summaries'],
    },
    'cybersecurity': {
        'name': 'Cybersecurity Education Agent',
        'description': 'Explains defensive security concepts and refuses offensive or harmful requests.',
        'capabilities': ['secure-coding review', 'hardening checklists', 'knowledge retrieval'],
    },
    'mathematics': {
        'name': 'Mathematics Agent',
        'description': 'Evaluates bounded expressions and explains the steps with a safe AST evaluator.',
        'capabilities': ['arithmetic', 'gcd/prime/fibonacci', 'summary statistics'],
    },
    'webdev': {
        'name': 'Web Development Agent',
        'description': 'Builds a real front-end or API scaffold and reviews it.',
        'capabilities': ['project builder', 'static review', 'run tests'],
    },
    'data': {
        'name': 'Data Analysis Agent',
        'description': 'Answers questions from the local SQLite database with read-only aggregate queries.',
        'capabilities': ['knowledge statistics', 'verification breakdown', 'time series'],
    },
    'testing': {
        'name': 'Software Testing Agent',
        'description': 'Executes an existing artifact in the sandbox and reports real pass/fail output.',
        'capabilities': ['program tests', 'project tests', 'exercise verification'],
    },
}

SAFE_REFUSAL = ('I can help with defensive security, secure coding and ethical labs. '
                'I will not provide instructions for unauthorised access, malware, credential theft, '
                'evasion or attacks on systems you do not own.')

MALICIOUS = ('hack into', 'steal password', 'keylogger', 'ransomware', 'ddos', 'botnet',
             'phishing kit', 'bypass authentication', 'crack password', 'reverse shell',
             'exploit this target', 'unauthorised access', 'unauthorized access')

_ALLOWED_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
                ast.UAdd: operator.pos}
_ALLOWED_FUNCS = {'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
                  'log': math.log, 'log10': math.log10, 'exp': math.exp, 'floor': math.floor,
                  'ceil': math.ceil, 'abs': abs, 'round': round}
_CONSTANTS = {'pi': math.pi, 'e': math.e, 'tau': math.tau}


class AgentRefusal(ValueError):
    pass


def _record(agent, task):
    with connect() as db:
        cur = db.execute('INSERT INTO agent_runs(agent,task,status,input,created_at) VALUES(?,?,?,?,?)',
                         (agent, task[:2000], 'running', task[:2000], now()))
        return cur.lastrowid


def _finish(run_id, status, output, steps, score=0):
    with connect() as db:
        db.execute('UPDATE agent_runs SET status=?,output=?,steps=?,score=?,finished_at=? WHERE id=?',
                   (status, output[:12000], json.dumps(steps)[:40000], score, now(), run_id))


def _safe_eval(expression):
    expression = expression.strip().replace('^', '**')
    if len(expression) > 200:
        raise ValueError('Expression is too long.')
    tree = ast.parse(expression, mode='eval')

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError('Exponent is too large.')
            return _ALLOWED_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Name) and node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
            args = [walk(arg) for arg in node.args]
            return _ALLOWED_FUNCS[node.func.id](*args)
        raise ValueError('Unsupported expression element.')

    return walk(tree)


# --------------------------------------------------------------------------- #
# Agent implementations
# --------------------------------------------------------------------------- #
async def _programming(task, run_id):
    from . import autoprogramming, proglang
    language = ''
    for meta in proglang.LANGUAGES:
        if re.search(rf'\b{re.escape(meta["id"])}\b', task.lower()):
            language = meta['id']
            break
    concept = ''
    for item in proglang.concepts(language or None):
        if item['concept'].lower() in task.lower():
            concept = item['concept']
            language = language or item['language']
            break
    steps = [{'step': 'select', 'detail': f'language={language or "auto"} concept={concept or "auto"}'}]
    result = await autoprogramming.study_and_practice(language=language or None, concept=concept or None,
                                                      assess=False)
    steps.append({'step': 'study', 'detail': result['study']['method'],
                  'source': result['study']['source_url']})
    steps.append({'step': 'test', 'detail': f'exit={result["execution"].get("exit_code")}',
                  'ok': result['verified']})
    output = (f'Studied {result["language_name"]} · {result["concept"]}.\n\n'
              f'Exercise: {result["exercise"]["title"] if result["exercise"] else "none"}\n'
              f'Source: {result["study"]["source_url"] or result["study"]["method"]}\n'
              f'Tests: {"passed" if result["verified"] else "did not pass"}\n'
              f'Mastery: {result["outcome"]["mastery"]:.0%}\n\n'
              f'{(result["execution"].get("stdout") or result["execution"].get("stderr") or "")[-1800:]}')
    return output, steps, 100 if result['verified'] else 40


async def _research(task, run_id):
    steps = []
    sources = []
    findings = []
    from .research import search_web, fetch_page, allowed_domain
    from .textutil import best_sentences
    from .database import read_bool
    try:
        if read_bool('permission_internet'):
            results = await search_web(task, limit=5)
            steps.append({'step': 'search', 'detail': f'{len(results)} candidates'})
            for item in results[:3]:
                if not allowed_domain(item['url']):
                    continue
                try:
                    title, text = await fetch_page(item['url'])
                    summary = ' '.join(best_sentences(task, text, limit=4))[:1200]
                    findings.append({'title': title, 'url': item['url'], 'summary': summary})
                    sources.append(item['url'])
                    steps.append({'step': 'fetch', 'detail': item['url'], 'ok': True})
                except Exception as exc:
                    steps.append({'step': 'fetch', 'detail': item['url'], 'ok': False, 'error': str(exc)[:200]})
        else:
            steps.append({'step': 'search', 'detail': 'internet permission is off; using local memory'})
    except Exception as exc:
        steps.append({'step': 'search', 'detail': f'web search unavailable: {exc}'})
    if findings:
        from .memory import store_knowledge
        for item in findings:
            await store_knowledge(item['title'], item['summary'], item['url'],
                                  f'research: {task[:60]}', 0.7, 'single-source')
    else:
        from .memory import retrieve
        rows = await retrieve(task, 6)
        findings = [{'title': r.get('title'), 'url': r.get('source_url') or '',
                     'summary': (r.get('content') or '')[:900]} for r in rows]
        steps.append({'step': 'local-retrieval', 'detail': f'{len(findings)} records'})
    lines = [f'Research: {task}', '']
    for item in findings[:6]:
        lines.append(f"- {item['title']} ({item['url'] or 'local'})")
        lines.append(item['summary'][:700])
        lines.append('')
    if not findings:
        lines.append('No evidence was found locally or inside the configured allowlist. '
                     'Enable internet access or add a documentation domain, then retry.')
    return '\n'.join(lines), steps, 80 if findings else 20


async def _cybersecurity(task, run_id):
    low = task.lower()
    if any(phrase in low for phrase in MALICIOUS):
        raise AgentRefusal(SAFE_REFUSAL)
    from .memory import retrieve
    rows = await retrieve(task, 5)
    steps = [{'step': 'intent', 'detail': 'defensive request accepted'},
             {'step': 'retrieve', 'detail': f'{len(rows)} knowledge records'}]
    evidence = [f"- {r['title']} ({r.get('source_url') or 'local'})" for r in rows]
    checklist = [
        'Validate and encode untrusted input at every trust boundary.',
        'Use parameterised queries; never concatenate SQL.',
        'Hash passwords with Argon2id, scrypt or bcrypt; never store plaintext.',
        'Enforce least privilege for tokens, services and file access.',
        'Keep dependencies patched and scan lockfiles in CI.',
        'Log security-relevant events without logging secrets.',
        'Serve HTTPS only, set CSP/HSTS and disable directory listing.',
    ]
    output = ('Defensive security guidance for: ' + task + '\n\n'
              'Practical checklist:\n' + '\n'.join(f'{i + 1}. {item}' for i, item in enumerate(checklist)) +
              '\n\nRelevant stored knowledge:\n' + ('\n'.join(evidence) or '- none stored yet') +
              '\n\nThis is educational guidance, not a penetration test of a specific target.')
    return output, steps, 75


async def _math(task, run_id):
    steps = []
    low = task.lower()
    match = re.search(r'(?:gcd|hcf)\D+(-?\d+)\D+(-?\d+)', low)
    if match:
        a, b = int(match.group(1)), int(match.group(2))
        result = math.gcd(a, b)
        steps.append({'step': 'gcd', 'detail': f'math.gcd({a}, {b})'})
        return f'gcd({a}, {b}) = {result}', steps, 100
    match = re.search(r'\bprime\D+(\d+)', low)
    if match:
        n = int(match.group(1))
        if n < 2:
            prime = False
        else:
            prime = all(n % k for k in range(2, int(n ** 0.5) + 1))
        steps.append({'step': 'prime-test', 'detail': f'trial division up to sqrt({n})'})
        return f'{n} is {"prime" if prime else "not prime"}.', steps, 100
    match = re.search(r'\bfib(?:onacci)?\D+(\d+)', low)
    if match:
        n = min(int(match.group(1)), 1000)
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        steps.append({'step': 'fibonacci', 'detail': f'iterative, {n} iterations'})
        return f'fib({n}) = {a}', steps, 100
    match = re.search(r'(?:mean|average)\D+([\d.,\s-]+)', low)
    if match:
        values = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', match.group(1))]
        if values:
            steps.append({'step': 'statistics', 'detail': f'{len(values)} values'})
            return (f'count={len(values)} sum={sum(values):g} mean={sum(values) / len(values):g} '
                    f'min={min(values):g} max={max(values):g}'), steps, 100
    expression = re.search(r'[-+*/^().\d\s*eEpi]{3,}', task)
    if expression:
        cleaned = expression.group(0).strip()
        try:
            value = _safe_eval(cleaned)
            steps.append({'step': 'evaluate', 'detail': cleaned})
            return f'{cleaned} = {value}', steps, 100
        except Exception as exc:
            steps.append({'step': 'evaluate', 'detail': f'failed: {exc}'})
    return ('I can evaluate arithmetic expressions and compute gcd, primality, Fibonacci numbers '
            'and basic summary statistics. No expression was found in the request.'), steps, 25


async def _webdev(task, run_id):
    from . import projects
    project = projects.build_project(task, run_tests=True, auto_review=True)
    steps = [{'step': 'plan', 'detail': project['archetype']},
             {'step': 'generate', 'detail': f'{len(project["file_rows"])} files'},
             {'step': 'test', 'detail': project['status']},
             {'step': 'review', 'detail': f'score {project["review_score"]}'}]
    output = (f'Built “{project["name"]}” ({project["archetype"]}).\n'
              f'Status: {project["status"]}\nReview score: {project["review_score"]}/100\n'
              f'Entry: {project["entry"]}\n\n{project.get("test_output") or "No test output."}')
    return output, steps, int(project['review_score'] or 0)


async def _data(task, run_id):
    with connect() as db:
        knowledge = db.execute('SELECT COUNT(*) n FROM knowledge').fetchone()['n']
        verified = db.execute("SELECT COUNT(*) n FROM knowledge WHERE verification_status='corroborated'").fetchone()['n']
        web = db.execute('SELECT COUNT(*) n FROM web_sources').fetchone()['n']
        topics = db.execute('SELECT topic,COUNT(*) n FROM knowledge GROUP BY topic ORDER BY n DESC LIMIT 6').fetchall()
        cats = db.execute('SELECT category,COUNT(*) n FROM knowledge WHERE category IS NOT NULL AND category<>\'\' '
                          'GROUP BY category ORDER BY n DESC').fetchall()
        daily = db.execute('SELECT substr(created_at,1,10) day,COUNT(*) n FROM knowledge '
                           'GROUP BY day ORDER BY day DESC LIMIT 7').fetchall()
        domains = db.execute("SELECT source_domain,COUNT(*) n FROM knowledge WHERE source_domain<>'' "
                             'GROUP BY source_domain ORDER BY n DESC LIMIT 5').fetchall()
    steps = [{'step': 'query', 'detail': 'read-only aggregates over SQLite'}]
    lines = [f'Data analysis: {task}', '',
             f'Knowledge records: {knowledge} ({verified} corroborated)',
             f'Web sources: {web}', '',
             'Top topics: ' + ', '.join(f'{r["topic"]} ({r["n"]})' for r in topics),
             'Categories: ' + ', '.join(f'{r["category"]} ({r["n"]})' for r in cats),
             'Last 7 days: ' + ', '.join(f'{r["day"]}: {r["n"]}' for r in reversed(daily)),
             'Top domains: ' + ', '.join(f'{r["source_domain"]} ({r["n"]})' for r in domains)]
    return '\n'.join(lines), steps, 90


async def _testing(task, run_id):
    from . import projects, autoprogramming
    target = None
    match = re.search(r'project\s*#?(\d+)', task.lower())
    if match:
        project = projects.get_project(int(match.group(1)))
        if not project:
            raise ValueError('Project not found.')
        result = projects.run_project_tests(project['id'])
        steps = [{'step': 'test-project', 'detail': f'#{project["id"]}', 'ok': result['ok']}]
        return f'Project #{project["id"]}: {"passed" if result["ok"] else "failed"}\n\n{result["output"][-2500:]}', steps, 100 if result['ok'] else 30
    match = re.search(r'exercise\s*#?(\d+)', task.lower())
    if match:
        exercise = autoprogramming.exercise_detail(int(match.group(1)))
        if not exercise:
            raise ValueError('Exercise not found.')
        steps = [{'step': 'verify-exercise', 'detail': f'#{exercise["id"]}',
                  'ok': bool(exercise['verified'])}]
        return (f'Exercise #{exercise["id"]} “{exercise["title"]}” is '
                f'{"verified" if exercise["verified"] else "not verified"} '
                f'(score {exercise["score"]}, {exercise["runtime_ms"]} ms).\n\n'
                f'{exercise["output"][-2500:]}'), steps, 100 if exercise['verified'] else 30
    project = projects.list_projects(1)
    if project:
        result = projects.run_project_tests(project[0]['id'])
        steps = [{'step': 'test-latest-project', 'detail': f'#{project[0]["id"]}', 'ok': result['ok']}]
        return (f'Tested latest project #{project[0]["id"]} “{project[0]["name"]}”: '
                f'{"passed" if result["ok"] else "failed"}\n\n{result["output"][-2500:]}'), steps, 100 if result['ok'] else 30
    return ('No project or exercise exists to test yet. Build a project or run Auto Programming first.',
            [{'step': 'lookup', 'detail': 'nothing to test'}], 10)


RUNNERS = {'programming': _programming, 'research': _research, 'cybersecurity': _cybersecurity,
           'mathematics': _math, 'webdev': _webdev, 'data': _data, 'testing': _testing}


async def run_agent(agent, task):
    agent = (agent or '').lower()
    if agent not in AGENTS:
        raise ValueError(f'Unknown agent: {agent}')
    if not (task or '').strip():
        raise ValueError('Give the agent a task.')
    run_id = _record(agent, task)
    try:
        output, steps, score = await RUNNERS[agent](task, run_id)
        _finish(run_id, 'completed', output, steps, score)
        event('agent', f'{AGENTS[agent]["name"]} completed run #{run_id} (score {score}).')
        return {'id': run_id, 'agent': agent, 'agent_name': AGENTS[agent]['name'], 'status': 'completed',
                'output': output, 'steps': steps, 'score': score}
    except AgentRefusal as exc:
        _finish(run_id, 'refused', str(exc), [{'step': 'policy', 'detail': 'refused'}], 0)
        event('agent', f'{AGENTS[agent]["name"]} refused a request on safety grounds.')
        return {'id': run_id, 'agent': agent, 'agent_name': AGENTS[agent]['name'], 'status': 'refused',
                'output': str(exc), 'steps': [{'step': 'policy', 'detail': 'refused'}], 'score': 0}
    except Exception as exc:
        _finish(run_id, 'failed', str(exc), [{'step': 'error', 'detail': str(exc)[:500]}], 0)
        event('warning', f'{AGENTS[agent]["name"]} failed: {exc}')
        return {'id': run_id, 'agent': agent, 'agent_name': AGENTS[agent]['name'], 'status': 'failed',
                'output': f'Agent failed: {exc}', 'steps': [], 'score': 0}


async def collaborate(task, agents=None):
    """Run a bounded multi-agent pipeline and keep the full transcript."""
    requested = agents or ['research', 'programming', 'testing']
    requested = [a for a in requested if a in AGENTS][:4] or ['research']
    with connect() as db:
        cur = db.execute('INSERT INTO agent_runs(agent,task,status,input,created_at) VALUES(?,?,?,?,?)',
                         ('team', task[:2000], 'running', task[:2000], now()))
        run_id = cur.lastrowid
    steps = []
    outputs = []
    score_total = 0
    for agent in requested:
        result = await run_agent(agent, task)
        steps.append({'agent': agent, 'run_id': result['id'], 'status': result['status'],
                      'score': result['score'], 'output': result['output'][:2000]})
        outputs.append(f'## {result["agent_name"]}\n{result["output"]}')
        score_total += result['score']
        if result['status'] == 'refused':
            break
    combined = f'# Team result\n\nTask: {task}\n\n' + '\n\n'.join(outputs)
    _finish(run_id, 'completed', combined, steps, round(score_total / max(1, len(requested))))
    event('agent', f'Agent team completed run #{run_id} with {len(requested)} specialist(s).')
    return {'id': run_id, 'status': 'completed', 'output': combined, 'steps': steps,
            'score': round(score_total / max(1, len(requested)))}


def list_runs(limit=60, agent=''):
    with connect() as db:
        if agent:
            rows = db.execute('SELECT * FROM agent_runs WHERE agent=? ORDER BY id DESC LIMIT ?',
                              (agent, max(1, min(limit, 200)))).fetchall()
        else:
            rows = db.execute('SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?',
                              (max(1, min(limit, 200)),)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item['steps'] = json.loads(item.get('steps') or '[]')
        except Exception:
            item['steps'] = []
        out.append(item)
    return out


def stats():
    with connect() as db:
        rows = db.execute('SELECT agent,COUNT(*) n,AVG(score) score,SUM(CASE WHEN status=\'completed\' '
                          'THEN 1 ELSE 0 END) completed FROM agent_runs GROUP BY agent').fetchall()
        total = db.execute('SELECT COUNT(*) n FROM agent_runs').fetchone()['n']
    return {'total': total, 'by_agent': [dict(r) for r in rows], 'agents': AGENTS}
