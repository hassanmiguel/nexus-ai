"""Offline program recipes for the NEXUS Program Forge.

Every recipe here is a small, complete, runnable program that NEXUS can write
without a generative model. Each one ships with a ``--selftest`` that asserts
its own behaviour, so "generated" never means "guessed": the forge runs the
checks and only reports a program as verified when they pass.

The recipes are deliberately dependency-light. Python recipes use the standard
library; the FastAPI recipe uses packages that already ship with NEXUS; the
JavaScript recipe needs Node, and the PowerShell recipe needs Windows
PowerShell 5.1+.
"""
from __future__ import annotations

import html
import json
import math
import re
import textwrap


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _slug(text, fallback='program'):
    value = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    value = re.sub(r'-{2,}', '-', value)[:48].strip('-')
    return value or fallback


def _topic(request, default='your project'):
    patterns = [
        r'\b(?:for|about|of|called|named|promoting|showcasing)\s+(?:my\s+|our\s+|a\s+|an\s+|the\s+)?([^.,;!?]{3,64})',
    ]
    for pattern in patterns:
        match = re.search(pattern, request or '', re.I)
        if match:
            topic = re.sub(r'\s+', ' ', match.group(1)).strip(' .')
            topic = re.sub(r'^(?:simple|small|basic|new|modern)\s+', '', topic, flags=re.I)
            if topic:
                return topic[:64]
    return default


def _title_words(text, limit=6):
    words = [w for w in re.split(r'\s+', (text or '').strip()) if w]
    return ' '.join(words[:limit]).title() or 'Program'


def _readme(title, summary, entry, run_command, files, notes=''):
    listing = '\n'.join(f'- `{name}`' for name in files if name != 'README.md')
    body = (
        f'# {title}\n\n'
        f'{summary}\n\n'
        '## Files\n\n'
        f'{listing}\n\n'
        '## Run\n\n'
        '```\n'
        f'{run_command}\n'
        '```\n\n'
        '## Self-test\n\n'
        '```\n'
        f'{run_command.split(" ")[0]} {entry} --selftest\n'
        '```\n\n'
        f'{notes}\n\n'
        '---\n'
        'Written by NEXUS Program Forge. Generated locally; review before running on important data.\n'
    )
    return body


def _check(name, args, expect, stdin=''):
    return {'name': name, 'args': list(args), 'expect': expect, 'stdin': stdin}


def _py_recipe(recipe_id, title, kind, summary, keywords, source, entry='main.py',
               checks=None, run=None, notes=''):
    """Wrap a Python program source string into a recipe dict."""
    files = {'main.py': source}
    title_line = title
    run_command = run or 'python main.py'
    readme = _readme(title_line, summary, entry, run_command, list(files) + ['README.md'], notes)
    return {
        'id': recipe_id,
        'title': title,
        'language': 'python',
        'kind': kind,
        'summary': summary,
        'keywords': keywords,
        'files': {**files, 'README.md': readme},
        'entry': entry,
        'checks': checks or [_check('self-test', ['--selftest'], 'SELFTEST OK')],
        'run': run_command,
    }


# --------------------------------------------------------------------------- #
# 1. CLI calculator
# --------------------------------------------------------------------------- #
def _calculator(context):
    source = r'''#!/usr/bin/env python3
"""Safe command-line calculator.

Only arithmetic is evaluated (numbers, + - * / // % **, parentheses and unary
signs). Expressions are parsed with :mod:`ast`; no Python code is executed.
"""
import argparse
import ast
import operator
import sys

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def evaluate(expression):
    """Evaluate a numeric expression safely."""
    tree = ast.parse(expression, mode='eval')

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.operand))
        raise ValueError('unsupported expression')

    return walk(tree)


def selftest():
    assert evaluate('2+3*4') == 14
    assert evaluate('(2+3)*4') == 20
    assert abs(evaluate('7/2') - 3.5) < 1e-9
    assert evaluate('-3 + 5') == 2
    assert evaluate('2 ** 5') == 32
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Safe command-line calculator')
    parser.add_argument('expression', nargs='*', help='arithmetic, e.g. "2+3*4"')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.expression:
        print('Enter an expression (blank line to quit).')
        for line in sys.stdin:
            line = line.strip()
            if not line:
                break
            try:
                print('=', evaluate(line))
            except Exception as exc:
                print('error:', exc)
        return
    print(evaluate(' '.join(args.expression)))


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-calculator', 'Safe CLI Calculator', 'cli',
        'A command-line arithmetic calculator that evaluates expressions with the Python AST instead of eval().',
        [('calculator', 3), ('arithmetic calculator', 4), ('calculate expressions', 4),
         ('math expression', 3), ('calculate', 1)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK'),
                _check('arithmetic', ['2+3*4'], '14')],
        run='python main.py "2+3*4"')


# --------------------------------------------------------------------------- #
# 2. Number guessing game
# --------------------------------------------------------------------------- #
def _guessing_game(context):
    source = r'''#!/usr/bin/env python3
"""Number guessing game."""
import argparse
import contextlib
import io
import random
import sys


def play(secret, guesses, low=1, high=100, out=print):
    """Play one round against an iterable of guesses."""
    tries = 0
    for raw in guesses:
        raw = str(raw).strip()
        if not raw:
            break
        try:
            guess = int(raw)
        except ValueError:
            out('Please enter a whole number.')
            continue
        tries += 1
        if guess < low or guess > high:
            out(f'Stay between {low} and {high}.')
        elif guess < secret:
            out('higher')
        elif guess > secret:
            out('lower')
        else:
            out(f'correct! You found it in {tries} tries.')
            return True
    out(f'Out of guesses. The number was {secret}.')
    return False


def selftest():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        won = play(7, iter(['3', '9', '7']), out=print)
    text = buffer.getvalue()
    assert won is True
    assert 'higher' in text and 'lower' in text and 'correct' in text
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Guess the secret number')
    parser.add_argument('--low', type=int, default=1)
    parser.add_argument('--high', type=int, default=100)
    parser.add_argument('--secret', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.low >= args.high:
        parser.error('--low must be smaller than --high')
    secret = args.secret if args.secret is not None else random.randint(args.low, args.high)
    print(f'I picked a number between {args.low} and {args.high}. Type guesses and press Enter.')
    play(secret, sys.stdin, args.low, args.high)


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-guessing-game', 'Number Guessing Game', 'game',
        'A small console game: NEXUS picks a number and tells you whether to guess higher or lower.',
        [('guessing game', 4), ('guess the number', 4), ('number guessing', 4),
         ('guess a number', 3), ('guessing', 1)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK'),
                _check('play a round', ['--secret', '7'], 'correct', stdin='3\n9\n7\n')])


# --------------------------------------------------------------------------- #
# 3. Todo CLI
# --------------------------------------------------------------------------- #
def _todo_cli(context):
    source = r'''#!/usr/bin/env python3
"""A small persistent todo list stored in JSON."""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime

DEFAULT_DB = 'todos.json'


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            return []


def save(path, items):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(items, handle, indent=2)


def add(path, text):
    items = load(path)
    items.append({'task': text, 'done': False, 'created': datetime.now().isoformat(timespec='seconds')})
    save(path, items)
    return items[-1]


def complete(path, index):
    items = load(path)
    if not 1 <= index <= len(items):
        raise IndexError('task number out of range')
    items[index - 1]['done'] = True
    save(path, items)
    return items[index - 1]


def remove(path, index):
    items = load(path)
    if not 1 <= index <= len(items):
        raise IndexError('task number out of range')
    return items.pop(index - 1), save(path, items)


def render(items):
    if not items:
        return 'No tasks yet. Add one with: add "your task"'
    lines = []
    for number, item in enumerate(items, 1):
        mark = 'x' if item.get('done') else ' '
        lines.append(f'{number:>2}. [{mark}] {item.get("task", "")}')
    return '\n'.join(lines)


def build_parser():
    parser = argparse.ArgumentParser(description='Persistent todo list')
    parser.add_argument('--db', default=DEFAULT_DB, help='JSON file to store tasks')
    sub = parser.add_subparsers(dest='command')
    add_parser = sub.add_parser('add', help='add a task')
    add_parser.add_argument('text')
    list_parser = sub.add_parser('list', help='show tasks')
    list_parser.add_argument('--all', action='store_true')
    done_parser = sub.add_parser('done', help='mark a task done')
    done_parser.add_argument('index', type=int)
    remove_parser = sub.add_parser('remove', help='delete a task')
    remove_parser.add_argument('index', type=int)
    parser.add_argument('--selftest', action='store_true')
    return parser


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'todos.json')
        add(path, 'write tests')
        add(path, 'ship it')
        assert len(load(path)) == 2
        complete(path, 1)
        assert load(path)[0]['done'] is True
        text = render(load(path))
        assert 'write tests' in text and '[x]' in text
        remove(path, 2)
        assert len(load(path)) == 1
    print('SELFTEST OK')


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.command:
        parser.print_help()
        return
    if args.command == 'add':
        item = add(args.db, args.text)
        print('Added:', item['task'])
    elif args.command == 'list':
        items = load(args.db)
        if not args.all:
            items = [item for item in items if not item.get('done')]
        print(render(items))
    elif args.command == 'done':
        print('Completed:', complete(args.db, args.index)['task'])
    elif args.command == 'remove':
        print('Removed:', remove(args.db, args.index)[0]['task'])


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-todo-cli', 'Persistent Todo CLI', 'cli',
        'A todo list that persists to JSON, with add, list, complete and remove commands.',
        [('todo', 3), ('to-do', 3), ('task list', 3), ('checklist', 2), ('todo list', 4)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py add "buy milk"  &&  python main.py list')


# --------------------------------------------------------------------------- #
# 4. Expense tracker
# --------------------------------------------------------------------------- #
def _expense_tracker(context):
    source = r'''#!/usr/bin/env python3
"""SQLite expense tracker with add, list and summary commands."""
import argparse
import os
import sqlite3
import tempfile

DEFAULT_DB = 'expenses.db'
SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT DEFAULT '',
    spent_on TEXT NOT NULL
)
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute(SCHEMA)
    return db


def add(db, amount, category, note, spent_on):
    cur = db.execute('INSERT INTO expenses(amount,category,note,spent_on) VALUES(?,?,?,?)',
                     (float(amount), category, note, spent_on))
    db.commit()
    return cur.lastrowid


def rows(db):
    return db.execute('SELECT * FROM expenses ORDER BY spent_on DESC, id DESC').fetchall()


