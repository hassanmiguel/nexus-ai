"""Autonomous project builder.

Requirements → plan → architecture → real files → dependencies → test → review.

The builder ships deterministic, runnable archetypes. It is honest about what it
produces: a working prototype scaffold, not a production system. Requests pick
an archetype and influence naming, copy and structure; tests are executed in the
sandbox and the review is stored with concrete findings.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR
from .database import connect, event, now, read_bool, setting
from . import review, sandbox

PROJECT_ROOT = DATA_DIR / 'projects'
PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

ARCHETYPES = {
    'static-site': {'label': 'Static website', 'stack': 'HTML + CSS + JavaScript',
                    'keywords': ('website', 'landing', 'portfolio', 'site', 'page', 'blog')},
    'chat-ui': {'label': 'Chat interface prototype', 'stack': 'HTML + CSS + JavaScript (local state)',
                'keywords': ('discord', 'chat', 'messaging', 'slack', 'community', 'forum')},
    'fastapi-api': {'label': 'Python HTTP API', 'stack': 'Python + FastAPI + Pydantic',
                    'keywords': ('api', 'rest', 'backend', 'server', 'endpoint', 'fastapi')},
    'python-cli': {'label': 'Python command-line tool', 'stack': 'Python standard library',
                   'keywords': ('cli', 'command', 'script', 'terminal', 'tool', 'automation')},
    'data-dashboard': {'label': 'Data dashboard', 'stack': 'Python + CSV + generated HTML',
                       'keywords': ('dashboard', 'data', 'chart', 'analytics', 'report', 'csv')},
}


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or 'project').lower()).strip('-')[:60] or 'project'


def _title(request):
    words = [w for w in re.findall(r'[A-Za-z][A-Za-z0-9+-]{2,}', request or '') if w.lower() not in
             ('build', 'create', 'make', 'a', 'an', 'the', 'with', 'that', 'for', 'like', 'application',
              'app', 'website', 'project', 'using', 'and', 'simple')]
    title = ' '.join(w.capitalize() for w in words[:4]) or 'Nexus Project'
    return title[:48]


def pick_archetype(request, requested=None):
    if requested in ARCHETYPES:
        return requested
    low = (request or '').lower()
    scores = {key: sum(1 for word in meta['keywords'] if word in low) for key, meta in ARCHETYPES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else 'static-site'


def _plan(request, archetype):
    meta = ARCHETYPES[archetype]
    steps = [
        'Clarify requirements and acceptance criteria from the request.',
        f'Select the {meta["stack"]} stack.',
        'Define the file structure and data flow.',
        'Generate the interface and/or service code.',
        'Add automated checks and documentation.',
        'Execute the checks in the sandbox.',
        'Review quality, security, accessibility and responsiveness.',
    ]
    architecture = (
        f'ARCHETYPE: {meta["label"]}\nSTACK: {meta["stack"]}\n'
        f'REQUEST: {request}\n\n'
        'COMPONENTS\n'
        '- entry point and static assets\n'
        '- domain logic kept separate from presentation\n'
        '- tests that exercise the public behaviour\n'
        '- README with the exact run command\n\n'
        'LIMITS\n'
        '- This is a generated prototype scaffold, not a hardened production deployment.\n'
        '- There is no authentication, persistence or deployment configuration unless explicitly listed.\n'
    )
    return steps, architecture


CHAT_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="app">
  <aside class="sidebar" aria-label="Channels">
    <div class="brand">__TITLE__</div>
    <nav>
      <button class="channel active" data-channel="general"># general</button>
      <button class="channel" data-channel="build-log"># build-log</button>
      <button class="channel" data-channel="random"># random</button>
    </nav>
    <div class="me"><span class="dot"></span><span>NEXUS user</span></div>
  </aside>
  <main class="chat">
    <header><h1 id="channelTitle"># general</h1><span class="pill" id="msgCount">0 messages</span></header>
    <div id="messages" class="messages" role="log" aria-live="polite"></div>
    <form id="composer" class="composer">
      <label class="sr-only" for="input">Message</label>
      <input id="input" autocomplete="off" placeholder="Message #general">
      <button type="submit">Send</button>
    </form>
  </main>
</div>
<script src="app.js"></script>
</body>
</html>
'''

CHAT_CSS = '''*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#0b1020;color:#e7edf7}
.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}
.sidebar{background:#0e1527;border-right:1px solid #1e2a44;padding:20px;display:flex;flex-direction:column;gap:18px}
.brand{font-weight:800;letter-spacing:.06em;color:#5eead4}
nav{display:flex;flex-direction:column;gap:6px}
.channel{background:none;border:0;color:#9fb0c9;text-align:left;padding:9px 10px;border-radius:8px;cursor:pointer;font-size:14px}
.channel:hover,.channel.active{background:#17223b;color:#fff}
.me{margin-top:auto;display:flex;align-items:center;gap:8px;font-size:13px;color:#9fb0c9}
.dot{width:8px;height:8px;border-radius:50%;background:#39ff9a}
.chat{display:flex;flex-direction:column;min-width:0}
header{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-bottom:1px solid #1e2a44}
header h1{font-size:17px;margin:0}
.pill{font-size:12px;color:#8fa3c0;border:1px solid #22304d;padding:4px 10px;border-radius:999px}
.messages{flex:1;overflow-y:auto;padding:18px 22px;display:flex;flex-direction:column;gap:14px}
.msg{display:flex;gap:10px;max-width:760px}
.avatar{width:34px;height:34px;border-radius:50%;background:#1e2a44;display:grid;place-items:center;font-weight:700;color:#5eead4;flex:none}
.msg .body{background:#121a30;border:1px solid #1d2942;padding:10px 13px;border-radius:10px}
.msg .who{font-size:12px;color:#7f93b3;margin-bottom:4px}
.msg.mine .body{background:#14303a;border-color:#1f4c55}
.composer{display:flex;gap:10px;padding:14px 22px 22px}
.composer input{flex:1;background:#121a30;border:1px solid #24314d;border-radius:10px;color:#e7edf7;padding:12px 14px;font-size:14px}
.composer button{background:#5eead4;color:#062018;border:0;border-radius:10px;padding:0 20px;font-weight:700;cursor:pointer}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
@media (max-width:720px){.app{grid-template-columns:1fr}.sidebar{flex-direction:row;align-items:center;overflow-x:auto;padding:10px}.sidebar nav{flex-direction:row}.me{display:none}.messages{padding:12px}.composer{padding:10px 12px 16px}}
'''

CHAT_JS = '''(function () {
  'use strict';
  const KEY = 'nexus-chat-' + document.title.replace(/\\s+/g, '-').toLowerCase();
  const seed = {
    general: [
      { who: 'NEXUS', text: 'Channel created. This prototype stores messages in localStorage.' },
      { who: 'Ada', text: 'The layout is responsive and keyboard accessible.' }
    ],
    'build-log': [{ who: 'NEXUS', text: 'Generated by the NEXUS project builder.' }],
    random: []
  };
  let current = 'general';
  let store = load();
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || seed; }
    catch (e) { return seed; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} }
  function render() {
    const box = document.getElementById('messages');
    const list = store[current] || [];
    box.innerHTML = '';
    list.forEach(function (msg) {
      const wrap = document.createElement('div');
      wrap.className = 'msg' + (msg.who === 'You' ? ' mine' : '');
      const avatar = document.createElement('div');
      avatar.className = 'avatar';
      avatar.textContent = msg.who.slice(0, 1).toUpperCase();
      const body = document.createElement('div');
      body.className = 'body';
      const who = document.createElement('div');
      who.className = 'who';
      who.textContent = msg.who;
      const text = document.createElement('div');
      text.textContent = msg.text;
      body.append(who, text);
      wrap.append(avatar, body);
      box.append(wrap);
    });
    box.scrollTop = box.scrollHeight;
    document.getElementById('msgCount').textContent = list.length + ' messages';
    document.getElementById('channelTitle').textContent = '#' + current;
  }
  document.querySelectorAll('.channel').forEach(function (button) {
    button.addEventListener('click', function () {
      current = button.dataset.channel;
      document.querySelectorAll('.channel').forEach(function (b) { b.classList.toggle('active', b === button); });
      render();
    });
  });
  document.getElementById('composer').addEventListener('submit', function (event) {
    event.preventDefault();
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text) return;
    (store[current] = store[current] || []).push({ who: 'You', text: text });
    input.value = '';
    save();
    render();
  });
  render();
})();
'''

STATIC_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="__TITLE__ — generated by NEXUS.">
<title>__TITLE__</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top">
  <span class="brand">__TITLE__</span>
  <button id="theme" class="ghost" type="button" aria-label="Toggle colour theme">Theme</button>
</header>
<main>
  <section class="hero">
    <p class="eyebrow">GENERATED PROTOTYPE</p>
    <h1>__TITLE__</h1>
    <p class="lede">__TAGLINE__</p>
    <a class="cta" href="#features">Explore features</a>
  </section>
  <section id="features" class="features">
    <article><h2>Fast</h2><p>No build step, no external assets, no tracker scripts.</p></article>
    <article><h2>Accessible</h2><p>Semantic landmarks, labelled controls and visible focus states.</p></article>
    <article><h2>Responsive</h2><p>Fluid layout that collapses cleanly on small screens.</p></article>
  </section>
  <section class="demo">
    <h2>Interactive counter</h2>
    <p>State is kept in memory while the page is open.</p>
    <div class="counter"><button id="dec" type="button" aria-label="Decrease">−</button><output id="value">0</output><button id="inc" type="button" aria-label="Increase">+</button></div>
  </section>
</main>
<footer><span>Built by NEXUS · __YEAR__</span></footer>
<script src="app.js"></script>
</body>
</html>
'''

STATIC_CSS = '''*{box-sizing:border-box}
:root{--bg:#070b16;--panel:#101a2e;--ink:#e9f0fb;--muted:#9aabc5;--accent:__ACCENT__}
body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:radial-gradient(1200px 600px at 20% -10%,#12213a,var(--bg));color:var(--ink);line-height:1.6}
body.light{--bg:#f5f8ff;--panel:#fff;--ink:#101a2e;--muted:#4a5b76;background:#f5f8ff}
.top{display:flex;justify-content:space-between;align-items:center;padding:20px clamp(16px,5vw,64px)}
.brand{font-weight:800;letter-spacing:.12em;color:var(--accent)}
.ghost{background:transparent;border:1px solid var(--accent);color:var(--accent);border-radius:999px;padding:8px 16px;cursor:pointer}
main{max-width:1100px;margin:0 auto;padding:0 clamp(16px,5vw,64px) 64px}
.hero{padding:60px 0 40px;max-width:720px}
.eyebrow{letter-spacing:.28em;font-size:12px;color:var(--accent)}
h1{font-size:clamp(2.2rem,6vw,4rem);line-height:1.05;margin:.2em 0}
.lede{color:var(--muted);font-size:clamp(1rem,2vw,1.2rem)}
.cta{display:inline-block;margin-top:18px;background:var(--accent);color:#04120f;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:700}
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:30px 0}
.features article,.demo{background:var(--panel);border:1px solid rgba(120,150,190,.18);border-radius:16px;padding:22px}
.features h2{margin-top:0;color:var(--accent)}
.demo{max-width:420px}
.counter{display:flex;align-items:center;gap:16px;font-size:22px}
.counter button{width:44px;height:44px;border-radius:12px;border:1px solid var(--accent);background:transparent;color:var(--accent);font-size:22px;cursor:pointer}
footer{text-align:center;color:var(--muted);padding:28px;border-top:1px solid rgba(120,150,190,.15)}
a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:600px){.hero{padding-top:32px}.features{grid-template-columns:1fr}}
'''

STATIC_JS = '''(function () {
  'use strict';
  let value = 0;
  const output = document.getElementById('value');
  function paint() { output.textContent = String(value); }
  document.getElementById('inc').addEventListener('click', function () { value += 1; paint(); });
  document.getElementById('dec').addEventListener('click', function () { value -= 1; paint(); });
  document.getElementById('theme').addEventListener('click', function () {
    document.body.classList.toggle('light');
  });
  paint();
})();
'''

FASTAPI_APP = '''"""__TITLE__ — generated FastAPI service.

