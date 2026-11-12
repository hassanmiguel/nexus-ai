"""Programming knowledge catalog and real, executable exercise generators.

Every exercise returned here is a complete pair of source + test harness. The
solutions are deterministic reference implementations; NEXUS runs them in the
sandbox before calling them verified. Languages whose toolchain is missing are
still studied conceptually, but they are never marked verified.

Only Python, JavaScript, PHP, SQL, C, C++ and Rust have runnable exercise
generators here because those were verified to exist on the target machine at
build time. TypeScript, Java, Go and C# are learned conceptually and executed
only if their toolchain appears later.
"""
from __future__ import annotations

LANGUAGES = [
    {
        'id': 'python', 'name': 'Python', 'ext': 'py', 'docs': 'https://docs.python.org/3/',
        'category': 'programming',
        'concepts': [
            ('variables and types', 'beginner', 'Names bind objects; int, float, str, bool and None are the core scalar types.'),
            ('control flow', 'beginner', 'if/elif/else branches, while and for loops, and break/continue control execution.'),
            ('functions and arguments', 'beginner', 'def defines functions; positional, keyword, default and *args/**kwargs parameters vary the call signature.'),
            ('lists and tuples', 'beginner', 'Lists are mutable sequences; tuples are immutable and hashable when their items are.'),
            ('dicts and sets', 'beginner', 'Dicts map hashable keys to values; sets store unique hashable items with average O(1) membership.'),
            ('exceptions', 'beginner', 'try/except/else/finally handles recoverable errors; raising propagates a typed failure.'),
            ('comprehensions', 'beginner', 'List, dict and set comprehensions build collections from iterables with optional filters.'),
            ('decorators', 'intermediate', 'A decorator is a callable that wraps another callable to extend its behaviour without editing it.'),
            ('generators and iterators', 'intermediate', 'yield turns a function into a lazy iterator; iterators implement __iter__ and __next__.'),
            ('classes and dataclasses', 'intermediate', 'class defines types with attributes and methods; dataclasses generate init, repr and equality.'),
            ('context managers', 'intermediate', 'with statements call __enter__/__exit__, guaranteeing deterministic cleanup.'),
            ('typing and protocols', 'advanced', 'Type hints document interfaces; Protocol describes structural typing for static checkers.'),
            ('asyncio', 'advanced', 'async/await schedules cooperative concurrency on an event loop; blocking calls must be offloaded.'),
            ('metaclasses', 'expert', 'A metaclass controls class creation; most problems are better solved with composition or decorators.'),
            ('descriptors', 'expert', '__get__/__set__ objects implement attribute access protocols used by methods and properties.'),
        ],
    },
    {
        'id': 'javascript', 'name': 'JavaScript', 'ext': 'js', 'docs': 'https://developer.mozilla.org/en-US/docs/Web/JavaScript',
        'category': 'programming',
        'concepts': [
            ('values and coercion', 'beginner', 'Primitive values coerce differently with == and ===; prefer strict equality.'),
            ('functions and closures', 'beginner', 'Functions capture their lexical scope, which enables closures and partial application.'),
            ('arrays and iteration', 'beginner', 'map, filter and reduce transform collections without mutating them.'),
            ('objects and prototypes', 'intermediate', 'Objects inherit through a prototype chain; class syntax is sugar over prototypes.'),
            ('promises', 'intermediate', 'A Promise represents a future value with then/catch/finally chaining.'),
            ('async and await', 'intermediate', 'async functions return promises; await suspends until the awaited promise settles.'),
            ('modules', 'intermediate', 'ES modules export named or default bindings and import them statically.'),
            ('error handling', 'intermediate', 'throw propagates exceptions; try/catch/finally handles them, including rejected awaits.'),
            ('event loop', 'advanced', 'Macrotasks and microtasks run on a single thread with a well-defined ordering.'),
            ('destructuring and spread', 'beginner', 'Pattern matching extracts values; spread copies enumerable properties or iterables.'),
        ],
    },
    {
        'id': 'typescript', 'name': 'TypeScript', 'ext': 'ts', 'docs': 'https://www.typescriptlang.org/docs/',
        'category': 'programming',
        'concepts': [
            ('type annotations', 'beginner', 'Annotations describe values and are erased at runtime.'),
            ('interfaces and type aliases', 'beginner', 'Both describe object shapes; interfaces can merge, aliases can compose unions.'),
            ('generics', 'intermediate', 'Type parameters abstract over types while preserving relationships.'),
            ('union and intersection types', 'intermediate', 'Unions model alternatives; intersections combine requirements.'),
            ('narrowing', 'intermediate', 'Control-flow analysis narrows union types using typeof, in and discriminants.'),
            ('utility types', 'advanced', 'Partial, Pick, Omit, Record and ReturnType derive types from existing ones.'),
            ('conditional types', 'advanced', 'Types can branch on assignability with extends and infer.'),
        ],
    },
    {
        'id': 'java', 'name': 'Java', 'ext': 'java', 'docs': 'https://docs.oracle.com/en/java/',
        'category': 'programming',
        'concepts': [
            ('classes and objects', 'beginner', 'Classes define state and behaviour; objects are instances allocated on the heap.'),
            ('inheritance and polymorphism', 'beginner', 'Subclasses extend behaviour; overridden methods dispatch dynamically.'),
            ('interfaces', 'beginner', 'Interfaces declare contracts and support default methods.'),
            ('collections', 'intermediate', 'List, Set and Map implementations differ in ordering, duplication and complexity.'),
            ('generics', 'intermediate', 'Generic types provide compile-time safety with type erasure at runtime.'),
            ('exceptions', 'intermediate', 'Checked and unchecked exceptions have different handling requirements.'),
            ('streams', 'advanced', 'The Stream API expresses lazy pipelines over collections.'),
            ('concurrency', 'advanced', 'Threads, executors and concurrent collections coordinate shared state.'),
        ],
    },
    {
        'id': 'cpp', 'name': 'C++', 'ext': 'cpp', 'docs': 'https://en.cppreference.com/w/',
        'category': 'programming',
        'concepts': [
            ('compilation model', 'beginner', 'Translation units compile independently and link into an executable.'),
            ('references and pointers', 'beginner', 'References alias objects; pointers store addresses and may be null.'),
            ('RAII', 'intermediate', 'Resource acquisition is initialisation: destructors release resources deterministically.'),
            ('standard library containers', 'intermediate', 'vector, map and unordered_map offer different complexity and stability trade-offs.'),
            ('move semantics', 'advanced', 'Rvalue references and move constructors transfer ownership instead of copying.'),
            ('templates', 'advanced', 'Templates instantiate code for concrete types at compile time.'),
            ('undefined behaviour', 'advanced', 'Out-of-bounds access, dangling references and signed overflow make a program invalid.'),
        ],
    },
    {
        'id': 'c', 'name': 'C', 'ext': 'c', 'docs': 'https://en.cppreference.com/w/c',
        'category': 'programming',
        'concepts': [
            ('pointers', 'beginner', 'A pointer stores an address; dereferencing accesses the pointed-to object.'),
            ('arrays and strings', 'beginner', 'Arrays decay to pointers; C strings are NUL-terminated char arrays.'),
            ('structs', 'beginner', 'Structs group fields into a single value type.'),
            ('dynamic memory', 'intermediate', 'malloc/free manage heap memory manually; leaks and double frees are bugs.'),
            ('file I/O', 'intermediate', 'FILE handles and fopen/fread/fclose perform buffered I/O.'),
            ('preprocessor', 'intermediate', 'Macros and includes are textual transformations before compilation.'),
        ],
    },
    {
        'id': 'rust', 'name': 'Rust', 'ext': 'rs', 'docs': 'https://doc.rust-lang.org/book/',
        'category': 'programming',
        'concepts': [
            ('ownership', 'beginner', 'Each value has one owner; dropping the owner frees the value.'),
            ('borrowing', 'intermediate', 'References borrow values immutably or mutably under aliasing rules.'),
            ('structs and enums', 'beginner', 'Structs group data; enums model alternatives, including Option and Result.'),
            ('traits', 'intermediate', 'Traits define shared behaviour and enable generic bounds.'),
            ('error handling', 'intermediate', 'Result and the ? operator propagate recoverable errors without exceptions.'),
            ('iterators', 'intermediate', 'Iterator adapters are lazy and compile to efficient loops.'),
            ('lifetimes', 'advanced', 'Lifetime parameters express how long references remain valid.'),
        ],
    },
    {
        'id': 'go', 'name': 'Go', 'ext': 'go', 'docs': 'https://go.dev/doc/',
        'category': 'programming',
        'concepts': [
            ('packages and modules', 'beginner', 'Code is organised into packages; modules declare dependencies.'),
            ('structs and methods', 'beginner', 'Methods attach behaviour to named types.'),
            ('interfaces', 'intermediate', 'Interfaces are satisfied implicitly by method sets.'),
            ('goroutines', 'intermediate', 'go statements run functions concurrently.'),
            ('channels', 'intermediate', 'Channels communicate typed values between goroutines.'),
            ('error values', 'beginner', 'Errors are ordinary values returned and checked by callers.'),
        ],
    },
    {
        'id': 'php', 'name': 'PHP', 'ext': 'php', 'docs': 'https://www.php.net/manual/en/',
        'category': 'programming',
        'concepts': [
            ('variables and arrays', 'beginner', 'PHP arrays are ordered maps used for both lists and dictionaries.'),
            ('functions', 'beginner', 'Functions support default, variadic and named arguments.'),
            ('classes', 'intermediate', 'Classes support visibility, inheritance, interfaces and traits.'),
            ('sessions and cookies', 'intermediate', 'Sessions persist server-side state keyed by a client cookie.'),
            ('PDO and prepared statements', 'intermediate', 'Prepared statements separate SQL from data and prevent injection.'),
            ('composer autoloading', 'intermediate', 'Composer maps namespaces to files with PSR-4 autoloading.'),
        ],
    },
    {
        'id': 'sql', 'name': 'SQL', 'ext': 'sql', 'docs': 'https://www.sqlite.org/lang.html',
        'category': 'programming',
        'concepts': [
            ('select and where', 'beginner', 'SELECT projects columns; WHERE filters rows before grouping.'),
            ('joins', 'beginner', 'INNER, LEFT and CROSS joins combine rows from related tables.'),
            ('aggregation', 'intermediate', 'GROUP BY groups rows and aggregate functions collapse each group.'),
            ('indexes', 'intermediate', 'Indexes trade write cost for faster lookups on selected columns.'),
            ('transactions', 'intermediate', 'Transactions group statements atomically with BEGIN/COMMIT/ROLLBACK.'),
            ('window functions', 'advanced', 'Window functions compute values across related rows without collapsing them.'),
            ('query planning', 'advanced', 'EXPLAIN reveals scan and join strategies chosen by the planner.'),
        ],
    },
    {
        'id': 'html', 'name': 'HTML', 'ext': 'html', 'docs': 'https://developer.mozilla.org/en-US/docs/Web/HTML',
        'category': 'webdev',
        'concepts': [
            ('document structure', 'beginner', 'doctype, html lang, head and body form a valid document skeleton.'),
            ('semantic elements', 'beginner', 'header, nav, main, section, article and footer describe meaning.'),
            ('forms and labels', 'beginner', 'Every control needs an associated label and correct input types.'),
            ('accessibility', 'intermediate', 'Alt text, landmarks, focus order and contrast make pages usable by everyone.'),
            ('metadata and viewport', 'beginner', 'The viewport meta tag enables responsive layout on mobile.'),
        ],
    },
    {
        'id': 'css', 'name': 'CSS', 'ext': 'css', 'docs': 'https://developer.mozilla.org/en-US/docs/Web/CSS',
        'category': 'webdev',
        'concepts': [
            ('box model', 'beginner', 'Content, padding, border and margin determine rendered size.'),
            ('flexbox', 'beginner', 'Flex containers distribute space along a main axis.'),
            ('grid', 'intermediate', 'Grid defines rows and columns for two-dimensional layout.'),
            ('responsive design', 'intermediate', 'Media queries and fluid units adapt layouts to viewport size.'),
            ('custom properties', 'intermediate', 'CSS variables cascade and can be scoped to selectors.'),
            ('specificity', 'intermediate', 'Cascade order, specificity and inheritance decide which declaration wins.'),
        ],
    },
    {
        'id': 'csharp', 'name': 'C#', 'ext': 'cs', 'docs': 'https://learn.microsoft.com/en-us/dotnet/csharp/',
        'category': 'programming',
        'concepts': [
            ('types and variables', 'beginner', 'C# is statically typed with value and reference types.'),
            ('classes and records', 'beginner', 'Records provide value equality and concise immutable data types.'),
            ('LINQ', 'intermediate', 'LINQ composes queries over collections with deferred execution.'),
            ('async and await', 'advanced', 'Task-based asynchrony composes non-blocking operations.'),
            ('dependency injection', 'advanced', 'DI supplies collaborators instead of constructing them internally.'),
        ],
    },
]

