"""Small dependency-free text helpers shared by the offline brain, repo indexer
and lexical retrieval."""
import math
import re
from collections import Counter

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'else', 'for', 'of', 'to',
    'in', 'on', 'at', 'by', 'with', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
    'been', 'being', 'this', 'that', 'these', 'those', 'it', 'its', 'can', 'could',
    'should', 'would', 'will', 'may', 'might', 'do', 'does', 'did', 'have', 'has',
    'had', 'not', 'no', 'so', 'than', 'too', 'very', 'we', 'you', 'i', 'they',
    'he', 'she', 'them', 'our', 'your', 'their', 'what', 'which', 'who', 'how',
    'why', 'when', 'where', 'about', 'into', 'over', 'under', 'between', 'also',
    'just', 'more', 'most', 'some', 'any', 'all', 'each', 'other', 'such', 'only',
    'own', 'same', 'up', 'down', 'out', 'off', 'again', 'there', 'here', 'one',
    'two', 'three', 'via', 'per', 'using', 'use', 'used', 'make', 'makes', 'made',
}

CODE_WORDS = {
    'function', 'class', 'def', 'const', 'let', 'var', 'return', 'import', 'export',
    'async', 'await', 'struct', 'interface', 'enum', 'public', 'private', 'static',
    'void', 'string', 'number', 'boolean', 'true', 'false', 'null', 'none', 'self',
    'this', 'new', 'try', 'catch', 'except', 'finally', 'while', 'switch', 'case',
}


def words(text):
    return re.findall(r'[A-Za-z0-9_]{2,}', (text or '').lower())


def keywords(text, limit=14):
    counts = Counter(w for w in words(text) if w not in STOPWORDS and len(w) > 2)
    return [w for w, _ in counts.most_common(limit)]


def keyword_set(text):
    return {w for w in words(text) if w not in STOPWORDS and len(w) > 2}


def jaccard(a, b):
    sa, sb = keyword_set(a), keyword_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def lexical_score(query, text):
    """Log-scaled overlap normalised by document length. Cheap BM25-ish score."""
    q = keyword_set(query)
    ws = [w for w in words(text) if w not in STOPWORDS]
    if not q or not ws:
        return 0.0
    counts = Counter(ws)
    raw = sum(math.log1p(counts[w]) for w in q if w in counts) / math.sqrt(len(ws))
    # reward exact phrase matches
    phrase = ' '.join(w for w in words(query) if w not in STOPWORDS)
    if len(phrase) > 6 and phrase in (text or '').lower():
        raw += 0.35
    return raw


def split_sentences(text, min_len=35, max_len=420):
    text = re.sub(r'\s+', ' ', text or '')
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(\[])', text)
    out = []
    for sentence in raw:
        sentence = sentence.strip()
        if min_len <= len(sentence) <= max_len:
            out.append(sentence)
        elif len(sentence) > max_len:
            for i in range(0, len(sentence), max_len):
                piece = sentence[i:i + max_len].strip()
                if len(piece) >= min_len:
                    out.append(piece)
    return out


def best_sentences(query, text, limit=8):
    sentences = split_sentences(text)
    if not sentences:
        return []
    scored = []
    for idx, sentence in enumerate(sentences):
        score = lexical_score(query, sentence)
        # prefer earlier + information-dense lines slightly
        score += 0.03 if idx < 6 else 0
        scored.append((score, idx, sentence))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [s for s in scored[:limit] if s[0] > 0]
    if not chosen:
        chosen = scored[:min(limit, 4)]
    chosen.sort(key=lambda x: x[1])
    return [sentence for _, _, sentence in chosen]


def summarize_text(text, limit=6):
    sentences = split_sentences(text)
    if not sentences:
        compact = re.sub(r'\s+', ' ', text or '').strip()
        return compact[:900]
    if len(sentences) <= limit:
        return ' '.join(sentences)
    return ' '.join(sentences[:limit])


def clip(text, size=1200):
    text = (text or '').strip()
    return text if len(text) <= size else text[:size].rstrip() + '…'