Run: uvicorn app:app --reload
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="__TITLE__")
ITEMS: dict[int, dict] = {}
NEXT_ID = {"value": 1}


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    done: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "service": "__TITLE__"}


@app.get("/items")
def list_items():
    return {"items": list(ITEMS.values())}


@app.post("/items", status_code=201)
def create_item(item: ItemIn):
    item_id = NEXT_ID["value"]
    NEXT_ID["value"] += 1
    record = {"id": item_id, **item.model_dump()}
    ITEMS[item_id] = record
    return record


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int):
    if item_id not in ITEMS:
        raise HTTPException(404, "Item not found")
    del ITEMS[item_id]
    return None
'''

FASTAPI_TEST = '''from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def run():
    assert client.get("/health").json()["status"] == "ok"
    created = client.post("/items", json={"name": "write tests"}).json()
    assert created["id"] == 1 and created["done"] is False
    assert len(client.get("/items").json()["items"]) == 1
    assert client.delete("/items/1").status_code == 204
    assert client.get("/items").json()["items"] == []
    assert client.delete("/items/999").status_code == 404
    print("TESTS OK")


if __name__ == "__main__":
    run()
'''

FASTAPI_REQS = 'fastapi>=0.110\nuvicorn[standard]>=0.27\nhttpx>=0.27\n'

CLI_MAIN = '''"""__TITLE__ — generated command-line task tracker.

Usage:
    python main.py add "write docs"
    python main.py list
    python main.py done 1
    python main.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import tempfile


def load(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save(path, items):
    pathlib.Path(path).write_text(json.dumps(items, indent=2), encoding="utf-8")


def add(items, text):
    items.append({"id": (items[-1]["id"] + 1) if items else 1, "text": text, "done": False})
    return items


def complete(items, item_id):
    for item in items:
        if item["id"] == item_id:
            item["done"] = True
            return True
    return False


def render(items):
    if not items:
        return "(empty)"
    return "\\n".join(f'[{"x" if i["done"] else " "}] {i["id"]}. {i["text"]}' for i in items)


def selftest():
    items = add(add([], "first"), "second")
    assert [i["id"] for i in items] == [1, 2]
    assert complete(items, 2) is True
    assert complete(items, 99) is False
    assert items[1]["done"] is True
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "tasks.json"
        save(path, items)
        assert load(path) == items
    assert "second" in render(items)
    print("TESTS OK")


def main(argv=None):
    parser = argparse.ArgumentParser(description="__TITLE__")
    parser.add_argument("--file", default="tasks.json")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    add_p = sub.add_parser("add"); add_p.add_argument("text")
    sub.add_parser("list")
    done_p = sub.add_parser("done"); done_p.add_argument("id", type=int)
    args = parser.parse_args(argv)
    if args.selftest:
        selftest(); return 0
    items = load(args.file)
    if args.command == "add":
        add(items, args.text)
        save(args.file, items)
    elif args.command == "done":
        complete(items, args.id)
        save(args.file, items)
    print(render(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

DATASET_CSV = '''month,users,revenue
2026-01,120,4200
2026-02,180,6100
2026-03,240,7800
2026-04,310,9400
2026-05,420,12100
2026-06,510,14800
'''

DASHBOARD_GEN = '''"""__TITLE__ — build a static dashboard from sales.csv."""
from __future__ import annotations

import csv
import html
import pathlib


def read_rows(path="sales.csv"):
    with open(path, newline="", encoding="utf-8") as handle:
        return [{"month": r["month"], "users": int(r["users"]), "revenue": int(r["revenue"])}
                for r in csv.DictReader(handle)]


def build(rows, title="__TITLE__"):
    peak = max(r["users"] for r in rows) or 1
    bars = "".join(
        f'<li><span class="label">{html.escape(r["month"])}</span>'
        f'<span class="bar" style="width:{r["users"] / peak * 100:.1f}%"></span>'
        f'<span class="value">{r["users"]} users · ${r["revenue"]:,}</span></li>'
        for r in rows
    )
    total = sum(r["revenue"] for r in rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b1020;color:#e8eefb;margin:0;padding:32px}}
main{{max-width:820px;margin:auto}}h1{{font-size:26px}}
ul{{list-style:none;padding:0;display:grid;gap:10px}}
li{{display:grid;grid-template-columns:90px 1fr 160px;align-items:center;gap:12px}}
.bar{{display:block;height:12px;background:#5eead4;border-radius:8px}}
.value{{color:#9fb0c9;font-size:13px}}footer{{margin-top:24px;color:#7f93b3}}
@media (max-width:600px){{li{{grid-template-columns:1fr}}.value{{margin-bottom:8px}}}}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<p>Generated from sales.csv · total revenue ${total:,}</p>
<ul>{bars}</ul>
<footer>Static report — regenerate with <code>python generate.py</code>.</footer>
</main></body></html>"""


