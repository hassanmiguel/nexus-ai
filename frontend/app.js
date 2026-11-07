/* NEXUS AI — frontend controller (vanilla, no build step) */
'use strict';

const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const titles = {
  overview: 'Command Center', repos: 'Repository Lab', chat: 'AI Chat',
  learning: 'Autonomous Research', knowledge: 'Knowledge Base', memory: 'Memory Manager',
  graph: 'Knowledge Graph', tasks: 'Task Manager', activity: 'Activity Stream',
  experiments: 'Experiments', analytics: 'Analytics', models: 'Providers',
  permissions: 'Permissions', settings: 'Settings'
};

const state = {
  status: null, providers: [], provider: 'nexus', repos: [],
  currentRepo: null, conversation: null, messages: [], repoContext: null,
  tools: [], permissions: null, sending: false, refreshing: false
};

const PAGE_LOADERS = {
  overview: () => { },
  repos: () => loadRepos(),
  chat: () => { loadConversations(); refreshRepoSelect(); updateChatEngine(); },
  learning: () => loadTasks(),
  knowledge: () => loadKnowledge(),
  memory: () => loadMemory(),
  graph: () => loadGraph(),
  tasks: () => loadTasks(),
  activity: () => loadEvents(),
  experiments: () => loadProposals(),
  analytics: () => loadAnalytics(),
  models: () => loadProviders(),
  permissions: () => loadPermissions(),
  settings: () => loadSettings()
};

