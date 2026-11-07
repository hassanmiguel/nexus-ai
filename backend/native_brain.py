"""NEXUS Core — the dependency-free reasoning brain.

This is the "switch to the AI itself" mode. It does not need Ollama or any
generative model: it answers from learned repository chunks, knowledge records,
experience memories and permitted tool observations using extractive synthesis.

It is deliberately honest: when the local memory does not contain an answer it
says so and offers concrete next steps instead of hallucinating. It also handles
the prompts used by the autonomous research pipeline (planning, page analysis,
claim auditing, improvement proposals) so the whole application still works
offline.
"""
import json
import re

from .database import read_bool, setting
from .memory import retrieve, retrieve_experiences
from .textutil import (best_sentences, clip, jaccard, keyword_set, keywords,
                       language_from_path, lexical_score, split_sentences, summarize_text)

CODE_HINTS = {
    'code', 'repo', 'repository', 'file', 'function', 'class', 'bug', 'error', 'api',
    'component', 'module', 'import', 'architecture', 'endpoint', 'database', 'schema',
    'test', 'build', 'deploy', 'typescript', 'javascript', 'python', 'react', 'next',
}


def _permission_summary():
    enabled = []
    for key, label in (('permission_internet', 'internet'), ('permission_pc_read', 'PC read'),
                       ('permission_pc_write', 'PC write'), ('permission_shell', 'shell')):
        if read_bool(key):
            enabled.append(label)
    return ', '.join(enabled) if enabled else 'none (locked down)'


def capabilities_text():
    return (
        '**NEXUS CORE // local capability map**\n\n'
        '- **Repo learning:** paste a GitHub URL or local folder in Repo Lab; NEXUS indexes files, symbols and line-addressed chunks into SQLite.\n'
        '- **Offline answers:** this mode retrieves from what NEXUS has learned (no Ollama, no API key).\n'
        '- **Generative providers:** switch to Ollama, llama.cpp/GGUF or any OpenAI-compatible server from the top bar.\n'
        '- **Research agent:** plan → crawl → extract → verify → store → evaluate.\n'
        '- **Tools:** web search/fetch, file read/write, glob search, shell commands — each gated by explicit permissions.\n'
        '- **Memory:** knowledge, experience lessons, task plans, claims, evaluations and proposals survive restarts.\n\n'
        f'Current permissions: `{_permission_summary()}`.\n'
        f"Provider: `{setting('provider', 'nexus')}` · Embeddings: `{setting('embedding_provider', 'auto')}`"
    )


async def _gather(question):
    knowledge = []
    experiences = []
    chunks = []
    try:
        knowledge = await retrieve(question, 8)
    except Exception:
        pass
    try:
        experiences = await retrieve_experiences(question, 3)
    except Exception:
        pass
    try:
        from .repos import search_chunks
        chunks = await search_chunks(question, limit=6)
    except Exception:
        pass
    return knowledge, experiences, chunks


def _bullet_for(row, question):
    content = row.get('content') or ''
    picks = best_sentences(question, content, 2)
    text = ' '.join(picks) if picks else clip(content, 320)
    source = row.get('source_url') or ''
    topic = row.get('topic') or 'memory'
    verification = row.get('verification_status') or 'unverified'
    cite = f' — `{source}`' if source else ''
    return f'- **{clip(row.get("title") or topic, 110)}** [{verification}]: {clip(text, 520)}{cite}'


def _code_block(chunk):
    lang = language_from_path(chunk.get('path', ''))
    lines = (chunk.get('content') or '').splitlines()
    snippet = '\n'.join(lines[:22])
    if len(lines) > 22:
        snippet += '\n…'
    return f"`{chunk.get('repo_name', 'repo')}/{chunk.get('path')}:{chunk.get('start_line')}-{chunk.get('end_line')}`\n```{lang}\n{snippet}\n```"


