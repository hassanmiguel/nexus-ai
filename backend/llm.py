"""Low-level inference transport.

Nothing in this module imports higher-level modules, so it can be used safely by
memory, repositories and providers without circular imports.

Two embedding spaces are supported:

* ``ollama`` - the configured Ollama embedding model (e.g. nomic-embed-text).
* ``local``  - a deterministic feature-hashing embedder that works with zero
  models installed. It is intentionally simple, but it gives NEXUS Core useful
  semantic-ish retrieval while completely offline.
"""
import hashlib
import json
import math
import re
import time

import httpx

from .config import OLLAMA_URL
from .database import setting

_ollama_down_until = 0.0


def ollama_base() -> str:
    return (setting('ollama_url', OLLAMA_URL) or OLLAMA_URL).rstrip('/')


def _is_ollama_reachable() -> bool:
    return time.time() >= _ollama_down_until


def _mark_ollama_down(seconds=20):
    global _ollama_down_until
    _ollama_down_until = time.time() + seconds


def _mark_ollama_up():
    global _ollama_down_until
    _ollama_down_until = 0.0


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def local_embed(text: str, dim: int = 384):
    """Deterministic hashing embedder (word unigrams + bigrams, signed hashing).

    Uses L2 normalisation and sublinear term frequency. It is not a transformer,
    but it is fast, dependency-free and stable across restarts.
    """
    text = (text or '').lower()
    tokens = re.findall(r'[a-z0-9_]{2,}', text)
    vec = [0.0] * dim
    if not tokens:
        return vec
    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    for a, b in zip(tokens, tokens[1:]):
        key = a + '_' + b
        counts[key] = counts.get(key, 0) + 1
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
        value = int.from_bytes(digest, 'little')
        idx = value % dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        vec[idx] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


async def ollama_embed(text: str, timeout: float = 6.0):
    if not _is_ollama_reachable():
        raise RuntimeError('Ollama temporarily marked offline')
    model = setting('embedding_model', 'nomic-embed-text')
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f'{ollama_base()}/api/embeddings',
                             json={'model': model, 'prompt': (text or '')[:6000]})
            r.raise_for_status()
            vector = r.json().get('embedding')
            if not vector:
                raise RuntimeError('Ollama returned no embedding vector')
            _mark_ollama_up()
            return vector
    except Exception:
        _mark_ollama_down()
        raise


async def embed_both(text: str):
    """Return {kind: vector}. Local is always available; Ollama is best-effort."""
    result = {'local': local_embed(text)}
    mode = (setting('embedding_provider', 'auto') or 'auto').lower()
    if mode in ('auto', 'ollama'):
        try:
            result['ollama'] = await ollama_embed(text)
        except Exception:
            pass
    return result


async def embed(text: str):
    """Legacy single-vector helper. Returns the best available vector."""
    vectors = await embed_both(text)
    if 'ollama' in vectors and (setting('embedding_provider', 'auto') or 'auto').lower() == 'ollama':
        return vectors['ollama']
    return vectors.get('ollama') or vectors['local']


async def embed_local(text: str):
    return local_embed(text)


# --------------------------------------------------------------------------- #
# Ollama transport
# --------------------------------------------------------------------------- #
def _ollama_options():
    opts = {
        'num_ctx': int(setting('num_ctx', '8192') or 8192),
        'num_predict': int(setting('num_predict', '900') or 900),
    }
    threads = int(setting('num_thread', '0') or 0)
    if threads > 0:
        opts['num_thread'] = threads
    return opts


async def ollama_status():
    if not _is_ollama_reachable():
        return {'online': False, 'models': [], 'error': 'Ollama marked offline after a failed request'}
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(f'{ollama_base()}/api/tags')
            r.raise_for_status()
            _mark_ollama_up()
            return {'online': True, 'models': [m['name'] for m in r.json().get('models', [])]}
    except Exception as e:
        _mark_ollama_down()
        return {'online': False, 'models': [], 'error': str(e)}


def _ollama_payload(messages, model=None, stream=False, options=None, temperature=None):
    opts = _ollama_options()
    if options:
        opts.update({k: v for k, v in options.items() if v is not None})
    if temperature is not None:
        opts['temperature'] = temperature
    return {
        'model': model or setting('model', 'qwen2.5:3b'),
        'stream': stream,
        'keep_alive': setting('keep_alive', '10m'),
        'options': opts,
        'messages': messages,
    }


async def ollama_chat(messages, model=None, options=None, temperature=None):
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f'{ollama_base()}/api/chat',
                         json=_ollama_payload(messages, model, False, options, temperature))
        r.raise_for_status()
        _mark_ollama_up()
        data = r.json()
        return data.get('message', {}).get('content', '')


async def ollama_chat_stream(messages, model=None, options=None, temperature=None):
    payload = _ollama_payload(messages, model, True, options, temperature)
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream('POST', f'{ollama_base()}/api/chat', json=payload) as r:
            r.raise_for_status()
            _mark_ollama_up()
            async for line in r.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = data.get('message', {}).get('content', '')
                if chunk:
                    yield chunk
                if data.get('done'):
                    break


async def pull_model(model):
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream('POST', f'{ollama_base()}/api/pull', json={'name': model}) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    yield line


# Backwards-compatible lazy import. Higher-level code should import from
# backend.providers directly, but old modules keep working.
async def generate(prompt, system='You are NEXUS AI, a careful local research agent.'):
    from .providers import generate as provider_generate
    return await provider_generate(prompt, system=system)
