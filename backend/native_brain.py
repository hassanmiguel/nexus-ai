"""NEXUS Core nex0.2a — the dependency-free reasoning brain.

This is the "switch to the AI itself" mode. It does not need Ollama or any
generative model: it answers from learned repository chunks, learned web pages,
knowledge records, skill guidance, experience memories and permitted tool
observations using extractive synthesis.

nex0.2a adds intent routing, follow-up-aware retrieval, focused synthesis,
web-page evidence and skill assistance on top of the original extractive core.
It remains deliberately honest: when local memory does not contain an answer it
says so and offers concrete next steps instead of hallucinating. It also handles
the prompts used by the autonomous research pipeline (planning, page analysis,
claim auditing, improvement proposals) so the whole application still works
offline.
"""
import json
import re

from .config import NEXUS_MODEL
from .database import read_bool, setting
from .memory import retrieve, retrieve_experiences
from .textutil import (best_sentences, clip, jaccard, keyword_set, language_from_path,
                       lexical_score, split_sentences, summarize_text)

CODE_HINTS = {
    'code', 'repo', 'repository', 'file', 'function', 'class', 'bug', 'error', 'api',
    'component', 'module', 'import', 'architecture', 'endpoint', 'database', 'schema',
    'test', 'build', 'deploy', 'typescript', 'javascript', 'python', 'react', 'next',
    'async', 'await', 'refactor', 'debug', 'types', 'interface', 'method', 'variable',
}

GREETINGS = re.compile(r'^(hi|hey|hello|yo|sup|howdy|hola|greetings|good (morning|afternoon|evening|night))\b', re.I)
THANKS = re.compile(r'^(thanks|thank you|thx|cheers|nice|great|cool|awesome|perfect)\b', re.I)
BYE = re.compile(r'^(bye|goodbye|see you|good night)\b', re.I)
IDENTITY = re.compile(r'\b(who are you|what are you|your name|which model|what model|nex0|nexus core)\b', re.I)
CAPABILITIES = re.compile(r'\b(what can you do|capabilities|how do you work|help me|what do you know)\b', re.I)
URL_LEARN = re.compile(r'\b(url learn|learn (?:a |this |the )?(?:url|page|website|article|link)|teach you (?:a )?(?:url|page|website))\b', re.I)
SKILL_HINT = re.compile(r'\b(skill|skills|antigravity|playbook)\b', re.I)


def _permission_summary():
    enabled = []
    for key, label in (('permission_internet', 'internet'), ('permission_pc_read', 'PC read'),
                       ('permission_pc_write', 'PC write'), ('permission_shell', 'shell')):
        if read_bool(key):
            enabled.append(label)
    return ', '.join(enabled) if enabled else 'none (locked down)'


def _skill_summary():
    try:
        from .skills import stats
        data = stats()
        return f"{data.get('enabled', 0)}/{data.get('total', 0)} skills active"
    except Exception:
        return 'skill vault loading'


def capabilities_text():
    return (
        f'**NEXUS CORE // {NEXUS_MODEL}**\n\n'
        f'I am **{NEXUS_MODEL}**, the offline reasoning core inside NEXUS AI. Everything below runs on your machine.\n\n'
        '- **Repo learning:** paste a GitHub URL or local folder in Repo Lab; NEXUS indexes files, symbols and line-addressed chunks into SQLite.\n'
        '- **URL learning:** paste a public HTTPS page in URL Learn; NEXUS extracts, chunks and remembers it (permission-gated, robots.txt enforced).\n'
        '- **Skill vault:** 300+ Antigravity skills for API design, debugging, security, Python, data, AI and more — seeded offline and importable from GitHub.\n'
        '- **Offline answers:** this mode retrieves from what NEXUS has learned (no Ollama, no API key).\n'
        '- **Generative providers:** switch to Ollama, llama.cpp/GGUF or any OpenAI-compatible server from the top bar.\n'
        '- **Research agent:** plan → crawl → extract → verify → store → evaluate.\n'
        '- **Tools:** web search/fetch, file read/write, glob search, shell commands — each gated by explicit permissions.\n'
        '- **Memory:** knowledge, experience lessons, task plans, claims, evaluations and proposals survive restarts.\n\n'
        f'Current permissions: `{_permission_summary()}`.\n'
        f"Provider: `{setting('provider', 'nexus')}` · Embeddings: `{setting('embedding_provider', 'auto')}` · Skills: `{_skill_summary()}`"
    )