async def answer(question, extra_context='', history=None):
    question = (question or '').strip()
    low = question.lower()
    if not question:
        return capabilities_text()
    if re.match(r'^(hi|hey|hello|yo|sup|good (morning|evening|afternoon))\b', low) or low in {'help', '?'}:
        return capabilities_text()
    if any(p in low for p in ('what can you do', 'capabilities', 'how do you work', 'who are you', 'what are you')):
        return capabilities_text()

    knowledge, experiences, chunks = await _gather(question)
    want_code = any(w in keyword_set(question) for w in CODE_HINTS) or bool(chunks)
    sections = []

    if chunks:
        lead = (
            f'I found **{len(chunks)} relevant code location(s)** in the repositories you taught me. '
            'This is extractive evidence from the indexed files, not a guess.'
        )
        if want_code:
            sections.append('### Code evidence\n' + lead + '\n\n' + '\n\n'.join(_code_block(c) for c in chunks[:4]))
        else:
            refs = '\n'.join(
                f"- `{c.get('repo_name', 'repo')}/{c.get('path')}:{c.get('start_line')}-{c.get('end_line')}` "
                f"(match {c.get('score')})" for c in chunks[:5])
            sections.append('### Repository references\n' + lead + '\n\n' + refs)

    if knowledge:
        sections.append('### Learned knowledge\n' + '\n'.join(_bullet_for(k, question) for k in knowledge[:6]))

    if experiences:
        lessons = '\n'.join(f"- **{e.get('kind', 'lesson')}**: {clip(e.get('content', ''), 360)}" for e in experiences[:3])
        sections.append('### Experience memory\n' + lessons)

    if extra_context:
        sections.append('### Live tool observations\n' + clip(extra_context, 6000))

    if not sections:
        sections.append(
            '### No matching learned memory\n'
            "I don't have enough stored evidence to answer that reliably in NEXUS Core mode. "
            "I'd rather tell you than invent an answer.\n\n"
            '**Useful next moves**\n'
            '1. **Repo Lab** → paste a GitHub URL or local folder and press *Learn repository*.\n'
            '2. **Overview** → queue a research objective; the agent will crawl and verify public sources.\n'
            '3. Switch the provider to **Ollama**, **llama.cpp** or **OpenAI-compatible** for free-form generation.\n'
            '4. Grant **Internet** or **PC read** in Permissions and ask me to fetch a URL or read a file.')

    confidence = 'low'
    if chunks and knowledge:
        confidence = 'high'
    elif chunks or len(knowledge) >= 2:
        confidence = 'medium'
    notes = [
        f'- Engine: **NEXUS Core** (offline extractive reasoning; no LLM).',
        f'- Retrieved: {len(knowledge)} knowledge records, {len(chunks)} code chunks, {len(experiences)} lessons.',
        f'- Permissions: {_permission_summary()}.',
    ]
    if confidence != 'high':
        notes.append('- For multi-step reasoning or writing, switch to a generative provider; Core is best at recalling what it learned.')
    sections.append(f'### Confidence\n**{confidence.upper()}**\n' + '\n'.join(notes))
    return '\n\n'.join(sections)


# --------------------------------------------------------------------------- #
# Research-pipeline prompt handlers
# --------------------------------------------------------------------------- #
def _extract_after(prompt, marker, stop=None):
    idx = prompt.find(marker)
    if idx < 0:
        return ''
    text = prompt[idx + len(marker):]
    if stop:
        end = text.find(stop)
        if end >= 0:
            text = text[:end]
    return text.strip()


def _analyze_webpage(prompt):
    question = _extract_after(prompt, 'research question:', '\n') or 'the research objective'
    title = _extract_after(prompt, 'TITLE:', '\n')
    url = _extract_after(prompt, 'URL:', '\n')
    text = _extract_after(prompt, 'TEXT:')
    picks = best_sentences(question, text, 8)
    if not picks:
        picks = best_sentences(question, text, 4)
    lines = [
        f'Extractive analysis of “{clip(title, 140)}” for: {clip(question, 220)}',
        f'Source: {url}',
        '',
        'Directly supported statements:',
    ]
    lines += [f'- {clip(s, 420)}' for s in picks] or ['- No clearly relevant factual sentence was found in the readable text.']
    lines.append('')
    lines.append('Limits: this offline extractor quotes the page; it does not independently validate the page, resolve dates, or detect subtle contradictions.')
    return '\n'.join(lines)