_LANG_INDEX = {item['id']: item for item in LANGUAGES}


def languages():
    return [{'id': item['id'], 'name': item['name'], 'docs': item['docs'],
             'concept_count': len(item['concepts']), 'category': item['category']}
            for item in LANGUAGES]


def language_meta(language):
    return _LANG_INDEX.get((language or '').lower())


def concepts(language=None):
    out = []
    for item in LANGUAGES:
        if language and item['id'] != language:
            continue
        for name, difficulty, summary in item['concepts']:
            out.append({'language': item['id'], 'language_name': item['name'],
                        'concept': name, 'difficulty': difficulty, 'summary': summary})
    return out


def docs_domains():
    """Domains needed for programming documentation discovery."""
    from urllib.parse import urlparse
    out = set()
    for item in LANGUAGES:
        host = (urlparse(item['docs']).hostname or '').lower()
        if host.startswith('www.'):
            host = host[4:]
        if host:
            out.add(host)
    out.update({'docs.python.org', 'developer.mozilla.org', 'www.typescriptlang.org',
                'docs.oracle.com', 'en.cppreference.com', 'doc.rust-lang.org', 'go.dev',
                'www.php.net', 'www.sqlite.org', 'learn.microsoft.com', 'nodejs.org'})
    return sorted(out)