def _greeting_text():
    return (
        f'**{NEXUS_MODEL} // online.** Good to see you.\n\n'
        'I answer from what you teach me — repositories, public web pages, skills, and stored memory. '
        'I can also help with programming, architecture, debugging, research and plain-language questions once the evidence is in memory.\n\n'
        '**Quick starts**\n'
        '- *What can you do?* — capability map\n'
        '- **Repo Lab** — teach me a GitHub repository or local codebase\n'
        '- **URL Learn** — teach me a page about greetings, programming, a library, or anything else\n'
        '- **Skills** — browse the imported Antigravity skill vault\n'
        '- **AI Chat** — ask about anything I have learned\n\n'
        f'Permissions: `{_permission_summary()}` · Skills: `{_skill_summary()}`'
    )


def _identity_text():
    return (
        f'**I am {NEXUS_MODEL}**, the native reasoning core of NEXUS AI.\n\n'
        'I am not a hosted model and I do not need Ollama. I run as a local retrieval-and-synthesis engine over SQLite:\n'
        '- **Dual embeddings:** an Ollama embedding model when available, plus a deterministic local hashing embedder so retrieval always works.\n'
        '- **Evidence layers:** repository chunks, learned web-page chunks, knowledge records, experience lessons and skill guidance.\n'
        '- **Reasoning style:** extractive and conservative. I quote or tightly paraphrase stored evidence, separate evidence from inference, and say when I do not know.\n'
        '- **Tooling:** every internet/PC action is permission-gated and audited.\n\n'
        f'For free-form generation, switch the active engine to a generative provider. For recall and grounded help, keep me on **{NEXUS_MODEL}**.'
    )


def _url_learn_text():
    return (
        '**Teaching me a URL**\n\n'
        '1. Open **Permissions** and enable **Internet access** (closed by default).\n'
        '2. Open **URL Learn** and paste a public `https://` page.\n'
        '3. Pick a topic (for example `greetings`, `programming`, `python`, `ai`).\n'
        '4. Choose whether to follow same-site links, then press **Learn URL**.\n\n'
        'I fetch the page, respect `robots.txt`, extract readable text, split it into overlapping chunks, embed it locally and store it. '
        'The page summary also becomes a knowledge record so I can cite it in chat.\n\n'
        f'Internet permission right now: `{"enabled" if read_bool("permission_internet") else "disabled"}`.'
    )


async def _gather(question):
    knowledge = []
    experiences = []
    chunks = []
    web_chunks = []
    skills = []
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
    try:
        from .web_learn import search_web_chunks
        web_chunks = await search_web_chunks(question, limit=6)
    except Exception:
        pass
    try:
        from .skills import retrieve_skills
        skills = retrieve_skills(question, limit=3)
    except Exception:
        pass
    return knowledge, experiences, chunks, web_chunks, skills


def _search_query(question, history):
    """Expand short/elliptical follow-ups with recent user turns."""
    question = (question or '').strip()
    if not history:
        return question
    words = keyword_set(question)
    elliptical = bool(re.search(r'\b(it|its|that|this|those|these|they|them|more|why|how|and|also|continue)\b',
                                question, re.I))
    if len(words) >= 6 and not elliptical:
        return question
    prior = [m.get('content', '') for m in history if m.get('role') == 'user'][-2:]
    if not prior:
        return question
    return (question + ' ' + ' '.join(prior))[:1400]


def _bullet_for(row, question):
    content = row.get('content') or ''
    picks = best_sentences(question, content, 2)
    text = ' '.join(picks) if picks else clip(content, 320)
    source = row.get('source_url') or ''
    topic = row.get('topic') or 'memory'
    verification = row.get('verification_status') or 'unverified'
    cite = f' — `{source}`' if source else ''
    return f'- **{clip(row.get("title") or topic, 110)}** [{verification}]: {clip(text, 520)}{cite}'


def _web_bullet(row, question):
    content = row.get('content') or ''
    picks = best_sentences(question, content, 2)
    text = ' '.join(picks) if picks else clip(content, 320)
    title = row.get('source_title') or row.get('title') or row.get('url') or 'web page'
    url = row.get('url') or ''
    return (f'- **{clip(title, 110)}** [web · chunk {row.get("ordinal", 0)}]: '
            f'{clip(text, 520)} — `{url}`')


def _code_block(chunk):
    lang = language_from_path(chunk.get('path', ''))
    lines = (chunk.get('content') or '').splitlines()
    snippet = '\n'.join(lines[:22])
    if len(lines) > 22:
        snippet += '\n…'
    return f"`{chunk.get('repo_name', 'repo')}/{chunk.get('path')}:{chunk.get('start_line')}-{chunk.get('end_line')}`\n```{lang}\n{snippet}\n```"