def language_from_path(path):
    ext = (path.rsplit('.', 1)[-1] if '.' in path else '').lower()
    return {
        'py': 'python', 'pyw': 'python', 'js': 'javascript', 'jsx': 'javascript',
        'mjs': 'javascript', 'cjs': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
        'java': 'java', 'cs': 'csharp', 'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp',
        'c': 'c', 'h': 'c', 'hpp': 'cpp', 'go': 'go', 'rs': 'rust', 'rb': 'ruby',
        'php': 'php', 'swift': 'swift', 'kt': 'kotlin', 'kts': 'kotlin', 'scala': 'scala',
        'sh': 'bash', 'ps1': 'powershell', 'bat': 'batch', 'cmd': 'batch',
        'html': 'html', 'htm': 'html', 'css': 'css', 'scss': 'scss', 'sass': 'sass',
        'less': 'less', 'vue': 'vue', 'svelte': 'svelte', 'sql': 'sql', 'json': 'json',
        'yaml': 'yaml', 'yml': 'yaml', 'toml': 'toml', 'ini': 'ini', 'xml': 'xml',
        'md': 'markdown', 'mdx': 'markdown', 'rst': 'rst', 'txt': 'text',
        'dockerfile': 'dockerfile', 'env': 'dotenv', 'gitignore': 'gitignore',
        'lua': 'lua', 'dart': 'dart', 'r': 'r', 'ex': 'elixir', 'exs': 'elixir',
        'zig': 'zig', 'nim': 'nim', 'sol': 'solidity', 'tf': 'terraform',
    }.get(ext, 'text')


def extract_symbols(path, content):
    lang = language_from_path(path)
    symbols = []
    patterns = {
        'python': r'^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)|^\s*class\s+([A-Za-z_]\w*)',
        'javascript': r'^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)|^\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(',
        'typescript': r'^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)',
        'go': r'^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)|^\s*type\s+([A-Za-z_]\w*)\s+struct',
        'rust': r'^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)|^\s*(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)',
        'java': r'^\s*(?:public|private|protected|static|final|abstract|synchronized|\s)*\s*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)|^\s*(?:public|private|protected|static|final|abstract|synchronized|\s)+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(',
        'csharp': r'^\s*(?:public|private|protected|internal|static|sealed|abstract|partial|\s)*\s*(?:class|interface|struct|enum|record)\s+([A-Za-z_]\w*)|^\s*(?:public|private|protected|internal|static|async|\s)+[\w<>\[\],]+\s+([A-Za-z_]\w*)\s*\(',
    }
    pattern = patterns.get(lang)
    if pattern:
        for m in re.finditer(pattern, content, re.M):
            name = next((g for g in m.groups() if g), None)
            if name and name not in symbols:
                symbols.append(name)
    return symbols[:80]


def parse_version_files(files):
    """Extract obvious dependencies from common manifests. ``files`` is a dict
    of path -> content."""
    deps = set()
    for path, content in files.items():
        low = path.lower()
        try:
            if low.endswith('package.json'):
                import json
                data = json.loads(content)
                for key in ('dependencies', 'devDependencies', 'peerDependencies'):
                    deps.update((data.get(key) or {}).keys())
            elif low.endswith('requirements.txt'):
                for line in content.splitlines():
                    line = re.split(r'[=<>!;\[ ]', line.strip())[0]
                    if line and not line.startswith('#'):
                        deps.add(line)
            elif low.endswith('pyproject.toml'):
                for m in re.finditer(r'^\s*([A-Za-z0-9_.\-]+)\s*=\s*["\{]', content, re.M):
                    deps.add(m.group(1))
                for m in re.finditer(r'["\']([A-Za-z0-9_.\-]+)\s*(?:[<>=!~]|["\'])', content):
                    deps.add(m.group(1))
            elif low.endswith('cargo.toml'):
                section = False
                for line in content.splitlines():
                    if line.strip().startswith('['):
                        section = 'dependencies' in line
                    elif section and '=' in line:
                        deps.add(line.split('=')[0].strip())
            elif low.endswith('go.mod'):
                for m in re.finditer(r'^\s*require\s+([^\s]+)', content, re.M):
                    deps.add(m.group(1))
                for m in re.finditer(r'^\s*([^\s]+)\s+v[0-9]', content, re.M):
                    deps.add(m.group(1))
        except Exception:
            continue
    return sorted(d for d in deps if d and len(d) < 80)[:80]