# --------------------------------------------------------------------------- #
# Executable exercise generators
# --------------------------------------------------------------------------- #
def _py(title, prompt, solution, tests, concept, difficulty, starter=''):
    return {'language': 'python', 'entry': 'test_solution.py', 'title': title, 'prompt': prompt,
            'concept': concept, 'difficulty': difficulty,
            'files': {'solution.py': solution.strip() + '\n', 'test_solution.py': tests.strip() + '\n'},
            'starter': starter or 'def solve(*args, **kwargs):\n    raise NotImplementedError\n',
            'solution': solution.strip() + '\n', 'tests': tests.strip() + '\n'}


PY_TESTS_HEADER = '''import solution


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"


'''


def _py_variants(concept, difficulty):
    c = (concept or '').lower()
    if 'dict' in c or 'set' in c:
        sol = '''
def word_frequency(text):
    counts = {}
    for word in text.lower().split():
        word = word.strip(".,!?;:")
        if word:
            counts[word] = counts.get(word, 0) + 1
    return counts

def unique_words(text):
    return len(set(text.lower().split()))
'''
        tests = PY_TESTS_HEADER + '''
check("frequency", solution.word_frequency("the cat and the hat"), {"the": 2, "cat": 1, "and": 1, "hat": 1})
check("unique", solution.unique_words("a b a"), 2)
print("TESTS OK")
'''
        return ('Word frequency with a dictionary', 'Return a dict of word counts and the number of unique words.', sol, tests)
    if 'list' in c or 'tuple' in c or 'comprehension' in c:
        sol = '''
def rotate(items, k):
    if not items:
        return []
    k %= len(items)
    return items[-k:] + items[:-k] if k else list(items)

def evens_squared(values):
    return [v * v for v in values if v % 2 == 0]
'''
        tests = PY_TESTS_HEADER + '''
check("rotate", solution.rotate([1, 2, 3, 4, 5], 2), [4, 5, 1, 2, 3])
check("rotate zero", solution.rotate([1, 2], 0), [1, 2])
check("evens", solution.evens_squared([1, 2, 3, 4]), [4, 16])
print("TESTS OK")
'''
        return ('Rotate a list and square the evens', 'Implement a rotation without mutating the input, plus a filtered comprehension.', sol, tests)
    if 'exception' in c or 'error' in c:
        sol = '''
def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def divide(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a / b
'''
        tests = PY_TESTS_HEADER + '''
check("safe ok", solution.safe_int("42"), 42)
check("safe bad", solution.safe_int("nope"), None)
try:
    solution.divide(1, 0)
    raise AssertionError("expected ValueError")
except ValueError:
    pass
print("TESTS OK")
'''
        return ('Safe parsing and explicit errors', 'Convert defensively and raise a typed error for invalid division.', sol, tests)
    if 'function' in c or 'decorator' in c or 'closure' in c:
        sol = '''
def memoize(fn):
    cache = {}
    def wrapper(*args):
        if args not in cache:
            cache[args] = fn(*args)
        return cache[args]
    return wrapper

@memoize
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)
'''
        tests = PY_TESTS_HEADER + '''
check("fib", solution.fib(20), 6765)
check("cached", solution.fib(60), 1548008755920)
print("TESTS OK")
'''
        return ('Memoised Fibonacci', 'Write a decorator that caches results and use it on a recursive function.', sol, tests)
    if 'class' in c or 'dataclass' in c:
        sol = '''
class Account:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.balance += amount
        return self.balance

    def withdraw(self, amount):
        if amount <= 0 or amount > self.balance:
            raise ValueError("invalid withdrawal")
        self.balance -= amount
        return self.balance
'''
        tests = PY_TESTS_HEADER + '''
acct = solution.Account("ada", 10)
check("deposit", acct.deposit(5), 15)
check("withdraw", acct.withdraw(7), 8)
try:
    acct.withdraw(99)
    raise AssertionError("expected ValueError")
except ValueError:
    pass
print("TESTS OK")
'''
        return ('Bank account invariants', 'Implement a class that rejects negative amounts and overdrafts.', sol, tests)
    if 'generator' in c or 'iterator' in c:
        sol = '''
def take(iterable, n):
    count = 0
    for item in iterable:
        if count >= n:
            return
        yield item
        count += 1

def primes(limit):
    sieve = [True] * (limit + 1)
    for n in range(2, limit + 1):
        if sieve[n]:
            yield n
            for multiple in range(n * n, limit + 1, n):
                sieve[multiple] = False
'''
        tests = PY_TESTS_HEADER + '''
check("take", list(solution.take(range(100), 3)), [0, 1, 2])
check("primes", list(solution.primes(20)), [2, 3, 5, 7, 11, 13, 17, 19])
print("TESTS OK")
'''
        return ('Lazy generators', 'Yield values lazily with a take helper and a sieve generator.', sol, tests)
    if 'asyncio' in c or 'concurrent' in c:
        sol = '''
import asyncio

async def gather_values(values):
    async def double(v):
        await asyncio.sleep(0)
        return v * 2
    return await asyncio.gather(*(double(v) for v in values))
'''
        tests = PY_TESTS_HEADER + '''
import asyncio
check("gather", asyncio.run(solution.gather_values([1, 2, 3])), [2, 4, 6])
print("TESTS OK")
'''
        return ('Concurrent aggregation', 'Use asyncio.gather to run coroutines concurrently and preserve order.', sol, tests)
    # Default algorithmic exercises, scaled by difficulty.
    if difficulty in ('advanced', 'expert'):
        sol = '''
def two_sum(nums, target):
    seen = {}
    for index, value in enumerate(nums):
        need = target - value
        if need in seen:
            return [seen[need], index]
        seen[value] = index
    return []

def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
'''
        tests = PY_TESTS_HEADER + '''
check("two_sum", solution.two_sum([2, 7, 11, 15], 9), [0, 1])
check("two_sum late", solution.two_sum([3, 2, 4], 6), [1, 2])
check("merge", solution.merge_intervals([[1, 3], [2, 6], [8, 10]]), [[1, 6], [8, 10]])
print("TESTS OK")
'''
        return ('Linear two-sum and interval merge', 'Solve both in better than quadratic time and handle empty inputs.', sol, tests)
    if difficulty == 'intermediate':
        sol = '''
def binary_search(values, target):
    low, high = 0, len(values) - 1
    while low <= high:
        mid = (low + high) // 2
        if values[mid] == target:
            return mid
        if values[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1

def anagram(a, b):
    return sorted(a.replace(" ", "").lower()) == sorted(b.replace(" ", "").lower())
'''
        tests = PY_TESTS_HEADER + '''
check("found", solution.binary_search([1, 3, 5, 7, 9], 7), 3)
check("missing", solution.binary_search([1, 3, 5], 2), -1)
check("anagram", solution.anagram("Dormitory", "dirty room"), True)
check("not anagram", solution.anagram("abc", "abd"), False)
print("TESTS OK")
'''
        return ('Binary search and anagram check', 'Implement log-time search on a sorted list and a normalised anagram test.', sol, tests)
    sol = '''
def fizzbuzz(n):
    out = []
    for value in range(1, n + 1):
        if value % 15 == 0:
            out.append("FizzBuzz")
        elif value % 3 == 0:
            out.append("Fizz")
        elif value % 5 == 0:
            out.append("Buzz")
        else:
            out.append(str(value))
    return out

def is_palindrome(text):
    cleaned = [ch.lower() for ch in text if ch.isalnum()]
    return cleaned == cleaned[::-1]
'''
    tests = PY_TESTS_HEADER + '''
check("fizzbuzz", solution.fizzbuzz(5), ["1", "2", "Fizz", "4", "Buzz"])
check("fizzbuzz 15", solution.fizzbuzz(15)[-1], "FizzBuzz")
check("palindrome", solution.is_palindrome("A man, a plan, a canal: Panama"), True)
check("not palindrome", solution.is_palindrome("Nexus"), False)
print("TESTS OK")
'''
    return ('FizzBuzz and palindrome', 'Implement both classic checks with correct edge cases.', sol, tests)