def main():
    rows = read_rows()
    pathlib.Path("report.html").write_text(build(rows), encoding="utf-8")
    print(f"Wrote report.html ({len(rows)} rows, {sum(r['revenue'] for r in rows):,} revenue)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

DASHBOARD_TEST = '''import pathlib
import generate

rows = generate.read_rows()
assert len(rows) == 6
assert rows[0]["month"] == "2026-01"
page = generate.build(rows, "Test")
assert "<!doctype html>" in page and "5eead4" in page
generate.main()
out = pathlib.Path("report.html")
assert out.exists() and "total revenue" in out.read_text(encoding="utf-8")
print("TESTS OK")
'''


def _files_for(archetype, title, request):
    tagline = f'A working prototype generated from: {request[:180]}'
    accent = '#5eead4'
    if archetype == 'chat-ui':
        return {'index.html': CHAT_HTML.replace('__TITLE__', html_escape(title)),
                'style.css': CHAT_CSS, 'app.js': CHAT_JS,
                'README.md': _readme(title, request, 'index.html', 'open index.html in a browser', ['index.html', 'style.css', 'app.js'])}
    if archetype == 'static-site':
        return {'index.html': (STATIC_HTML.replace('__TITLE__', html_escape(title))
                               .replace('__TAGLINE__', html_escape(tagline))
                               .replace('__YEAR__', str(datetime.now(timezone.utc).year))),
                'style.css': STATIC_CSS.replace('__ACCENT__', accent), 'app.js': STATIC_JS,
                'README.md': _readme(title, request, 'index.html', 'open index.html in a browser', ['index.html', 'style.css', 'app.js'])}
    if archetype == 'fastapi-api':
        return {'app.py': FASTAPI_APP.replace('__TITLE__', html_escape(title)),
                'test_app.py': FASTAPI_TEST, 'requirements.txt': FASTAPI_REQS,
                'README.md': _readme(title, request, 'app.py', 'python -m uvicorn app:app --reload',
                                     ['app.py', 'test_app.py', 'requirements.txt'], test_command='python test_app.py')}
    if archetype == 'python-cli':
        return {'main.py': CLI_MAIN.replace('__TITLE__', html_escape(title)),
                'README.md': _readme(title, request, 'main.py', 'python main.py --selftest',
                                     ['main.py'], test_command='python main.py --selftest')}
    return {'generate.py': DASHBOARD_GEN.replace('__TITLE__', html_escape(title)),
            'sales.csv': DATASET_CSV, 'test_generate.py': DASHBOARD_TEST,
            'README.md': _readme(title, request, 'generate.py', 'python generate.py',
                                 ['generate.py', 'sales.csv', 'test_generate.py'],
                                 test_command='python test_generate.py')}


def html_escape(value):
    return (value or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _readme(title, request, entry, run, files, test_command=''):
    listed = '\n'.join(f'- `{name}`' for name in files)
    test_line = f'\n## Test\n\n```\n{test_command}\n```\n' if test_command else ''
    return (f'# {title}\n\nGenerated by the NEXUS project builder.\n\n'
            f'**Request:** {request}\n\n## Files\n\n{listed}\n\n## Entry point\n\n`{entry}`\n\n'
            f'## Run\n\n```\n{run}\n```\n{test_line}\n'
            '## Scope\n\nThis is a prototype scaffold. Review it before deployment; '
            'it has no authentication or production hardening.\n')


def _test_target(archetype, files):
    if archetype == 'fastapi-api':
        return 'python', 'test_app.py', files, []
    if archetype == 'python-cli':
        return 'python', 'main.py', files, ['--selftest']
    if archetype == 'data-dashboard':
        return 'python', 'test_generate.py', files, []
    return None, None, files, []


def build_project(request, archetype=None, name=None, run_tests=None, auto_review=None):
    request = (request or '').strip()
    if len(request) < 4:
        raise ValueError('Describe the project in at least a few words.')
    archetype = pick_archetype(request, archetype)
    title = (name or _title(request)).strip()[:60]
    slug = _slug(title)
    directory = PROJECT_ROOT / f'{slug}-{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}'
    directory.mkdir(parents=True, exist_ok=True)
    files = _files_for(archetype, title, request)
    for path, content in files.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    steps, architecture = _plan(request, archetype)
    meta = ARCHETYPES[archetype]
    with connect() as db:
        cur = db.execute(
            'INSERT INTO projects(name,slug,request,archetype,stack,status,directory,entry,files,'
            'architecture,plan,dependencies,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (title, slug, request, archetype, meta['stack'], 'planned', str(directory),
             'index.html' if archetype in ('static-site', 'chat-ui') else
             ('app.py' if archetype == 'fastapi-api' else ('main.py' if archetype == 'python-cli' else 'generate.py')),
             json.dumps(sorted(files)), architecture, json.dumps(steps),
             FASTAPI_REQS.strip() if archetype == 'fastapi-api' else 'standard library only',
             now(), now()))
        project_id = cur.lastrowid
        for path, content in files.items():
            db.execute('INSERT INTO project_files(project_id,path,language,content,created_at) '
                       'VALUES(?,?,?,?,?)', (project_id, path, _ext_lang(path), content, now()))
    event('project', f'Project #{project_id} “{title}” generated ({archetype}, {len(files)} files).')
    test_output = ''
    status = 'built'
    if run_tests is None:
        run_tests = read_bool('project_auto_test', True)
    language, entry, test_files, test_args = _test_target(archetype, files)
    if run_tests and language:
        try:
            result = sandbox.run_code(language, files, entry=entry, args=test_args)
            test_output = ((result.get('stdout') or '') + '\n' + (result.get('stderr') or '')).strip()
            status = 'tested' if result.get('ok') else 'built (tests failed)'
            if result.get('toolchain_missing'):
                status = 'built (toolchain missing)'
        except Exception as exc:
            test_output = f'Test execution skipped: {exc}'
            status = 'built (tests not run)'
    if auto_review is None:
        auto_review = read_bool('review_auto', True)
    review_result = None
    if auto_review:
        try:
            review_result = review.review_files(files, title=title, run_tests=False, ai=False)
            review.save_review('project', project_id, title, review_result)
        except Exception as exc:
            event('warning', f'Project review skipped: {exc}')
    with connect() as db:
        db.execute('UPDATE projects SET status=?,test_output=?,review_score=?,updated_at=? WHERE id=?',
                   (status, test_output[-8000:], (review_result or {}).get('overall', 0), now(), project_id))
    event('project', f'Project #{project_id} status: {status}.')
    return get_project(project_id)


def tests_files(archetype, files):
    """Kept for callers that only need the source map."""
    return files


def _ext_lang(path):
    ext = Path(path).suffix.lower()
    return {'.py': 'python', '.js': 'javascript', '.html': 'html', '.css': 'css',
            '.md': 'markdown', '.csv': 'csv', '.txt': 'text', '.json': 'json'}.get(ext, 'text')


def get_project(project_id):
    with connect() as db:
        row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            return None
        files = [dict(r) for r in db.execute('SELECT path,language,content FROM project_files '
                                             'WHERE project_id=? ORDER BY path', (project_id,)).fetchall()]
        reviews = [dict(r) for r in db.execute("SELECT * FROM reviews WHERE target_kind='project' "
                                               'AND target_id=? ORDER BY id DESC LIMIT 8', (project_id,)).fetchall()]
    data = dict(row)
    for key in ('files', 'plan'):
        try:
            data[key] = json.loads(data.get(key) or '[]')
        except Exception:
            data[key] = []
    data['file_rows'] = files
    data['review_history'] = reviews
    return data


def list_projects(limit=60):
    with connect() as db:
        rows = [dict(r) for r in db.execute(
            'SELECT id,name,slug,request,archetype,stack,status,entry,review_score,files,created_at,updated_at '
            'FROM projects ORDER BY id DESC LIMIT ?', (max(1, min(limit, 200)),)).fetchall()]
    for row in rows:
        try:
            row['files'] = json.loads(row.get('files') or '[]')
        except Exception:
            row['files'] = []
    return rows


def delete_project(project_id):
    with connect() as db:
        row = db.execute('SELECT directory FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise LookupError('Project not found')
        db.execute('DELETE FROM project_files WHERE project_id=?', (project_id,))
        db.execute("DELETE FROM reviews WHERE target_kind='project' AND target_id=?", (project_id,))
        db.execute('DELETE FROM projects WHERE id=?', (project_id,))
    directory = Path(row['directory']).resolve()
    try:
        if PROJECT_ROOT.resolve() in directory.parents:
            shutil.rmtree(directory, ignore_errors=True)
    except Exception:
        pass
    return {'ok': True, 'deleted': project_id}


def run_project_tests(project_id):
    project = get_project(project_id)
    if not project:
        raise LookupError('Project not found')
    files = {row['path']: row['content'] for row in project['file_rows']}
    language, entry, _, test_args = _test_target(project['archetype'], files)
    if not language:
        result = review.run(files, 'html', entry='index.html', mode='test')
        result['ok'] = result.get('ok', False)
    else:
        result = sandbox.run_code(language, files, entry=entry, args=test_args)
    output = ((result.get('stdout') or '') + '\n' + (result.get('stderr') or '')).strip()
    with connect() as db:
        db.execute('UPDATE projects SET test_output=?,status=?,updated_at=? WHERE id=?',
                   (output[-8000:], 'tested' if result.get('ok') else 'built (tests failed)', now(), project_id))
    return {'ok': bool(result.get('ok')), 'output': output, 'result': result}


def export_files(project_id):
    project = get_project(project_id)
    if not project:
        raise LookupError('Project not found')
    return {row['path']: row['content'] for row in project['file_rows']}, project['slug']