/* ------------------------------------------------------------------ helpers */
function esc(value = '') {
  return String(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function clip(text = '', size = 600) {
  const s = String(text);
  return s.length <= size ? s : s.slice(0, size).trimEnd() + '…';
}
function num(value) { return Number(value || 0).toLocaleString(); }
function time(value) {
  if (!value) return '';
  try { return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return ''; }
}
function when(value) {
  if (!value) return '';
  try { return new Date(value).toLocaleString(); } catch { return ''; }
}
function debounce(fn, wait = 400) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
}
function toast(message, kind = '') {
  const stack = $('toastStack');
  if (!stack) return;
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(8px)'; }, 4200);
  setTimeout(() => el.remove(), 4700);
}
async function api(path, opts = {}) {
  const response = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' }, ...opts
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try { message = JSON.parse(text).detail || text; } catch { }
    throw new Error(String(message).slice(0, 500));
  }
  return response.json();
}
function download(name, text, type = 'text/plain') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/* --------------------------------------------------------------- markdown-lite */
function inlineMd(text) {
  let s = text;
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  return s;
}
function md(text) {
  const src = esc(text || '');
  const lines = src.split(/\r?\n/);
  const out = [];
  let inCode = false, code = [], list = null, para = [];
  const closeList = () => { if (list) { out.push('</' + list + '>'); list = null; } };
  const flush = () => { if (para.length) { out.push('<p>' + para.join('<br>') + '</p>'); para = []; } };
  for (const line of lines) {
    if (/^\s*```/.test(line)) {
      if (inCode) { out.push('<pre><code>' + code.join('\n') + '</code></pre>'); code = []; inCode = false; }
      else { flush(); closeList(); inCode = true; }
      continue;
    }
    if (inCode) { code.push(line); continue; }
    if (!line.trim()) { flush(); closeList(); continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
      flush(); closeList();
      const level = m[1].length;
      out.push('<h' + level + '>' + inlineMd(m[2]) + '</h' + level + '>');
      continue;
    }
    if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
      flush();
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul'; }
      out.push('<li>' + inlineMd(m[1]) + '</li>');
      continue;
    }
    if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flush();
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol'; }
      out.push('<li>' + inlineMd(m[1]) + '</li>');
      continue;
    }
    if ((m = line.match(/^&gt;\s?(.*)$/))) {
      flush(); closeList(); out.push('<blockquote>' + inlineMd(m[1]) + '</blockquote>');
      continue;
    }
    if (/^\s*([-*_])\1\1+\s*$/.test(line)) {
      flush(); closeList(); out.push('<hr>');
      continue;
    }
    para.push(inlineMd(line));
  }
  if (inCode && code.length) out.push('<pre><code>' + code.join('\n') + '</code></pre>');
  flush(); closeList();
  return out.join('\n') || '<p class="muted">(empty)</p>';
}

/* ------------------------------------------------------------------ routing */
function showPage(name) {
  if (!titles[name]) name = 'overview';
  $$('.page').forEach((el) => el.classList.toggle('active', el.id === name));
  $$('.nav').forEach((el) => el.classList.toggle('active', el.dataset.page === name));
  $('pageTitle').textContent = titles[name];
  $('crumb').textContent = name.toUpperCase();
  if (PAGE_LOADERS[name]) {
    Promise.resolve(PAGE_LOADERS[name]()).catch((e) => toast(e.message, 'error'));
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ------------------------------------------------------------------- status */
function renderProviderSwitch() {
  const box = $('providerSwitch');
  if (!box) return;
  if (!state.providers.length) { box.innerHTML = '<button class="active"><i></i>CORE</button>'; return; }
  box.innerHTML = state.providers.map((p) => (
    '<button data-provider="' + esc(p.id) + '" class="' + (p.selected ? 'active ' : '') + (p.online ? '' : 'offline') + '" title="' + esc(p.detail || p.tagline) + '">' +
    '<i></i>' + esc(p.label.toUpperCase()) + '</button>'
  )).join('');
}
function updateChatEngine() {
  const p = state.providers.find((x) => x.id === state.provider) || { label: 'NEXUS Core', kind: 'native', online: true, detail: '' };
  const name = String(p.label || 'NEXUS Core').toUpperCase();
  if ($('chatEngineName')) $('chatEngineName').textContent = name;
  if ($('chatEngineSub')) $('chatEngineSub').textContent = p.online ? (p.kind === 'native' ? 'offline reasoning' : 'local inference') : 'offline';
  if ($('chatEngineDot')) $('chatEngineDot').style.background = p.online ? '#39ff9a' : '#ff5470';
  if ($('chatProviderTag')) $('chatProviderTag').textContent = name;
  if ($('heroProvider')) $('heroProvider').textContent = name;
  if ($('sideProvider')) $('sideProvider').textContent = name;
  if ($('sideProviderState')) $('sideProviderState').textContent = p.online ? 'READY' : 'OFFLINE';
  if ($('chatSubtitle')) {
    $('chatSubtitle').textContent = p.kind === 'native'
      ? 'NEXUS Core answers from what it learned — no Ollama required. Switch engines in the top bar.'
      : name + ' is the active generative engine. NEXUS still retrieves learned memory and repository code as context.';
  }
}
function updateStatusUI(s) {
  state.status = s;
  $('mKnowledge').textContent = num(s.knowledge_count);
  $('mRepos').textContent = num(s.repo_count);
  $('mChunks').textContent = num(s.repo_chunks);
  $('mTasks').textContent = num(s.completed_tasks);
  $('mPages').textContent = num(s.pages_seen);
  const provider = s.provider || {};
  $('mModel').textContent = String(provider.label || '—').toUpperCase();
  $('modelSub').textContent = provider.online ? ((provider.models || [])[0] || 'ready') : 'offline';
  $('sideModel').textContent = String(provider.label || 'CHECKING').toUpperCase();
  $('sideVersion').textContent = 'v' + (s.version || '0.4.0');
  $('footVersion').textContent = 'v' + (s.version || '0.4.0');
  $('statusText').textContent = s.running ? (s.paused ? 'PAUSED' : 'AGENT ONLINE') : 'CORE READY';
  $('statusDot').style.background = s.running ? (s.paused ? '#ffc857' : '#39ff9a') : '#39ff9a';
  $('statusDot').style.boxShadow = '0 0 10px ' + (s.running ? (s.paused ? '#ffc857' : '#39ff9a') : '#39ff9a');
  $('orbState').textContent = s.running ? (s.paused ? 'PAUSED' : 'ACTIVE') : 'STANDBY';
  $('agentState').textContent = s.running ? (s.paused ? 'PAUSED' : 'RUNNING') : 'STANDBY';
  $('currentObjective').textContent = s.current_task || 'No active objective';
  $('learningMode').textContent = String(s.mode || 'assisted').toUpperCase() + ' MODE';
  $('objectiveMode').textContent = String(s.mode || 'assisted').toUpperCase();
  $('learningPulse').style.background = s.running && !s.paused ? '#39ff9a' : '#3b5a60';
  $('learningPulse').style.boxShadow = s.running && !s.paused ? '0 0 12px #39ff9a' : 'none';
  $('qualityScore').textContent = s.latest_quality_score != null ? Number(s.latest_quality_score).toFixed(1) + '/100' : '—';
  const hw = s.hardware || {};
  $('hwTitle').textContent = (hw.ram_gb ? hw.ram_gb + ' GB RAM' : 'Hardware') + (hw.cpu_threads ? ' · ' + hw.cpu_threads + ' threads' : '');
  $('hwText').textContent = hw.gpu || hw.recommendation || 'No hardware profile yet.';
  const perms = s.permissions || {};
  $('permMini').innerHTML = ['internet', 'pc_read', 'pc_write', 'shell'].map((key) => (
    '<span class="chip ' + (perms[key] ? 'on' : '') + '">' + key.toUpperCase() + '</span>'
  )).join('');
  state.providers = s.providers || state.providers;
  state.provider = (s.provider && s.provider.id) || state.provider;
  renderProviderSwitch();
  updateChatEngine();
}
async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    const s = await api('/status');
    updateStatusUI(s);
    try {
      const events = await api('/events');
      const html = events.slice(0, 6).map(eventHTML).join('') || '<div class="empty">No runtime events yet.</div>';
      if ($('liveEvents')) $('liveEvents').innerHTML = html;
    } catch { }
  } catch (e) {
    $('statusText').textContent = 'BACKEND OFFLINE';
    $('statusDot').style.background = '#ff5470';
    $('modelSub').textContent = 'start the local backend';
  } finally {
    state.refreshing = false;
  }
}

/* ------------------------------------------------------------------- events */
function eventHTML(e) {
  const kind = String(e.kind || 'event').toUpperCase();
  return '<div class="event"><i></i><div><b>' + esc(kind) + '</b><small>' + esc(e.message || '') + '</small></div><time>' + time(e.created_at) + '</time></div>';
}
async function loadEvents() {
  try {
    const events = await api('/events');
    $('allEvents').innerHTML = events.map(eventHTML).join('') || '<div class="empty">No recorded events.</div>';
    $('eventCountTag').textContent = events.length + ' EVENTS';
  } catch (e) { toast(e.message, 'error'); }
}

/* -------------------------------------------------------------------- agent */
async function agentAction(action) {
  try {
    await api('/agent/' + action, { method: 'POST' });
    toast('Agent ' + action + ' requested.');
    await refresh();
    if (action === 'start' || action === 'resume') toast('Research loop is ' + action + 'ed.', '');
  } catch (e) { toast(e.message, 'error'); }
}
async function submitObjective() {
  const value = $('objective').value.trim();
  if (!value) return toast('Enter a research objective first.', 'warn');
  try {
    await api('/tasks', { method: 'POST', body: JSON.stringify({ objective: value }) });
    $('objective').value = '';
    toast('Objective queued. The agent will start researching.');
    await refresh(); loadTasks();
  } catch (e) { toast(e.message, 'error'); }
}
async function submitTask() {
  const value = $('taskObjective').value.trim();
  if (!value) return toast('Enter an objective first.', 'warn');
  try {
    await api('/tasks', { method: 'POST', body: JSON.stringify({ objective: value }) });
    $('taskObjective').value = '';
    toast('Task queued.'); loadTasks(); refresh();
  } catch (e) { toast(e.message, 'error'); }
}

/* -------------------------------------------------------------------- repos */
function repoCard(r) {
  const active = state.currentRepo && state.currentRepo.id === r.id ? 'active' : '';
  const meta = r.meta || {};
  const phase = meta.phase ? meta.phase + (meta.total ? ' ' + (meta.processed || 0) + '/' + meta.total : '') : '';
  return '<div class="repo-card ' + active + '" data-repo="' + r.id + '">' +
    '<span class="repo-state ' + esc(r.status) + '">' + esc(String(r.status || '').toUpperCase()) + '</span>' +
    '<h4>' + esc(r.name) + '</h4>' +
    '<small>' + esc(r.kind) + ' · ' + num(r.file_count) + ' files · ' + num(r.chunk_count) + ' chunks<br>' +
    esc(r.languages || 'indexing…') + '<br>' + esc(clip(r.source, 90)) + '</small>' +
    (r.status === 'ingesting' || r.status === 'queued' ? '<small style="color:#ffc857;margin-top:5px">' + esc(phase) + '</small>' : '') +
    '</div>';
}
function renderRepoList() {
  const list = $('repoList');
  if (!list) return;
  list.innerHTML = state.repos.map(repoCard).join('') || '<div class="empty">No repositories yet. Paste a GitHub URL or local folder on the left.</div>';
  $('repoCountTag').textContent = state.repos.length + ' REPOS';
  refreshRepoSelect();
}
async function loadRepos(silent = false) {
  try {
    state.repos = await api('/repos');
    renderRepoList();
    if (!silent && state.currentRepo) {
      const existing = state.repos.find((r) => r.id === state.currentRepo.id);
      if (!existing) { state.currentRepo = null; $('repoDetail').classList.add('hidden'); }
    }
  } catch (e) { if (!silent) toast(e.message, 'error'); }
}
async function ingestRepo() {
  const source = $('repoSource').value.trim();
  if (!source) return toast('Paste a GitHub URL or local path.', 'warn');
  const button = $('repoIngestBtn');
  button.disabled = true; button.textContent = '⟳ Starting…';
  $('repoProgress').classList.remove('hidden');
  $('repoProgress').textContent = 'Submitting repository…';
  try {
    const payload = {
      source,
      branch: $('repoBranch').value.trim() || null,
      name: $('repoName').value.trim() || null,
      token: $('repoToken').value.trim() || null
    };
    const result = await api('/repos/ingest', { method: 'POST', body: JSON.stringify(payload) });
    $('repoToken').value = '';
    toast('Repository queued for learning (id ' + result.id + ').');
    const target = result.id;
    let ticks = 0;
    const timer = setInterval(async () => {
      ticks += 1;
      try {
        const repos = await api('/repos');
        state.repos = repos;
        renderRepoList();
        const repo = repos.find((r) => r.id === target);
        if (!repo) return;
        const meta = repo.meta || {};
        $('repoProgress').textContent = 'Repo #' + repo.id + ' · ' + repo.status.toUpperCase() +
          (meta.phase ? ' · ' + meta.phase : '') +
          (meta.total ? ' · ' + (meta.processed || 0) + '/' + meta.total : '') +
          (meta.error ? '\n' + meta.error : '');
        if (repo.status === 'ready' || repo.status === 'failed') {
          clearInterval(timer);
          button.disabled = false; button.textContent = '⌥ Learn repository';
          if (repo.status === 'ready') {
            toast('Repository learned: ' + repo.name + ' (' + repo.file_count + ' files, ' + repo.chunk_count + ' chunks).');
            $('repoProgress').textContent = 'READY · ' + repo.name + ' · ' + repo.file_count + ' files · ' + repo.chunk_count + ' chunks.';
            await selectRepo(repo.id);
          } else {
            toast('Repository indexing failed. Check the progress panel.', 'error');
          }
          $('repoSource').value = '';
          refresh();
        }
        if (ticks > 240) { clearInterval(timer); button.disabled = false; button.textContent = '⌥ Learn repository'; }
      } catch { }
    }, 1500);
  } catch (e) {
    toast(e.message, 'error');
    button.disabled = false; button.textContent = '⌥ Learn repository';
    $('repoProgress').textContent = 'ERROR · ' + e.message;
  }
}
function treeHTML(nodes) {
  return nodes.map((node) => {
    if (node.type === 'dir') {
      return '<div class="tree-node dir">▾ ' + esc(node.name) + '</div><div class="tree-children">' + treeHTML(node.children || []) + '</div>';
    }
    return '<div class="tree-node file" data-path="' + esc(node.path) + '">' + esc(node.name) + '</div>';
  }).join('');
}
async function selectRepo(id) {
  try {
    const data = await api('/repos/' + id);
    state.currentRepo = data.repo;
    state.repoFiles = data.files || [];
    $('repoDetail').classList.remove('hidden');
    $('repoDetailName').textContent = data.repo.name;
    $('repoDetailStats').textContent = data.repo.file_count + ' FILES · ' + data.repo.chunk_count + ' CHUNKS · ' + (data.repo.languages || '');
    $('repoSummary').innerHTML = md(data.repo.summary || 'No summary yet.');
    $('repoTree').innerHTML = treeHTML(data.tree || []) || '<div class="empty">No files indexed.</div>';
    $('codePath').textContent = 'Select a file';
    $('codeContent').textContent = '// file content appears here';
    $('repoAnswer').innerHTML = '';
    renderRepoList();
    $('repoDetail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { toast(e.message, 'error'); }
}
async function loadRepoFile(path) {
  if (!state.currentRepo) return;
  try {
    const file = await api('/repos/' + state.currentRepo.id + '/file?path=' + encodeURIComponent(path));
    $('codePath').textContent = file.path + ' · ' + (file.language || 'text') + ' · ' + num((file.content || '').length) + ' chars';
    $('codeContent').textContent = clip(file.content || '', 220000);
  } catch (e) { toast(e.message, 'error'); }
}
function copyCode() {
  const text = $('codeContent').textContent || '';
  navigator.clipboard.writeText(text).then(() => toast('Code copied.')).catch(() => toast('Clipboard blocked.', 'warn'));
}
async function askRepo() {
  if (!state.currentRepo) return toast('Select a repository first.', 'warn');
  const question = $('repoQuestion').value.trim();
  if (!question) return toast('Ask a question first.', 'warn');
  const target = $('repoAnswer');
  target.innerHTML = '<p class="muted"><span class="typing"><i></i><i></i><i></i></span> Reading indexed chunks…</p>';
  try {
    const result = await api('/chat', {
      method: 'POST',
      body: JSON.stringify({ message: question, repo_id: state.currentRepo.id, provider: state.provider })
    });
    target.innerHTML = md(result.answer) + '<p class="knowledge-meta" style="margin-top:10px">ENGINE · ' + esc(result.provider) + ' · ' + result.memory_results + ' memory hits</p>';
    $('repoQuestion').value = '';
    loadConversations();
  } catch (e) {
    target.innerHTML = '<p class="muted">' + esc(e.message) + '</p>';
    toast(e.message, 'error');
  }
}
async function deleteCurrentRepo() {
  if (!state.currentRepo) return;
  if (!confirm('Delete the index for "' + state.currentRepo.name + '"? The SQLite rows will be removed.')) return;
  try {
    await api('/repos/' + state.currentRepo.id, { method: 'DELETE' });
    state.currentRepo = null;
    $('repoDetail').classList.add('hidden');
    toast('Repository index deleted.');
    loadRepos(); refresh();
  } catch (e) { toast(e.message, 'error'); }
}

/* --------------------------------------------------------------- chat logic */
function messageHTML(message) {
  const isUser = message.role === 'user';
  const meta = message.meta || {};
  const body = isUser ? esc(message.content || '').replace(/\n/g, '<br>') : md(message.content || '');
  const tools = (meta.tools || []).map((t) => '<span class="chip ' + (t.ok === false ? '' : 'on') + '">' + esc(t) + '</span>').join('');
  const sources = (meta.sources || []).slice(0, 5).map((s) => '<span class="chip">' + esc(clip(s, 46)) + '</span>').join('');
  const engine = meta.provider ? '<span class="chip">' + esc(String(meta.provider).toUpperCase()) + '</span>' : '';
  return '<div class="message ' + (isUser ? 'user' : 'bot') + '">' +
    '<div class="msgavatar">' + (isUser ? 'YOU' : 'N') + '</div>' +
    '<div class="msgbody"><b>' + (isUser ? 'YOU' : 'NEXUS AI') +
    '<span class="msg-time">' + time(message.created_at) + '</span></b>' +
    '<div class="md">' + body + '</div>' +
    '<div class="msg-tools">' + engine + tools + sources + '</div></div></div>';
}
function welcomeHTML() {
  return messageHTML({
    role: 'assistant',
    content: "I'm online. Ask about a repository you taught me, your research memory, or switch to a generative engine for free-form work.",
    meta: {}, created_at: new Date().toISOString()
  });
}
function renderMessages() {
  const box = $('messages');
  if (!box) return;
  box.innerHTML = state.messages.length ? state.messages.map(messageHTML).join('') : welcomeHTML();
  box.scrollTop = box.scrollHeight;
}
async function loadConversations() {
  try {
    const conversations = await api('/conversations');
    const box = $('conversationList');
    if (!box) return;
    box.innerHTML = conversations.map((c) => (
      '<button class="conv-item ' + (state.conversation === c.id ? 'active' : '') + '" data-conv="' + c.id + '">' +
      esc(clip(c.title, 42)) + '<small>' + (c.message_count || 0) + ' msgs · ' + when(c.updated_at) + '</small>' +
      '<span class="conv-del" data-del="' + c.id + '">✕</span></button>'
    )).join('') || '<div class="empty">No threads yet.</div>';
  } catch { }
}
async function openConversation(id) {
  try {
    const data = await api('/conversations/' + id);
    state.conversation = id;
    state.messages = data.messages || [];
    renderMessages();
    loadConversations();
    const lastProvider = [...state.messages].reverse().find((m) => m.meta && m.meta.provider);
    if (lastProvider) {
      $('chatProviderTag').textContent = String(lastProvider.meta.provider).toUpperCase();
    }
  } catch (e) { toast(e.message, 'error'); }
}
function newChat() {
  state.conversation = null;
  state.messages = [];
  renderMessages();
  loadConversations();
  $('chatInput').focus();
}
async function deleteConversation(id) {
  try {
    await api('/conversations/' + id, { method: 'DELETE' });
    if (state.conversation === id) newChat();
    loadConversations();
    toast('Thread deleted.');
  } catch (e) { toast(e.message, 'error'); }
}
function clearCurrentChat() {
  if (!state.conversation) return newChat();
  if (!confirm('Delete this conversation?')) return;
  deleteConversation(state.conversation);
}
function exportConversation() {
  if (!state.messages.length) return toast('Nothing to export yet.', 'warn');
  const text = state.messages.map((m) => '## ' + (m.role === 'user' ? 'You' : 'NEXUS AI') + '\n\n' + m.content).join('\n\n---\n\n');
  download('nexus-conversation-' + Date.now() + '.md', text, 'text/markdown');
  toast('Conversation exported.');
}
function updateRepoBadge() {
  const badge = $('chatRepoBadge');
  if (!badge) return;
  const repo = state.repos.find((r) => r.id === state.repoContext);
  badge.classList.toggle('hidden', !repo);
  if (repo) badge.textContent = 'REPO · ' + repo.name.toUpperCase();
}
function refreshRepoSelect() {
  const select = $('chatRepoSelect');
  if (!select) return;
  select.innerHTML = '<option value="">No repo context</option>' + state.repos.map((r) => (
    '<option value="' + r.id + '">' + esc(r.name) + '</option>'
  )).join('');
  select.value = state.repoContext || '';
  updateRepoBadge();
}
function toggleRepoContext() {
  const select = $('chatRepoSelect');
  if (!select) return;
  if (!state.repos.length) return toast('Learn a repository first in Repo Lab.', 'warn');
  select.style.display = select.style.display === 'none' ? 'block' : 'none';
  if (select.style.display === 'block') select.focus();
}
function initChatRepoSelect() {
  const foot = document.querySelector('.chat-foot');
  if (!foot || $('chatRepoSelect')) return;
  const select = document.createElement('select');
  select.id = 'chatRepoSelect';
  select.style.cssText = 'max-width:210px;padding:5px 8px;font:8px var(--mono);display:none';
  select.onchange = () => {
    state.repoContext = select.value ? Number(select.value) : null;
    updateRepoBadge();
    toast(state.repoContext ? 'Repository context pinned.' : 'Repository context cleared.');
  };
  foot.insertBefore(select, $('chatRepoBadge'));
}

async function sendChat() {
  if (state.sending) return;
  const box = $('chatInput');
  const text = box.value.trim();
  if (!text) return;
  box.value = '';
  state.sending = true;
  $('chatSendBtn').disabled = true;
  const userMessage = { role: 'user', content: text, meta: {}, created_at: new Date().toISOString() };
  state.messages.push(userMessage);
  const liveId = 'live-answer-' + Date.now();
  $('messages').insertAdjacentHTML('beforeend', messageHTML(userMessage));
  $('messages').insertAdjacentHTML('beforeend',
    '<div class="message bot" id="' + liveId + '"><div class="msgavatar">N</div><div class="msgbody">' +
    '<b>NEXUS AI<span class="msg-time">streaming</span></b>' +
    '<div class="md"><span class="typing"><i></i><i></i><i></i></span> thinking with ' + esc(state.provider) + '…</div>' +
    '<div class="msg-tools" id="' + liveId + '-tools"></div></div></div>');
  const live = $(liveId);
  live.scrollIntoView({ behavior: 'smooth', block: 'end' });
  let answer = '';
  let finalMeta = { provider: state.provider };
  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text, conversation_id: state.conversation,
        provider: state.provider, repo_id: state.repoContext
      })
    });
    if (!response.ok || !response.body) throw new Error((await response.text()).slice(0, 400));
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const handle = (payload) => {
      let data;
      try { data = JSON.parse(payload); } catch { return; }
      if (data.type === 'meta') {
        if (data.conversation_id) state.conversation = data.conversation_id;
        finalMeta = { provider: data.provider, sources: data.sources || [], tools: (data.tools || []).map((t) => t.tool) };
        const chips = (data.tools || []).map((t) => '<span class="chip ' + (t.ok ? 'on' : '') + '">' + esc(t.tool) + '</span>').join('');
        const sources = (data.sources || []).slice(0, 4).map((s) => '<span class="chip">' + esc(clip(s, 42)) + '</span>').join('');
        $(liveId + '-tools').innerHTML = chips + sources;
      } else if (data.type === 'delta') {
        answer += data.text || '';
        live.querySelector('.md').innerHTML = md(answer);
        live.scrollIntoView({ block: 'end' });
      } else if (data.type === 'done') {
        if (data.conversation_id) state.conversation = data.conversation_id;
        finalMeta.sources = data.sources || finalMeta.sources || [];
        if (data.memory_used) $('chatMemoryTag').textContent = 'MEMORY USED';
      } else if (data.type === 'error') {
        throw new Error(data.error || 'stream error');
      }
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index;
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const chunk = buffer.slice(0, index).trim();
        buffer = buffer.slice(index + 2);
        if (chunk.startsWith('data:')) handle(chunk.slice(5).trim());
      }
    }
    if (!answer) answer = 'No response text was returned.';
    live.querySelector('.md').innerHTML = md(answer);
    live.querySelector('.msg-time').textContent = time(new Date().toISOString());
    state.messages.push({ role: 'assistant', content: answer, meta: finalMeta, created_at: new Date().toISOString() });
    loadConversations();
    refresh();
  } catch (e) {
    live.querySelector('.md').innerHTML = '<p style="color:#ff8aa0">' + esc(e.message) + '</p><p class="muted">Try switching provider in the top bar, or check that the selected engine is online.</p>';
    toast(e.message, 'error');
  } finally {
    state.sending = false;
    $('chatSendBtn').disabled = false;
    $('chatInput').focus();
    const boxEl = $('messages');
    boxEl.scrollTop = boxEl.scrollHeight;
  }
}

/* ---------------------------------------------------------------- knowledge */
function knowledgeCard(k) {
  const verification = String(k.verification_status || 'unverified');
  const full = esc(k.content || '');
  return '<article class="knowledge-card">' +
    '<button class="delete" onclick="deleteKnowledge(' + k.id + ')">Delete</button>' +
    '<h4>' + esc(k.title || 'Untitled') + '</h4>' +
    '<div class="knowledge-meta">' + esc(k.topic || 'research') + ' · ' + verification.toUpperCase() +
    ' · confidence ' + (Number(k.confidence || 0) * 100).toFixed(0) + '% · ' + when(k.created_at) + '</div>' +
    '<p>' + esc(clip(k.content || '', 640)) + '</p>' +
    (String(k.content || '').length > 680 ? '<details><summary class="knowledge-meta">Expand full record</summary><p>' + full + '</p></details>' : '') +
    (k.source_url ? '<a href="' + esc(k.source_url) + '" target="_blank" rel="noopener">' + esc(clip(k.source_url, 90)) + ' ↗</a>' : '') +
    '</article>';
}
async function loadKnowledge() {
  try {
    const query = $('knowledgeSearch') ? $('knowledgeSearch').value.trim() : '';
    const rows = await api('/knowledge?q=' + encodeURIComponent(query));
    $('knowledgeCount').textContent = rows.length + ' RECORDS';
    $('knowledgeList').innerHTML = rows.map(knowledgeCard).join('') || '<div class="empty">No stored knowledge yet. Learn a repository or queue a research objective.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
async function deleteKnowledge(id) {
  if (!confirm('Delete this knowledge record?')) return;
  try { await api('/knowledge/' + id, { method: 'DELETE' }); loadKnowledge(); refresh(); }
  catch (e) { toast(e.message, 'error'); }
}
async function globalSearch() {
  const query = $('knowledgeSearch').value.trim();
  if (!query) return toast('Type a search query first.', 'warn');
  try {
    const r = await api('/search', { method: 'POST', body: JSON.stringify({ q: query, limit: 10 }) });
    const chunks = (r.chunks || []).map((c) => (
      '<article class="knowledge-card"><h4>' + esc(c.repo_name + '/' + c.path) + '</h4>' +
      '<div class="knowledge-meta">LINES ' + c.start_line + '–' + c.end_line + ' · SCORE ' + c.score + '</div>' +
      '<pre>' + esc(clip(c.content, 900)) + '</pre></article>'
    )).join('');
    const memories = (r.memories || []).map((m) => (
      '<article class="knowledge-card"><h4>' + esc(m.kind) + '</h4><p>' + esc(clip(m.content, 500)) + '</p></article>'
    )).join('');
    $('searchResults').classList.remove('hidden');
    $('searchResults').innerHTML = '<div class="panel" style="margin-bottom:12px"><div class="panelhead"><div><label>HYBRID SEARCH</label><h3>' +
      esc(query) + '</h3></div><button class="textbtn" onclick="document.getElementById(\'searchResults\').classList.add(\'hidden\')">Close ✕</button></div>' +
      '<div class="knowledge-list">' + ((r.knowledge || []).map(knowledgeCard).join('') + chunks + memories || '<div class="empty">No matches.</div>') + '</div></div>';
  } catch (e) { toast(e.message, 'error'); }
}

/* ------------------------------------------------------------------- memory */
function memoryCard(m) {
  return '<article class="knowledge-card">' +
    '<button class="delete" onclick="deleteMemory(' + m.id + ')">Delete</button>' +
    '<h4>' + esc(String(m.kind || 'memory').toUpperCase()) + '</h4>' +
    '<div class="knowledge-meta">importance ' + (Number(m.importance || 0) * 100).toFixed(0) + '% · ' + when(m.created_at) + '</div>' +
    '<p>' + esc(clip(m.content || '', 900)) + '</p></article>';
}
async function loadMemory() {
  try {
    const query = $('memorySearch') ? $('memorySearch').value.trim() : '';
    const rows = await api('/memory?q=' + encodeURIComponent(query));
    $('memoryList').innerHTML = rows.map(memoryCard).join('') || '<div class="empty">No experience memories yet. Complete research tasks to build this layer.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
async function deleteMemory(id) {
  if (!confirm('Delete this experience memory?')) return;
  try { await api('/memory/' + id, { method: 'DELETE' }); loadMemory(); }
  catch (e) { toast(e.message, 'error'); }
}

/* -------------------------------------------------------------------- graph */
async function loadGraph() {
  try {
    const rows = await api('/knowledge');
    const groups = {};
    rows.forEach((k) => { const topic = k.topic || 'Uncategorized'; (groups[topic] = groups[topic] || []).push(k); });
    const entries = Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
    const max = Math.max(1, ...entries.map(([, items]) => items.length));
    $('graphBars').innerHTML = entries.slice(0, 12).map(([topic, items]) => (
      '<div class="gbar"><span>' + esc(clip(topic, 26)) + '</span><div class="track"><div class="fill" style="width:' +
      Math.round(items.length / max * 100) + '%"></div></div><b>' + items.length + '</b></div>'
    )).join('') || '<div class="empty">No graph nodes yet.</div>';
    $('graphList').innerHTML = entries.map(([topic, items]) => (
      '<article class="knowledge-card"><h4>◈ ' + esc(topic) + '</h4>' +
      '<div class="knowledge-meta">' + items.length + ' linked record(s)</div>' +
      '<p>' + items.map((x) => esc(clip(x.title, 80))).join(' · ') + '</p></article>'
    )).join('') || '<div class="empty">Store knowledge to create topic clusters.</div>';
  } catch (e) { toast(e.message, 'error'); }
}

/* -------------------------------------------------------------------- tasks */
async function loadTasks() {
  try {
    const rows = await api('/tasks');
    $('taskList').innerHTML = rows.map((t) => (
      '<div class="task"><div><b>' + esc(t.objective) + '</b>' +
      '<small>' + esc(t.notes || 'created ' + when(t.created_at)) + ' · attempts ' + (t.attempts || 0) + '</small>' +
      '<button class="textbtn" onclick="viewPlan(' + t.id + ')">View plan</button>' +
      '<div id="plan-' + t.id + '"></div></div>' +
      '<span class="taskstatus ' + esc(t.status) + '">' + esc(String(t.status || '').toUpperCase()) + '</span></div>'
    )).join('') || '<div class="empty">No research tasks queued.</div>';
    const active = rows.filter((t) => ['queued', 'running', 'interrupted'].includes(t.status));
    $('learningTasks').innerHTML = active.map((t) => (
      '<div class="event"><i></i><div><b>' + esc(t.objective) + '</b><small>' + esc(t.status) + ' · ' + (t.attempts || 0) + ' attempt(s)</small></div></div>'
    )).join('') || '<div class="empty">Queue is clear.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
async function viewPlan(id) {
  const target = $('plan-' + id);
  if (!target) return;
  if (target.innerHTML) { target.innerHTML = ''; return; }
  try {
    const plan = await api('/tasks/' + id + '/plan');
    target.innerHTML = '<pre class="code-block" style="max-height:220px;margin-top:7px">' +
      (plan.map((p, i) => (i + 1) + '. ' + esc(p.step)).join('\n') || 'No plan stored.') + '</pre>';
  } catch (e) { toast(e.message, 'error'); }
}

/* --------------------------------------------------------------- experiments */
async function loadProposals() {
  try {
    const [proposals, experiments] = await Promise.all([api('/proposals'), api('/experiments')]);
    $('proposalList').innerHTML = proposals.map((p) => (
      '<article class="knowledge-card"><h4>' + esc(p.title) + '</h4>' +
      '<div class="knowledge-meta">' + esc(p.category) + ' · ' + esc(p.status) + ' · ' + when(p.created_at) + '</div>' +
      '<p>' + esc(p.description) + '</p>' +
      (p.patch ? '<pre>' + esc(p.patch) + '</pre>' : '') +
      '<p class="muted">' + esc(p.test_result || 'Not tested') + '</p>' +
      '<button onclick="testProposal(' + p.id + ')">Run isolated static test</button>' +
      '<button onclick="decideProposal(' + p.id + ',\'approved\')">Approve</button>' +
      '<button onclick="decideProposal(' + p.id + ',\'rejected\')">Reject</button></article>'
    )).join('') || '<div class="empty">No improvement proposals yet.</div>';
    $('experimentList').innerHTML = experiments.map((x) => eventHTML({
      kind: x.passed ? 'PASS' : 'FAIL', message: x.result, created_at: x.created_at
    })).join('') || '<div class="empty">No experiments run.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
async function testProposal(id) {
  try { const r = await api('/proposals/' + id + '/sandbox-test', { method: 'POST' }); toast(r.result); loadProposals(); }
  catch (e) { toast(e.message, 'error'); }
}
async function decideProposal(id, status) {
  try {
    await api('/proposals/' + id + '/decision', { method: 'POST', body: JSON.stringify({ status }) });
    toast('Decision recorded. Deployment remains manual.');
    loadProposals();
  } catch (e) { toast(e.message, 'error'); }
}

/* ----------------------------------------------------------------- analytics */
async function loadAnalytics() {
  try {
    const [stats, status, evaluations] = await Promise.all([api('/stats'), api('/status'), api('/evaluations')]);
    $('aKnowledge').textContent = num(status.knowledge_count);
    $('aChunks').textContent = num(status.repo_chunks);
    $('aCorroborated').textContent = num((stats.claims || {}).corroborated || 0);
    $('aDisputed').textContent = num((stats.claims || {}).disputed || 0);
    const daily = stats.daily || [];
    const max = Math.max(1, ...daily.map((d) => d.n));
    $('analyticsDaily').innerHTML = daily.map((d) => (
      '<div class="bar-col"><div class="bar" style="height:' + Math.max(2, Math.round(d.n / max * 100)) + '%" title="' +
      d.n + ' records"></div><small>' + esc((d.day || '').slice(5)) + '</small></div>'
    )).join('') || '<div class="empty">No knowledge timeline yet.</div>';
    $('analyticsTopics').innerHTML = (stats.topics || []).map((t) => (
      '<span class="topic-pill">' + esc(t.topic || 'unknown') + '<b>' + t.n + '</b></span>'
    )).join('') || '<div class="empty">No topics yet.</div>';
    $('evaluationList').innerHTML = evaluations.map((v) => (
      '<article class="knowledge-card"><h4>Quality score: ' + Number(v.score || 0).toFixed(1) + '/100</h4>' +
      '<div class="knowledge-meta">' + when(v.created_at) + ' · task ' + v.task_id + '</div>' +
      '<p>Coverage ' + (Number(v.coverage || 0) * 100).toFixed(0) + '% · diversity ' +
      (Number(v.source_diversity || 0) * 100).toFixed(0) + '% · verification ' +
      (Number(v.verification || 0) * 100).toFixed(0) + '%</p>' +
      '<p class="muted">' + esc(v.issues || 'No recorded issues') + '</p></article>'
    )).join('') || '<div class="empty">No evaluations yet.</div>';
  } catch (e) { toast(e.message, 'error'); }
}

/* ----------------------------------------------------------------- providers */
function providerCardsHTML(list) {
  return list.map((p) => (
    '<div class="provider-card ' + (p.selected ? 'selected' : '') + '" data-provider="' + esc(p.id) + '">' +
    '<h4>' + esc(p.label) + '</h4>' +
    '<div class="p-tagline">' + esc(p.tagline) + '</div>' +
    '<div class="p-state ' + (p.online ? 'online' : '') + '"><i></i>' + (p.online ? 'AVAILABLE' : 'OFFLINE') + '</div>' +
    '<div class="p-models">' + esc((p.models || []).slice(0, 4).join(', ') || p.needs) + '</div>' +
    '<button class="secondary small" data-test="' + esc(p.id) + '">Test engine</button></div>'
  )).join('');
}
async function loadProviders() {
  try {
    const data = await api('/providers');
    state.providers = data.providers || [];
    state.provider = data.selected || state.provider;
    $('providerCards').innerHTML = providerCardsHTML(state.providers);
    renderProviderSwitch(); updateChatEngine();
    const models = await api('/models');
    $('ollamaStatus').textContent = models.online ? 'Ollama connected · ' + (models.models || []).length + ' model(s)' : 'Ollama not detected';
    $('modelList').innerHTML = (models.models || []).map((name) => (
      '<div class="event"><i></i><div><b>' + esc(name) + '</b><small>installed local model</small></div></div>'
    )).join('') || '<div class="empty">' + esc(models.error || 'Install and start Ollama to use it.') + '</div>';
    await loadSettings();
  } catch (e) { toast(e.message, 'error'); }
}
async function switchProvider(id) {
  try {
    const result = await api('/providers/select', { method: 'POST', body: JSON.stringify({ provider: id }) });
    state.provider = result.provider;
    state.providers = result.providers || state.providers;
    renderProviderSwitch(); updateChatEngine();
    if ($('providerCards')) $('providerCards').innerHTML = providerCardsHTML(state.providers);
    toast('Active engine: ' + id.toUpperCase());
    refresh();
  } catch (e) { toast(e.message, 'error'); }
}
async function testProvider(id) {
  try {
    const result = await api('/providers/test', { method: 'POST', body: JSON.stringify({ provider: id }) });
    toast(result.online ? result.label + ' is available. ' + (result.detail || '') : result.label + ' is offline: ' + (result.detail || 'unknown'), result.online ? '' : 'warn');
    loadProviders();
  } catch (e) { toast(e.message, 'error'); }
}
async function pullModel() {
  const model = $('modelName').value.trim();
  if (!model) return toast('Enter a model tag.', 'warn');
  try {
    await api('/models/pull', { method: 'POST', body: JSON.stringify({ objective: model }) });
    $('modelFeedback').textContent = 'Download requested. Watch the activity stream or refresh when complete.';
    toast('Model download requested.');
  } catch (e) { toast(e.message, 'error'); }
}
async function saveProviderConfig() {
  try {
    await api('/settings', {
      method: 'POST', body: JSON.stringify({
        llamacpp_model_path: $('cfgLlamaPath').value.trim(),
        llamacpp_n_ctx: Number($('cfgLlamaCtx').value) || 4096,
        llamacpp_n_gpu_layers: Number($('cfgLlamaGpu').value) || 0,
        openai_base_url: $('cfgOpenaiBase').value.trim() || 'http://localhost:1234/v1',
        openai_model: $('cfgOpenaiModel').value.trim(),
        openai_api_key: $('cfgOpenaiKey').value
      })
    });
    toast('Engine configuration saved.');
    loadProviders();
  } catch (e) { toast(e.message, 'error'); }
}

/* --------------------------------------------------------------- permissions */
function renderPermissionState(perms) {
  state.permissions = perms;
  const enabled = ['internet', 'pc_read', 'pc_write', 'shell'].filter((k) => perms[k]);
  $('permStateTag').textContent = enabled.length ? enabled.join(' · ').toUpperCase() : 'LOCKED DOWN';
  $('permStateTag').style.color = enabled.length ? '#ffc857' : '#39ff9a';
  const chips = ['internet', 'pc_read', 'pc_write', 'shell'].map((key) => (
    '<span class="chip ' + (perms[key] ? 'on' : '') + '">' + key.toUpperCase() + '</span>'
  )).join('');
  $('permMini').innerHTML = chips;
}
async function loadPermissions() {
  try {
    const perms = await api('/permissions');
    renderPermissionState(perms);
    $('permInternet').checked = !!perms.internet;
    $('permPcRead').checked = !!perms.pc_read;
    $('permPcWrite').checked = !!perms.pc_write;
    $('permShell').checked = !!perms.shell;
    $('permRoots').value = (perms.allowed_roots || []).join('\n');
    $('permCommands').value = (perms.allowed_commands || []).join('\n');
    await loadTools();
    loadAudit();
  } catch (e) { toast(e.message, 'error'); }
}
async function savePermissions() {
  try {
    const perms = await api('/permissions', {
      method: 'POST', body: JSON.stringify({
        internet: $('permInternet').checked,
        pc_read: $('permPcRead').checked,
        pc_write: $('permPcWrite').checked,
        shell: $('permShell').checked,
        allowed_roots: $('permRoots').value,
        allowed_commands: $('permCommands').value
      })
    });
    renderPermissionState(perms);
    toast('Permissions saved. Every tool call is audited.');
    refresh();
  } catch (e) { toast(e.message, 'error'); }
}
async function loadTools() {
  try {
    const data = await api('/tools');
    state.tools = data.tools || [];
    const select = $('toolSelect');
    if (select && !select.options.length) {
      select.innerHTML = state.tools.map((t) => '<option value="' + esc(t.name) + '">' + esc(t.name) + ' · needs ' + esc(t.permission) + '</option>').join('');
    }
    toolArgsHint();
  } catch { }
}
function toolArgsHint() {
  const spec = state.tools.find((t) => t.name === $('toolSelect').value);
  if (!spec) return;
  $('toolPermTag').textContent = spec.permission.toUpperCase();
  $('toolArgs').placeholder = JSON.stringify(spec.args || {});
}
async function runToolConsole() {
  const tool = $('toolSelect').value;
  let args = {};
  try { args = JSON.parse($('toolArgs').value || '{}'); }
  catch { return toast('Arguments must be valid JSON.', 'warn'); }
  $('toolOutput').textContent = '// executing ' + tool + '…';
  try {
    const result = await api('/tools/run', { method: 'POST', body: JSON.stringify({ tool, args }) });
    $('toolOutput').textContent = result.ok ? result.output : ('DENIED / ERROR\n\n' + (result.error || result.output));
    toast(result.ok ? 'Tool completed.' : (result.error || 'Tool failed.'), result.ok ? '' : 'warn');
    loadAudit();
  } catch (e) {
    $('toolOutput').textContent = e.message;
    toast(e.message, 'error');
  }
}
async function loadAudit() {
  try {
    const [auditRows, runs] = await Promise.all([api('/audit'), api('/tool-runs')]);
    $('auditList').innerHTML = auditRows.map((r) => eventHTML({
      kind: (r.allowed ? 'ALLOW' : 'DENY') + ' · ' + r.action,
      message: r.detail, created_at: r.created_at
    })).join('') || '<div class="empty">No audited actions yet.</div>';
    $('toolRunList').innerHTML = runs.map((r) => eventHTML({
      kind: r.status + ' · ' + r.tool,
      message: clip(r.result || r.args, 220),
      created_at: r.created_at
    })).join('') || '<div class="empty">No tool runs yet.</div>';
  } catch { }
}

/* ------------------------------------------------------------------ settings */
const SETTING_MAP = {
  sModel: 'model', sEmbedding: 'embedding_model', sEmbeddingProvider: 'embedding_provider',
  sCtx: 'num_ctx', sPredict: 'num_predict', sThreads: 'num_thread', sKeepAlive: 'keep_alive',
  sChatHistory: 'chat_history', sMode: 'mode', sPages: 'max_pages_per_task',
  sDeepPages: 'deep_research_pages', sDelay: 'request_delay_seconds',
  sInterval: 'research_interval_seconds', sVerify: 'verification_sources',
  sAutoResume: 'auto_resume', sDomains: 'allowed_domains', sRepoFiles: 'max_repo_files',
  sRepoKb: 'max_repo_file_kb', sRepoMb: 'max_repo_mb', sChunkLines: 'repo_chunk_lines',
  sChunkOverlap: 'repo_chunk_overlap'
};
async function loadSettings() {
  try {
    const s = await api('/settings');
    Object.entries(SETTING_MAP).forEach(([id, key]) => {
      const el = $(id);
      if (el) el.value = s[key] != null ? s[key] : '';
    });
    $('cfgLlamaPath').value = s.llamacpp_model_path || '';
    $('cfgLlamaCtx').value = s.llamacpp_n_ctx || 4096;
    $('cfgLlamaGpu').value = s.llamacpp_n_gpu_layers || 0;
    $('cfgOpenaiBase').value = s.openai_base_url || '';
    $('cfgOpenaiModel').value = s.openai_model || '';
    $('cfgOpenaiKey').value = s.openai_api_key || '';
  } catch (e) { toast(e.message, 'error'); }
}
async function saveSettings() {
  try {
    const numeric = new Set(['num_ctx', 'num_predict', 'num_thread', 'chat_history', 'max_pages_per_task',
      'deep_research_pages', 'request_delay_seconds', 'research_interval_seconds', 'verification_sources',
      'max_repo_files', 'max_repo_file_kb', 'max_repo_mb', 'repo_chunk_lines', 'repo_chunk_overlap']);
    const payload = {};
    Object.entries(SETTING_MAP).forEach(([id, key]) => {
      const el = $(id);
      if (!el) return;
      if (key === 'auto_resume') payload[key] = el.value === 'true';
      else if (numeric.has(key)) payload[key] = Number(el.value);
      else payload[key] = el.value;
    });
    await api('/settings', { method: 'POST', body: JSON.stringify(payload) });
    toast('Configuration saved.');
    refresh();
  } catch (e) { toast(e.message, 'error'); }
}
async function downloadExport() {
  try {
    const data = await api('/export');
    download('nexus-export-' + new Date().toISOString().slice(0, 10) + '.json', JSON.stringify(data, null, 2), 'application/json');
    toast('Local data exported.');
  } catch (e) { toast(e.message, 'error'); }
}

/* ------------------------------------------------------------------- matrix */
function initMatrix() {
  const canvas = $('matrix');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx = canvas.getContext('2d');
  const glyphs = '01NEXUSAI<>{}[]/\\=+*#$%&_01アカサタナハマヤラワ';
  let width = 0, height = 0, columns = 0, drops = [];
  const size = 15;
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
    columns = Math.floor(width / size);
    drops = Array.from({ length: columns }, () => Math.random() * -80);
  }
  resize();
  window.addEventListener('resize', debounce(resize, 200));
  let last = 0;
  function frame(now) {
    if (now - last > 66) {
      last = now;
      ctx.fillStyle = 'rgba(4,7,10,0.13)';
      ctx.fillRect(0, 0, width, height);
      ctx.font = size + 'px monospace';
      for (let i = 0; i < columns; i++) {
        const glyph = glyphs[Math.floor(Math.random() * glyphs.length)];
        ctx.fillStyle = Math.random() > 0.94 ? 'rgba(46,230,255,0.85)' : 'rgba(57,255,154,0.55)';
        ctx.fillText(glyph, i * size, drops[i] * size);
        if (drops[i] * size > height && Math.random() > 0.975) drops[i] = 0;
        drops[i] += 1;
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

/* -------------------------------------------------------------- websockets */
let socket = null;
const wsRefresh = debounce(() => refresh(), 900);
function connectWS() {
  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(proto + '://' + location.host + '/ws');
    socket.onmessage = (event) => {
      let value;
      try { value = JSON.parse(event.data); } catch { return; }
      const html = eventHTML(value);
      if ($('liveEvents')) $('liveEvents').insertAdjacentHTML('afterbegin', html);
      if ($('allEvents')) $('allEvents').insertAdjacentHTML('afterbegin', html);
      wsRefresh();
    };
    socket.onclose = () => setTimeout(connectWS, 4000);
    socket.onerror = () => { try { socket.close(); } catch { } };
  } catch { }
}

/* --------------------------------------------------------------- bootstrapping */
function init() {
  $$('.nav').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.page)));

  $('providerSwitch').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-provider]');
    if (button) switchProvider(button.dataset.provider);
  });

  $('repoList').addEventListener('click', (event) => {
    const card = event.target.closest('[data-repo]');
    if (card) selectRepo(Number(card.dataset.repo));
  });
  $('repoTree').addEventListener('click', (event) => {
    const file = event.target.closest('.tree-node.file');
    if (file) loadRepoFile(file.dataset.path);
  });
  $$('#repoTabs .tab').forEach((tab) => tab.addEventListener('click', () => {
    $$('#repoTabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
    $$('[id^="rtab-"]').forEach((panel) => panel.classList.toggle('active', panel.id === 'rtab-' + tab.dataset.rtab));
  }));

  $('conversationList').addEventListener('click', (event) => {
    const del = event.target.closest('[data-del]');
    if (del) { event.stopPropagation(); deleteConversation(Number(del.dataset.del)); return; }
    const button = event.target.closest('[data-conv]');
    if (button) openConversation(Number(button.dataset.conv));
  });

  if ($('providerCards')) {
    $('providerCards').addEventListener('click', (event) => {
      const test = event.target.closest('[data-test]');
      if (test) { event.stopPropagation(); testProvider(test.dataset.test); return; }
      const card = event.target.closest('[data-provider]');
      if (card) switchProvider(card.dataset.provider);
    });
  }

  $('chatInput').addEventListener('input', () => {
    const el = $('chatInput');
    el.style.height = 'auto';
    el.style.height = Math.min(180, el.scrollHeight) + 'px';
  });

  initChatRepoSelect();
  initMatrix();
  connectWS();

  $('footerTime').textContent = new Date().toLocaleDateString();
  const sideVersion = $('sideVersion');
  if (sideVersion) sideVersion.textContent = 'v0.4.0';

  refresh().then(() => {
    loadConversations();
    loadRepos(true);
  });
  setInterval(refresh, 8000);
  setInterval(() => { if ($('activity').classList.contains('active')) loadEvents(); }, 12000);
}

document.addEventListener('DOMContentLoaded', init);