def _js_variants(concept, difficulty):
    sol = '''
function twoSum(nums, target) {
  const seen = new Map();
  for (let i = 0; i < nums.length; i += 1) {
    const need = target - nums[i];
    if (seen.has(need)) return [seen.get(need), i];
    seen.set(nums[i], i);
  }
  return [];
}

function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    (acc[key] ||= []).push(item);
    return acc;
  }, {});
}

module.exports = { twoSum, groupBy };
'''
    tests = '''
const assert = require('assert');
const { twoSum, groupBy } = require('./solution.js');
assert.deepStrictEqual(twoSum([2, 7, 11, 15], 9), [0, 1]);
assert.deepStrictEqual(twoSum([3, 2, 4], 6), [1, 2]);
assert.deepStrictEqual(groupBy([1, 2, 3, 4], (n) => (n % 2 ? 'odd' : 'even')), { odd: [1, 3], even: [2, 4] });
console.log('TESTS OK');
'''
    return {'language': 'javascript', 'entry': 'test_solution.js', 'title': 'Two-sum and grouping',
            'prompt': 'Implement O(n) two-sum and a groupBy reducer, then satisfy the assertions.',
            'concept': concept or 'arrays and iteration', 'difficulty': difficulty or 'beginner',
            'files': {'solution.js': sol.strip() + '\n', 'test_solution.js': tests.strip() + '\n'},
            'starter': 'function twoSum(nums, target) {}\n', 'solution': sol.strip() + '\n', 'tests': tests.strip() + '\n'}