def summary(db):
    result = db.execute(
        'SELECT category, ROUND(SUM(amount), 2) total, COUNT(*) count '
        'FROM expenses GROUP BY category ORDER BY total DESC').fetchall()
    total = db.execute('SELECT ROUND(COALESCE(SUM(amount), 0), 2) FROM expenses').fetchone()[0]
    return total, result


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        db = connect(os.path.join(folder, 'test.db'))
        try:
            add(db, 12.50, 'food', 'lunch', '2025-01-01')
            add(db, 30.00, 'transport', 'train', '2025-01-02')
            add(db, 7.25, 'food', 'coffee', '2025-01-03')
            total, by_category = summary(db)
            totals = {row['category']: row['total'] for row in by_category}
            assert abs(total - 49.75) < 1e-9, total
            assert len(rows(db)) == 3
            assert totals['food'] == 19.75 and totals['transport'] == 30.0
            assert by_category[0]['category'] == 'transport'
        finally:
            db.close()
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Track expenses in SQLite')
    parser.add_argument('--db', default=DEFAULT_DB)
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='command')
    add_parser = sub.add_parser('add')
    add_parser.add_argument('amount', type=float)
    add_parser.add_argument('category')
    add_parser.add_argument('--note', default='')
    add_parser.add_argument('--date', default='today')
    sub.add_parser('list')
    sub.add_parser('summary')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    db = connect(args.db)
    if args.command == 'add':
        spent_on = args.date
        if spent_on == 'today':
            from datetime import date
            spent_on = date.today().isoformat()
        new_id = add(db, args.amount, args.category, args.note, spent_on)
        print(f'Added expense #{new_id}')
    elif args.command in ('list', 'summary'):
        total, by_category = summary(db)
        if args.command == 'summary':
            print(f'Total: {total:.2f}')
            for row in by_category:
                print(f"  {row['category']:<14} {row['total']:>9.2f}  ({row['count']} items)")
        else:
            for row in rows(db):
                print(f"#{row['id']:<3} {row['spent_on']}  {row['category']:<12} {row['amount']:>8.2f}  {row['note']}")
            print(f'Total: {total:.2f}')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-expense-tracker', 'SQLite Expense Tracker', 'cli',
        'A dependency-free expense tracker: add expenses, list them and see totals by category in SQLite.',
        [('expense', 3), ('budget', 2), ('spending', 2), ('finance tracker', 3), ('expenses', 3)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py add 12.50 food --note "lunch"  &&  python main.py summary')


# --------------------------------------------------------------------------- #
# 5. Password generator
# --------------------------------------------------------------------------- #
def _password_generator(context):
    source = r'''#!/usr/bin/env python3
"""Cryptographically strong password generator."""
import argparse
import secrets
import string

LETTERS = string.ascii_letters
DIGITS = string.digits
SYMBOLS = '!@#$%^&*()-_=+[]{};:,.?'


def generate(length=20, symbols=True):
    if length < 8:
        raise ValueError('use at least 8 characters')
    alphabet = LETTERS + DIGITS + (SYMBOLS if symbols else '')
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in password) and any(c.isupper() for c in password) \
                and any(c.isdigit() for c in password) \
                and (not symbols or any(c in SYMBOLS for c in password)):
            return password


def entropy_bits(length, symbols=True):
    alphabet = len(LETTERS + DIGITS + (SYMBOLS if symbols else ''))
    return round(length * __import__('math').log2(alphabet), 1)


def selftest():
    for _ in range(20):
        password = generate(24, True)
        assert len(password) == 24
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in SYMBOLS for c in password)
    assert entropy_bits(20, True) > 100
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Generate strong passwords')
    parser.add_argument('--length', type=int, default=20)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--no-symbols', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    for _ in range(max(1, args.count)):
        print(generate(args.length, not args.no_symbols))
    print(f'# {entropy_bits(args.length, not args.no_symbols)} bits of entropy per password')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-password-generator', 'Password Generator', 'tool',
        'A cryptographic password generator using the secrets module, with an entropy estimate.',
        [('password generator', 4), ('generate passwords', 3), ('strong password', 3), ('password', 1)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py --length 24 --count 3')


# --------------------------------------------------------------------------- #
# 6. Unit converter
# --------------------------------------------------------------------------- #
def _unit_converter(context):
    source = r'''#!/usr/bin/env python3
"""Length, mass and temperature unit converter."""
import argparse

LENGTH = {
    'mm': 0.001, 'cm': 0.01, 'm': 1.0, 'km': 1000.0,
    'in': 0.0254, 'ft': 0.3048, 'yd': 0.9144, 'mi': 1609.344,
}
MASS = {
    'mg': 0.000001, 'g': 0.001, 'kg': 1.0, 't': 1000.0,
    'oz': 0.028349523125, 'lb': 0.45359237,
}


def convert_length(value, source, target):
    return value * LENGTH[source] / LENGTH[target]


def convert_mass(value, source, target):
    return value * MASS[source] / MASS[target]


def convert_temperature(value, source, target):
    source, target = source.lower(), target.lower()
    if source == target:
        return value
    if source == 'c':
        celsius = value
    elif source == 'f':
        celsius = (value - 32) * 5 / 9
    elif source == 'k':
        celsius = value - 273.15
    else:
        raise ValueError(f'unknown temperature unit: {source}')
    if target == 'c':
        return celsius
    if target == 'f':
        return celsius * 9 / 5 + 32
    if target == 'k':
        return celsius + 273.15
    raise ValueError(f'unknown temperature unit: {target}')


def convert(value, source, target):
    source, target = source.lower(), target.lower()
    if source in LENGTH and target in LENGTH:
        return convert_length(value, source, target)
    if source in MASS and target in MASS:
        return convert_mass(value, source, target)
    if source in ('c', 'f', 'k') and target in ('c', 'f', 'k'):
        return convert_temperature(value, source, target)
    raise ValueError(f'cannot convert {source} to {target}')


def selftest():
    assert abs(convert(1, 'km', 'mi') - 0.621371) < 0.0001
    assert abs(convert(100, 'c', 'f') - 212) < 1e-9
    assert abs(convert(32, 'f', 'c')) < 1e-9
    assert abs(convert(1, 'kg', 'lb') - 2.20462) < 0.0001
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Convert length, mass and temperature units')
    parser.add_argument('value', type=float, nargs='?')
    parser.add_argument('source', nargs='?')
    parser.add_argument('target', nargs='?')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.value is None:
        print('Length:', ', '.join(LENGTH))
        print('Mass:  ', ', '.join(MASS))
        print('Temp:   c, f, k')
        print('Example: python main.py 100 c f')
        return
    print(f'{args.value:g} {args.source} = {convert(args.value, args.source, args.target):.6g} {args.target}')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-unit-converter', 'Unit Converter', 'tool',
        'Convert length, mass and temperature units from the command line.',
        [('unit converter', 4), ('unit conversion', 4), ('convert units', 3),
         ('celsius', 3), ('fahrenheit', 3), ('temperature', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK'),
                _check('convert', ['100', 'c', 'f'], '212')],
        run='python main.py 100 c f')


# --------------------------------------------------------------------------- #
# 7. Countdown timer
# --------------------------------------------------------------------------- #
def _timer(context):
    source = r'''#!/usr/bin/env python3
"""Countdown timer with a stopwatch-style display."""
import argparse
import sys
import time


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}'


def countdown(total, sleep=time.sleep, out=print, tick=1):
    remaining = max(0, int(total))
    while remaining > 0:
        out(format_duration(remaining))
        sleep(min(tick, remaining))
        remaining -= min(tick, remaining)
    out('00:00:00')
    out('Time is up.')
    return 0


def parse_duration(text):
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    match = __import__('re').fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', text)
    if not match or not any(match.groups()):
        raise ValueError('use seconds (90) or a duration like 1h30m')
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def selftest():
    assert format_duration(0) == '00:00:00'
    assert format_duration(3661) == '01:01:01'
    assert parse_duration('1h30m') == 5400
    assert parse_duration('45s') == 45
    seen = []
    countdown(3, sleep=lambda _: None, out=seen.append)
    assert seen == ['00:00:03', '00:00:02', '00:00:01', '00:00:00', 'Time is up.']
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Countdown timer')
    parser.add_argument('duration', nargs='?', default='5m', help='seconds or 1h30m')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    try:
        seconds = parse_duration(args.duration)
    except ValueError as exc:
        parser.error(str(exc))
    countdown(seconds)


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-timer', 'Countdown Timer', 'tool',
        'A countdown timer that accepts seconds or durations such as 1h30m.',
        [('countdown', 3), ('timer', 2), ('stopwatch', 2), ('pomodoro', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py 5m')


# --------------------------------------------------------------------------- #
# 8. File organizer
# --------------------------------------------------------------------------- #
def _file_organizer(context):
    source = r'''#!/usr/bin/env python3
"""Organize files into folders by extension, with a safe dry-run default."""
import argparse
import os
import shutil
import tempfile

CATEGORIES = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff'},
    'documents': {'.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.odt'},
    'spreadsheets': {'.csv', '.xls', '.xlsx', '.ods'},
    'audio': {'.mp3', '.wav', '.flac', '.ogg', '.m4a'},
    'video': {'.mp4', '.mkv', '.avi', '.mov', '.webm'},
    'archives': {'.zip', '.rar', '.7z', '.tar', '.gz'},
    'code': {'.py', '.js', '.ts', '.html', '.css', '.json', '.yml', '.yaml', '.sql', '.ps1'},
}


def category_for(filename):
    extension = os.path.splitext(filename)[1].lower()
    for category, extensions in CATEGORIES.items():
        if extension in extensions:
            return category
    return 'other'