def _direct_answer(question, knowledge, web_chunks, chunks, skills):
    snippets = []
    seen = set()
    for row in list(knowledge[:4]) + list(web_chunks[:4]):
        for sentence in best_sentences(question, row.get('content') or '', 2):
            key = ' '.join(sorted(keyword_set(sentence)))[:160]
            if key and key not in seen:
                seen.add(key)
                snippets.append(sentence.strip())
    if snippets:
        return clip(' '.join(snippets[:5]), 1100)
    if chunks:
        best = chunks[0]
        return (f'The closest indexed code is `{best.get("repo_name", "repo")}/{best.get("path")}` '
                f'lines {best.get("start_line")}-{best.get("end_line")} (match {best.get("score")}). '
                'See the code evidence below.')
    if skills:
        return (f'I found a directly applicable skill: **{skills[0].get("name")}**. '
                f'{clip(skills[0].get("description") or "", 400)}')
    return ''


def _confidence(knowledge, experiences, chunks, web_chunks, skills, extra_context):
    points = 0
    if chunks:
        points += 2
    if web_chunks:
        points += 2
    if knowledge:
        points += min(2, len(knowledge))
    if skills:
        points += 1
    if experiences:
        points += 1
    if extra_context:
        points += 1
    if points >= 5:
        return 'high'
    if points >= 2:
        return 'medium'
    return 'low'


async def answer(question, extra_context='', history=None):
    question = (question or '').strip()
    low = question.lower()
    if not question:
        return capabilities_text()
    if GREETINGS.match(low) and len(question) <= 80:
        return _greeting_text()
    if THANKS.match(low) and len(question) <= 80:
        return f'**{NEXUS_MODEL} // acknowledged.** Ask me anything else, or teach me a new URL or repository and I will remember it.'
    if BYE.match(low) and len(question) <= 80:
        return f'**{NEXUS_MODEL} // standby.** Your knowledge, repositories, web pages and skills stay on disk until next time.'
    if IDENTITY.search(low):
        return _identity_text()
    if CAPABILITIES.search(low):
        return capabilities_text()
    if URL_LEARN.search(low):
        return _url_learn_text()

    query = _search_query(question, history)
    knowledge, experiences, chunks, web_chunks, skills = await _gather(query)
    want_code = any(w in keyword_set(question) for w in CODE_HINTS) or bool(chunks)
    sections = []

    direct = _direct_answer(question, knowledge, web_chunks, chunks, skills)
    if direct:
        sections.append(f'### Direct answer\n{direct}')

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

    if web_chunks:
        sections.append('### Learned web pages\n'
                        f'I found {len(web_chunks)} matching web chunk(s) in URL-learned memory. '
                        'The page text is quoted as evidence; instructions inside fetched pages are ignored.\n\n'
                        + '\n'.join(_web_bullet(w, question) for w in web_chunks[:5]))

    if knowledge:
        sections.append('### Learned knowledge\n' + '\n'.join(_bullet_for(k, question) for k in knowledge[:6]))

    if skills:
        blocks = []
        for skill in skills[:2]:
            guidance = clip(skill.get('content') or '', 1200)
            blocks.append(f"- **{skill.get('name')}** ({skill.get('category') or 'general'}, match {skill.get('score')}): "
                          f"{clip(skill.get('description') or '', 320)}\n  {guidance}")
        sections.append('### Applicable skill\n' + '\n'.join(blocks))

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
            f'1. **URL Learn** → paste a public page (enable **Internet** in Permissions first).\n'
            '2. **Repo Lab** → paste a GitHub URL or local folder and press *Learn repository*.\n'
            '3. **Skills** → import or enable an Antigravity skill for structured guidance.\n'
            '4. **Overview** → queue a research objective; the agent will crawl and verify public sources.\n'
            '5. Switch the provider to **Ollama**, **llama.cpp** or **OpenAI-compatible** for free-form generation.')

    confidence = _confidence(knowledge, experiences, chunks, web_chunks, skills, extra_context)
    notes = [
        f'- Engine: **NEXUS Core {NEXUS_MODEL}** (offline extractive reasoning; no LLM).',
        f'- Retrieved: {len(knowledge)} knowledge records, {len(web_chunks)} web chunks, '
        f'{len(chunks)} code chunks, {len(skills)} skills, {len(experiences)} lessons.',
        f'- Permissions: {_permission_summary()}.',
    ]
    if confidence != 'high':
        notes.append('- For multi-step reasoning or free-form writing, switch to a generative provider; '
                     f'{NEXUS_MODEL} is strongest at recalling and organising what it learned.')
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