def _php_variants(concept, difficulty):
    sol = '''<?php
function wordFrequency(string $text): array {
    $words = preg_split('/\\s+/', strtolower(trim($text)));
    $counts = [];
    foreach ($words as $word) {
        $word = trim($word, ".,!?;:");
        if ($word === '') continue;
        $counts[$word] = ($counts[$word] ?? 0) + 1;
    }
    return $counts;
}

function safeDivide(float $a, float $b): ?float {
    return $b == 0.0 ? null : $a / $b;
}
'''
    tests = '''<?php
require __DIR__ . '/solution.php';
function check($label, $got, $want) { if ($got !== $want) { fwrite(STDERR, "$label failed\\n"); exit(1); } }
check('freq', wordFrequency('the cat and the hat'), ['the' => 2, 'cat' => 1, 'and' => 1, 'hat' => 1]);
check('divide', safeDivide(9, 3), 3.0);
check('divide zero', safeDivide(1, 0), null);
echo "TESTS OK\\n";
'''
    return {'language': 'php', 'entry': 'test_solution.php', 'title': 'PHP word frequency',
            'prompt': 'Count words with an associative array and guard division by zero.',
            'concept': concept or 'variables and arrays', 'difficulty': difficulty or 'beginner',
            'files': {'solution.php': sol, 'test_solution.php': tests},
            'starter': '<?php\nfunction wordFrequency(string $text): array { return []; }\n',
            'solution': sol, 'tests': tests}