def _make_plan(prompt):
    objective = _extract_after(prompt, 'Create a research plan for this objective:', '\nMode:') or _extract_after(prompt, 'objective:', '\n')
    objective = clip(objective or 'the objective', 240)
    return '\n'.join([
        f'What exactly is {objective}, and which problem does it solve?',
        f'What are the main components, approaches and competing definitions of {objective}?',
        f'What concrete evidence supports the central claims about {objective}?',
        f'What limitations, failure modes, risks and unresolved questions apply to {objective}?',
        f'What recent developments or credible alternatives to {objective} should be compared?',
    ])


def _audit_claims(prompt):
    min_sources = max(2, int(setting('verification_sources', '2') or 2))
    raw_sources = re.split(r'\nSOURCE\s+\d+\s*\|', prompt)
    sources = []
    for block in raw_sources[1:]:
        m = re.search(r'domain=([^\s|]+)', block)
        domain = m.group(1).strip() if m else f'source{len(sources) + 1}'
        body = block.split('\n', 2)
        text = body[2] if len(body) > 2 else block
        sources.append((domain, text))
    clusters = []
    for domain, text in sources:
        for sentence in split_sentences(text, 45, 360):
            keys = keyword_set(sentence)
            if len(keys) < 4:
                continue
            if re.search(r'\b(cookie|subscribe|privacy policy|all rights reserved)\b', sentence, re.I):
                continue
            match = None
            for cluster in clusters:
                if jaccard(sentence, cluster['claim']) >= 0.42:
                    match = cluster
                    break
            if match:
                if domain not in match['domains']:
                    match['domains'].append(domain)
                if lexical_score(sentence, match['claim']) > lexical_score(match['claim'], match['claim']):
                    pass
            else:
                clusters.append({'claim': sentence, 'domains': [domain], 'score': len(keys)})
    clusters.sort(key=lambda c: (len(c['domains']), c['score']), reverse=True)
    claims = []
    for cluster in clusters[:12]:
        domains = cluster['domains']
        status = 'corroborated' if len(domains) >= min_sources else 'single-source'
        claims.append({
            'claim': clip(cluster['claim'], 500),
            'supporting_domains': domains,
            'contradicting_domains': [],
            'status': status,
            'confidence': 0.72 if status == 'corroborated' else 0.45,
        })
    return json.dumps(claims, ensure_ascii=False)


def _propose_objective(prompt):
    block = _extract_after(prompt, 'Existing knowledge:')
    entries = [line.strip() for line in block.splitlines() if line.strip() and ':' in line]
    counts = {}
    for entry in entries[:40]:
        topic = entry.split(':', 1)[0].strip()
        if topic:
            counts[topic] = counts.get(topic, 0) + 1
    topics = [t for t, _ in sorted(counts.items(), key=lambda x: (x[1], x[0]))]
    topic = topics[0] if topics else 'local AI research memory'
    templates = [
        f'Compare recent approaches and limitations in {topic}',
        f'Identify unresolved gaps and failure modes in {topic}',
        f'Evaluate practical trade-offs and evidence quality for {topic}',
    ]
    idx = len(entries) % len(templates)
    return templates[idx]


def _propose_improvement(prompt):
    return json.dumps({
        'title': 'Improve source-diversity checks before corroboration',
        'category': 'prompt',
        'description': (
            'Require at least two independent registered domains for every corroborated claim, '
            'explicitly discard syndicated copies, and record the exact supporting sentences so '
            'the audit is reproducible. This is a review-only proposal; nothing is deployed automatically.'
        ),
        'patch': '',
    }, ensure_ascii=False)


async def handle_prompt(prompt):
    """Entry point for the autonomous research pipeline when provider is nexus."""
    prompt = prompt or ''
    low = prompt.lower()
    if 'analyze this untrusted public webpage' in low or 'untrusted public webpage' in low:
        return _analyze_webpage(prompt)
    if 'create a research plan' in low:
        return _make_plan(prompt)
    if 'conservative evidence auditor' in low:
        return _audit_claims(prompt)
    if 'create one novel' in low:
        return _propose_objective(prompt)
    if 'safe, measurable improvement' in low:
        return _propose_improvement(prompt)
    return await answer(prompt)