def unique_target(folder, name):
    target = os.path.join(folder, name)
    if not os.path.exists(target):
        return target
    stem, extension = os.path.splitext(name)
    counter = 1
    while True:
        candidate = os.path.join(folder, f'{stem} ({counter}){extension}')
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def organize(root, apply=False, out=print):
    moves = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isfile(path) or name.startswith('.'):
            continue
        category = category_for(name)
        target_dir = os.path.join(root, category)
        target = unique_target(target_dir, name)
        moves.append((path, target, category))
        if apply:
            os.makedirs(target_dir, exist_ok=True)
            shutil.move(path, target)
    for source, target, category in moves:
        out(f'{"MOVED" if apply else "WOULD MOVE"}  {os.path.basename(source)} -> {category}/')
    if not moves:
        out('Nothing to organize.')
    return moves


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        for name in ('photo.png', 'notes.txt', 'song.mp3', 'script.py'):
            with open(os.path.join(folder, name), 'w', encoding='utf-8') as handle:
                handle.write('x')
        moves = organize(folder, apply=True, out=lambda *_: None)
        assert len(moves) == 4
        assert os.path.isdir(os.path.join(folder, 'images'))
        assert os.path.isfile(os.path.join(folder, 'code', 'script.py'))
        assert not os.path.isfile(os.path.join(folder, 'photo.png'))
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Organize files by extension')
    parser.add_argument('directory', nargs='?', default='.')
    parser.add_argument('--apply', action='store_true', help='actually move files (default is a dry run)')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    root = os.path.abspath(args.directory)
    if not os.path.isdir(root):
        parser.error(f'not a directory: {root}')
    organize(root, apply=args.apply)
    if not args.apply:
        print('Dry run only. Add --apply to move the files.')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-file-organizer', 'File Organizer', 'automation',
        'Sort files into images, documents, audio, video, archives and code folders. Dry-run by default.',
        [('organize files', 4), ('file organizer', 4), ('sort files', 3),
         ('by extension', 3), ('clean up folder', 3), ('organize folder', 4),
         ('rename files', 4), ('rename', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py "C:\\Users\\you\\Downloads"   # dry run')


# --------------------------------------------------------------------------- #
# 9. Duplicate finder
# --------------------------------------------------------------------------- #
def _duplicate_finder(context):
    source = r'''#!/usr/bin/env python3
"""Find duplicate files by size and SHA-256 content hash."""
import argparse
import hashlib
import os
import tempfile


def hash_file(path, chunk_size=65536):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(root, min_size=1):
    by_size = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size >= min_size:
                by_size.setdefault(size, []).append(path)
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash = {}
        for path in paths:
            try:
                by_hash.setdefault(hash_file(path), []).append(path)
            except OSError:
                continue
        for digest, matches in by_hash.items():
            if len(matches) > 1:
                groups.append({'size': size, 'sha256': digest, 'files': matches})
    groups.sort(key=lambda group: group['size'] * len(group['files']), reverse=True)
    return groups


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        payload = b'identical content'
        for name in ('a.txt', 'b.txt', 'sub/c.txt'):
            path = os.path.join(folder, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as handle:
                handle.write(payload)
        with open(os.path.join(folder, 'unique.txt'), 'wb') as handle:
            handle.write(b'different')
        groups = find_duplicates(folder)
        assert len(groups) == 1, groups
        assert len(groups[0]['files']) == 3
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Find duplicate files')
    parser.add_argument('directory', nargs='?', default='.')
    parser.add_argument('--min-size', type=int, default=1, help='ignore files smaller than this many bytes')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    groups = find_duplicates(os.path.abspath(args.directory), args.min_size)
    if not groups:
        print('No duplicates found.')
        return
    wasted = 0
    for number, group in enumerate(groups, 1):
        print(f'Group {number} — {group["size"]} bytes each, sha256 {group["sha256"][:16]}…')
        for path in group['files']:
            print('  ', path)
        wasted += group['size'] * (len(group['files']) - 1)
    print(f'\n{wasted} bytes could be reclaimed. Nothing was deleted.')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-duplicate-finder', 'Duplicate File Finder', 'automation',
        'Find duplicate files by size and SHA-256 hash. Read-only: it never deletes anything.',
        [('duplicate files', 4), ('duplicate finder', 4), ('find duplicates', 4),
         ('duplicate', 2), ('same file', 1)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py "C:\\Users\\you\\Pictures"')


# --------------------------------------------------------------------------- #
# 10. Backup script
# --------------------------------------------------------------------------- #
def _backup_script(context):
    source = r'''#!/usr/bin/env python3
"""Create a timestamped ZIP backup of a folder."""
import argparse
import os
import tempfile
import zipfile
from datetime import datetime


def create_backup(source, destination=None, out=print):
    source = os.path.abspath(source)
    if not os.path.isdir(source):
        raise NotADirectoryError(source)
    if destination is None:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        destination = os.path.join(os.path.dirname(source), f'{os.path.basename(source)}-backup-{stamp}.zip')
    destination = os.path.abspath(destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    count = 0
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for folder, _dirs, files in os.walk(source):
            for name in files:
                path = os.path.join(folder, name)
                if os.path.abspath(path) == destination:
                    continue
                archive.write(path, os.path.relpath(path, source))
                count += 1
    out(f'Backed up {count} file(s) to {destination}')
    return destination, count


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, 'data')
        os.makedirs(os.path.join(source, 'nested'))
        with open(os.path.join(source, 'a.txt'), 'w', encoding='utf-8') as handle:
            handle.write('alpha')
        with open(os.path.join(source, 'nested', 'b.txt'), 'w', encoding='utf-8') as handle:
            handle.write('beta')
        destination = os.path.join(folder, 'backup.zip')
        path, count = create_backup(source, destination, out=lambda *_: None)
        assert count == 2
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            assert 'a.txt' in names and 'nested/b.txt' in names
            assert archive.read('nested/b.txt') == b'beta'
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='ZIP a folder with a timestamped name')
    parser.add_argument('source', nargs='?')
    parser.add_argument('--dest', help='output .zip path')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.source:
        parser.error('provide a source folder')
    create_backup(args.source, args.dest)


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-backup-script', 'Backup Script', 'automation',
        'Zip a folder into a timestamped archive, keeping relative paths intact.',
        [('backup', 4), ('archive folder', 3), ('zip folder', 3), ('compress folder', 3)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py "C:\\Users\\you\\Documents"')


# --------------------------------------------------------------------------- #
# 11. Log analyzer
# --------------------------------------------------------------------------- #
def _log_analyzer(context):
    source = r'''#!/usr/bin/env python3
"""Analyze common/combined web-server access logs."""
import argparse
import collections
import json
import re
import sys

LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>[^"]*?) \S+" (?P<status>\d{3}) (?P<size>\S+)')


def parse_line(line):
    match = LINE.match(line.strip())
    if not match:
        return None
    data = match.groupdict()
    data['size'] = int(data['size']) if data['size'].isdigit() else 0
    return data


def analyze(text):
    records = [record for record in (parse_line(line) for line in text.splitlines()) if record]
    status = collections.Counter(record['status'] for record in records)
    paths = collections.Counter(record['path'].split('?')[0] for record in records)
    ips = collections.Counter(record['ip'] for record in records)
    errors = sum(count for code, count in status.items() if code.startswith(('4', '5')))
    return {
        'requests': len(records),
        'unique_ips': len(ips),
        'errors': errors,
        'status': dict(status.most_common()),
        'top_paths': paths.most_common(10),
        'top_ips': ips.most_common(10),
        'bytes': sum(record['size'] for record in records),
    }


def report(summary):
    lines = [
        f"Requests: {summary['requests']}  Unique IPs: {summary['unique_ips']}  "
        f"Errors: {summary['errors']}  Bytes: {summary['bytes']}",
        '',
        'Status codes:',
    ]
    lines += [f'  {code}: {count}' for code, count in summary['status'].items()]
    lines += ['', 'Top paths:']
    lines += [f'  {count:>5}  {path}' for path, count in summary['top_paths']]
    lines += ['', 'Top IPs:']
    lines += [f'  {count:>5}  {ip}' for ip, count in summary['top_ips']]
    return '\n'.join(lines)


SAMPLE = (
    '127.0.0.1 - - [10/Oct/2025:13:55:36 +0000] "GET /index.html HTTP/1.1" 200 1234\n'
    '127.0.0.1 - - [10/Oct/2025:13:55:37 +0000] "GET /index.html HTTP/1.1" 200 1234\n'
    '10.0.0.9 - - [10/Oct/2025:13:55:38 +0000] "POST /api/login HTTP/1.1" 401 88\n'
    '10.0.0.9 - - [10/Oct/2025:13:55:39 +0000] "GET /missing HTTP/1.1" 404 12\n'
)


def selftest():
    summary = analyze(SAMPLE)
    assert summary['requests'] == 4
    assert summary['unique_ips'] == 2
    assert summary['errors'] == 2
    assert summary['top_paths'][0] == ('/index.html', 2)
    assert 'Requests: 4' in report(summary)
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Summarize an access log')
    parser.add_argument('file', nargs='?', help='log file (stdin if omitted)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.file:
        with open(args.file, 'r', encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    summary = analyze(text)
    print(json.dumps(summary, indent=2) if args.json else report(summary))


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-log-analyzer', 'Access Log Analyzer', 'data',
        'Parse common/combined access logs and report status codes, top paths, top IPs and bandwidth.',
        [('log analyzer', 4), ('analyze logs', 4), ('access log', 4), ('server log', 4),
         ('parse logs', 3), ('log file', 2), ('apache log', 5), ('nginx log', 5),
         ('web server log', 5)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py access.log')


# --------------------------------------------------------------------------- #
# 12. CSV summary
# --------------------------------------------------------------------------- #
def _csv_summary(context):
    source = r'''#!/usr/bin/env python3
"""Summarize a CSV file: row counts, numeric statistics and top values."""
import argparse
import csv
import json
import math
import tempfile


def is_number(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def summarize(path, column=None):
    with open(path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if not rows:
        return {'rows': 0, 'columns': fields, 'numeric': {}, 'text': {}}
    numeric = {}
    text = {}
    for field in fields:
        values = [row.get(field, '') for row in rows]
        numbers = [float(value) for value in values if is_number(value) and value != '']
        if numbers and len(numbers) >= max(1, len(values) // 2):
            numeric[field] = {
                'count': len(numbers),
                'min': min(numbers),
                'max': max(numbers),
                'mean': round(sum(numbers) / len(numbers), 4),
                'sum': round(sum(numbers), 4),
            }
        else:
            counts = {}
            for value in values:
                counts[value] = counts.get(value, 0) + 1
            top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
            text[field] = {'unique': len(counts), 'top': top}
    result = {'rows': len(rows), 'columns': fields, 'numeric': numeric, 'text': text}
    if column:
        if column not in fields:
            raise KeyError(f'column not found: {column}')
        result['selected'] = {column: numeric.get(column) or text.get(column)}
    return result


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        path = f'{folder}/sample.csv'
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(['name', 'score', 'city'])
            writer.writerow(['Ada', '91', 'London'])
            writer.writerow(['Grace', '88', 'New York'])
            writer.writerow(['Alan', '75', 'London'])
        summary = summarize(path)
        assert summary['rows'] == 3
        assert summary['numeric']['score']['max'] == 91
        assert abs(summary['numeric']['score']['mean'] - 84.6667) < 0.001
        assert summary['text']['city']['top'][0] == ('London', 2)
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Summarize a CSV file')
    parser.add_argument('file', nargs='?')
    parser.add_argument('--column', help='focus on one column')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.file:
        parser.error('provide a CSV file')
    summary = summarize(args.file, args.column)
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"Rows: {summary['rows']}  Columns: {', '.join(summary['columns'])}")
    for name, stats in summary['numeric'].items():
        print(f"  {name:<16} min {stats['min']:g}  max {stats['max']:g}  mean {stats['mean']:g}  sum {stats['sum']:g}")
    for name, stats in summary['text'].items():
        print(f"  {name:<16} {stats['unique']} unique; top: {stats['top'][:3]}")


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-csv-summary', 'CSV Summary', 'data',
        'Read a CSV and report numeric statistics plus the most common values in text columns.',
        [('csv summary', 4), ('summarize csv', 4), ('csv file', 3), ('csv', 2), ('spreadsheet', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py data.csv')


# --------------------------------------------------------------------------- #
# 13. Web scraper
# --------------------------------------------------------------------------- #
def _web_scraper(context):
    source = r'''#!/usr/bin/env python3
"""Extract titles, headings, links and meta descriptions from a page."""
import argparse
import json
import re
import tempfile
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

USER_AGENT = 'NexusProgramForge/1.0 (+local personal use)'


class Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.headings = []
        self.links = []
        self.description = ''
        self._tag = None
        self._buffer = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self._in_title = True
        if tag in ('h1', 'h2', 'h3'):
            self._tag = tag
            self._buffer = []
        if tag == 'a' and attrs.get('href'):
            self.links.append({'href': attrs['href'], 'text': ''})
        if tag == 'meta' and attrs.get('name', '').lower() == 'description':
            self.description = attrs.get('content', '')

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._tag:
            self._buffer.append(data)
        if self.links and self.links[-1]['text'] == '':
            self.links[-1]['text'] = re.sub(r'\s+', ' ', data).strip()

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag == self._tag:
            text = re.sub(r'\s+', ' ', ' '.join(self._buffer)).strip()
            if text:
                self.headings.append({'tag': tag, 'text': text})
            self._tag = None
            self._buffer = []


def extract(html_text, base_url=''):
    parser = Extractor()
    parser.feed(html_text)
    links = []
    seen = set()
    for link in parser.links:
        href = urljoin(base_url, link['href']) if base_url else link['href']
        if not href or href in seen or href.startswith(('javascript:', 'mailto:')):
            continue
        seen.add(href)
        links.append({'href': href, 'text': link['text']})
    return {
        'title': re.sub(r'\s+', ' ', parser.title).strip(),
        'description': parser.description.strip(),
        'headings': parser.headings[:40],
        'links': links[:200],
    }


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or 'utf-8'
        return response.read().decode(charset, errors='replace')


SAMPLE = """<html><head><title>Demo Page</title>
<meta name="description" content="A tiny demo">
</head><body><h1>Welcome</h1><h2>Features</h2>
<a href="/docs">Docs</a><a href="https://example.com">Example</a></body></html>"""


def selftest():
    with tempfile.TemporaryDirectory() as folder:
        path = f'{folder}/page.html'
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(SAMPLE)
        with open(path, 'r', encoding='utf-8') as handle:
            data = extract(handle.read(), 'https://demo.test/base/')
        assert data['title'] == 'Demo Page'
        assert data['description'] == 'A tiny demo'
        assert data['headings'][0] == {'tag': 'h1', 'text': 'Welcome'}
        assert data['links'][0]['href'] == 'https://demo.test/docs'
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Extract structure from a web page')
    parser.add_argument('--url')
    parser.add_argument('--file')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.url and not args.file:
        parser.error('provide --url or --file')
    if args.url:
        data = extract(fetch(args.url), args.url)
    else:
        with open(args.file, 'r', encoding='utf-8', errors='replace') as handle:
            data = extract(handle.read(), '')
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print('Title:', data['title'] or '(none)')
    if data['description']:
        print('Description:', data['description'])
    print('\nHeadings:')
    for heading in data['headings']:
        print(f"  {heading['tag']}: {heading['text']}")
    print(f"\nLinks ({len(data['links'])}):")
    for link in data['links'][:30]:
        print(f"  {link['text'][:50]:<50} {link['href']}")


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-web-scraper', 'Web Page Scraper', 'data',
        'Extract the title, meta description, headings and links from a public page using only the standard library.',
        [('web scraper', 4), ('scrape', 3), ('scraper', 3), ('extract links', 4),
         ('crawl page', 3), ('scrape website', 4), ('scrape a webpage', 6),
         ('scrape webpage', 6), ('list links', 5), ('webpage links', 5)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py --url https://example.com')


# --------------------------------------------------------------------------- #
# 14. REST API
# --------------------------------------------------------------------------- #
def _rest_api(context):
    source = r'''#!/usr/bin/env python3
"""A small FastAPI todo API with in-memory storage."""
import argparse
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title='NEXUS Todo API', version='1.0.0')
TODOS = {}
NEXT_ID = 1


class TodoCreate(BaseModel):
    title: str
    done: bool = False


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


@app.get('/health')
def health():
    return {'status': 'ok', 'todos': len(TODOS)}


@app.get('/todos')
def list_todos(done: Optional[bool] = None):
    items = list(TODOS.values())
    if done is not None:
        items = [item for item in items if item['done'] == done]
    return items


@app.post('/todos', status_code=201)
def create_todo(payload: TodoCreate):
    global NEXT_ID
    item = {'id': NEXT_ID, 'title': payload.title, 'done': payload.done}
    TODOS[NEXT_ID] = item
    NEXT_ID += 1
    return item


@app.get('/todos/{todo_id}')
def get_todo(todo_id: int):
    if todo_id not in TODOS:
        raise HTTPException(status_code=404, detail='todo not found')
    return TODOS[todo_id]


@app.patch('/todos/{todo_id}')
def update_todo(todo_id: int, payload: TodoUpdate):
    if todo_id not in TODOS:
        raise HTTPException(status_code=404, detail='todo not found')
    item = TODOS[todo_id]
    if payload.title is not None:
        item['title'] = payload.title
    if payload.done is not None:
        item['done'] = payload.done
    return item


@app.delete('/todos/{todo_id}')
def delete_todo(todo_id: int):
    if todo_id not in TODOS:
        raise HTTPException(status_code=404, detail='todo not found')
    return TODOS.pop(todo_id)


def selftest():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get('/health').json()['status'] == 'ok'
    created = client.post('/todos', json={'title': 'write tests'}).json()
    assert created['id'] == 1 and created['done'] is False
    assert client.get('/todos').json()[0]['title'] == 'write tests'
    assert client.patch('/todos/1', json={'done': True}).json()['done'] is True
    assert client.get('/todos?done=true').json()[0]['id'] == 1
    assert client.delete('/todos/1').json()['id'] == 1
    assert client.get('/todos/1').status_code == 404
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Run the todo API')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
'''
    files = {
        'main.py': source,
        'requirements.txt': 'fastapi\nuvicorn[standard]\n',
    }
    readme = _readme(
        'Todo REST API', 'A FastAPI CRUD API for todos with validation, filtering and health checks.',
        'main.py', 'uvicorn main:app --reload --port 8000',
        list(files) + ['README.md'],
        'Interactive docs are at http://127.0.0.1:8000/docs once the server is running. '
        'Storage is in memory, so restarting clears the list.')
    return {
        'id': 'python-rest-api',
        'title': 'Todo REST API',
        'language': 'python',
        'kind': 'api',
        'summary': 'A FastAPI CRUD API for todos with validation, filtering and health checks.',
        'keywords': [('rest api', 4), ('api', 2), ('fastapi', 4), ('crud', 3),
                     ('web server', 3), ('json api', 3), ('todo api', 4)],
        'files': {**files, 'README.md': readme},
        'entry': 'main.py',
        'checks': [_check('self-test', ['--selftest'], 'SELFTEST OK')],
        'run': 'uvicorn main:app --reload --port 8000',
    }


# --------------------------------------------------------------------------- #
# 15. Static website
# --------------------------------------------------------------------------- #
def _static_site(context):
    topic = html.escape((context.get('topic') or 'Your Project').strip())
    title = html.escape(_title_words(topic))
    accent = '#22d3ee'
    index = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{topic} — a modern landing page.">
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="nav">
    <a class="brand" href="#top">{title}</a>
    <nav>
      <a href="#features">Features</a>
      <a href="#about">About</a>
      <a href="#contact">Contact</a>
      <button id="theme" class="theme" aria-label="Toggle theme">◐</button>
    </nav>
  </header>

  <main id="top">
    <section class="hero">
      <p class="eyebrow">WELCOME</p>
      <h1>{topic}</h1>
      <p class="lead">A clean, responsive page generated by NEXUS Program Forge. Replace this copy with your own story.</p>
      <div class="actions">
        <a class="button primary" href="#contact">Get started</a>
        <a class="button ghost" href="#features">Learn more</a>
      </div>
    </section>

    <section id="features" class="features">
      <article><h2>Fast</h2><p>No frameworks, no build step — just semantic HTML, modern CSS and a little JavaScript.</p></article>
      <article><h2>Responsive</h2><p>Fluid type, flexible grids and layouts that work from phones to wide monitors.</p></article>
      <article><h2>Accessible</h2><p>Keyboard-friendly navigation, visible focus states and sensible colour contrast.</p></article>
    </section>

    <section id="about" class="about">
      <h2>About {title}</h2>
      <p>This section is yours. Say who you are, what you offer and why it matters. Keep it short and specific.</p>
    </section>

    <section id="contact" class="contact">
      <h2>Stay in touch</h2>
      <p>Add your real email address or a form endpoint here before publishing.</p>
      <a class="button primary" href="mailto:hello@example.com">hello@example.com</a>
    </section>
  </main>

  <footer>
    <span>© <span id="year"></span> {title}</span>
    <span>Built locally with NEXUS</span>
  </footer>
  <script src="app.js"></script>
</body>
</html>
'''
    styles = f''':root {{
  --bg: #070b14;
  --panel: #0e1626;
  --text: #e8f1ff;
  --muted: #9aa8bd;
  --accent: {accent};
  --line: rgba(120, 160, 200, .18);
  color-scheme: dark;
}}
[data-theme="light"] {{
  --bg: #f5f8fc;
  --panel: #ffffff;
  --text: #101828;
  --muted: #5b6b82;
  --line: rgba(16, 24, 40, .12);
  color-scheme: light;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: radial-gradient(1200px 600px at 80% -10%, rgba(34, 211, 238, .16), transparent 60%), var(--bg);
  color: var(--text);
  font: 16px/1.65 system-ui, -apple-system, "Segoe UI", sans-serif;
}}
a {{ color: inherit; }}
.nav {{
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px clamp(20px, 6vw, 80px);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
}}
.brand {{ font-weight: 800; letter-spacing: .02em; text-decoration: none; }}
.nav nav {{ display: flex; align-items: center; gap: 18px; font-size: 14px; }}
.nav nav a {{ text-decoration: none; color: var(--muted); }}
.nav nav a:hover {{ color: var(--text); }}
.theme {{ background: none; border: 1px solid var(--line); color: var(--text); border-radius: 999px; width: 34px; height: 34px; cursor: pointer; }}
main {{ width: min(1100px, 92vw); margin: 0 auto; }}
.hero {{ padding: clamp(70px, 12vw, 150px) 0 80px; max-width: 780px; }}
.eyebrow {{ color: var(--accent); letter-spacing: .3em; font-size: 12px; font-weight: 700; }}
h1 {{ font-size: clamp(44px, 9vw, 92px); line-height: 1.02; margin: 14px 0 20px; letter-spacing: -.03em; }}
.lead {{ font-size: clamp(17px, 2.2vw, 21px); color: var(--muted); max-width: 60ch; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 32px; }}
.button {{ display: inline-block; padding: 13px 24px; border-radius: 12px; text-decoration: none; font-weight: 650; }}
.button.primary {{ background: var(--accent); color: #041016; box-shadow: 0 12px 40px rgba(34, 211, 238, .25); }}
.button.ghost {{ border: 1px solid var(--line); }}
.features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; padding: 30px 0 70px; }}
.features article, .contact {{
  background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 26px;
}}
.features h2, .about h2, .contact h2 {{ margin-top: 0; font-size: 22px; }}
.features p, .about p, .contact p {{ color: var(--muted); margin-bottom: 0; }}
.about {{ padding: 40px 0 70px; max-width: 70ch; }}
.contact {{ margin-bottom: 80px; }}
.contact .button {{ margin-top: 18px; }}
footer {{
  display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between;
  padding: 26px clamp(20px, 6vw, 80px); border-top: 1px solid var(--line); color: var(--muted); font-size: 13px;
}}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
'''
    script = '''// Theme toggle + footer year. No dependencies.
const root = document.documentElement;
const stored = localStorage.getItem('theme');
if (stored) root.dataset.theme = stored;
document.getElementById('theme').addEventListener('click', () => {
  const next = root.dataset.theme === 'light' ? 'dark' : 'light';
  root.dataset.theme = next;
  localStorage.setItem('theme', next);
});
document.getElementById('year').textContent = new Date().getFullYear();
'''
    files = {'index.html': index, 'styles.css': styles, 'app.js': script}
    readme = _readme(
        f'{title} Website', f'A responsive landing page for {topic} using plain HTML, CSS and JavaScript.',
        'index.html', 'start index.html  (or double-click it)', list(files) + ['README.md'],
        'Replace the placeholder copy, contact address and accent colour before publishing.')
    return {
        'id': 'html-static-site',
        'title': f'{title} Website',
        'language': 'html',
        'kind': 'website',
        'summary': f'A responsive landing page for {topic} using plain HTML, CSS and JavaScript.',
        'keywords': [('website', 4), ('landing page', 4), ('web page', 3), ('html page', 4),
                     ('webpage', 4), ('site', 3), ('portfolio', 3), ('html css', 3)],
        'files': {**files, 'README.md': readme},
        'entry': 'index.html',
        'checks': [],
        'run': 'start index.html',
    }


# --------------------------------------------------------------------------- #
# 16. JavaScript calculator
# --------------------------------------------------------------------------- #
def _js_calculator(context):
    source = r'''#!/usr/bin/env node
'use strict';
// Recursive-descent arithmetic calculator. No eval().

function tokenize(input) {
  const tokens = [];
  let i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (ch === ' ') { i += 1; continue; }
    if ('+-*/%()'.includes(ch)) { tokens.push(ch); i += 1; continue; }
    if (/[0-9.]/.test(ch)) {
      let start = i;
      while (i < input.length && /[0-9.]/.test(input[i])) i += 1;
      const value = Number(input.slice(start, i));
      if (Number.isNaN(value)) throw new Error('invalid number: ' + input.slice(start, i));
      tokens.push(value);
      continue;
    }
    throw new Error('unexpected character: ' + ch);
  }
  return tokens;
}

function parse(tokens) {
  let index = 0;
  function peek() { return tokens[index]; }
  function take() { return tokens[index++]; }

  function factor() {
    const token = take();
    if (typeof token === 'number') return token;
    if (token === '(') {
      const value = expression();
      if (take() !== ')') throw new Error('missing )');
      return value;
    }
    if (token === '-') return -factor();
    if (token === '+') return factor();
    throw new Error('unexpected token: ' + token);
  }
  function term() {
    let value = factor();
    while (peek() === '*' || peek() === '/' || peek() === '%') {
      const op = take();
      const rhs = factor();
      if (op === '*') value *= rhs;
      else if (op === '/') {
        if (rhs === 0) throw new Error('division by zero');
        value /= rhs;
      } else {
        if (rhs === 0) throw new Error('division by zero');
        value %= rhs;
      }
    }
    return value;
  }
  function expression() {
    let value = term();
    while (peek() === '+' || peek() === '-') {
      const op = take();
      const rhs = term();
      value = op === '+' ? value + rhs : value - rhs;
    }
    return value;
  }
  const result = expression();
  if (index !== tokens.length) throw new Error('unexpected input at token ' + index);
  return result;
}

function evaluate(input) { return parse(tokenize(String(input))); }

function selftest() {
  const cases = [['2+3*4', 14], ['(2+3)*4', 20], ['7/2', 3.5], ['-3+5', 2], ['10%4', 2]];
  for (const [input, expected] of cases) {
    const actual = evaluate(input);
    if (Math.abs(actual - expected) > 1e-9) {
      throw new Error(input + ' => ' + actual + ', expected ' + expected);
    }
  }
  console.log('SELFTEST OK');
}

function main() {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) { selftest(); return; }
  const input = args.join(' ');
  if (!input) {
    console.log('Usage: node main.js "2+3*4"');
    return;
  }
  try { console.log(evaluate(input)); }
  catch (error) { console.error('error:', error.message); process.exitCode = 1; }
}

main();
'''
    files = {'main.js': source}
    readme = _readme(
        'JavaScript Calculator', 'A Node.js arithmetic calculator with a hand-written parser (no eval).',
        'main.js', 'node main.js "2+3*4"', list(files) + ['README.md'],
        'Requires Node.js 18 or newer.')
    return {
        'id': 'javascript-calculator',
        'title': 'JavaScript Calculator',
        'language': 'javascript',
        'kind': 'cli',
        'summary': 'A Node.js arithmetic calculator with a hand-written parser (no eval).',
        'keywords': [('javascript calculator', 4), ('node calculator', 4), ('javascript', 2),
                     ('node.js', 3), ('js', 2), ('javascript program', 3)],
        'files': {**files, 'README.md': readme},
        'entry': 'main.js',
        'checks': [_check('self-test', ['--selftest'], 'SELFTEST OK'),
                   _check('arithmetic', ['2+3*4'], '14')],
        'run': 'node main.js "2+3*4"',
    }


# --------------------------------------------------------------------------- #
# 17. SQLite schema demo
# --------------------------------------------------------------------------- #
def _sql_demo(context):
    schema = '''-- Customers and orders demo schema (SQLite).
CREATE TABLE IF NOT EXISTS customers (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    city    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount      REAL NOT NULL,
    ordered_on  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(ordered_on);
'''
    queries = '''-- 1. Revenue by city
SELECT c.city, ROUND(SUM(o.amount), 2) AS revenue
FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.city
ORDER BY revenue DESC;

-- 2. Top customers
SELECT c.name, ROUND(SUM(o.amount), 2) AS spent, COUNT(*) AS orders
FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.id
ORDER BY spent DESC
LIMIT 5;

-- 3. Monthly revenue
SELECT substr(o.ordered_on, 1, 7) AS month, ROUND(SUM(o.amount), 2) AS revenue
FROM orders o
GROUP BY month
ORDER BY month;
'''
    demo = r'''#!/usr/bin/env python3
"""Apply schema.sql to SQLite, insert sample rows and run queries.sql."""
import argparse
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))


def read(name):
    with open(os.path.join(HERE, name), 'r', encoding='utf-8') as handle:
        return handle.read()


def build(db):
    db.executescript(read('schema.sql'))
    if db.execute('SELECT COUNT(*) FROM customers').fetchone()[0] == 0:
        db.executemany('INSERT INTO customers(name,city) VALUES(?,?)',
                       [('Ada Lovelace', 'London'), ('Grace Hopper', 'New York'),
                        ('Alan Turing', 'London'), ('Katherine Johnson', 'Hampton')])
        db.executemany('INSERT INTO orders(customer_id,amount,ordered_on) VALUES(?,?,?)',
                       [(1, 120.00, '2025-01-12'), (1, 80.50, '2025-02-03'),
                        (2, 240.00, '2025-01-22'), (3, 60.25, '2025-02-14'),
                        (4, 310.75, '2025-03-01')])
        db.commit()
    return db


def run_queries(db):
    output = []
    for statement in statements():
        rows = db.execute(statement).fetchall()
        output.append(rows)
    return output


def statements():
    lines = [line for line in read('queries.sql').splitlines() if not line.strip().startswith('--')]
    return [part.strip() for part in '\n'.join(lines).split(';') if part.strip()]


def selftest():
    db = build(sqlite3.connect(':memory:'))
    revenue = db.execute(
        'SELECT c.city, ROUND(SUM(o.amount),2) FROM customers c '
        'JOIN orders o ON o.customer_id=c.id GROUP BY c.city ORDER BY 2 DESC').fetchall()
    assert revenue[0] == ('London', 260.75), revenue
    assert len(run_queries(db)) == 3
    assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 5
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='SQLite schema and query demo')
    parser.add_argument('--db', default='demo.db')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    db = build(sqlite3.connect(args.db))
    titles = ['Revenue by city', 'Top customers', 'Monthly revenue']
    for title, rows in zip(titles, run_queries(db)):
        print(f'\n{title}:')
        for row in rows:
            print('  ', ' | '.join(str(value) for value in row))
    print(f'\nDatabase written to {os.path.abspath(args.db)}')


if __name__ == '__main__':
    main()
'''
    files = {'schema.sql': schema, 'queries.sql': queries, 'demo.py': demo}
    readme = _readme(
        'SQLite Schema + Queries', 'A normalized customers/orders schema with revenue, top-customer and monthly queries.',
        'demo.py', 'python demo.py --db demo.db', list(files) + ['README.md'],
        'Edit schema.sql to extend the model; queries.sql holds the reporting queries.')
    return {
        'id': 'sql-schema-demo',
        'title': 'SQLite Schema + Queries',
        'language': 'sql',
        'kind': 'database',
        'summary': 'A normalized customers/orders schema with revenue, top-customer and monthly queries.',
        'keywords': [('sql', 3), ('sqlite', 4), ('database schema', 4), ('database', 2),
                     ('schema', 3), ('sql queries', 3), ('tables', 2)],
        'files': {**files, 'README.md': readme},
        'entry': 'demo.py',
        'checks': [_check('self-test', ['--selftest'], 'SELFTEST OK')],
        'run': 'python demo.py --db demo.db',
    }


# --------------------------------------------------------------------------- #
# 18. PowerShell file report
# --------------------------------------------------------------------------- #
def _ps_file_report(context):
    source = r'''<#
.SYNOPSIS
    Summarize a folder: file count, total size, extensions and largest files.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File report.ps1 -Path C:\Users\you\Downloads
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Path = ".",
    [string]$OutFile = "",
    [int]$Top = 10,
    [switch]$SelfTest
)

function Get-FileReport {
    param([string]$Root, [int]$Top = 10)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Not a directory: $Root"
    }

    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue)
    $totalBytes = [long]0
    foreach ($file in $files) { $totalBytes += $file.Length }

    $byExtension = @{}
    foreach ($file in $files) {
        $extension = $file.Extension.ToLowerInvariant()
        if ([string]::IsNullOrEmpty($extension)) { $extension = "(none)" }
        if (-not $byExtension.ContainsKey($extension)) {
            $byExtension[$extension] = [pscustomobject]@{
                Extension = $extension
                Count     = 0
                Bytes     = [long]0
            }
        }
        $byExtension[$extension].Count += 1
        $byExtension[$extension].Bytes += $file.Length
    }

    $largest = @($files |
        Sort-Object -Property Length -Descending |
        Select-Object -First $Top |
        ForEach-Object {
            [pscustomobject]@{ Name = $_.FullName; Bytes = $_.Length }
        })

    [pscustomobject]@{
        Path        = (Resolve-Path -LiteralPath $Root).Path
        Files       = $files.Count
        Bytes       = $totalBytes
        Megabytes   = [math]::Round($totalBytes / 1MB, 2)
        ByExtension = @($byExtension.Values | Sort-Object -Property Bytes -Descending)
        Largest     = $largest
    }
}

function Invoke-SelfTest {
    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("nexus-report-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $temp | Out-Null
    try {
        Set-Content -LiteralPath (Join-Path $temp "a.txt") -Value "alpha" -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $temp "b.txt") -Value "bravo!" -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $temp "c.log") -Value "charlie!!" -Encoding UTF8
        $report = Get-FileReport -Root $temp -Top 2
        if ($report.Files -ne 3) { throw "expected 3 files, got $($report.Files)" }
        if ($report.Bytes -le 0) { throw "expected a positive byte count" }
        if ($report.ByExtension[0].Count -lt 1) { throw "expected extension stats" }
        if ($report.Largest.Count -gt 2) { throw "top list not limited" }
        Write-Output "SELFTEST OK"
    }
    finally {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$report = Get-FileReport -Root $Path -Top $Top

Write-Output ("Folder:    " + $report.Path)
Write-Output ("Files:     " + $report.Files)
Write-Output ("Size:      {0} bytes ({1} MB)" -f $report.Bytes, $report.Megabytes)
Write-Output ""
Write-Output "By extension:"
foreach ($item in $report.ByExtension) {
    Write-Output ("  {0,-10} {1,5} files {2,12} bytes" -f $item.Extension, $item.Count, $item.Bytes)
}
Write-Output ""
Write-Output "Largest files:"
foreach ($item in $report.Largest) {
    Write-Output ("  {0,12} bytes  {1}" -f $item.Bytes, $item.Name)
}

if ($OutFile) {
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutFile -Encoding UTF8
    Write-Output ""
    Write-Output ("JSON written to " + (Resolve-Path -LiteralPath $OutFile).Path)
}
'''
    files = {'report.ps1': source}
    readme = _readme(
        'PowerShell File Report', 'Summarize a Windows folder: file count, size, extensions and largest files.',
        'report.ps1', 'powershell -ExecutionPolicy Bypass -File report.ps1 -Path "C:\\Users\\you\\Downloads"',
        list(files) + ['README.md'],
        'Needs Windows PowerShell 5.1+ (built into Windows 10/11). Add -OutFile report.json for JSON output.')
    return {
        'id': 'powershell-file-report',
        'title': 'PowerShell File Report',
        'language': 'powershell',
        'kind': 'automation',
        'summary': 'Summarize a Windows folder: file count, size, extensions and largest files.',
        'keywords': [('powershell', 4), ('powershell script', 4), ('windows script', 3),
                     ('file report', 3), ('folder report', 3), ('ps1', 3)],
        'files': {**files, 'README.md': readme},
        'entry': 'report.ps1',
        'checks': [_check('self-test', ['-SelfTest'], 'SELFTEST OK')],
        'run': 'powershell -ExecutionPolicy Bypass -File report.ps1 -Path "C:\\Users\\you\\Downloads"',
    }


# --------------------------------------------------------------------------- #
# 19. Snake game
# --------------------------------------------------------------------------- #
def _snake_game(context):
    source = r'''#!/usr/bin/env python3
"""Snake game: pure game logic plus a Tkinter window."""
import argparse
import random

DIRECTIONS = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}


class Board:
    """Grid snake logic, independent of any GUI."""

    def __init__(self, width=20, height=15, seed=None):
        self.width = width
        self.height = height
        self.random = random.Random(seed)
        self.snake = [(width // 2, height // 2)]
        self.direction = (1, 0)
        self.score = 0
        self.alive = True
        self.food = None
        self.place_food()

    def free_cells(self):
        body = set(self.snake)
        return [(x, y) for y in range(self.height) for x in range(self.width)
                if (x, y) not in body]

    def place_food(self):
        free = self.free_cells()
        self.food = self.random.choice(free) if free else None

    def turn(self, name):
        new = DIRECTIONS.get(name)
        if not new:
            raise ValueError(f'unknown direction: {name}')
        if (new[0] == -self.direction[0] and new[1] == -self.direction[1]):
            return False
        self.direction = new
        return True

    def step(self):
        if not self.alive:
            return False
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        head = (head_x + dx, head_y + dy)
        if not (0 <= head[0] < self.width and 0 <= head[1] < self.height):
            self.alive = False
            return False
        growing = head == self.food
        body = self.snake if growing else self.snake[:-1]
        if head in body:
            self.alive = False
            return False
        self.snake.insert(0, head)
        if growing:
            self.score += 1
            self.place_food()
        else:
            self.snake.pop()
        return True


def selftest():
    board = Board(6, 6, seed=1)
    start = len(board.snake)
    assert board.turn('down') is True
    assert board.step() is True
    assert len(board.snake) == start
    assert board.snake[0] == (3, 4)
    assert board.turn('up') is False, 'reverse direction must be ignored'
    assert board.direction == (0, 1)

    # Growing: put food directly ahead.
    board = Board(6, 6, seed=2)
    head_x, head_y = board.snake[0]
    board.food = (head_x + 1, head_y)
    assert board.step() is True
    assert board.score == 1
    assert len(board.snake) == 2

    # Wall collision.
    board = Board(3, 3, seed=3)
    board.snake = [(2, 1)]
    board.direction = (1, 0)
    assert board.step() is False
    assert board.alive is False

    # Self collision: moving into the body (not the tail) ends the game.
    board = Board(6, 6, seed=4)
    board.snake = [(2, 2), (2, 3), (3, 3), (3, 2)]
    board.direction = (0, 1)
    assert board.step() is False
    assert board.alive is False
    print('SELFTEST OK')


def run_gui(width=20, height=15):
    import tkinter as tk
    from tkinter import messagebox

    cell = 24
    delay = 120
    board = Board(width, height)
    root = tk.Tk()
    root.title('Snake - NEXUS Program Forge')
    canvas = tk.Canvas(root, width=width * cell, height=height * cell, bg='#08111f',
                       highlightthickness=0)
    canvas.pack()
    status = tk.Label(root, text='Score: 0', bg='#08111f', fg='#5eead4', font=('Consolas', 12))
    status.pack(fill='x')

    def draw():
        canvas.delete('all')
        for x, y in board.snake:
            canvas.create_rectangle(x * cell + 1, y * cell + 1,
                                    (x + 1) * cell - 1, (y + 1) * cell - 1,
                                    fill='#22d3ee', outline='')
        if board.food:
            fx, fy = board.food
            canvas.create_oval(fx * cell + 4, fy * cell + 4,
                               (fx + 1) * cell - 4, (fy + 1) * cell - 4,
                               fill='#f472b6', outline='')
        status.config(text=f'Score: {board.score}')

    def tick():
        if board.alive:
            board.step()
            draw()
            if board.alive:
                root.after(delay, tick)
            else:
                if messagebox.askyesno('Game over', f'Final score: {board.score}\nPlay again?'):
                    restart()
        else:
            restart()

    def restart():
        nonlocal board
        board = Board(width, height)
        draw()
        root.after(delay, tick)

    def on_key(event):
        names = {'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right',
                 'w': 'up', 's': 'down', 'a': 'left', 'd': 'right'}
        name = names.get(event.keysym) or names.get(event.char)
        if name:
            board.turn(name)

    root.bind('<Key>', on_key)
    draw()
    root.after(delay, tick)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='Play snake')
    parser.add_argument('--width', type=int, default=20)
    parser.add_argument('--height', type=int, default=15)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    run_gui(args.width, args.height)


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-snake-game', 'Snake Game', 'game',
        'A classic snake game with separate, testable game logic and a Tkinter window.',
        [('snake game', 5), ('snake', 4), ('arcade game', 3), ('tkinter game', 4),
         ('game', 1), ('pygame', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py')


# --------------------------------------------------------------------------- #
# 20. JSON tool
# --------------------------------------------------------------------------- #
def _json_tool(context):
    source = r'''#!/usr/bin/env python3
"""Validate, pretty-print, minify and query JSON documents."""
import argparse
import json
import sys

MISSING = object()


def load(path):
    if path in (None, '-'):
        return json.load(sys.stdin)
    with open(path, 'r', encoding='utf-8-sig') as handle:
        return json.load(handle)


def query(data, dotted):
    current = data
    for part in [piece for piece in dotted.split('.') if piece]:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return MISSING
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


def selftest():
    sample = {'user': {'name': 'Ada', 'tags': ['math', 'code']}, 'active': True}
    text = json.dumps(sample)
    assert json.loads(text) == sample
    assert json.dumps(sample, separators=(',', ':')) == '{"user":{"name":"Ada","tags":["math","code"]},"active":true}'
    assert query(sample, 'user.name') == 'Ada'
    assert query(sample, 'user.tags.1') == 'code'
    assert query(sample, 'missing') is MISSING
    assert query(sample, 'user.tags.9') is MISSING
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Inspect JSON')
    parser.add_argument('file', nargs='?', help='input file (stdin if omitted)')
    parser.add_argument('--query', help='dot path, e.g. user.name or items.0.id')
    parser.add_argument('--minify', action='store_true')
    parser.add_argument('--indent', type=int, default=2)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    try:
        data = load(args.file)
    except FileNotFoundError:
        parser.error(f'no such file: {args.file}')
    except json.JSONDecodeError as exc:
        print(f'Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})', file=sys.stderr)
        raise SystemExit(1)
    if args.query:
        value = query(data, args.query)
        if value is MISSING:
            print('Path not found.', file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps(value, indent=args.indent) if not isinstance(value, str) else value)
        return
    if args.minify:
        print(json.dumps(data, separators=(',', ':')))
    else:
        print(json.dumps(data, indent=args.indent, sort_keys=False))


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-json-tool', 'JSON Tool', 'tool',
        'Validate, pretty-print, minify and query JSON with a dot-path syntax.',
        [('json tool', 5), ('json formatter', 4), ('format json', 4), ('validate json', 4),
         ('minify json', 4), ('json', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py data.json --query items.0.name')


# --------------------------------------------------------------------------- #
# 21. Port scanner
# --------------------------------------------------------------------------- #
def _port_scanner(context):
    source = r'''#!/usr/bin/env python3
"""Scan TCP ports on a host you own. Use responsibly."""
import argparse
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor

COMMON = {
    21: 'ftp', 22: 'ssh', 23: 'telnet', 25: 'smtp', 53: 'dns', 80: 'http',
    110: 'pop3', 143: 'imap', 443: 'https', 445: 'smb', 587: 'smtp',
    993: 'imaps', 995: 'pop3s', 1433: 'mssql', 1521: 'oracle', 3306: 'mysql',
    3389: 'rdp', 5432: 'postgres', 5900: 'vnc', 6379: 'redis', 8000: 'http-alt',
    8080: 'http-alt', 8443: 'https-alt', 9000: 'http-alt', 11434: 'ollama',
}


def scan_port(host, port, timeout=0.5):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def scan(host, start, end, timeout=0.5, workers=128, progress=None):
    ports = list(range(start, end + 1))
    open_ports = []

    def probe(port):
        try:
            if scan_port(host, port, timeout):
                if progress:
                    progress(port)
                return port
        except OSError:
            return None
        return None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for result in pool.map(probe, ports):
            if result is not None:
                open_ports.append(result)
    return sorted(open_ports)


def selftest():
    # A local listener guarantees at least one open port without touching the network.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    try:
        assert scan_port('127.0.0.1', port, timeout=2) is True
        # Drain the probe connection so the backlog stays clear for the scan.
        listener.settimeout(2)
        accepted, _address = listener.accept()
        accepted.close()
        found = scan('127.0.0.1', port, port, timeout=2, workers=2)
        assert found == [port], found
        # A port we just closed must be reported closed.
        closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        closed.bind(('127.0.0.1', 0))
        closed_port = closed.getsockname()[1]
        closed.close()
        assert scan_port('127.0.0.1', closed_port, timeout=0.5) is False
    finally:
        listener.close()
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Scan TCP ports on a host you own')
    parser.add_argument('host', nargs='?', default='127.0.0.1')
    parser.add_argument('--start', type=int, default=1)
    parser.add_argument('--end', type=int, default=1024)
    parser.add_argument('--timeout', type=float, default=0.5)
    parser.add_argument('--workers', type=int, default=128)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not (1 <= args.start <= args.end <= 65535):
        parser.error('ports must satisfy 1 <= start <= end <= 65535')
    started = time.time()
    print(f'Scanning {args.host} ports {args.start}-{args.end}...')
    found = scan(args.host, args.start, args.end, args.timeout, args.workers)
    elapsed = round(time.time() - started, 2)
    if args.json:
        print(json.dumps({'host': args.host, 'open': found, 'seconds': elapsed}, indent=2))
        return
    if not found:
        print('No open TCP ports found.')
        return
    print(f'{len(found)} open port(s) in {elapsed}s:')
    for port in found:
        print(f'  {port:>5}  {COMMON.get(port, "unknown")}')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-port-scanner', 'TCP Port Scanner', 'network',
        'Scan TCP ports on a host you own using a thread pool; includes a local self-test.',
        [('port scanner', 5), ('scan ports', 4), ('open ports', 4), ('network scanner', 4),
         ('tcp scan', 4), ('port scan', 4), ('nmap', 3)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py 127.0.0.1 --start 1 --end 1024')


# --------------------------------------------------------------------------- #
# 22. Markdown to HTML
# --------------------------------------------------------------------------- #
def _markdown_to_html(context):
    source = r'''#!/usr/bin/env python3
"""Convert a small, safe subset of Markdown to HTML."""
import argparse
import html
import re
import sys

INLINE_CODE = re.compile(r'`([^`]+)`')
BOLD = re.compile(r'\*\*([^*]+)\*\*')
ITALIC = re.compile(r'(?<!\*)\*([^*]+)\*(?!\*)')
LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
HEADING = re.compile(r'^(#{1,6})\s+(.*)$')
BULLET = re.compile(r'^[-*+]\s+(.*)$')
NUMBERED = re.compile(r'^\d+\.\s+(.*)$')
RULE = re.compile(r'^(-{3,}|\*{3,}|_{3,})$')


def inline(text):
    text = INLINE_CODE.sub(r'<code>\1</code>', text)
    text = BOLD.sub(r'<strong>\1</strong>', text)
    text = ITALIC.sub(r'<em>\1</em>', text)
    text = LINK.sub(r'<a href="\2">\1</a>', text)
    return text


def convert(markdown):
    output = []
    in_code = False
    list_tag = None
    in_quote = False

    def close_list():
        nonlocal list_tag
        if list_tag:
            output.append(f'</{list_tag}>')
            list_tag = None

    def close_quote():
        nonlocal in_quote
        if in_quote:
            output.append('</blockquote>')
            in_quote = False

    for raw in markdown.replace('\r\n', '\n').split('\n'):
        if raw.strip().startswith('```'):
            close_list()
            close_quote()
            if in_code:
                output.append('</code></pre>')
                in_code = False
            else:
                output.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            output.append(html.escape(raw, quote=False))
            continue
        line = raw.rstrip()
        if not line.strip():
            close_list()
            close_quote()
            continue
        heading = HEADING.match(line)
        if heading:
            close_list()
            close_quote()
            level = len(heading.group(1))
            output.append(f'<h{level}>{inline(html.escape(heading.group(2)))}</h{level}>')
            continue
        if RULE.match(line.strip()):
            close_list()
            close_quote()
            output.append('<hr>')
            continue
        if line.lstrip().startswith('> '):
            close_list()
            if not in_quote:
                output.append('<blockquote>')
                in_quote = True
            output.append(f'<p>{inline(html.escape(line.lstrip()[2:]))}</p>')
            continue
        bullet = BULLET.match(line)
        numbered = NUMBERED.match(line)
        if bullet or numbered:
            close_quote()
            wanted = 'ul' if bullet else 'ol'
            if list_tag != wanted:
                close_list()
                output.append(f'<{wanted}>')
                list_tag = wanted
            item = (bullet or numbered).group(1)
            output.append(f'<li>{inline(html.escape(item))}</li>')
            continue
        close_list()
        close_quote()
        output.append(f'<p>{inline(html.escape(line))}</p>')

    if in_code:
        output.append('</code></pre>')
    close_list()
    close_quote()
    return '\n'.join(output)


def page(title, body):
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{html.escape(title)}</title>\n'
        '<style>body{max-width:760px;margin:40px auto;padding:0 20px;'
        'font:16px/1.65 system-ui,sans-serif;color:#1a2433}'
        'pre{background:#f4f6fa;padding:14px;border-radius:10px;overflow:auto}'
        'code{background:#f4f6fa;padding:2px 5px;border-radius:5px}'
        'blockquote{border-left:4px solid #22d3ee;margin:0;padding-left:16px;color:#4a5a70}'
        '</style>\n</head>\n<body>\n'
        f'{body}\n</body>\n</html>\n'
    )


SAMPLE = """# Markdown demo

This is **bold**, this is *italic* and this is `code`.

- first item
- second item

> A quoted line.

[Example](https://example.com)

```python
print('hello')
```
"""


def selftest():
    result = convert(SAMPLE)
    assert '<h1>Markdown demo</h1>' in result
    assert '<strong>bold</strong>' in result
    assert '<em>italic</em>' in result
    assert '<code>code</code>' in result
    assert '<ul>' in result and '<li>first item</li>' in result
    assert '<blockquote>' in result
    assert '<a href="https://example.com">Example</a>' in result
    assert '<pre><code>' in result and "print('hello')" in result
    assert '<script>' not in convert('<script>alert(1)</script>')
    assert '&lt;script&gt;' in convert('<script>alert(1)</script>')
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Convert Markdown to standalone HTML')
    parser.add_argument('source', nargs='?', help='input .md file (stdin if omitted)')
    parser.add_argument('--out', help='output .html file')
    parser.add_argument('--title', default='Document')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.source:
        with open(args.source, 'r', encoding='utf-8') as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    document = page(args.title, convert(text))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            handle.write(document)
        print(f'Wrote {args.out}')
    else:
        print(document)


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-markdown-html', 'Markdown to HTML', 'tool',
        'Convert a safe Markdown subset (headings, emphasis, lists, quotes, code, links) into standalone HTML.',
        [('markdown to html', 5), ('markdown converter', 5), ('md to html', 5),
         ('convert markdown', 4), ('markdown', 2)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py README.md --title "My Document" --out page.html')


# --------------------------------------------------------------------------- #
# 23. Weather CLI
# --------------------------------------------------------------------------- #
def _weather_cli(context):
    source = r'''#!/usr/bin/env python3
"""Current weather and a short forecast using the free Open-Meteo API."""
import argparse
import json
import sys
import urllib.parse
import urllib.request

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
USER_AGENT = 'NexusProgramForge/1.0'

WEATHER_CODES = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Drizzle',
    55: 'Dense drizzle', 56: 'Light freezing drizzle', 57: 'Freezing drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Light freezing rain',
    67: 'Freezing rain', 71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
    77: 'Snow grains', 80: 'Light showers', 81: 'Showers', 82: 'Violent showers',
    85: 'Light snow showers', 86: 'Snow showers', 95: 'Thunderstorm',
    96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail',
}


def describe(code):
    return WEATHER_CODES.get(int(code), f'Unknown ({code})')


def _get_json(url, params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f'{url}?{query}', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


def geocode(name):
    payload = _get_json(GEOCODE_URL, {'name': name, 'count': 1, 'language': 'en', 'format': 'json'})
    results = payload.get('results') or []
    if not results:
        raise LookupError(f'could not find a place called {name!r}')
    place = results[0]
    return {
        'name': place['name'],
        'country': place.get('country', ''),
        'latitude': place['latitude'],
        'longitude': place['longitude'],
        'timezone': place.get('timezone', 'auto'),
    }


def forecast(latitude, longitude):
    return _get_json(FORECAST_URL, {
        'latitude': latitude,
        'longitude': longitude,
        'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code',
        'daily': 'temperature_2m_max,temperature_2m_min,weather_code',
        'forecast_days': 3,
        'timezone': 'auto',
    })


def summarize(payload, place):
    current = payload.get('current', {})
    units = payload.get('current_units', {})
    temp_unit = units.get('temperature_2m', '°C')
    wind_unit = units.get('wind_speed_10m', 'km/h')
    lines = [f'Weather for {place}:']
    if current:
        lines.append(
            f"  Now: {current.get('temperature_2m')}{temp_unit}, "
            f"{describe(current.get('weather_code', -1))}, "
            f"humidity {current.get('relative_humidity_2m')}%, "
            f"wind {current.get('wind_speed_10m')} {wind_unit}")
    daily = payload.get('daily') or {}
    dates = daily.get('time') or []
    highs = daily.get('temperature_2m_max') or []
    lows = daily.get('temperature_2m_min') or []
    codes = daily.get('weather_code') or []
    if dates:
        lines.append('  Forecast:')
        for index, day in enumerate(dates):
            high = highs[index] if index < len(highs) else '?'
            low = lows[index] if index < len(lows) else '?'
            code = codes[index] if index < len(codes) else -1
            lines.append(f'    {day}  {low}–{high}{temp_unit}  {describe(code)}')
    return '\n'.join(lines)


SAMPLE = {
    'current': {'temperature_2m': 21.5, 'relative_humidity_2m': 55,
                'wind_speed_10m': 8.2, 'weather_code': 2},
    'current_units': {'temperature_2m': '°C', 'wind_speed_10m': 'km/h'},
    'daily': {'time': ['2025-01-01', '2025-01-02'],
              'temperature_2m_max': [24.0, 22.5],
              'temperature_2m_min': [15.0, 14.0],
              'weather_code': [3, 61]},
}


def selftest():
    text = summarize(SAMPLE, 'Berlin')
    assert 'Berlin' in text
    assert '21.5' in text
    assert 'Partly cloudy' in text
    assert 'Overcast' in text and 'Light rain' in text
    assert describe(999) == 'Unknown (999)'
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Weather without an API key (Open-Meteo)')
    parser.add_argument('place', nargs='?', default='Berlin')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    try:
        location = geocode(args.place)
        payload = forecast(location['latitude'], location['longitude'])
    except LookupError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
    except OSError as exc:
        print(f'Network error: {exc}. This program needs internet access.', file=sys.stderr)
        raise SystemExit(1)
    label = f"{location['name']}, {location['country']}".strip(', ')
    if args.json:
        print(json.dumps({'place': label, 'latitude': location['latitude'],
                          'longitude': location['longitude'], 'weather': payload}, indent=2))
    else:
        print(summarize(payload, label))


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-weather-cli', 'Weather CLI', 'tool',
        'Current weather plus a three-day forecast from Open-Meteo — free, no API key. Needs internet for live data.',
        [('weather', 5), ('weather app', 5), ('forecast', 4), ('temperature today', 4),
         ('open-meteo', 4), ('weather cli', 5)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py Berlin')


# --------------------------------------------------------------------------- #
# 24. Word count
# --------------------------------------------------------------------------- #
def _word_count(context):
    source = r'''#!/usr/bin/env python3
"""Count lines, words, characters, sentences and the most frequent words."""
import argparse
import collections
import json
import re
import sys

WORD = re.compile(r"[A-Za-z0-9']+")


def analyze(text, top=10):
    words = WORD.findall(text)
    lowered = [word.lower() for word in words]
    counts = collections.Counter(lowered)
    lines = text.count('\n') + (1 if text and not text.endswith('\n') else 0)
    sentences = [part for part in re.split(r'[.!?]+', text) if part.strip()]
    letters = sum(1 for char in text if char.isalpha())
    return {
        'lines': lines,
        'words': len(words),
        'unique_words': len(counts),
        'characters': len(text),
        'characters_no_spaces': sum(1 for char in text if not char.isspace()),
        'letters': letters,
        'sentences': len(sentences),
        'average_word_length': round(letters / len(words), 2) if words else 0,
        'reading_minutes': round(len(words) / 220, 1),
        'top': counts.most_common(top),
    }


def selftest():
    text = 'The quick brown fox jumps over the lazy dog.\nThe dog sleeps!'
    stats = analyze(text)
    assert stats['lines'] == 2
    assert stats['words'] == 12
    assert stats['sentences'] == 2
    assert stats['top'][0] == ('the', 3)
    assert stats['characters'] == len(text)
    assert stats['unique_words'] == 9
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Count words in text files')
    parser.add_argument('files', nargs='*', help='files to read (stdin if none)')
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.files:
        chunks = []
        for path in args.files:
            with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                chunks.append(handle.read())
        text = '\n'.join(chunks)
    else:
        text = sys.stdin.read()
    stats = analyze(text, args.top)
    if args.json:
        print(json.dumps(stats, indent=2))
        return
    print(f"Lines:      {stats['lines']}")
    print(f"Words:      {stats['words']} ({stats['unique_words']} unique)")
    print(f"Characters: {stats['characters']} ({stats['characters_no_spaces']} without spaces)")
    print(f"Sentences:  {stats['sentences']}")
    print(f"Avg word:   {stats['average_word_length']} letters")
    print(f"Reading:    about {stats['reading_minutes']} minute(s)")
    print('\nTop words:')
    for word, count in stats['top']:
        print(f'  {count:>4}  {word}')


if __name__ == '__main__':
    main()
'''
    return _py_recipe(
        'python-word-count', 'Word Count', 'text',
        'Count lines, words, characters and sentences in files, plus the most frequent words.',
        [('word count', 5), ('count words', 5), ('word counter', 5), ('text statistics', 4),
         ('wc', 3), ('readability', 3)],
        source,
        checks=[_check('self-test', ['--selftest'], 'SELFTEST OK')],
        run='python main.py README.md')


# --------------------------------------------------------------------------- #
# 25. Chat server
# --------------------------------------------------------------------------- #
def _chat_server(context):
    server = r'''#!/usr/bin/env python3
"""A tiny multi-client TCP chat server using only the standard library."""
import argparse
import socket
import socketserver
import threading
import time

DEFAULT_PORT = 5050
MAX_LINE = 4096


class ChatRoom:
    """Tracks connected clients and broadcasts messages to all of them."""

    def __init__(self):
        self.clients = {}
        self.lock = threading.Lock()

    def join(self, name, connection):
        name = (name or '').strip()[:24]
        if not name:
            return False
        with self.lock:
            if name in self.clients:
                return False
            self.clients[name] = connection
        return True

    def leave(self, name):
        with self.lock:
            self.clients.pop(name, None)

    def names(self):
        with self.lock:
            return sorted(self.clients)

    def deliver(self, name, text):
        with self.lock:
            connection = self.clients.get(name)
        if connection is None:
            return False
        try:
            connection.sendall((text + '\n').encode('utf-8'))
            return True
        except OSError:
            self.leave(name)
            return False

    def broadcast(self, text, exclude=None):
        with self.lock:
            targets = [(name, connection) for name, connection in self.clients.items()
                       if name != exclude]
        dead = []
        for name, connection in targets:
            try:
                connection.sendall((text + '\n').encode('utf-8'))
            except OSError:
                dead.append(name)
        for name in dead:
            self.leave(name)
        return len(targets) - len(dead)


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data.decode('utf-8').rstrip('\n'))


def selftest():
    room = ChatRoom()
    alice, bob = FakeSocket(), FakeSocket()
    assert room.join('alice', alice) is True
    assert room.join('bob', bob) is True
    assert room.join('alice', FakeSocket()) is False, 'names must be unique'
    assert room.names() == ['alice', 'bob']
    assert room.broadcast('hello all') == 2
    assert alice.sent == ['hello all'] and bob.sent == ['hello all']
    assert room.broadcast('not for alice', exclude='alice') == 1
    assert alice.sent == ['hello all']
    assert room.deliver('bob', 'private note') is True
    assert bob.sent[-1] == 'private note'
    room.leave('bob')
    assert room.names() == ['alice']
    assert room.deliver('bob', 'gone') is False
    print('SELFTEST OK')


class ChatHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(600)
        self.wfile.write(b'Name: ')
        self.wfile.flush()
        raw = self.rfile.readline(MAX_LINE)
        name = raw.decode('utf-8', errors='replace').strip()
        room = self.server.room
        if not name or not room.join(name, self.connection):
            self.wfile.write(b'That name is taken or invalid. Bye.\n')
            return
        room.broadcast(f'* {name} joined ({len(room.names())} online)', exclude=name)
        room.deliver(name, f'Welcome {name}. Commands: /who, /help, /quit')
        try:
            while True:
                line = self.rfile.readline(MAX_LINE)
                if not line:
                    break
                text = line.decode('utf-8', errors='replace').strip()
                if not text:
                    continue
                if text == '/quit':
                    break
                if text == '/who':
                    room.deliver(name, 'Online: ' + ', '.join(room.names()))
                    continue
                if text == '/help':
                    room.deliver(name, 'Type a message to broadcast. /who lists users, /quit leaves.')
                    continue
                stamp = time.strftime('%H:%M')
                room.broadcast(f'[{stamp}] {name}: {text}')
        finally:
            room.leave(name)
            room.broadcast(f'* {name} left ({len(room.names())} online)')


class ChatServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, room):
        self.room = room
        super().__init__(address, ChatHandler)


def main():
    parser = argparse.ArgumentParser(description='Tiny TCP chat server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    room = ChatRoom()
    with ChatServer((args.host, args.port), room) as server:
        print(f'Chat server listening on {args.host}:{args.port}. Ctrl+C to stop.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nStopping.')


if __name__ == '__main__':
    main()
'''
    client = r'''#!/usr/bin/env python3
"""Console client for the NEXUS chat server."""
import argparse
import socket
import sys
import threading

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 5050


def read_prompt(connection, stop):
    buffer = b''
    while not stop.is_set():
        try:
            chunk = connection.recv(1024)
        except OSError:
            break
        if not chunk:
            break
        buffer += chunk
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            sys.stdout.write('\r' + line.decode('utf-8', errors='replace') + '\n> ')
            sys.stdout.flush()
    stop.set()


def main():
    parser = argparse.ArgumentParser(description='Connect to the chat server')
    parser.add_argument('name', nargs='?', default='guest')
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    stop = threading.Event()
    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        connection.settimeout(None)
        prompt = connection.recv(64)
        sys.stdout.write(prompt.decode('utf-8', errors='replace'))
        sys.stdout.flush()
        connection.sendall((args.name + '\n').encode('utf-8'))
        thread = threading.Thread(target=read_prompt, args=(connection, stop), daemon=True)
        thread.start()
        try:
            while not stop.is_set():
                message = sys.stdin.readline()
                if not message:
                    break
                connection.sendall(message.encode('utf-8'))
                if message.strip() == '/quit':
                    break
        except (KeyboardInterrupt, OSError):
            pass
        finally:
            stop.set()


if __name__ == '__main__':
    main()
'''
    files = {'server.py': server, 'client.py': client}
    readme = _readme(
        'TCP Chat Server', 'A threaded chat server with a console client: join, broadcast, /who and /quit.',
        'server.py', 'python server.py --port 5050   # then: python client.py yourname',
        list(files) + ['README.md'],
        'Plain TCP, no encryption. Bind to 127.0.0.1 for local use; do not expose it to the public internet.')
    return {
        'id': 'python-chat-server',
        'title': 'TCP Chat Server',
        'language': 'python',
        'kind': 'network',
        'summary': 'A threaded chat server with a console client: join, broadcast, /who and /quit.',
        'keywords': [('chat server', 5), ('chat app', 4), ('chat', 3), ('messaging server', 5),
                     ('tcp server', 4), ('socket server', 4), ('multiplayer chat', 4)],
        'files': {**files, 'README.md': readme},
        'entry': 'server.py',
        'checks': [_check('self-test', ['--selftest'], 'SELFTEST OK')],
        'run': 'python server.py --port 5050',
    }


# --------------------------------------------------------------------------- #
# 26-38. Small algorithm snippets
# --------------------------------------------------------------------------- #
def _snippet(recipe_id, title, summary, keywords, source, run='python main.py'):
    return _py_recipe(recipe_id, title, 'snippet', summary, keywords, source, run=run)


def _reverse_string(context):
    source = r'''#!/usr/bin/env python3
"""Reverse characters, words or lines."""
import argparse


def reverse(text):
    return text[::-1]


def reverse_words(text):
    return ' '.join(reversed(text.split()))


def reverse_lines(text):
    return '\n'.join(reversed(text.splitlines()))


def selftest():
    assert reverse('hello') == 'olleh'
    assert reverse('') == ''
    assert reverse('a') == 'a'
    assert reverse_words('one two three') == 'three two one'
    assert reverse_lines('a\nb\nc') == 'c\nb\na'
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Reverse text')
    parser.add_argument('text', nargs='*')
    parser.add_argument('--words', action='store_true')
    parser.add_argument('--lines', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    text = ' '.join(args.text) or 'hello world'
    if args.words:
        print(reverse_words(text))
    elif args.lines:
        print(reverse_lines(text))
    else:
        print(reverse(text))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-reverse-string', 'Reverse a String',
        'Reverse characters, word order or line order in text.',
        [('reverse string', 5), ('reverse text', 4), ('reverse words', 4),
         ('string reversal', 5), ('reverse', 2)],
        source)


def _palindrome(context):
    source = r'''#!/usr/bin/env python3
"""Check whether text reads the same forwards and backwards."""
import argparse
import re


def normalize(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def is_palindrome(text):
    cleaned = normalize(text)
    return cleaned == cleaned[::-1]


def selftest():
    assert is_palindrome('racecar') is True
    assert is_palindrome('A man, a plan, a canal: Panama') is True
    assert is_palindrome('hello') is False
    assert is_palindrome('') is True
    assert normalize('No. 1!') == 'no1'
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Palindrome checker')
    parser.add_argument('text', nargs='*')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    text = ' '.join(args.text) or 'A man, a plan, a canal: Panama'
    print('yes' if is_palindrome(text) else 'no')


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-palindrome', 'Palindrome Checker',
        'Check whether a word or phrase is a palindrome, ignoring case, spaces and punctuation.',
        [('palindrome', 5), ('palindrome checker', 5), ('is palindrome', 5),
         ('mirror word', 3)],
        source)


def _fizzbuzz(context):
    source = r'''#!/usr/bin/env python3
"""Classic FizzBuzz."""
import argparse


def fizzbuzz(limit):
    output = []
    for number in range(1, limit + 1):
        if number % 15 == 0:
            output.append('FizzBuzz')
        elif number % 3 == 0:
            output.append('Fizz')
        elif number % 5 == 0:
            output.append('Buzz')
        else:
            output.append(str(number))
    return output


def selftest():
    result = fizzbuzz(15)
    assert len(result) == 15
    assert result[0] == '1'
    assert result[2] == 'Fizz'
    assert result[4] == 'Buzz'
    assert result[14] == 'FizzBuzz'
    assert fizzbuzz(0) == []
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Print FizzBuzz')
    parser.add_argument('limit', nargs='?', type=int, default=15)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.limit < 0:
        parser.error('limit must be zero or positive')
    print('\n'.join(fizzbuzz(args.limit)))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-fizzbuzz', 'FizzBuzz',
        'Print Fizz for multiples of 3, Buzz for 5 and FizzBuzz for both.',
        [('fizzbuzz', 5), ('fizz buzz', 5), ('fizzbuzz program', 5), ('multiples of 3', 3)],
        source)


def _factorial(context):
    source = r'''#!/usr/bin/env python3
"""Factorial, iteratively and with memoized recursion."""
import argparse
import sys
from functools import lru_cache

sys.setrecursionlimit(10000)


def factorial(number):
    if number < 0:
        raise ValueError('factorial is undefined for negative numbers')
    result = 1
    for value in range(2, number + 1):
        result *= value
    return result


@lru_cache(maxsize=None)
def factorial_recursive(number):
    if number < 0:
        raise ValueError('factorial is undefined for negative numbers')
    return 1 if number < 2 else number * factorial_recursive(number - 1)


def selftest():
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(5) == 120
    assert factorial(10) == 3628800
    assert factorial_recursive(6) == 720
    assert len(str(factorial(100))) == 158
    try:
        factorial(-1)
    except ValueError:
        pass
    else:
        raise AssertionError('negative input must raise')
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Compute factorials')
    parser.add_argument('number', nargs='?', type=int, default=10)
    parser.add_argument('--recursive', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    compute = factorial_recursive if args.recursive else factorial
    print(compute(args.number))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-factorial', 'Factorial',
        'Compute factorials iteratively or with memoized recursion, including huge integers.',
        [('factorial', 5), ('factorial program', 5), ('n factorial', 5), ('math', 1)],
        source)


def _fibonacci(context):
    source = r'''#!/usr/bin/env python3
"""Fibonacci numbers: iterative sequence and a single fast-doubling term."""
import argparse


def sequence(count):
    if count <= 0:
        return []
    values = [0]
    if count == 1:
        return values
    values.append(1)
    while len(values) < count:
        values.append(values[-1] + values[-2])
    return values


def term(index):
    """Return F(index) using fast doubling."""
    if index < 0:
        raise ValueError('index must be non-negative')

    def pair(number):
        if number == 0:
            return 0, 1
        a, b = pair(number >> 1)
        c = a * (2 * b - a)
        d = a * a + b * b
        if number & 1:
            return d, c + d
        return c, d

    return pair(index)[0]


def selftest():
    assert sequence(0) == []
    assert sequence(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
    assert term(0) == 0
    assert term(1) == 1
    assert term(10) == 55
    assert term(50) == 12586269025
    for index in range(25):
        assert term(index) == sequence(index + 1)[-1]
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Fibonacci numbers')
    parser.add_argument('count', nargs='?', type=int, default=10)
    parser.add_argument('--nth', action='store_true', help='print only F(count)')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.nth:
        print(term(args.count))
    else:
        print(' '.join(str(value) for value in sequence(args.count)))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-fibonacci', 'Fibonacci Sequence',
        'Generate Fibonacci numbers, with fast doubling for very large indexes.',
        [('fibonacci', 5), ('fibonacci sequence', 5), ('fib', 4), ('golden ratio', 3)],
        source)


def _primes(context):
    source = r'''#!/usr/bin/env python3
"""Prime testing and a sieve of Eratosthenes."""
import argparse
import math


def is_prime(number):
    if number < 2:
        return False
    if number % 2 == 0:
        return number == 2
    limit = math.isqrt(number)
    for divisor in range(3, limit + 1, 2):
        if number % divisor == 0:
            return False
    return True


def sieve(limit):
    if limit < 2:
        return []
    flags = bytearray(b'\x01') * (limit + 1)
    flags[0:2] = b'\x00\x00'
    for number in range(2, math.isqrt(limit) + 1):
        if flags[number]:
            start = number * number
            flags[start:limit + 1:number] = b'\x00' * (((limit - start) // number) + 1)
    return [number for number in range(limit + 1) if flags[number]]


def factorize(number):
    if number < 2:
        return []
    factors = []
    divisor = 2
    while divisor * divisor <= number:
        while number % divisor == 0:
            factors.append(divisor)
            number //= divisor
        divisor += 1 if divisor == 2 else 2
    if number > 1:
        factors.append(number)
    return factors


def selftest():
    assert is_prime(2) and is_prime(97) and not is_prime(1)
    assert not is_prime(91) and not is_prime(100)
    assert sieve(30) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert sieve(1) == []
    assert factorize(360) == [2, 2, 2, 3, 3, 5]
    assert factorize(97) == [97]
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Primes and factorization')
    parser.add_argument('number', nargs='?', type=int, default=100)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--factor', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.check:
        print(f'{args.number} is {"prime" if is_prime(args.number) else "not prime"}')
    elif args.factor:
        print(' x '.join(str(value) for value in factorize(args.number)) or 'nothing to factor')
    else:
        print(', '.join(str(value) for value in sieve(args.number)))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-primes', 'Prime Numbers',
        'Test primality, list primes with a sieve and factorize numbers.',
        [('prime numbers', 5), ('primes', 4), ('sieve', 4), ('prime check', 5),
         ('factorize', 4), ('is prime', 5)],
        source)


def _binary_search(context):
    source = r'''#!/usr/bin/env python3
"""Binary search over a sorted list, with duplicate-aware bounds."""
import argparse


def binary_search(values, target):
    low, high = 0, len(values) - 1
    while low <= high:
        middle = (low + high) // 2
        if values[middle] == target:
            return middle
        if values[middle] < target:
            low = middle + 1
        else:
            high = middle - 1
    return -1


def lower_bound(values, target):
    low, high = 0, len(values)
    while low < high:
        middle = (low + high) // 2
        if values[middle] < target:
            low = middle + 1
        else:
            high = middle
    return low


def upper_bound(values, target):
    low, high = 0, len(values)
    while low < high:
        middle = (low + high) // 2
        if values[middle] <= target:
            low = middle + 1
        else:
            high = middle
    return low


def selftest():
    data = [1, 3, 3, 3, 5, 9, 12]
    assert binary_search(data, 9) == 5
    assert binary_search(data, 4) == -1
    assert binary_search([], 1) == -1
    assert lower_bound(data, 3) == 1
    assert upper_bound(data, 3) == 4
    assert lower_bound(data, 4) == 4
    assert upper_bound(data, 100) == len(data)
    for value in data:
        assert data[binary_search(data, value)] == value
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Binary search')
    parser.add_argument('target', nargs='?', type=int, default=0)
    parser.add_argument('values', nargs='*', type=int, help='sorted numbers')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    values = sorted(args.values or [1, 3, 5, 7, 9, 11])
    index = binary_search(values, args.target)
    if index < 0:
        print(f'{args.target} not found in {values}')
    else:
        print(f'{args.target} found at index {index} in {values}')


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-binary-search', 'Binary Search',
        'Find values in sorted lists, with lower/upper bound variants.',
        [('binary search', 5), ('search sorted list', 5), ('binary search algorithm', 5),
         ('lower bound', 3)],
        source)


def _anagram(context):
    source = r'''#!/usr/bin/env python3
"""Anagram check plus grouped anagrams."""
import argparse
import collections
import re


def normalize(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def is_anagram(first, second):
    return sorted(normalize(first)) == sorted(normalize(second))


def group(words):
    buckets = collections.defaultdict(list)
    for word in words:
        key = ''.join(sorted(normalize(word)))
        if key:
            buckets[key].append(word)
    return [values for values in buckets.values() if len(values) > 1]


def selftest():
    assert is_anagram('listen', 'silent') is True
    assert is_anagram('Dormitory', 'dirty room') is True
    assert is_anagram('abc', 'abd') is False
    assert is_anagram('', '') is True
    groups = group(['listen', 'silent', 'enlist', 'hello', 'world'])
    assert len(groups) == 1 and len(groups[0]) == 3
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Anagram checker and grouper')
    parser.add_argument('--first')
    parser.add_argument('--second')
    parser.add_argument('words', nargs='*')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.first and args.second:
        print('anagram' if is_anagram(args.first, args.second) else 'not anagram')
        return
    words = args.words or ['listen', 'silent', 'enlist', 'hello']
    found = group(words)
    if not found:
        print('No anagram groups.')
    for values in found:
        print(', '.join(values))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-anagram', 'Anagram Checker',
        'Check whether two phrases are anagrams and group words by their letters.',
        [('anagram', 5), ('anagram checker', 5), ('anagrams', 5), ('same letters', 3)],
        source)


def _word_frequency(context):
    source = r'''#!/usr/bin/env python3
"""Count the most frequent words in text."""
import argparse
import collections
import re
import sys

WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'else', 'of', 'to', 'in',
    'on', 'at', 'for', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'it',
    'this', 'that', 'as', 'by', 'from', 'we', 'you', 'they', 'he', 'she', 'i',
    'not', 'no', 'so', 'do', 'does', 'did', 'has', 'have', 'had', 'can', 'will',
}


def frequency(text, top=10, ignore_stopwords=False):
    words = [word.lower() for word in WORD.findall(text)]
    if ignore_stopwords:
        words = [word for word in words if word not in STOPWORDS]
    counts = collections.Counter(words)
    return counts.most_common(top)


def selftest():
    text = 'The cat and the dog. The cat wins!'
    result = frequency(text, top=3)
    assert result[0] == ('the', 3)
    assert ('cat', 2) in result
    filtered = frequency(text, top=3, ignore_stopwords=True)
    assert filtered[0] == ('cat', 2)
    assert frequency('', top=5) == []
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Most frequent words')
    parser.add_argument('files', nargs='*')
    parser.add_argument('--top', type=int, default=15)
    parser.add_argument('--ignore-stopwords', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.files:
        chunks = []
        for path in args.files:
            with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                chunks.append(handle.read())
        text = '\n'.join(chunks)
    else:
        text = sys.stdin.read()
    for word, count in frequency(text, args.top, args.ignore_stopwords):
        print(f'{count:>6}  {word}')


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-word-frequency', 'Word Frequency',
        'Rank the most common words in a file, optionally ignoring stopwords.',
        [('word frequency', 5), ('word count ranking', 4), ('frequent words', 5),
         ('text analysis', 4), ('most common words', 5)],
        source)


def _dedupe(context):
    source = r'''#!/usr/bin/env python3
"""Remove duplicates while keeping first-seen order."""
import argparse
import json


def dedupe(items):
    seen = set()
    output = []
    for item in items:
        key = item if isinstance(item, (str, int, float, bool, type(None))) else json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def dedupe_lines(text, case_sensitive=True):
    seen = set()
    output = []
    for line in text.splitlines():
        key = line if case_sensitive else line.lower()
        if key not in seen:
            seen.add(key)
            output.append(line)
    return output


def selftest():
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert dedupe(['a', 'A', 'a']) == ['a', 'A']
    assert dedupe([]) == []
    assert dedupe([{'a': 1}, {'a': 1}, {'a': 2}]) == [{'a': 1}, {'a': 2}]
    assert dedupe_lines('one\ntwo\none\nTHREE\nthree') == ['one', 'two', 'THREE', 'three']
    assert dedupe_lines('one\nOne', case_sensitive=False) == ['one']
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Remove duplicate values or lines')
    parser.add_argument('values', nargs='*')
    parser.add_argument('--case-insensitive', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    values = args.values or ['apple', 'banana', 'apple', 'cherry', 'banana']
    if len(values) == 1 and '\n' in values[0]:
        for line in dedupe_lines(values[0], not args.case_insensitive):
            print(line)
        return
    for item in dedupe(values):
        print(item)


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-dedupe', 'Remove Duplicates',
        'Deduplicate lists or lines while preserving the first occurrence.',
        [('remove duplicates', 5), ('dedupe', 5), ('deduplicate', 5), ('unique values', 4),
         ('unique lines', 4)],
        source)


def _gcd_lcm(context):
    source = r'''#!/usr/bin/env python3
"""Greatest common divisor and least common multiple."""
import argparse
import math


def gcd(first, second):
    return math.gcd(abs(first), abs(second))


def gcd_many(numbers):
    result = 0
    for number in numbers:
        result = math.gcd(result, abs(number))
    return result


def lcm(first, second):
    if first == 0 or second == 0:
        return 0
    return abs(first * second) // math.gcd(first, second)


def lcm_many(numbers):
    result = 1
    for number in numbers:
        result = lcm(result, number)
    return result


def selftest():
    assert gcd(12, 18) == 6
    assert gcd(-12, 18) == 6
    assert gcd(0, 5) == 5
    assert gcd_many([12, 18, 24]) == 6
    assert lcm(4, 6) == 12
    assert lcm(0, 5) == 0
    assert lcm_many([2, 3, 4]) == 12
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='GCD and LCM')
    parser.add_argument('numbers', nargs='*', type=int)
    parser.add_argument('--lcm', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    numbers = args.numbers or [12, 18]
    if len(numbers) < 2:
        parser.error('provide at least two numbers')
    print(lcm_many(numbers) if args.lcm else gcd_many(numbers))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-gcd-lcm', 'GCD and LCM',
        'Compute the greatest common divisor and least common multiple of several numbers.',
        [('gcd', 5), ('lcm', 5), ('greatest common divisor', 5), ('least common multiple', 5),
         ('hcf', 4)],
        source)


def _leap_year(context):
    source = r'''#!/usr/bin/env python3
"""Leap-year check and the number of days in a month."""
import argparse
import calendar


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if not 1 <= month <= 12:
        raise ValueError('month must be 1-12')
    return calendar.monthrange(year, month)[1]


def selftest():
    assert is_leap(2000) is True
    assert is_leap(1900) is False
    assert is_leap(2024) is True
    assert is_leap(2023) is False
    assert days_in_month(2024, 2) == 29
    assert days_in_month(2023, 2) == 28
    assert days_in_month(2024, 12) == 31
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Leap years and month lengths')
    parser.add_argument('year', nargs='?', type=int, default=2024)
    parser.add_argument('--month', type=int)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.month:
        print(f'{args.year}-{args.month:02d} has {days_in_month(args.year, args.month)} days')
    else:
        print(f'{args.year} is {"a leap year" if is_leap(args.year) else "not a leap year"}')


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-leap-year', 'Leap Year Check',
        'Check leap years and get the exact number of days in any month.',
        [('leap year', 5), ('leap year check', 5), ('days in month', 4), ('calendar', 3)],
        source)


def _temperature(context):
    source = r'''#!/usr/bin/env python3
"""Convert temperatures between Celsius, Fahrenheit and Kelvin."""
import argparse


def to_celsius(value, unit):
    unit = unit.upper()
    if unit == 'C':
        return value
    if unit == 'F':
        return (value - 32) * 5 / 9
    if unit == 'K':
        return value - 273.15
    raise ValueError(f'unknown unit: {unit}')


def from_celsius(value, unit):
    unit = unit.upper()
    if unit == 'C':
        return value
    if unit == 'F':
        return value * 9 / 5 + 32
    if unit == 'K':
        return value + 273.15
    raise ValueError(f'unknown unit: {unit}')


def convert(value, source, target):
    return from_celsius(to_celsius(value, source), target)


def describe(value, unit='C'):
    celsius = to_celsius(value, unit)
    if celsius <= 0:
        label = 'freezing'
    elif celsius < 15:
        label = 'cold'
    elif celsius < 25:
        label = 'mild'
    elif celsius < 35:
        label = 'warm'
    else:
        label = 'hot'
    return f'{value:g}°{unit.upper()} is {label} ({celsius:.1f}°C)'


def selftest():
    assert abs(convert(100, 'C', 'F') - 212) < 1e-9
    assert abs(convert(32, 'F', 'C')) < 1e-9
    assert abs(convert(0, 'C', 'K') - 273.15) < 1e-9
    assert abs(convert(273.15, 'K', 'C')) < 1e-9
    assert abs(convert(-40, 'C', 'F') + 40) < 1e-9
    assert 'warm' in describe(28, 'C')
    assert 'freezing' in describe(32, 'F')
    print('SELFTEST OK')


def main():
    parser = argparse.ArgumentParser(description='Convert temperatures')
    parser.add_argument('value', nargs='?', type=float, default=100)
    parser.add_argument('source', nargs='?', default='C')
    parser.add_argument('target', nargs='?', default='F')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    print(convert(args.value, args.source, args.target))


if __name__ == '__main__':
    main()
'''
    return _snippet(
        'snippet-temperature', 'Temperature Converter',
        'Convert between Celsius, Fahrenheit and Kelvin, with a plain-language description.',
        [('temperature converter', 5), ('celsius to fahrenheit', 5), ('fahrenheit to celsius', 5),
         ('kelvin', 4), ('temperature conversion', 5)],
        source)


# --------------------------------------------------------------------------- #
# Registry, detection and build entry points
# --------------------------------------------------------------------------- #
BUILDERS = [
    _calculator,
    _guessing_game,
    _todo_cli,
    _expense_tracker,
    _password_generator,
    _unit_converter,
    _timer,
    _file_organizer,
    _duplicate_finder,
    _backup_script,
    _log_analyzer,
    _csv_summary,
    _web_scraper,
    _rest_api,
    _static_site,
    _js_calculator,
    _sql_demo,
    _ps_file_report,
    _snake_game,
    _json_tool,
    _port_scanner,
    _markdown_to_html,
    _weather_cli,
    _word_count,
    _chat_server,
    _reverse_string,
    _palindrome,
    _fizzbuzz,
    _factorial,
    _fibonacci,
    _primes,
    _binary_search,
    _anagram,
    _word_frequency,
    _dedupe,
    _gcd_lcm,
    _leap_year,
    _temperature,
]

_LANGUAGE_HINTS = {
    'python': ('python', 'py', 'flask', 'django', 'fastapi'),
    'javascript': ('javascript', 'node', 'nodejs', 'node.js', 'js', 'npm'),
    'powershell': ('powershell', 'ps1', 'windows script'),
    'html': ('html', 'website', 'webpage', 'web page', 'landing page', 'css'),
    'sql': ('sql', 'sqlite', 'database schema', 'query'),
}

_CACHE = None
_ALL = None
_BY_ID = None


def _all():
    global _ALL
    if _ALL is None:
        _ALL = [builder({}) for builder in BUILDERS]
    return _ALL


def _by_id():
    global _BY_ID
    if _BY_ID is None:
        _BY_ID = {built['id']: builder for built, builder in zip(_all(), BUILDERS)}
    return _BY_ID


def _summarize(built):
    return {
        'id': built['id'],
        'title': built['title'],
        'language': built['language'],
        'kind': built['kind'],
        'summary': built['summary'],
        'keywords': [word for word, _weight in built.get('keywords', [])],
        'run': built.get('run', ''),
        'entry': built.get('entry', ''),
        'files': sorted(built.get('files', {})),
    }


def catalog():
    """Return lightweight metadata for every offline recipe."""
    global _CACHE
    if _CACHE is None:
        _CACHE = [_summarize(built) for built in _all()]
    return [dict(item) for item in _CACHE]


def recipe_by_id(recipe_id):
    for built in _all():
        if built['id'] == recipe_id:
            return dict(built)
    return None


def get_recipe(recipe_id):
    """Alias kept for readability in the API layer."""
    return recipe_by_id(recipe_id)


def languages():
    return sorted({item['language'] for item in catalog()})


def detect(request, limit=5):
    """Rank offline recipes against a natural-language request.

    Returns a list of ``{'id', 'title', 'language', 'kind', 'summary', 'score'}``
    dictionaries, best first. Every score comes from keyword evidence in the
    request, so an empty list means "no offline recipe fits".
    """
    text = (request or '').lower()
    if not text.strip():
        return []
    language_preference = None
    for language, hints in _LANGUAGE_HINTS.items():
        if any(re.search(r'\b' + re.escape(hint) + r'\b', text) for hint in hints):
            language_preference = language
            break
    ranked = []
    for built in _all():
        score = 0.0
        for phrase, weight in built.get('keywords', []):
            phrase = phrase.lower()
            if phrase in text:
                score += weight * (2.0 + min(len(phrase), 24) / 12.0)
            else:
                parts = [part for part in phrase.split() if part]
                hits = sum(1 for part in parts
                           if re.search(r'\b' + re.escape(part) + r'\b', text))
                if parts and hits == len(parts):
                    score += weight * 0.6 * hits
        if score <= 0:
            continue
        if language_preference and built['language'] == language_preference:
            score += 2.5
        ranked.append({
            'id': built['id'],
            'title': built['title'],
            'language': built['language'],
            'kind': built['kind'],
            'summary': built['summary'],
            'score': round(score, 2),
        })
    ranked.sort(key=lambda entry: (-entry['score'], entry['title']))
    return ranked[:limit]


def best_match(request):
    matches = detect(request, limit=1)
    return matches[0] if matches else None


def topic_from(request, default=''):
    """Pull a short project topic out of a request, used by templates."""
    text = (request or '').strip()
    if not text:
        return default
    topic = _topic(text, default='')
    if topic:
        return topic
    match = re.search(r'\b(?:called|named)\s+([^.,;!?]{2,48})', text, re.I)
    if match:
        return match.group(1).strip()
    return default


def build(recipe_id=None, request='', context=None):
    """Build a complete recipe.

    Raises ``LookupError`` when ``recipe_id`` is unknown or no offline recipe
    matches ``request``. Callers should treat that as a normal outcome and
    fall back to a generative provider (or decline) rather than inventing code.
    """
    request = request or ''
    if recipe_id:
        builder = _by_id().get(recipe_id)
        if builder is None:
            raise LookupError(f'unknown recipe: {recipe_id}')
    else:
        match = best_match(request)
        if not match:
            raise LookupError('no offline recipe matches this request')
        builder = _by_id()[match['id']]
    base_context = dict(context or {})
    base_context.setdefault('topic', topic_from(request, ''))
    built = dict(builder(base_context))
    built['request'] = request
    built['topic'] = base_context.get('topic', '')
    built['keywords'] = [word for word, _weight in built.get('keywords', [])]
    return built