def _c_variants(concept, difficulty):
    sol = r'''
#include <stdio.h>

int gcd(int a, int b) {
    while (b != 0) {
        int t = b;
        b = a % b;
        a = t;
    }
    return a < 0 ? -a : a;
}

long long factorial(int n) {
    long long result = 1;
    for (int i = 2; i <= n; i++) result *= i;
    return result;
}

int main(void) {
    if (gcd(48, 18) != 6) { printf("gcd failed\n"); return 1; }
    if (gcd(-9, 6) != 3) { printf("gcd negative failed\n"); return 1; }
    if (factorial(10) != 3628800LL) { printf("factorial failed\n"); return 1; }
    printf("TESTS OK\n");
    return 0;
}
'''
    return {'language': 'c', 'entry': 'main.c', 'title': 'C numeric helpers',
            'prompt': 'Implement integer gcd and factorial safely, including negative inputs.',
            'concept': concept or 'pointers', 'difficulty': difficulty or 'beginner',
            'files': {'main.c': sol.strip() + '\n'}, 'starter': '#include <stdio.h>\n',
            'solution': sol.strip() + '\n', 'tests': 'embedded assertions'}


def _cpp_variants(concept, difficulty):
    sol = r'''
#include <iostream>
#include <vector>
#include <algorithm>

std::vector<int> twoSum(const std::vector<int>& nums, int target) {
    for (size_t i = 0; i < nums.size(); ++i)
        for (size_t j = i + 1; j < nums.size(); ++j)
            if (nums[i] + nums[j] == target) return {static_cast<int>(i), static_cast<int>(j)};
    return {};
}

int main() {
    if (twoSum({2, 7, 11, 15}, 9) != std::vector<int>({0, 1})) { std::cout << "twoSum failed\n"; return 1; }
    if (!twoSum({1, 2, 3}, 99).empty()) { std::cout << "missing case failed\n"; return 1; }
    std::cout << "TESTS OK\n";
    return 0;
}
'''
    return {'language': 'cpp', 'entry': 'main.cpp', 'title': 'C++ containers',
            'prompt': 'Use std::vector to implement two-sum with a checked missing case.',
            'concept': concept or 'standard library containers', 'difficulty': difficulty or 'beginner',
            'files': {'main.cpp': sol.strip() + '\n'}, 'starter': '#include <vector>\n',
            'solution': sol.strip() + '\n', 'tests': 'embedded assertions'}


def _rust_variants(concept, difficulty):
    sol = r'''
fn two_sum(nums: &[i32], target: i32) -> Option<(usize, usize)> {
    for i in 0..nums.len() {
        for j in (i + 1)..nums.len() {
            if nums[i] + nums[j] == target {
                return Some((i, j));
            }
        }
    }
    None
}

fn main() {
    assert_eq!(two_sum(&[2, 7, 11, 15], 9), Some((0, 1)));
    assert_eq!(two_sum(&[1, 2, 3], 99), None);
    println!("TESTS OK");
}
'''
    return {'language': 'rust', 'entry': 'main.rs', 'title': 'Rust ownership practice',
            'prompt': 'Implement two-sum over a borrowed slice using Option, then assert both cases.',
            'concept': concept or 'ownership', 'difficulty': difficulty or 'beginner',
            'files': {'main.rs': sol.strip() + '\n'}, 'starter': 'fn two_sum(nums: &[i32], target: i32) -> Option<(usize, usize)> { None }\n',
            'solution': sol.strip() + '\n', 'tests': 'embedded assertions'}


def _sql_variants(concept, difficulty):
    sol = '''
CREATE TABLE employees(id INTEGER PRIMARY KEY, name TEXT, dept TEXT, salary INTEGER);
INSERT INTO employees VALUES (1, 'Ada', 'eng', 120), (2, 'Bo', 'eng', 90), (3, 'Cy', 'ops', 70), (4, 'Di', 'ops', 80);

CREATE TABLE departments(name TEXT PRIMARY KEY, floor INTEGER);
INSERT INTO departments VALUES ('eng', 3), ('ops', 1);

CREATE VIEW department_totals AS
SELECT e.dept, COUNT(*) AS people, SUM(e.salary) AS payroll, d.floor
FROM employees e JOIN departments d ON d.name = e.dept
GROUP BY e.dept, d.floor;
'''
    tests = '''import sqlite3

db = sqlite3.connect(":memory:")
db.executescript(open("solution.sql", encoding="utf-8").read())
rows = db.execute("SELECT dept, people, payroll, floor FROM department_totals ORDER BY dept").fetchall()
assert rows == [("eng", 2, 210, 3), ("ops", 2, 150, 1)], rows
count = db.execute("SELECT COUNT(*) FROM employees WHERE salary > 75").fetchone()[0]
assert count == 3, count
print("TESTS OK")
'''
    return {'language': 'sql', 'entry': 'test_solution.py', 'title': 'Joins and aggregation',
            'prompt': 'Create tables, join them and expose an aggregated view.',
            'concept': concept or 'joins', 'difficulty': difficulty or 'beginner',
            'files': {'solution.sql': sol.strip() + '\n', 'test_solution.py': tests.strip() + '\n'},
            'starter': '-- write your schema here\n', 'solution': sol.strip() + '\n', 'tests': tests.strip() + '\n'}


def _html_exercise(concept, difficulty):
    page = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Semantic profile card</title>
<style>
body{font-family:system-ui,sans-serif;background:#0b1020;color:#e6edf7;margin:0;display:grid;place-items:center;min-height:100vh}
.card{background:#121a30;padding:24px;border-radius:16px;max-width:320px;border:1px solid #23304d}
.card img{width:72px;height:72px;border-radius:50%}
</style>
</head>
<body>
<main class="card">
  <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='72' height='72'%3E%3Crect width='72' height='72' fill='%235eead4'/%3E%3C/svg%3E" alt="Abstract avatar">
  <h1>Ada Lovelace</h1>
  <p>Mathematician and first programmer.</p>
  <a href="#contact">Contact</a>
</main>
</body>
</html>
'''
    return {'language': 'html', 'entry': 'index.html', 'title': 'Semantic accessible card',
            'prompt': 'Build a semantic, accessible profile card with viewport metadata and alt text.',
            'concept': concept or 'semantic elements', 'difficulty': difficulty or 'beginner',
            'files': {'index.html': page}, 'starter': '<!doctype html>\n<html>\n', 'solution': page,
            'tests': 'static accessibility checks'}


def build_exercise(language, concept='', difficulty='beginner'):
    """Return a complete, real exercise for a language, or ``None``."""
    language = (language or 'python').lower()
    difficulty = difficulty if difficulty in ('beginner', 'intermediate', 'advanced', 'expert') else 'beginner'
    if language == 'python':
        title, prompt, sol, tests = _py_variants(concept, difficulty)
        return _py(title, prompt, sol, tests, concept, difficulty)
    if language == 'javascript':
        return _js_variants(concept, difficulty)
    if language == 'php':
        return _php_variants(concept, difficulty)
    if language == 'c':
        return _c_variants(concept, difficulty)
    if language == 'cpp':
        return _cpp_variants(concept, difficulty)
    if language == 'rust':
        return _rust_variants(concept, difficulty)
    if language == 'sql':
        return _sql_variants(concept, difficulty)
    if language in ('html', 'css'):
        return _html_exercise(concept, difficulty)
    return None


def assessment_spec(language, concept='', difficulty='beginner', variant=0):
    """Return a challenge plus an alternative implementation for comparison."""
    language = (language or 'python').lower()
    if language == 'python':
        base = _py_variants(concept, difficulty)
        alt_solution = base[2]
        alt_tests = base[3]
        if 'two_sum' in base[2] and difficulty in ('advanced', 'expert'):
            alt_solution = '''
def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []

def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
'''
        return {'language': 'python', 'entry': 'test_solution.py', 'title': base[0], 'question': base[1],
                'files': {'solution.py': base[2], 'test_solution.py': base[3]},
                'alternative_files': {'solution.py': alt_solution, 'test_solution.py': alt_tests},
                'solution': base[2], 'tests': base[3], 'complexity': 'O(n)' if difficulty in ('advanced', 'expert') else 'O(log n) / O(n log n)'}
    ex = build_exercise(language, concept, difficulty)
    if not ex:
        return None
    alt = dict(ex['files'])
    if language == 'javascript':
        alt['solution.js'] = '''function twoSum(nums, target) {
  for (let i = 0; i < nums.length; i += 1) {
    for (let j = i + 1; j < nums.length; j += 1) {
      if (nums[i] + nums[j] === target) return [i, j];
    }
  }
  return [];
}
function groupBy(items, keyFn) {
  const out = {};
  for (const item of items) {
    const key = keyFn(item);
    if (!out[key]) out[key] = [];
    out[key].push(item);
  }
  return out;
}
module.exports = { twoSum, groupBy };
'''
    return {'language': language, 'entry': ex['entry'], 'title': ex['title'], 'question': ex['prompt'],
            'files': ex['files'], 'alternative_files': alt, 'solution': ex['solution'],
            'tests': ex['tests'], 'complexity': 'reference implementation'}
