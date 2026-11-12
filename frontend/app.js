/* NEXUS AI — frontend controller (vanilla, no build step) */
'use strict';

const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const titles = {
  overview: 'Command Center', repos: 'Repository Lab', urllearn: 'URL Learn',
  skills: 'Skill Vault', chat: 'Nexus Core', programs: 'Code Studio',
  autonomous: 'Autonomous Learning',
  learning: 'Autonomous Research', knowledge: 'Knowledge Base', memory: 'Memory Manager',
  graph: 'Knowledge Graph', history: 'Learning History', tasks: 'Task Manager',
  activity: 'Activity Stream', monitor: 'System Monitor',
  experiments: 'Experiments', analytics: 'Analytics', models: 'Providers',
  permissions: 'Permissions', settings: 'Settings',
  dashboard: 'Dashboard', autoprogramming: 'Auto Programming',
  review: 'Review Studio', projects: 'Projects', playground: 'Playground', agents: 'AI Agents'
};

const state = {
  status: null, providers: [], provider: 'nexus', repos: [],
  currentRepo: null, conversation: null, messages: [], repoContext: null,
  tools: [], permissions: null, sending: false, refreshing: false,
  webSources: [], currentWeb: null, skills: [], currentSkill: null, skillMeta: null,
  auto: null, autoTimer: null, lastEventId: 0, coreTimer: null,
  graph: { nodes: [], edges: [], stats: null, scale: 1, offsetX: 0, offsetY: 0,
           dragging: null, pointer: null, hover: null, selected: null, active: false },
  programs: [], programRecipes: [], programStatus: null, currentProgram: null,
  programFiles: [], programFile: '', programContent: '',
  dashboard: null, ap: null, apConcepts: [], apExercises: [], apCurrentExercise: null,
  rv: null, rvHistory: [], pj: null, pjList: [], pjCurrent: null,
  ag: null, agRuns: []
};

const PAGE_LOADERS = {
  overview: () => { },
  repos: () => loadRepos(),
  urllearn: () => loadUrlLearn(),
  skills: () => loadSkillPage(),
  chat: () => { loadConversations(); refreshRepoSelect(); updateChatEngine(); },
  programs: () => loadProgramPage(),
  autonomous: () => loadAutonomous(),
  learning: () => loadTasks(),
  knowledge: () => loadKnowledge(),
  memory: () => loadMemory(),
  graph: () => loadGraph(),
  history: () => loadHistory(),
  tasks: () => loadTasks(),
  activity: () => loadEvents(),
  monitor: () => loadMonitor(),
  experiments: () => loadProposals(),
  analytics: () => loadAnalytics(),
  models: () => loadProviders(),
  permissions: () => loadPermissions(),
  settings: () => loadSettings(),
  dashboard: () => loadDashboard(),
  autoprogramming: () => loadAutoProgramming(),
  review: () => loadReview(),
  projects: () => loadProjects(),
  playground: () => { pgLangChanged(); },
  agents: () => loadAgents()
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
  state.graph.active = name === 'graph';
  if (name === 'autonomous') {
    startAutoPolling();
  } else {
    stopAutoPolling();
  }
  if (name === 'graph') startGraphLoop();
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
  $('sideVersion').textContent = 'v' + (s.version || '0.5.0');
  $('footVersion').textContent = 'v' + (s.version || '0.5.0');
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
  state.permissions = s.permissions || state.permissions;
  state.provider = (s.provider && s.provider.id) || state.provider;
  const core = $('coreVisual');
  if (core) {
    core.dataset.state = s.autonomous_running
      ? (s.autonomous_paused ? 'paused' : 'learning')
      : (s.running ? (s.paused ? 'paused' : 'active') : 'idle');
  }
  if ($('autoStateTag')) {
    $('autoStateTag').textContent = s.autonomous_running
      ? (s.autonomous_paused ? 'PAUSED' : 'LEARNING') : 'IDLE';
  }
  renderProviderSwitch();
  updateChatEngine();
}

function pulseCore(kind) {
  const core = $('coreVisual');
  if (!core) return;
  const cls = kind === 'error' ? 'core-error' : 'core-pulse';
  core.classList.remove('core-pulse', 'core-error');
  void core.offsetWidth;
  core.classList.add(cls);
  clearTimeout(state.coreTimer);
  state.coreTimer = setTimeout(() => core.classList.remove('core-pulse', 'core-error'), 2400);
}

function pulseFromEvents(events) {
  if (!events || !events.length) return;
  const latest = Math.max(...events.map((e) => Number(e.id || 0)));
  if (!state.lastEventId) { state.lastEventId = latest; return; }
  if (latest <= state.lastEventId) return;
  const fresh = events.filter((e) => Number(e.id || 0) > state.lastEventId);
  state.lastEventId = latest;
  if (fresh.some((e) => /warning|error|failed|blocked/i.test(String(e.kind)))) {
    pulseCore('error');
  } else if (fresh.some((e) => /learning|discovery|verification|knowledge|web|repo|skills/i.test(String(e.kind)))) {
    pulseCore('knowledge');
  } else {
    pulseCore('event');
  }
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
      pulseFromEvents(events);
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

/* ---------------------------------------------------------------- url learn */
function webCard(s) {
  const phase = (s.meta && s.meta.phase) ? s.meta.phase : '';
  const active = state.currentWeb && state.currentWeb.id === s.id ? 'active' : '';
  return '<div class="repo-card ' + active + '" data-web="' + s.id + '">' +
    '<span class="repo-state ' + esc(s.status) + '">' + esc(String(s.status || '').toUpperCase()) + '</span>' +
    '<h4>' + esc(s.title || s.url) + '</h4>' +
    '<small>' + esc(s.topic || 'web') + ' · ' + num(s.chunk_count) + ' chunks · depth ' + (s.depth || 0) +
    (phase && s.status !== 'ready' ? ' · ' + esc(phase) : '') + '<br>' + esc(clip(s.url, 90)) + '</small>' +
    '</div>';
}
function renderWebSources() {
  const list = $('webList');
  if (!list) return;
  list.innerHTML = state.webSources.map(webCard).join('') || '<div class="empty">No pages learned yet. Paste a public HTTPS URL on the left.</div>';
  $('webCountTag').textContent = state.webSources.length + ' PAGES';
  const perm = state.permissions || {};
  $('webPermTag').textContent = perm.internet ? 'INTERNET ON' : 'INTERNET OFF';
  $('webPermTag').className = 'tag' + (perm.internet ? ' on' : '');
}
async function loadUrlLearn() {
  try {
    const [sources, packs, perms] = await Promise.all([api('/learn/url'), api('/learn/packs'), api('/permissions')]);
    state.webSources = sources;
    state.permissions = perms;
    renderWebSources();
    const canLearn = !!perms.internet;
    $('webPacks').innerHTML = (packs || []).map((p) => (
      '<button class="pack-card" data-pack="' + esc(p.id) + '"' + (canLearn ? '' : ' disabled') + '>' +
      '<b>' + esc(p.label) + '</b><small>' + esc(p.description) + '</small>' +
      '<span>' + (p.urls || []).length + ' sources</span></button>'
    )).join('') || '<div class="empty">No packs available.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
function loadWebSources() { return loadUrlLearn(); }
async function learnUrl() {
  const url = $('webUrl').value.trim();
  if (!url) return toast('Paste a public HTTPS URL.', 'warn');
  const button = $('webLearnBtn');
  button.disabled = true; button.textContent = '⟳ Starting…';
  $('webProgress').classList.remove('hidden');
  $('webProgress').textContent = 'Submitting URL…';
  try {
    const result = await api('/learn/url', {
      method: 'POST',
      body: JSON.stringify({
        url,
        topic: $('webTopic').value.trim() || null,
        depth: Number($('webDepth').value || 0)
      })
    });
    toast('URL queued for learning (id ' + result.id + ').');
    pollWebSource(result.id, button);
  } catch (e) {
    toast(e.message, 'error');
    button.disabled = false; button.textContent = '⇲ Learn URL';
    $('webProgress').textContent = 'ERROR · ' + e.message;
  }
}
function pollWebSource(id, button) {
  let ticks = 0;
  const timer = setInterval(async () => {
    ticks += 1;
    try {
      const sources = await api('/learn/url');
      state.webSources = sources;
      renderWebSources();
      const row = sources.find((s) => s.id === id);
      if (row) {
        const phase = (row.meta && row.meta.phase) ? row.meta.phase : '';
        $('webProgress').textContent = 'Page #' + row.id + ' · ' + String(row.status || '').toUpperCase() +
          (phase ? ' · ' + phase : '') + ' · ' + (row.chunk_count || 0) + ' chunks' +
          (row.meta && row.meta.error ? '\n' + row.meta.error : '');
        if (row.status === 'ready' || row.status === 'failed') {
          clearInterval(timer);
          button.disabled = false; button.textContent = '⇲ Learn URL';
          if (row.status === 'ready') {
            toast('Page learned: ' + (row.title || row.url) + ' (' + row.chunk_count + ' chunks).');
            $('webUrl').value = '';
            await selectWebSource(row.id);
            refresh();
          } else {
            toast('URL learning failed. Check the progress panel.', 'error');
          }
        }
      }
      if (ticks > 240) { clearInterval(timer); button.disabled = false; button.textContent = '⇲ Learn URL'; }
    } catch { }
  }, 1600);
}
async function learnPack(packId) {
  try {
    const result = await api('/learn/pack', { method: 'POST', body: JSON.stringify({ pack: packId }) });
    toast('Queued ' + result.queued + ' page(s) from the ' + packId + ' pack.');
    $('webProgress').classList.remove('hidden');
    $('webProgress').textContent = 'Pack ' + packId + ' queued (' + result.queued + ' pages). Watch the index and Activity stream.';
    setTimeout(loadUrlLearn, 1500);
  } catch (e) { toast(e.message, 'error'); }
}
async function selectWebSource(id) {
  try {
    const data = await api('/learn/url/' + id);
    const source = data.source || {};
    state.currentWeb = source;
    $('webDetail').classList.remove('hidden');
    $('webDetailTitle').textContent = source.title || source.url;
    $('webDetailStats').textContent = String(source.status || '').toUpperCase() + ' · ' + (source.chunk_count || 0) + ' CHUNKS · ' + (source.topic || 'web');
    $('webSummary').innerHTML = md(source.summary || 'No summary stored yet.') +
      (source.url ? '<p><a href="' + esc(source.url) + '" target="_blank" rel="noopener">' + esc(clip(source.url, 100)) + ' ↗</a></p>' : '');
    $('webChunks').innerHTML = (data.chunks || []).map((c) => (
      '<article class="knowledge-card"><div class="knowledge-meta">CHUNK ' + (c.ordinal + 1) + '</div><p>' + esc(clip(c.content, 900)) + '</p></article>'
    )).join('') || '<div class="empty">No chunks stored for this page.</div>';
    renderWebSources();
    $('webDetail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { toast(e.message, 'error'); }
}
async function deleteWebSource() {
  if (!state.currentWeb) return;
  if (!confirm('Delete this learned page and its chunks?')) return;
  try {
    await api('/learn/url/' + state.currentWeb.id, { method: 'DELETE' });
    state.currentWeb = null;
    $('webDetail').classList.add('hidden');
    toast('Learned page deleted.');
    loadUrlLearn(); refresh();
  } catch (e) { toast(e.message, 'error'); }
}
async function searchWeb() {
  const query = $('webSearch').value.trim();
  if (!query) return toast('Type a query first.', 'warn');
  try {
    const rows = await api('/learn/url/search', { method: 'POST', body: JSON.stringify({ q: query, limit: 10 }) });
    $('webResults').classList.remove('hidden');
    $('webResults').innerHTML = rows.map((r) => (
      '<article class="knowledge-card"><h4>' + esc(r.source_title || r.title || r.url) + '</h4>' +
      '<div class="knowledge-meta">CHUNK ' + (r.ordinal + 1) + ' · SCORE ' + r.score + ' · ' + esc(r.topic || 'web') + '</div>' +
      '<p>' + esc(clip(r.content, 800)) + '</p><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(clip(r.url, 90)) + ' ↗</a></article>'
    )).join('') || '<div class="empty">No web chunks matched.</div>';
  } catch (e) { toast(e.message, 'error'); }
}

/* --------------------------------------------------------------- skill vault */
function skillCard(s) {
  return '<div class="skill-card ' + (s.enabled ? '' : 'disabled') + '" data-skill="' + esc(s.skill_id) + '">' +
    '<b>' + esc(s.name) + '</b>' +
    '<span class="tag tiny">' + esc(s.category || 'general') + '</span>' +
    '<small>' + esc(clip(s.description || 'No description.', 210)) + '</small>' +
    '<span class="skill-foot">' + (s.bundles && s.bundles.length ? esc(s.bundles.join(' · ')) : 'standalone') +
    ' · ' + num(s.content_length) + ' chars</span>' +
    '</div>';
}
function renderSkills() {
  const list = $('skillList');
  if (!list) return;
  list.innerHTML = state.skills.map(skillCard).join('') || '<div class="empty">No skills match that filter.</div>';
}
async function loadSkillPage() {
  await Promise.all([loadSkills(), loadSkillImports()]);
}
async function loadSkills() {
  try {
    const query = $('skillSearch') ? $('skillSearch').value.trim() : '';
    const category = $('skillCategory') ? $('skillCategory').value : '';
    const data = await api('/skills?q=' + encodeURIComponent(query) + '&category=' + encodeURIComponent(category) + '&limit=600');
    state.skills = data.skills || [];
    state.skillMeta = data.stats || {};
    renderSkills();
    const stats = data.stats || {};
    $('skillCountTag').textContent = num(stats.total) + ' SKILLS';
    $('skillEnabledTag').textContent = num(stats.enabled) + ' ENABLED';
    $('skillSeedTag').textContent = stats.seed_version ? 'SEED ' + String(stats.seed_version).slice(0, 22) : 'SEED LOCAL';
    const select = $('skillCategory');
    if (select && select.options.length <= 1) {
      (stats.categories || []).forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c.category;
        opt.textContent = c.category + ' (' + c.n + ')';
        select.appendChild(opt);
      });
    }
    const bundles = data.bundles || [];
    $('skillBundles').innerHTML = bundles.slice(0, 14).map((b) => '<span class="chip">' + esc(b) + '</span>').join('') || '<span class="chip">no bundles</span>';
  } catch (e) { toast(e.message, 'error'); }
}
async function loadSkillImports() {
  try {
    const rows = await api('/skills/imports');
    $('skillImports').innerHTML = rows.map((r) => (
      '<div class="event"><i></i><div><b>' + esc(r.source) + '</b><small>' + esc(String(r.status || '').toUpperCase()) +
      ' · ' + num(r.imported) + ' imported · ' + num(r.skipped) + ' skipped · ' + when(r.created_at) + '</small>' +
      (r.detail ? '<small>' + esc(clip(r.detail, 220)) + '</small>' : '') + '</div></div>'
    )).join('') || '<div class="empty">No imports yet.</div>';
  } catch (e) { toast(e.message, 'error'); }
}
async function importSkills() {
  const button = $('skillImportBtn');
  button.disabled = true; button.textContent = '⟳ Importing…';
  $('skillProgress').classList.remove('hidden');
  $('skillProgress').textContent = 'Requesting import…';
  try {
    const result = await api('/skills/import', {
      method: 'POST',
      body: JSON.stringify({
        source: $('skillSource').value.trim() || null,
        branch: $('skillBranch').value.trim() || null,
        token: $('skillToken').value.trim() || null
      })
    });
    $('skillToken').value = '';
    $('skillProgress').textContent = 'Import #' + result.id + ' queued. Downloading and parsing SKILL.md files…';
    let ticks = 0;
    const timer = setInterval(async () => {
      ticks += 1;
      try {
        const rows = await api('/skills/imports');
        const row = rows.find((r) => r.id === result.id);
        $('skillImports').innerHTML = rows.map((r) => (
          '<div class="event"><i></i><div><b>' + esc(r.source) + '</b><small>' + esc(String(r.status || '').toUpperCase()) +
          ' · ' + num(r.imported) + ' imported · ' + num(r.skipped) + ' skipped</small></div></div>'
        )).join('') || '<div class="empty">No imports yet.</div>';
        if (row) {
          $('skillProgress').textContent = 'Import #' + row.id + ' · ' + String(row.status || '').toUpperCase() +
            ' · ' + num(row.imported) + ' imported · ' + num(row.skipped) + ' skipped' +
            (row.detail ? '\n' + row.detail : '');
          if (['ready', 'failed'].includes(row.status)) {
            clearInterval(timer);
            button.disabled = false; button.textContent = '✦ Import skills';
            toast(row.status === 'ready' ? 'Skills imported: ' + row.imported + '.' : 'Skill import failed.', row.status === 'ready' ? '' : 'error');
            loadSkills();
          }
        }
        if (ticks > 240) { clearInterval(timer); button.disabled = false; button.textContent = '✦ Import skills'; }
      } catch { }
    }, 1800);
  } catch (e) {
    toast(e.message, 'error');
    button.disabled = false; button.textContent = '✦ Import skills';
    $('skillProgress').textContent = 'ERROR · ' + e.message;
  }
}
async function seedSkills() {
  try {
    const r = await api('/skills/seed', { method: 'POST', body: '{}' });
    toast(r.seeded ? 'Seeded ' + r.seeded + ' offline skills.' : 'Offline skills already up to date.');
    loadSkills();
  } catch (e) { toast(e.message, 'error'); }
}
async function openSkill(skillId) {
  try {
    const skill = await api('/skills/' + encodeURIComponent(skillId));
    state.currentSkill = skill;
    $('skillDetail').classList.remove('hidden');
    $('skillDetailTitle').textContent = skill.name;
    $('skillDetailMeta').textContent = (skill.category || 'general').toUpperCase() + ' · ' + (skill.enabled ? 'ENABLED' : 'DISABLED') +
      (skill.bundles && skill.bundles.length ? ' · ' + skill.bundles.join(', ') : '');
    $('skillDetailBody').innerHTML = md('**' + (skill.description || '') + '**\n\n' + (skill.content || 'No body stored.'));
    $('skillDetail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { toast(e.message, 'error'); }
}
async function toggleCurrentSkill() {
  if (!state.currentSkill) return;
  try {
    const r = await api('/skills/' + encodeURIComponent(state.currentSkill.skill_id) + '/toggle', { method: 'POST', body: '{}' });
    toast('Skill ' + (r.enabled ? 'enabled' : 'disabled') + '.');
    await loadSkills();
    openSkill(state.currentSkill.skill_id);
  } catch (e) { toast(e.message, 'error'); }
}
async function deleteCurrentSkill() {
  if (!state.currentSkill) return;
  if (!confirm('Delete skill "' + state.currentSkill.name + '" from the vault?')) return;
  try {
    await api('/skills/' + encodeURIComponent(state.currentSkill.skill_id), { method: 'DELETE' });
    state.currentSkill = null;
    $('skillDetail').classList.add('hidden');
    toast('Skill deleted.');
    loadSkills();
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
    const web = (r.web || []).map((w) => (
      '<article class="knowledge-card"><h4>' + esc(w.source_title || w.title || w.url) + '</h4>' +
      '<div class="knowledge-meta">WEB · CHUNK ' + (w.ordinal + 1) + ' · SCORE ' + w.score + '</div>' +
      '<p>' + esc(clip(w.content, 700)) + '</p></article>'
    )).join('');
    const skills = (r.skills || []).map((s) => (
      '<article class="knowledge-card"><h4>✦ ' + esc(s.name) + '</h4>' +
      '<div class="knowledge-meta">SKILL · ' + esc(s.category || 'general') + ' · SCORE ' + s.score + '</div>' +
      '<p>' + esc(clip(s.description, 500)) + '</p></article>'
    )).join('');
    $('searchResults').classList.remove('hidden');
    $('searchResults').innerHTML = '<div class="panel" style="margin-bottom:12px"><div class="panelhead"><div><label>HYBRID SEARCH</label><h3>' +
      esc(query) + '</h3></div><button class="textbtn" onclick="document.getElementById(\'searchResults\').classList.add(\'hidden\')">Close ✕</button></div>' +
      '<div class="knowledge-list">' + ((r.knowledge || []).map(knowledgeCard).join('') + chunks + web + skills + memories || '<div class="empty">No matches.</div>') + '</div></div>';
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
const GRAPH_COLORS = { knowledge: '#5eead4', topic: '#7aa2ff', source: '#f472b6', concept: '#fbbf24' };
const EDGE_COLORS = { in_topic: 'rgba(122,162,255,0.22)', from_source: 'rgba(244,114,182,0.18)',
                      mentions: 'rgba(94,234,212,0.14)', related: 'rgba(251,191,36,0.28)' };

function knowledgeNodeColor(node) {
  const status = String(node.verification || 'unverified');
  if (status === 'corroborated' || status === 'verified') return '#39ff9a';
  if (status === 'user-reported') return '#fbbf24';
  if (status === 'single-source') return '#5eead4';
  if (status === 'web-learned') return '#7aa2ff';
  return '#8fa3b8';
}

function graphNodeRadius(node) {
  return Math.max(3.5, Math.min(14, Number(node.size || 5) * 0.82));
}

function layoutGraph(data) {
  const nodes = data.nodes.map((n) => Object.assign({}, n));
  const topics = nodes.filter((n) => n.type === 'topic');
  const concepts = nodes.filter((n) => n.type === 'concept');
  const sources = nodes.filter((n) => n.type === 'source');
  const knowledge = nodes.filter((n) => n.type === 'knowledge');
  const topicAngle = new Map();
  topics.forEach((t, i) => topicAngle.set(t.id, (i / Math.max(1, topics.length)) * Math.PI * 2));
  const inner = 120 + Math.min(130, topics.length * 4);
  topics.forEach((t) => {
    const a = topicAngle.get(t.id);
    t.x = Math.cos(a) * inner; t.y = Math.sin(a) * inner;
  });
  const perTopic = new Map();
  knowledge.forEach((k) => {
    const tid = 't:' + (k.topic || 'uncategorized');
    const base = topicAngle.has(tid) ? topicAngle.get(tid) : 0;
    const idx = perTopic.get(tid) || 0;
    perTopic.set(tid, idx + 1);
    const ring = inner + 44 + Math.floor(idx / 8) * 38;
    const angle = base + (((idx % 8) / 8) - 0.5) * 1.05;
    k.x = Math.cos(angle) * ring; k.y = Math.sin(angle) * ring;
  });
  concepts.forEach((c, i) => {
    const label = String(c.label || '').toLowerCase();
    const linked = knowledge.filter((k) => String(k.title || '').toLowerCase().includes(label)).slice(0, 12);
    if (linked.length) {
      c.x = linked.reduce((sum, k) => sum + k.x, 0) / linked.length + Math.cos(i * 2.4) * 32;
      c.y = linked.reduce((sum, k) => sum + k.y, 0) / linked.length + Math.sin(i * 2.4) * 32;
    } else {
      const a = i * 0.9, r = inner + 230;
      c.x = Math.cos(a) * r; c.y = Math.sin(a) * r;
    }
  });
  sources.forEach((s, i) => {
    const label = String(s.label || '');
    const linked = knowledge.filter((k) => k.source_url && String(k.source_url).includes(label));
    if (linked.length) {
      s.x = linked.reduce((sum, k) => sum + k.x, 0) / linked.length;
      s.y = linked.reduce((sum, k) => sum + k.y, 0) / linked.length + 46;
    } else {
      const a = -i * 0.7, r = inner + 300;
      s.x = Math.cos(a) * r; s.y = Math.sin(a) * r;
    }
  });
  nodes.forEach((n, i) => {
    if (typeof n.x !== 'number' || typeof n.y !== 'number') {
      const a = i * 0.8, r = inner + 310;
      n.x = Math.cos(a) * r; n.y = Math.sin(a) * r;
    }
  });
  // Light deterministic separation so labels/nodes do not stack.
  for (let pass = 0; pass < 20; pass++) {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 > 3600) continue;
        if (d2 < 1) { dx = 0.7; dy = 0.4; d2 = 1; }
        const d = Math.sqrt(d2);
        const push = (60 - d) * 0.045;
        dx /= d; dy /= d;
        a.x -= dx * push; a.y -= dy * push;
        b.x += dx * push; b.y += dy * push;
      }
    }
  }
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return { nodes, edges: data.edges || [], byId, stats: data.stats || {} };
}

function fillGraphSelect(id, values, current) {
  const el = $(id);
  if (!el) return;
  const keep = current != null ? current : el.value;
  el.innerHTML = '<option value="">' + (id === 'graphTopic' ? 'All topics' : 'All verification') + '</option>' +
    values.map((v) => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
  if (values.includes(keep)) el.value = keep;
}

function graphStatRow(label, value) {
  return '<div class="graph-stat"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
}

function renderGraphSummary(stats) {
  const counts = stats.counts || {};
  if ($('graphNodeTag')) $('graphNodeTag').textContent = num(stats.nodes || 0) + ' NODES';
  if ($('graphStats')) {
    $('graphStats').innerHTML =
      graphStatRow('Knowledge nodes', num(counts.knowledge || 0)) +
      graphStatRow('Topic nodes', num(counts.topic || 0)) +
      graphStatRow('Source domains', num(counts.source || 0)) +
      graphStatRow('Concept keywords', num(counts.concept || 0)) +
      graphStatRow('Relationships', num(stats.edges || 0)) +
      graphStatRow('Verified records', num(stats.verified || 0));
  }
  if ($('graphBars')) {
    const topics = stats.topics || [];
    const max = Math.max(1, ...topics.map((t) => Number(t.count || 0)));
    $('graphBars').innerHTML = topics.slice(0, 14).map((t) => (
      '<div class="gbar"><span>' + esc(clip(t.topic, 28)) + '</span>' +
      '<div class="track"><div class="fill" style="width:' + Math.round(Number(t.count || 0) / max * 100) + '%"></div></div>' +
      '<b>' + Number(t.count || 0) + '</b></div>'
    )).join('') || '<div class="empty">No stored topics yet.</div>';
  }
  if ($('graphLegend')) {
    $('graphLegend').innerHTML = [
      ['knowledge', 'Knowledge'], ['topic', 'Topic'], ['source', 'Source domain'], ['concept', 'Concept keyword']
    ].map(([key, label]) => '<span class="legend"><i style="background:' + GRAPH_COLORS[key] + '"></i>' + label + '</span>').join('') +
      '<span class="legend"><i style="background:#39ff9a"></i>Corroborated</span>' +
      '<span class="legend"><i style="background:#fbbf24"></i>User reported</span>';
  }
}

async function loadGraph() {
  try {
    const qs = new URLSearchParams();
    qs.set('limit', '220');
    const topic = $('graphTopic') ? $('graphTopic').value : '';
    const verification = $('graphVerification') ? $('graphVerification').value : '';
    if (topic) qs.set('topic', topic);
    if (verification) qs.set('verification', verification);
    const data = await api('/knowledge/graph?' + qs.toString());
    const layout = layoutGraph(data);
    const g = state.graph;
    g.nodes = layout.nodes; g.edges = layout.edges; g.byId = layout.byId; g.stats = layout.stats;
    g.selected = null; g.hover = null; g.dragging = null; g.pointer = null;
    g.scale = 1; g.offsetX = 0; g.offsetY = 0;
    fillGraphSelect('graphTopic', (layout.stats.topics || []).map((t) => t.topic), topic);
    fillGraphSelect('graphVerification', ['corroborated', 'single-source', 'web-learned', 'user-reported', 'unverified'], verification);
    renderGraphSummary(layout.stats);
    if ($('graphInspector')) $('graphInspector').classList.add('hidden');
    startGraphLoop();
  } catch (e) { toast(e.message, 'error'); }
}

function graphSize() {
  const canvas = $('graphCanvas');
  if (!canvas) return null;
  const wrap = canvas.parentElement;
  const rect = wrap.getBoundingClientRect();
  const w = Math.max(320, Math.floor(rect.width));
  const h = Math.max(300, Math.floor(rect.height || 540));
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const targetW = Math.floor(w * dpr), targetH = Math.floor(h * dpr);
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }
  return { canvas, w, h, dpr };
}

function graphScreenToWorld(sx, sy) {
  const g = state.graph;
  const view = g.view || { w: 800, h: 540 };
  return { x: (sx - view.w / 2 - g.offsetX) / g.scale,
           y: (sy - view.h / 2 - g.offsetY) / g.scale };
}

function graphHitTest(sx, sy) {
  const g = state.graph;
  const view = g.view || { w: 800, h: 540 };
  let best = null, bestDist = Infinity;
  for (const node of g.nodes) {
    const nx = view.w / 2 + g.offsetX + node.x * g.scale;
    const ny = view.h / 2 + g.offsetY + node.y * g.scale;
    const d = Math.hypot(nx - sx, ny - sy);
    const radius = Math.max(7, graphNodeRadius(node) * g.scale + 5);
    if (d <= radius && d < bestDist) { best = node; bestDist = d; }
  }
  return best;
}

function graphNodeScreen(node) {
  const g = state.graph;
  const view = g.view || { w: 800, h: 540 };
  return { x: view.w / 2 + g.offsetX + node.x * g.scale,
           y: view.h / 2 + g.offsetY + node.y * g.scale };
}

function drawGraph(now) {
  const sized = graphSize();
  if (!sized) return;
  const { canvas, w, h, dpr } = sized;
  state.graph.view = { w, h };
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const g = state.graph;
  const bg = ctx.createRadialGradient(w / 2, h / 2, 40, w / 2, h / 2, Math.max(w, h) / 1.25);
  bg.addColorStop(0, 'rgba(11,22,34,0.96)');
  bg.addColorStop(1, 'rgba(5,9,15,0.99)');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  const filter = (($('graphSearch') || {}).value || '').trim().toLowerCase();
  const selected = g.selected;
  const hover = g.hover;
  const pulse = 0.5 + Math.sin((now || 0) / 900) * 0.5;

  // Edges
  ctx.lineWidth = 1;
  for (const edge of g.edges) {
    const a = g.byId.get(edge.source), b = g.byId.get(edge.target);
    if (!a || !b) continue;
    const sa = graphNodeScreen(a), sb = graphNodeScreen(b);
    const dimA = filter && !String(a.label || '').toLowerCase().includes(filter);
    const dimB = filter && !String(b.label || '').toLowerCase().includes(filter);
    ctx.strokeStyle = EDGE_COLORS[edge.relation] || 'rgba(120,150,170,0.12)';
    if (dimA && dimB) ctx.strokeStyle = 'rgba(120,150,170,0.045)';
    ctx.beginPath();
    ctx.moveTo(sa.x, sa.y);
    ctx.lineTo(sb.x, sb.y);
    ctx.stroke();
  }

  // Nodes
  for (const node of g.nodes) {
    const pos = graphNodeScreen(node);
    if (pos.x < -80 || pos.y < -80 || pos.x > w + 80 || pos.y > h + 80) continue;
    const radius = Math.max(2.5, graphNodeRadius(node) * g.scale);
    const base = node.type === 'knowledge' ? knowledgeNodeColor(node) : (GRAPH_COLORS[node.type] || '#8fa3b8');
    const dim = filter && !String(node.label || '').toLowerCase().includes(filter);
    const active = node === selected || node === hover;
    ctx.globalAlpha = dim ? 0.16 : (node.type === 'knowledge' ? 0.9 : 1);
    if (active || node.type === 'topic') {
      ctx.shadowColor = base;
      ctx.shadowBlur = active ? 22 : 10 + pulse * 8;
    } else {
      ctx.shadowBlur = 0;
    }
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
    if (active) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius + 3, 0, Math.PI * 2);
      ctx.stroke();
    }
    const showLabel = !dim && (node.type === 'topic' || node.type === 'source' || active || g.scale >= 0.95);
    if (showLabel) {
      ctx.globalAlpha = dim ? 0.2 : 0.92;
      ctx.fillStyle = '#dbe7f3';
      ctx.font = (node.type === 'topic' ? '600 11px ' : '10px ') + 'JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(String(node.label || ''), pos.x, pos.y + radius + 12);
    }
  }
  ctx.globalAlpha = 1;
  ctx.shadowBlur = 0;
}

function startGraphLoop() {
  if (!state.graph.active || state.graph.raf) return;
  const tick = (ts) => {
    if (!state.graph.active) { state.graph.raf = null; return; }
    if (!state.graph.last || ts - state.graph.last > 33) {
      state.graph.last = ts;
      if (state.graph.nodes.length) drawGraph(ts);
    }
    state.graph.raf = requestAnimationFrame(tick);
  };
  state.graph.raf = requestAnimationFrame(tick);
}

function filterGraph() { startGraphLoop(); }

function resetGraphView() {
  const g = state.graph;
  g.scale = 1; g.offsetX = 0; g.offsetY = 0; g.selected = null; g.hover = null;
  if ($('graphInspector')) $('graphInspector').classList.add('hidden');
  startGraphLoop();
}

function selectGraphNode(node) {
  const g = state.graph;
  g.selected = node;
  const box = $('graphInspector');
  if (!box) return;
  box.classList.remove('hidden');
  let body = '';
  if (node.type === 'knowledge') {
    body =
      '<div class="inspector-kicker">KNOWLEDGE NODE</div>' +
      '<h4>' + esc(node.label) + '</h4>' +
      '<div class="knowledge-meta">' + esc(node.topic || 'uncategorized') + ' · ' +
      esc(String(node.verification || 'unverified').toUpperCase()) + '</div>' +
      '<p class="muted">Stored ' + esc(when(node.created_at)) + '</p>' +
      (node.source_url ? '<a href="' + esc(node.source_url) + '" target="_blank" rel="noopener">Open source ↗</a>' : '<p class="muted">No external source URL.</p>') +
      '<button class="secondary small" data-title="' + esc(node.label) + '" onclick="openHistoryFor(this.dataset.title)">Find in history ↗</button>';
  } else {
    const label = node.type === 'topic' ? 'TOPIC NODE' : (node.type === 'source' ? 'SOURCE DOMAIN' : 'CONCEPT KEYWORD');
    const connections = g.edges.filter((e) => e.source === node.id || e.target === node.id).length;
    body =
      '<div class="inspector-kicker">' + label + '</div>' +
      '<h4>' + esc(node.label) + '</h4>' +
      '<div class="graph-stat"><span>Connections</span><b>' + connections + '</b></div>' +
      '<p class="muted">This node is derived from stored knowledge records, not generated.</p>';
  }
  box.innerHTML = '<button class="inspector-close" onclick="document.getElementById(\'graphInspector\').classList.add(\'hidden\')">✕</button>' + body;
}

function graphPointerPosition(event) {
  const canvas = $('graphCanvas');
  const rect = canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function bindGraphCanvas() {
  const canvas = $('graphCanvas');
  if (!canvas || canvas.dataset.bound) return;
  canvas.dataset.bound = '1';
  canvas.addEventListener('pointerdown', (event) => {
    const p = graphPointerPosition(event);
    const g = state.graph;
    canvas.setPointerCapture(event.pointerId);
    const hit = graphHitTest(p.x, p.y);
    if (hit) {
      const world = graphScreenToWorld(p.x, p.y);
      g.dragging = { node: hit, ox: hit.x - world.x, oy: hit.y - world.y, moved: false };
      g.hover = hit;
    } else {
      g.pointer = { x: p.x, y: p.y };
    }
    canvas.style.cursor = hit ? 'grabbing' : 'grabbing';
  });
  canvas.addEventListener('pointermove', (event) => {
    const p = graphPointerPosition(event);
    const g = state.graph;
    if (g.dragging) {
      const world = graphScreenToWorld(p.x, p.y);
      g.dragging.node.x = world.x + g.dragging.ox;
      g.dragging.node.y = world.y + g.dragging.oy;
      g.dragging.moved = true;
    } else if (g.pointer) {
      g.offsetX += p.x - g.pointer.x;
      g.offsetY += p.y - g.pointer.y;
      g.pointer = { x: p.x, y: p.y };
    } else {
      g.hover = graphHitTest(p.x, p.y);
      canvas.style.cursor = g.hover ? 'pointer' : 'grab';
    }
  });
  const release = (event) => {
    const g = state.graph;
    try { canvas.releasePointerCapture(event.pointerId); } catch { }
    if (g.dragging && !g.dragging.moved) selectGraphNode(g.dragging.node);
    g.dragging = null;
    g.pointer = null;
    canvas.style.cursor = 'grab';
  };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('pointerleave', () => { state.graph.hover = null; });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    const p = graphPointerPosition(event);
    const g = state.graph;
    const world = graphScreenToWorld(p.x, p.y);
    g.scale = Math.max(0.22, Math.min(3.2, g.scale * (event.deltaY < 0 ? 1.12 : 0.89)));
    const view = g.view || { w: 800, h: 540 };
    g.offsetX = p.x - view.w / 2 - world.x * g.scale;
    g.offsetY = p.y - view.h / 2 - world.y * g.scale;
    startGraphLoop();
  }, { passive: false });
  canvas.style.cursor = 'grab';
}

/* --------------------------------------------------------- autonomous learning */
function renderAutoTopics(topics) {
  if (!$('autoTopicList')) return;
  $('autoTopicList').innerHTML = (topics || []).slice(0, 40).map((t) => (
    '<div class="auto-topic"><div><b>' + esc(clip(t.topic, 70)) + '</b>' +
    '<small>' + esc(String(t.status || 'pending').toUpperCase()) + ' · priority ' + (t.priority || 5) +
    ' · ' + esc(t.source || 'curated') + '</small></div>' +
    '<button class="textbtn danger-text" onclick="removeAutoTopic(' + t.id + ')">Remove</button></div>'
  )).join('') || '<div class="empty">No topics queued. Add one or let NEXUS discover a topic.</div>';
}

function renderAutoSessions(sessions) {
  if (!$('autoSessionList')) return;
  $('autoSessionList').innerHTML = (sessions || []).map((s) => (
    '<div class="event auto-session"><i class="' + (s.status === 'completed' ? 'ok' : (s.status === 'failed' ? 'bad' : '')) + '"></i>' +
    '<div><b>' + esc(clip(s.topic, 80)) + '</b><small>' +
    esc(String(s.status || '').toUpperCase()) + ' · ' + (s.pages_learned || 0) + '/' + (s.pages_visited || 0) +
    ' pages · +' + (s.knowledge_added || 0) + ' knowledge · ' + (s.errors || 0) + ' errors' +
    (s.detail ? ' · ' + esc(clip(s.detail, 90)) : '') + '</small></div>' +
    '<time>' + esc(when(s.started_at)) + '</time></div>'
  )).join('') || '<div class="empty">No autonomous sessions yet.</div>';
}

function renderAutoStatus(data) {
  state.auto = data;
  const current = data.state || {};
  const stats = data.stats || {};
  const settings = data.settings || {};
  if ($('autoStateTag')) $('autoStateTag').textContent = current.running ? (current.paused ? 'PAUSED' : 'LEARNING') : 'IDLE';
  if ($('autoPhase')) $('autoPhase').textContent = String(current.phase || (current.running ? 'working' : 'idle')).toUpperCase();
  if ($('autoTopic')) $('autoTopic').textContent = current.topic || 'No learning session';
  if ($('autoUrl')) $('autoUrl').textContent = current.current_url || current.last_error || 'Waiting for start…';
  if ($('autoCore')) $('autoCore').dataset.state = current.running ? (current.paused ? 'paused' : 'learning') : 'idle';
  if ($('autoKnowledge')) $('autoKnowledge').textContent = num(stats.knowledge_auto);
  if ($('autoSources')) $('autoSources').textContent = num(stats.sources_discovered);
  if ($('autoPagesDone')) $('autoPagesDone').textContent = num(stats.pages_analyzed);
  if ($('autoSessions')) $('autoSessions').textContent = num(stats.sessions_completed);
  if ($('autoSuccess')) $('autoSuccess').textContent = (stats.success_rate || 0) + '% success';
  if ($('autoTopics')) $('autoTopics').textContent = num(stats.topics_explored);
  if ($('autoFailures')) $('autoFailures').textContent = num((stats.pages_failed || 0) + (stats.sessions_failed || 0));
  if ($('autoAllowlist')) {
    const allow = data.allowlist || [];
    $('autoAllowlist').textContent = allow.length
      ? 'Allowlist restricted to: ' + allow.join(', ')
      : 'Allowlist: all public HTTPS destinations';
  }
  if ($('autoSpeed') && document.activeElement !== $('autoSpeed')) $('autoSpeed').value = (data.speed || {}).name || 'normal';
  if ($('autoPages') && document.activeElement !== $('autoPages')) $('autoPages').value = settings.pages_per_session || 5;
  renderAutoTopics(data.topics);
  renderAutoSessions(data.sessions);
}

async function loadAutonomous() {
  try {
    const data = await api('/autonomous/status');
    renderAutoStatus(data);
  } catch (e) { toast(e.message, 'error'); }
}

function startAutoPolling() {
  stopAutoPolling();
  state.autoTimer = setInterval(() => {
    if ($('autonomous') && $('autonomous').classList.contains('active')) loadAutonomous();
  }, 4000);
}
function stopAutoPolling() {
  if (state.autoTimer) clearInterval(state.autoTimer);
  state.autoTimer = null;
}

async function autonomousAction(action) {
  try {
    let body = {};
    if (action === 'start') {
      const topic = $('autoTopicInput') ? $('autoTopicInput').value.trim() : '';
      body = { topic: topic || null, mode: 'topic' };
    }
    const data = await api('/autonomous/' + action, { method: 'POST', body: JSON.stringify(body) });
    if (action === 'start' && $('autoTopicInput')) $('autoTopicInput').value = '';
    toast('Autonomous learning: ' + action + '.');
    if (data && data.state) renderAutoStatus(data);
    loadAutonomous();
    refresh();
  } catch (e) { toast(e.message, 'error'); }
}

async function saveAutoSettings() {
  try {
    const payload = {
      learning_speed: $('autoSpeed') ? $('autoSpeed').value : 'normal',
      learning_pages_per_session: $('autoPages') ? Number($('autoPages').value) : 5
    };
    await api('/settings', { method: 'POST', body: JSON.stringify(payload) });
    toast('Learning speed saved.');
    loadAutonomous();
  } catch (e) { toast(e.message, 'error'); }
}

async function addAutoTopic() {
  const input = $('autoTopicAdd');
  const topic = input ? input.value.trim() : '';
  if (!topic) return toast('Type a learning topic first.', 'warn');
  try {
    await api('/autonomous/topics', { method: 'POST', body: JSON.stringify({ topic }) });
    input.value = '';
    toast('Topic queued.');
    loadAutonomous();
  } catch (e) { toast(e.message, 'error'); }
}

async function removeAutoTopic(id) {
  try {
    await api('/autonomous/topics/' + id, { method: 'DELETE' });
    loadAutonomous();
  } catch (e) { toast(e.message, 'error'); }
}

async function discoverTopics() {
  try {
    const result = await api('/autonomous/topics/discover', { method: 'POST', body: '{}' });
    toast('Discovered: ' + ((result.created || []).join(', ') || 'no new topic'));
    loadAutonomous();
  } catch (e) { toast(e.message, 'error'); }
}

/* ----------------------------------------------------------- learning history */
function historyCard(k) {
  const verification = String(k.verification_status || 'unverified');
  const status = verification === 'user-reported' || String(k.source_url || '').startsWith('user:')
    ? 'USER REPORTED' : (k.source_url ? 'WEB LEARNED' : 'LOCAL / RESEARCH');
  const full = esc(k.content || '');
  return '<article class="knowledge-card history-card">' +
    '<button class="delete" onclick="deleteKnowledgeHistory(' + k.id + ')">Delete</button>' +
    '<div class="knowledge-meta">' + esc(k.topic || 'uncategorized') + ' · ' + esc(status) + ' · ' + esc(verification.toUpperCase()) + '</div>' +
    '<h4>' + esc(k.title || 'Untitled') + '</h4>' +
    '<p>' + esc(clip(k.content || '', 620)) + '</p>' +
    (String(k.content || '').length > 680 ? '<details><summary class="knowledge-meta">Expand extracted text</summary><p>' + full + '</p></details>' : '') +
    '<div class="knowledge-meta">' + esc(when(k.created_at)) + ' · confidence ' + (Number(k.confidence || 0) * 100).toFixed(0) + '%' +
    (k.session_id ? ' · session #' + k.session_id : '') + '</div>' +
    (k.source_url ? '<a href="' + esc(k.source_url) + '" target="_blank" rel="noopener">' + esc(clip(k.source_url, 110)) + ' ↗</a>' : '') +
    '</article>';
}

async function loadHistory() {
  try {
    const params = new URLSearchParams();
    if ($('historySearch')) params.set('q', $('historySearch').value.trim());
    if ($('historyTopic')) params.set('topic', $('historyTopic').value);
    if ($('historyVerification')) params.set('verification', $('historyVerification').value);
    if ($('historyStatus')) params.set('status', $('historyStatus').value);
    params.set('limit', '250');
    const data = await api('/knowledge/history?' + params.toString());
    const topicEl = $('historyTopic'), verifyEl = $('historyVerification');
    if (topicEl) {
      const keep = topicEl.value;
      topicEl.innerHTML = '<option value="">All topics</option>' +
        (data.topics || []).map((t) => '<option value="' + esc(t) + '">' + esc(t) + '</option>').join('');
      topicEl.value = (data.topics || []).includes(keep) ? keep : '';
    }
    if (verifyEl) {
      const keep = verifyEl.value;
      verifyEl.innerHTML = '<option value="">All verification</option>' +
        (data.verifications || []).map((v) => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
      verifyEl.value = (data.verifications || []).includes(keep) ? keep : '';
    }
    if ($('historyCount')) $('historyCount').textContent = num(data.total) + ' RECORDS';
    if ($('historyList')) {
      $('historyList').innerHTML = (data.items || []).map(historyCard).join('') ||
        '<div class="empty">No records match these filters. Learn a URL or start autonomous learning.</div>';
    }
  } catch (e) { toast(e.message, 'error'); }
}
const debouncedHistory = debounce(() => loadHistory(), 350);

function openHistoryFor(title) {
  showPage('history');
  setTimeout(() => {
    if ($('historySearch')) $('historySearch').value = title || '';
    loadHistory();
  }, 80);
}

async function deleteKnowledgeHistory(id) {
  if (!confirm('Delete this learning record from the knowledge base?')) return;
  try {
    await api('/knowledge/' + id, { method: 'DELETE' });
    toast('Record deleted.');
    loadHistory(); refresh();
  } catch (e) { toast(e.message, 'error'); }
}

/* ------------------------------------------------------------- system monitor */
function monitorRow(label, value) {
  return '<div class="graph-stat"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
}

async function loadMonitor() {
  try {
    const [s, events] = await Promise.all([api('/status'), api('/events')]);
    const hw = s.hardware || {};
    const provider = s.provider || {};
    const perms = s.permissions || {};
    if ($('monBackend')) $('monBackend').textContent = 'ONLINE';
    if ($('monEngine')) $('monEngine').textContent = String(provider.label || 'NEXUS CORE').toUpperCase();
    if ($('monEngineSub')) $('monEngineSub').textContent = provider.online ? 'ready' : 'offline';
    if ($('monKnowledge')) $('monKnowledge').textContent = num(s.knowledge_count);
    if ($('monChunks')) $('monChunks').textContent = num(s.web_chunk_count);
    if ($('monEvents')) $('monEvents').textContent = num(events.length);
    if ($('monPerms')) $('monPerms').textContent = ['internet', 'pc_read', 'pc_write', 'shell'].filter((k) => perms[k]).length + '/4';
    if ($('monHwTitle')) $('monHwTitle').textContent = (hw.ram_gb ? hw.ram_gb + ' GB RAM' : 'Hardware profile') +
      (hw.cpu_threads ? ' · ' + hw.cpu_threads + ' threads' : '');
    if ($('monHwText')) $('monHwText').textContent = hw.gpu || hw.recommendation || 'No GPU recommendation available.';
    if ($('monHwGrid')) {
      $('monHwGrid').innerHTML = Object.entries(hw).filter(([, v]) => v != null && typeof v !== 'object')
        .slice(0, 8).map(([k, v]) => monitorRow(k.replace(/_/g, ' '), v)).join('') || '<div class="empty">No hardware data.</div>';
    }
    if ($('monProvider')) $('monProvider').textContent = String(provider.label || 'NEXUS CORE').toUpperCase();
    if ($('monProviderText')) $('monProviderText').textContent = provider.detail || provider.tagline || '';
    if ($('monProviderMeta')) {
      $('monProviderMeta').innerHTML =
        monitorRow('Online', provider.online ? 'yes' : 'no') +
        monitorRow('Kind', provider.kind || 'native') +
        monitorRow('Models', (provider.models || []).length) +
        monitorRow('Selected', provider.selected ? 'yes' : 'no');
    }
    const warnings = events.filter((e) => /warning|error|failed|blocked/i.test(String(e.kind)));
    if ($('monErrors')) $('monErrors').innerHTML = warnings.slice(0, 12).map(eventHTML).join('') ||
      '<div class="empty">No warnings recorded.</div>';
    if ($('monEventsList')) $('monEventsList').innerHTML = events.slice(0, 12).map(eventHTML).join('') ||
      '<div class="empty">No events recorded.</div>';
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
  sChunkOverlap: 'repo_chunk_overlap', sLearnDepth: 'learn_depth', sLearnLinks: 'learn_max_links',
  sWebChars: 'web_chunk_chars', sWebOverlap: 'web_chunk_overlap', sWebPages: 'max_web_pages',
  sSkillContext: 'skills_auto_context', sSkillsRepo: 'skills_repo',
  sLearningSpeed: 'learning_speed', sLearningPages: 'learning_pages_per_session',
  sLearningInterval: 'learning_session_interval_seconds', sLearningRandom: 'learning_random',
  sLearningVerify: 'learning_auto_verify', sLearningResume: 'learning_resume',
  sLearningTopics: 'learning_topics', sCodegenProvider: 'codegen_provider',
  sCodeExecTimeout: 'code_exec_timeout',
  sApEnabled: 'autoprogramming_enabled', sApLanguages: 'autoprogramming_languages',
  sApDifficulty: 'autoprogramming_difficulty', sApInterval: 'autoprogramming_interval_seconds',
  sApConcepts: 'autoprogramming_concepts_per_cycle', sApInternet: 'autoprogramming_use_internet',
  sApAssess: 'autoprogramming_auto_assess', sExplorationCategories: 'exploration_categories',
  sExplorationInterval: 'exploration_interval_seconds', sExplorationSites: 'exploration_sites_per_cycle',
  sReviewAuto: 'review_auto', sReviewMinScore: 'review_min_score',
  sProjectAutoTest: 'project_auto_test'
};
const BOOLEAN_SETTINGS = ['auto_resume', 'skills_auto_context', 'learning_random',
  'learning_auto_verify', 'learning_resume', 'autoprogramming_enabled',
  'autoprogramming_use_internet', 'autoprogramming_auto_assess', 'review_auto', 'project_auto_test'];
async function loadSettings() {
  try {
    const s = await api('/settings');
    Object.entries(SETTING_MAP).forEach(([id, key]) => {
      const el = $(id);
      if (!el) return;
      if (BOOLEAN_SETTINGS.includes(key)) {
        el.value = String(s[key]).toLowerCase() === 'true' ? 'true' : 'false';
      } else {
        el.value = s[key] != null ? s[key] : '';
      }
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
      'max_repo_files', 'max_repo_file_kb', 'max_repo_mb', 'repo_chunk_lines', 'repo_chunk_overlap',
      'learn_depth', 'learn_max_links', 'web_chunk_chars', 'web_chunk_overlap', 'max_web_pages',
      'learning_pages_per_session', 'learning_session_interval_seconds', 'code_exec_timeout',
      'autoprogramming_interval_seconds', 'autoprogramming_concepts_per_cycle',
      'exploration_interval_seconds', 'exploration_sites_per_cycle', 'review_min_score']);
    const booleans = new Set(BOOLEAN_SETTINGS);
    const payload = {};
    Object.entries(SETTING_MAP).forEach(([id, key]) => {
      const el = $(id);
      if (!el) return;
      if (booleans.has(key)) payload[key] = el.value === 'true';
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

/* ---------------------------------------------------------------- code studio */
const debouncedProgramDetect = debounce(() => detectProgramTemplates(), 450);

function codegenLabel(value) {
  const v = String(value || 'auto').toLowerCase();
  if (v === 'off' || v === 'none' || v === 'disabled') return 'CODEGEN OFF';
  if (v === 'auto') return 'CODEGEN AUTO';
  return 'CODEGEN ' + v.toUpperCase();
}

function renderProgramStatus(status) {
  if (!status) return;
  state.programStatus = status;
  if ($('progCountTag')) $('progCountTag').textContent = num(status.total) + ' PROGRAMS';
  if ($('progProviderTag')) $('progProviderTag').textContent = codegenLabel(status.codegen_provider);
  if ($('progShellTag')) {
    $('progShellTag').textContent = status.shell ? 'SHELL ON' : 'SHELL OFF';
    $('progShellTag').classList.toggle('on', !!status.shell);
  }
}

function programCard(program) {
  const status = String(program.status || 'unverified');
  const stateLabel = program.verified ? 'VERIFIED' : status.replace(/_/g, ' ').toUpperCase();
  let stateClass = 'program-state';
  if (!program.verified) {
    if (/fail|error/.test(status)) stateClass += ' failed';
    else if (program.source === 'model') stateClass += ' model';
    else stateClass += ' draft';
  }
  const active = state.currentProgram && state.currentProgram.id === program.id ? ' active' : '';
  return '<div class="program-card' + active + '" data-program="' + program.id + '">' +
    '<span class="' + stateClass + '">' + esc(stateLabel) + '</span>' +
    '<h4>' + esc(program.name || 'Program') + '</h4>' +
    '<small>' + esc(program.language || '?') + ' · ' + esc(program.kind || 'script') + ' · ' +
    (program.source === 'model' ? 'MODEL' : 'RECIPE') + ' · ' + esc(when(program.created_at)) + '</small>' +
    '<small>' + esc(clip(program.request || '', 160)) + '</small>' +
    '</div>';
}

function renderProgramList() {
  const list = $('programList');
  if (!list) return;
  list.innerHTML = state.programs.map(programCard).join('') ||
    '<div class="empty">No programs yet. Write one on the left.</div>';
}

async function loadPrograms() {
  const data = await api('/programs');
  state.programs = data.programs || [];
  renderProgramStatus(data.status);
  renderProgramList();
}

async function loadProgramRecipes() {
  try {
    const data = await api('/programs/recipes');
    state.programRecipes = data.recipes || [];
    renderProgramStatus(data.status);
    const select = $('programRecipe');
    const current = select.value;
    select.innerHTML = '<option value="">Auto-detect</option>' + state.programRecipes.map((recipe) =>
      '<option value="' + esc(recipe.id) + '">' + esc(recipe.title) + ' · ' + esc(recipe.language) + '</option>'
    ).join('');
    if (state.programRecipes.some((recipe) => recipe.id === current)) select.value = current;
    renderProgramRecipeChips();
  } catch (e) {
    if ($('programRecipes')) $('programRecipes').innerHTML = '<div class="empty">' + esc(e.message) + '</div>';
  }
}

function renderProgramRecipeChips() {
  const box = $('programRecipes');
  if (!box) return;
  const selected = $('programRecipe') ? $('programRecipe').value : '';
  box.innerHTML = state.programRecipes.map((recipe) => (
    '<button class="chip program-chip' + (recipe.id === selected ? ' on' : '') + '" data-recipe="' +
    esc(recipe.id) + '" title="' + esc((recipe.summary || '') + ' — ' + (recipe.language || '') + ' ' + (recipe.kind || '')) + '">' +
    esc(recipe.title) + ' · ' + esc(recipe.language) + '</button>'
  )).join('') || '<div class="empty">No templates available.</div>';
}

function applyRecipeSelection() {
  renderProgramRecipeChips();
}

async function detectProgramTemplates() {
  const request = $('programRequest').value.trim();
  const box = $('programMatches');
  if (!box) return;
  if (!request) {
    box.innerHTML = '<div class="empty">Type a request to see matching templates.</div>';
    return;
  }
  try {
    const data = await api('/programs/detect', { method: 'POST', body: JSON.stringify({ request }) });
    const matches = data.matches || [];
    box.innerHTML = matches.map((match) => (
      '<button class="chip program-chip" data-recipe="' + esc(match.id) + '" title="' +
      esc(match.summary || '') + '">' + esc(match.title) + ' · ' + esc(match.language) + ' · ' +
      Number(match.score || 0).toFixed(1) + '</button>'
    )).join('') || '<div class="empty">No offline template matches. A local model will be used if one is configured.</div>';
  } catch (e) {
    box.innerHTML = '<div class="empty">' + esc(e.message) + '</div>';
  }
}

async function forgeProgram() {
  const button = $('programBuildBtn');
  const progress = $('programProgress');
  const select = $('programRecipe');
  const recipeId = select.value || null;
  let request = $('programRequest').value.trim();
  if (!request && recipeId) {
    request = 'Offline template: ' + (select.options[select.selectedIndex]?.text || recipeId);
  }
  if (!request) return toast('Describe the program you want, or pick a template.', 'warn');
  button.disabled = true;
  button.textContent = '⌬ Writing…';
  progress.classList.remove('hidden');
  progress.textContent = 'Writing real files, then verifying them. Model generation can take a minute.';
  try {
    const data = await api('/programs/generate', {
      method: 'POST',
      body: JSON.stringify({
        request,
        recipe_id: recipeId,
        provider: $('programProvider').value || null
      })
    });
    const program = data.program;
    progress.textContent = 'DONE · program #' + program.id + ' · ' + program.status +
      (program.verified ? ' · self-tests passed' : ' · not executed');
    toast('Program #' + program.id + ' written' + (program.verified ? ' and verified.' : '. Check the verification report.'),
      program.verified ? '' : 'warn');
    $('programRequest').value = '';
    select.value = '';
    renderProgramRecipeChips();
    await loadPrograms();
    await openProgram(program.id);
  } catch (e) {
    progress.textContent = 'ERROR · ' + e.message;
    toast(e.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = '⌬ Write program';
  }
}

function renderProgramFiles() {
  const box = $('programFiles');
  if (!box) return;
  box.innerHTML = state.programFiles.map((name) => (
    '<button class="program-file' + (name === state.programFile ? ' active' : '') + '" data-file="' +
    esc(name) + '">' + esc(name) + '</button>'
  )).join('');
}

function renderProgramDetail(program) {
  state.currentProgram = program;
  state.programFiles = program.files || [];
  $('programDetail').classList.remove('hidden');
  $('programDetailName').textContent = program.name || 'Program';
  $('programDetailMeta').textContent = '#' + program.id + ' · ' + (program.language || '?') + ' · ' +
    (program.kind || 'script') + ' · ' + (program.source === 'model' ? 'model-generated' : 'offline recipe') +
    ' · ' + when(program.created_at);
  const tag = $('programStatusTag');
  tag.textContent = program.verified ? 'VERIFIED' : String(program.status || 'unverified').replace(/_/g, ' ').toUpperCase();
  tag.classList.toggle('on', !!program.verified);
  $('programPreviewBtn').classList.toggle('hidden', program.language !== 'html');
  $('programVerification').textContent = program.verification || 'No verification report yet.';
  $('programOutput').textContent = program.last_output || 'No runs yet.';
  if (!state.programFiles.includes(state.programFile)) state.programFile = state.programFiles[0] || '';
  renderProgramFiles();
  if (state.programFile) openProgramFile(state.programFile);
  renderProgramList();
}

async function openProgram(id) {
  try {
    const program = await api('/programs/' + id);
    $('programPreview').classList.add('hidden');
    $('programPreviewFrame').src = 'about:blank';
    renderProgramDetail(program);
    $('programDetail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { toast(e.message, 'error'); }
}

async function openProgramFile(name) {
  if (!state.currentProgram) return;
  try {
    const file = await api('/programs/' + state.currentProgram.id + '/file?name=' + encodeURIComponent(name));
    state.programFile = file.name;
    state.programContent = file.content || '';
    $('programFilePath').textContent = file.name + ' · ' + num(state.programContent.length) + ' chars';
    $('programCode').textContent = clip(state.programContent, 400000);
    renderProgramFiles();
  } catch (e) { toast(e.message, 'error'); }
}

function copyProgramCode() {
  const text = $('programCode').textContent || '';
  navigator.clipboard.writeText(text).then(() => toast('Code copied.')).catch(() => toast('Clipboard blocked.', 'warn'));
}

function downloadProgramFile() {
  if (!state.programFile || !state.currentProgram) return;
  download(state.programFile, state.programContent || '', 'text/plain');
}

function previewProgram() {
  const program = state.currentProgram;
  if (!program) return;
  if (program.language !== 'html') return toast('Preview is only available for HTML programs.', 'warn');
  const name = state.programFile && state.programFile.endsWith('.html') ? state.programFile : program.entry;
  const frame = $('programPreviewFrame');
  frame.src = '/api/programs/' + program.id + '/raw/' + encodeURIComponent(name) + '?t=' + Date.now();
  $('programPreview').classList.remove('hidden');
  toast('Previewing ' + name + ' in a sandboxed iframe.');
}

async function verifyProgram() {
  const program = state.currentProgram;
  if (!program) return;
  $('programVerification').textContent = 'Verifying…';
  try {
    const updated = await api('/programs/' + program.id + '/verify', { method: 'POST', body: '{}' });
    renderProgramDetail(updated);
    await loadPrograms();
    toast(updated.verified ? 'Self-tests passed. Program verified.' : 'Verification finished: ' + updated.status + '.',
      updated.verified ? '' : 'warn');
  } catch (e) {
    $('programVerification').textContent = 'ERROR · ' + e.message;
    toast(e.message, 'error');
  }
}

async function runProgram() {
  const program = state.currentProgram;
  if (!program) return;
  const args = $('programArgs').value.trim().split(/\s+/).filter(Boolean).slice(0, 20);
  const output = $('programOutput');
  output.textContent = 'Running…';
  try {
    const result = await api('/programs/' + program.id + '/run', {
      method: 'POST',
      body: JSON.stringify({ args })
    });
    output.textContent = result.output || (result.ok ? '(no output)' : '(no output, exit ' + result.exit + ')');
    toast(result.ok ? 'Program exited 0.' : 'Program exited ' + result.exit + '.', result.ok ? '' : 'warn');
    if (result.program) renderProgramDetail(result.program);
    await loadPrograms();
  } catch (e) {
    output.textContent = 'ERROR · ' + e.message;
    toast(e.message, 'error');
  }
}

async function deleteProgram() {
  const program = state.currentProgram;
  if (!program) return;
  if (!confirm('Delete "' + program.name + '" and its files from data/programs?')) return;
  try {
    await api('/programs/' + program.id, { method: 'DELETE' });
    closeProgram();
    await loadPrograms();
    toast('Program #' + program.id + ' deleted.');
  } catch (e) { toast(e.message, 'error'); }
}

function closeProgram() {
  state.currentProgram = null;
  state.programFiles = [];
  state.programFile = '';
  state.programContent = '';
  $('programDetail').classList.add('hidden');
  $('programPreview').classList.add('hidden');
  $('programPreviewFrame').src = 'about:blank';
  renderProgramList();
}

async function loadProgramPage() {
  await Promise.allSettled([loadProgramRecipes(), loadPrograms()]);
}

/* -------------------------------------------------------------- websockets */
let socket = null;
const wsRefresh = debounce(() => refresh(), 900);
const autoLiveRefresh = debounce(() => {
  if ($('autonomous') && $('autonomous').classList.contains('active')) loadAutonomous();
}, 1400);
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
      if (/warning|error|failed|blocked/i.test(String(value.kind))) pulseCore('error');
      else if (/learning|discovery|verification|knowledge|web|repo|skills/i.test(String(value.kind))) pulseCore('knowledge');
      if (String(value.kind || '').match(/learning|discovery|verification|web/)) autoLiveRefresh();
      wsRefresh();
    };
    socket.onclose = () => setTimeout(connectWS, 4000);
    socket.onerror = () => { try { socket.close(); } catch { } };
  } catch { }
}

/* --------------------------------------------------------------- bootstrapping */
function init() {
  $$('.nav').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.page)));

  window.addEventListener('message', (event) => {
    const data = event.data || {};
    if (!data.__nexusPreview) return;
    const frame = $('rvPreviewFrame');
    if (!frame || event.source !== frame.contentWindow) return;
    const log = $('rvPreviewLog');
    if (!log) return;
    const kind = String(data.type || 'log');
    const line = document.createElement('div');
    line.className = 'preview-line ' + kind;
    line.textContent = '[' + kind + '] ' + (Array.isArray(data.args) ? data.args.join(' ') : String(data.args || ''));
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  });

  if ($('pgLang')) $('pgLang').addEventListener('change', () => pgLangChanged(true));

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
  if ($('webList')) {
    $('webList').addEventListener('click', (event) => {
      const card = event.target.closest('[data-web]');
      if (card) selectWebSource(Number(card.dataset.web));
    });
  }
  if ($('webPacks')) {
    $('webPacks').addEventListener('click', (event) => {
      const pack = event.target.closest('[data-pack]');
      if (pack) learnPack(pack.dataset.pack);
    });
  }
  if ($('skillList')) {
    $('skillList').addEventListener('click', (event) => {
      const card = event.target.closest('[data-skill]');
      if (card) openSkill(card.dataset.skill);
    });
  }
  if ($('programList')) {
    $('programList').addEventListener('click', (event) => {
      const card = event.target.closest('[data-program]');
      if (card) openProgram(Number(card.dataset.program));
    });
  }
  ['programMatches', 'programRecipes'].forEach((id) => {
    if (!$(id)) return;
    $(id).addEventListener('click', (event) => {
      const chip = event.target.closest('[data-recipe]');
      if (!chip) return;
      $('programRecipe').value = chip.dataset.recipe;
      applyRecipeSelection();
    });
  });
  if ($('programFiles')) {
    $('programFiles').addEventListener('click', (event) => {
      const file = event.target.closest('[data-file]');
      if (file) openProgramFile(file.dataset.file);
    });
  }
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
  bindGraphCanvas();
  initMatrix();
  connectWS();

  window.addEventListener('resize', debounce(() => {
    if (state.graph.active) startGraphLoop();
  }, 200));

  $('footerTime').textContent = new Date().toLocaleDateString();
  const sideVersion = $('sideVersion');
  if (sideVersion) sideVersion.textContent = 'v0.5.0';

  refresh().then(() => {
    loadConversations();
    loadRepos(true);
  });
  setInterval(refresh, 8000);
  setInterval(() => { if ($('activity').classList.contains('active')) loadEvents(); }, 12000);
  setInterval(() => { if ($('monitor') && $('monitor').classList.contains('active')) loadMonitor(); }, 12000);
}

/* ========================================================================
   DASHBOARD
   ======================================================================== */
async function loadDashboard() {
  try {
    const days = 30;
    state.dashboard = await api(`/dashboard?days=${days}`);
    renderDashboard();
  } catch (e) { toast('Dashboard load failed: ' + e.message, 'error'); }
}

function renderDashboard() {
  const d = state.dashboard || {};
  const o = d.overview || {};
  $('dKnowledge').textContent = num(o.knowledge);
  $('dKnowledgeVerified').textContent = (o.verified_knowledge || 0) + ' verified';
  $('dConcepts').textContent = num(o.concepts);
  $('dConceptsMastered').textContent = (o.mastered_concepts || 0) + ' mastered';
  $('dExercises').textContent = num(o.exercises);
  $('dExercisesVerified').textContent = (o.verified_exercises || 0) + ' verified';
  $('dProjects').textContent = num(o.projects);
  $('dAvgReview').textContent = (o.avg_review_score || 0) + '/100';
  $('dAssessments').textContent = num(o.assessments);
  $('dAssessmentsSolved').textContent = (o.solved_assessments || 0) + ' solved';
  $('dExplored').textContent = num(o.explored_sites);
  $('dExploredLearned').textContent = (o.learned_sites || 0) + ' learned';

  if (d.knowledge) drawBarChart('chartKnowledge', d.knowledge.daily.map(x => ({ label: x.day, value: x.n })), '#5eead4');
  if (d.skills) drawBarChart('chartSkills', d.skills.map(x => ({ label: x.name, value: Math.round(x.score) })), '#39ff9a');
  if (d.tasks) {
    const labels = Object.keys(o.tasks_by_status || {});
    drawPieChart('chartTasks', labels.map(k => ({ label: k, value: o.tasks_by_status[k] })));
  }
  if (d.exploration) {
    drawBarChart('chartExplore', d.exploration.by_status.map(x => ({ label: x.status, value: x.n })), '#ffb74d');
  }

  const sys = $('dashboardSystem');
  if (sys) sys.textContent = JSON.stringify(d.system || {}, null, 2);
  const detail = $('dashboardDetail');
  if (detail) detail.classList.remove('hidden');
}

function drawBarChart(id, items, color) {
  const cv = $(id); if (!cv) return;
  const ctx = cv.getContext('2d');
  const w = cv.width = cv.clientWidth * (window.devicePixelRatio || 1);
  const h = cv.height = cv.clientHeight * (window.devicePixelRatio || 1);
  ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
  const cw = cv.clientWidth, ch = cv.clientHeight;
  ctx.clearRect(0, 0, cw, ch);
  if (!items || !items.length) return;
  const max = Math.max(...items.map(x => x.value), 1);
  const pad = 40, gap = 14, bw = (cw - pad - gap * (items.length - 1)) / items.length;
  ctx.font = '11px JetBrains Mono, monospace';
  ctx.fillStyle = '#64748b';
  items.forEach((it, i) => {
    const x = pad + i * (bw + gap);
    const barH = (it.value / max) * (ch - 30);
    ctx.fillStyle = color;
    ctx.fillRect(x, ch - 24 - barH, bw * 0.72, barH);
    ctx.fillStyle = '#64748b';
    ctx.fillText(String(it.value), x + bw * 0.36 - 6, ch - 26 - barH);
    ctx.fillText(it.label.length > 8 ? it.label.slice(0, 8) + '…' : it.label, x, ch - 8);
  });
}

function drawPieChart(id, items) {
  const cv = $(id); if (!cv) return;
  const ctx = cv.getContext('2d');
  const w = cv.width = cv.clientWidth * (window.devicePixelRatio || 1);
  const h = cv.height = cv.clientHeight * (window.devicePixelRatio || 1);
  ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
  const cw = cv.clientWidth, ch = cv.clientHeight;
  ctx.clearRect(0, 0, cw, ch);
  if (!items || !items.length) return;
  const total = items.reduce((s, x) => s + x.value, 0) || 1;
  const colors = ['#5eead4', '#39ff9a', '#ffb74d', '#ff5470', '#bb86fc'];
  let angle = 0;
  const cx = cw * 0.22, cy = ch * 0.5, r = Math.min(cx, ch * 0.42);
  items.forEach((it, i) => {
    const slice = (it.value / total) * 2 * Math.PI;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, angle, angle + slice);
    ctx.closePath();
    ctx.fillStyle = colors[i % colors.length];
    ctx.fill();
    angle += slice;
  });
  ctx.fillStyle = '#64748b'; ctx.font = '11px JetBrains Mono, monospace';
  let y = 16;
  items.forEach((it, i) => {
    ctx.fillStyle = colors[i % colors.length];
    ctx.fillRect(14, y - 9, 10, 10);
    ctx.fillStyle = '#64748b';
    ctx.fillText(it.label + ': ' + it.value, 28, y);
    y += 18;
  });
}

/* ========================================================================
   AUTO PROGRAMMING
   ======================================================================== */
async function loadAutoProgramming() {
  try {
    state.ap = await api('/autoprogramming/status');
    renderAutoProgramming();
    await apLoadConcepts();
    await apLoadExercises();
  } catch (e) { toast('Auto Programming load failed: ' + e.message, 'error'); }
}

function renderAutoProgramming() {
  const ap = state.ap || {};
  const st = ap.state || {};
  $('apStatusTag').textContent = (st.running ? (st.paused ? 'PAUSED' : 'RUNNING') : 'IDLE') + '  ·  cycle ' + (st.cycle || 0);
  $('apCycleTag').textContent = st.phase || 'idle';
  const langSel = $('apLang');
  if (langSel && !langSel.dataset.loaded) {
    const catalog = (ap.stats && ap.stats.catalog) || [];
    langSel.innerHTML = '<option value="">auto (all enabled)</option>' + catalog.map(function (l) {
      const tool = (ap.stats.toolchains || {})[l.id] || {};
      const suffix = tool.available ? (tool.executable ? '' : ' · static') : ' · not installed';
      return '<option value="' + esc(l.id) + '">' + esc(l.name) + suffix + '</option>';
    }).join('');
    langSel.dataset.loaded = '1';
  }
  const box = $('apDetail');
  if (ap.stats) {
    const s = ap.stats;
    box.innerHTML = '<div class="ap-summary"><b>Concepts:</b> ' + num(s.concepts_total) + ' total · ' + num(s.mastered) + ' mastered · ' + num(s.studying) + ' studying · ' + num(s.queued) + ' queued<br>' +
      '<b>Exercises:</b> ' + num(s.exercises) + ' · ' + num(s.verified_exercises) + ' verified<br>' +
      '<b>Assessments:</b> ' + num(s.assessments) + ' · avg ' + (s.assessment_avg || 0) + '<br>' +
      '<b>Programming knowledge:</b> ' + num(s.programming_knowledge) + ' · <b>Cycles:</b> ' + num(s.cycles) + ' · <b>Errors fixed:</b> ' + num(s.errors_fixed) +
      '</div>';
  }
}

async function apStart() {
  const body = {};
  const l = $('apLang'); if (l && l.value) body.language = l.value;
  const c = $('apConcept'); if (c && c.value) body.concept = c.value;
  const diff = $('apDifficulty'); if (diff && diff.value) body.difficulty = diff.value;
  const assess = $('apAssess'); if (assess) body.assess = assess.value === 'true';
  state.ap = await apiPost('/autoprogramming/start', body);
  renderAutoProgramming(); toast('Auto programming started.');
}
async function apPause() { state.ap = await api('/autoprogramming/pause', { method: 'POST' }); renderAutoProgramming(); }
async function apResume() { state.ap = await apiPost('/autoprogramming/resume', {}); renderAutoProgramming(); }
async function apStop() { state.ap = await api('/autoprogramming/stop', { method: 'POST' }); renderAutoProgramming(); }
async function apStudy() {
  const body = {};
  const l = $('apLang'); if (l && l.value) body.language = l.value;
  const c = $('apConcept'); if (c && c.value) body.concept = c.value;
  const diff = $('apDifficulty'); const assess = $('apAssess');
  const r = await apiPost('/autoprogramming/study', { language: body.language, concept: body.concept, difficulty: diff ? diff.value : undefined, assess: assess ? assess.value === 'true' : undefined });
  state.apCurrentExercise = r.exercise || null;
  renderAutoProgramming(); renderApExercise(r);
  toast('Cycle complete · verified: ' + (r.verified ? 'yes' : 'no') + ' · mastery: ' + (r.outcome ? (r.outcome.mastery * 100).toFixed(0) + '%' : '—'));
}

async function apLoadConcepts() {
  try {
    state.apConcepts = (await api('/autoprogramming/concepts')).concepts || [];
    const tbody = $('apConceptsBody'); if (!tbody) return;
    tbody.innerHTML = '';
    for (const c of state.apConcepts) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + esc(c.language) + '</td><td>' + esc(c.concept) + '</td><td>' + esc(c.difficulty) + '</td>' +
        '<td><span class="badge badge-' + (c.status || 'queued') + '">' + esc(c.status || 'queued') + '</span></td>' +
        '<td>' + Number(c.mastery || 0).toFixed(2) + '</td><td>' + num(c.attempts) + '</td><td>' + num(c.successes) + '</td>';
      tbody.appendChild(tr);
    }
  } catch (e) { toast('Concepts load failed: ' + e.message, 'error'); }
}

async function apLoadExercises() {
  try {
    state.apExercises = (await api('/autoprogramming/exercises?limit=40')).exercises || [];
    const tbody = $('apExercisesBody'); if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of state.apExercises) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + num(e.id) + '</td><td>' + esc(e.title) + '</td><td>' + esc(e.language) + '</td>' +
        '<td>' + esc(e.concept || '') + '</td>' +
        '<td><span class="badge badge-' + (e.status || '') + '">' + esc(e.status || '') + '</span></td>' +
        '<td>' + (e.score != null ? e.score.toFixed(0) : '—') + '</td><td>' + num(e.runtime_ms || 0) + ' ms</td>';
      tr.onclick = () => apSelectExercise(e.id);
      tbody.appendChild(tr);
    }
  } catch (e) { toast('Exercises load failed: ' + e.message, 'error'); }
}

async function apSelectExercise(id) {
  const e = await api('/autoprogramming/exercises/' + id);
  state.apCurrentExercise = e;
  renderApExercise(e);
}

function renderApExercise(r) {
  const box = $('apExerciseDetail');
  const e = r.exercise || r;
  if (!e) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('apExerciseTitle').textContent = e.title || '—';
  $('apExercisePrompt').textContent = e.prompt || '—';
  const ex = r.execution || null;
  $('apExerciseOutput').textContent = ex
    ? ((ex.ok ? 'TESTS PASSED' : (ex.skipped ? 'SKIPPED' : 'TESTS FAILED')) +
       ' · exit ' + (ex.exit_code == null ? '—' : ex.exit_code) + ' · ' + num(ex.duration_ms || 0) + ' ms\n' +
       (ex.stdout || ex.stderr || ex.note || 'No output.'))
    : (e.output || 'Not run yet — press “Run tests”.');
  const sol = $('apExerciseSolution'); sol.classList.add('hidden'); sol.textContent = e.solution || '—';
  const det = $('apExerciseDetail');
  det.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function apRunExercise() {
  if (!state.apCurrentExercise) return toast('No exercise selected.');
  const id = state.apCurrentExercise.id;
  if (!id) return toast('This exercise has no stored id yet. Run a study cycle first.');
  try {
    const r = await apiPost('/autoprogramming/exercises/' + id + '/run', {});
    state.apCurrentExercise = r.exercise || state.apCurrentExercise;
    renderApExercise(r);
    toast('Run ' + (r.verified ? 'passed' : 'failed') + ' · score ' + (r.score || 0));
    await apLoadExercises();
    await apLoadConcepts();
  } catch (err) { toast('Run failed: ' + err.message, 'error'); }
}

function apShowSolution() { const s = $('apExerciseSolution'); if (s) s.classList.remove('hidden'); }
function apHideExercise() { const b = $('apExerciseDetail'); if (b) b.classList.add('hidden'); }

/* ========================================================================
   REVIEW STUDIO
   ======================================================================== */
async function loadReview() { await rvLoadHistory(); }

function rvGetFiles() {
  try { return JSON.parse($('rvFiles').value || '{}'); } catch (e) { throw new Error('Invalid JSON in files.'); }
}

async function rvAnalyze() {
  try {
    const files = rvGetFiles();
    const r = await apiPost('/review/analyze', { files, title: $('rvTitle').value || undefined, language: $('rvLang').value || undefined, run_tests: true, ai: true, save: false });
    state.rv = r;
    renderReview(r);
  } catch (e) { toast('Review failed: ' + e.message, 'error'); }
}

async function rvRun() {
  try {
    const files = rvGetFiles();
    const lang = $('rvLang').value || undefined;
    const r = await apiPost('/review/run', { files, language: lang, entry: undefined, mode: 'test', args: [] });
    $('rvExecution').textContent = JSON.stringify({ ok: r.ok, exit_code: r.exit_code, stdout: r.stdout, stderr: r.stderr, duration_ms: r.duration_ms }, null, 2);
    toast('Run ' + (r.ok ? 'passed' : 'failed') + ' · ' + (r.duration_ms || 0) + ' ms');
  } catch (e) { toast('Run failed: ' + e.message, 'error'); }
}

async function rvFix() {
  try {
    const files = rvGetFiles();
    const r = await apiPost('/review/fix', { files });
    $('rvFiles').value = JSON.stringify(r.files, null, 2);
    toast('Applied ' + (r.changes || []).length + ' conservative fix(es). Re-run Analyze to re-score.');
  } catch (e) { toast('Fix failed: ' + e.message, 'error'); }
}

async function rvPreview() {
  try {
    const files = rvGetFiles();
    const html = await apiPostRaw('/review/preview', { files, entry: undefined });
    const frame = $('rvPreviewFrame'); const box = $('rvPreviewBox');
    const log = $('rvPreviewLog');
    if (log) log.innerHTML = '';
    frame.srcdoc = html;
    box.classList.remove('hidden');
  } catch (e) { toast('Preview failed: ' + e.message, 'error'); }
}

async function apiPostRaw(path, body) {
  const response = await fetch('/api' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) { const t = await response.text(); throw new Error(t.slice(0, 300)); }
  return response.text();
}

async function rvSave() {
  if (!state.rv) return toast('Nothing to save. Analyze first.');
  try {
    const r = await apiPost('/review/analyze', { files: rvGetFiles(), title: $('rvTitle').value || 'Review Studio', language: $('rvLang').value || undefined, run_tests: true, ai: true, save: true });
    toast('Review saved #' + r.review_id);
    await rvLoadHistory();
  } catch (e) { toast('Save failed: ' + e.message, 'error'); }
}

async function rvExport() {
  try {
    const files = rvGetFiles();
    const res = await fetch('/api/review/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files, entry: undefined }) });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'nexus-review.zip'; a.click();
    URL.revokeObjectURL(url);
  } catch (e) { toast('Export failed: ' + e.message, 'error'); }
}

async function rvLoadHistory() {
  try {
    state.rvHistory = (await api('/review/history?limit=40')).reviews || [];
    const tbody = $('rvHistoryBody'); if (!tbody) return;
    tbody.innerHTML = '';
    for (const r of state.rvHistory) {
      const s = r.scores || {};
      const sev = (r.issues || []);
      const c = { high: sev.filter(x => x.severity === 'high').length,
                  medium: sev.filter(x => x.severity === 'medium').length,
                  low: sev.filter(x => x.severity === 'low').length };
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + when(r.created_at) + '</td><td>' + esc(r.title) + '</td><td>' + (r.target_kind || '') + (r.target_id ? '#' + r.target_id : '') + '</td>' +
        '<td>' + (r.overall != null ? r.overall.toFixed(0) : '—') + '</td>' +
        '<td>' + num(c.high) + '</td><td>' + num(c.medium) + '</td><td>' + num(c.low) + '</td>';
      tbody.appendChild(tr);
    }
  } catch (e) { toast('History load failed: ' + e.message, 'error'); }
}

function renderReview(r) {
  const box = $('rvResult'); if (!box) return;
  box.classList.remove('hidden');
  const s = r.scores || {};
  let html = '';
  const keys = ['quality', 'correctness', 'performance', 'security', 'accessibility', 'responsiveness', 'design', 'bugs'];
  for (const k of keys) {
    const v = s[k] != null ? s[k] : 0;
    html += '<div class="score-chip"><strong>' + esc(k) + '</strong> <span class="score-val">' + v + '</span><div class="score-bar"><div class="score-fill" style="width:' + v + '%"></div></div></div>';
  }
  $('rvScores').innerHTML = html;
  const c = (r.counts || (r.analysis && r.analysis.counts) || {});
  $('rvIssues').innerHTML = '<div class="issues"><strong>' + (r.overall || 0).toFixed(0) + '/100 overall</strong> · ' +
    num(c.high) + ' high, ' + num(c.medium) + ' medium, ' + num(c.low) + ' low · ' +
    num(r.metrics ? r.metrics.files : 0) + ' files, ' + num(r.metrics ? r.metrics.lines : 0) + ' lines</div>' +
    (r.issues && r.issues.length ? '<ul style="margin-top:6px">' + r.issues.slice(0, 10).map(f => '<li><span class="sev sev-' + f.severity + '">' + f.severity.toUpperCase() + '</span> ' + esc(f.message) + (f.file ? ' (' + esc(f.file) + ')' : '') + '</li>').join('') + '</ul>' : '');
  const exec = r.execution;
  if (exec) {
    $('rvExecution').textContent = (exec.ok ? 'TESTS PASSED' : 'TESTS ' + (exec.skipped ? 'SKIPPED' : 'FAILED')) +
      ' · exit ' + exec.exit_code + ' · ' + exec.duration_ms + ' ms\n' + (exec.stdout || exec.stderr || '');
  } else {
    $('rvExecution').textContent = 'Execution not run.';
  }
  $('rvSummary').textContent = r.summary || '';
}

/* ========================================================================
   PROJECTS
   ======================================================================== */
async function loadProjects() {
  try {
    state.pjList = (await api('/projects?limit=60')).projects || [];
    renderProjects();
  } catch (e) { toast('Projects load failed: ' + e.message, 'error'); }
}

function renderProjects() {
  const tbody = $('pjListBody'); if (!tbody) return;
  tbody.innerHTML = '';
  for (const p of state.pjList) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + num(p.id) + '</td><td>' + esc(p.name) + '</td><td>' + esc(p.archetype) + '</td>' +
      '<td><span class="badge badge-' + (p.status || 'built') + '">' + esc(p.status || 'built') + '</span></td>' +
      '<td>' + (p.review_score != null ? p.review_score.toFixed(0) : '—') + '</td><td>' + num(p.files ? p.files.length : 0) + '</td>' +
      '<td>' + when(p.created_at) + '</td>' +
      '<td><button class="textbtn small" onclick="pjSelect(' + num(p.id) + ')">Open</button></td>';
    tbody.appendChild(tr);
  }
}

async function pjBuild() {
  try {
    const p = await apiPost('/projects', { request: $('pjRequest').value, archetype: $('pjArchetype').value || undefined, name: $('pjName').value || undefined, run_tests: true, auto_review: true });
    state.pjCurrent = p;
    renderProjectDetail(p);
    await loadProjects();
    toast('Project built · ' + p.status + ' · review ' + (p.review_score || 0).toFixed(0) + '/100');
  } catch (e) { toast('Build failed: ' + e.message, 'error'); }
}

async function pjSelect(id) {
  const p = await api('/projects/' + id);
  state.pjCurrent = p;
  renderProjectDetail(p);
}

function renderProjectDetail(p) {
  const box = $('pjDetail'); if (!box) return;
  box.classList.remove('hidden');
  $('pjDetailName').textContent = p.name || '—';
  $('pjDetailMeta').textContent = p.archetype + ' · ' + p.status + ' · ' + (p.file_rows ? p.file_rows.length : 0) + ' files';
  const fl = $('pjDetailFiles');
  fl.innerHTML = '<strong>Files:</strong> ' + (p.file_rows || []).map(f => '<code>' + esc(f.path) + '</code> (' + esc(f.language) + ')').join(' · ');
  const out = $('pjDetailTest');
  out.textContent = p.test_output ? (p.test_output.slice(0, 1500) + (p.test_output.length > 1500 ? '…' : '')) : 'No test output.';
  const rv = $('pjDetailReview');
  if (p.review_history && p.review_history.length) {
    const latest = p.review_history[0];
    rv.innerHTML = '<strong>Latest review:</strong> ' + (latest.overall || 0).toFixed(0) + '/100 · ' + (latest.summary || '').slice(0, 300);
  } else {
    rv.textContent = 'No review yet.';
  }
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function pjTest() { if (!state.pjCurrent) return; try { const r = await apiPost('/projects/' + state.pjCurrent.id + '/test', {}); state.pjCurrent = await api('/projects/' + state.pjCurrent.id); renderProjectDetail(state.pjCurrent); toast('Test ' + (r.ok ? 'passed' : 'failed')); } catch (e) { toast('Test failed: ' + e.message, 'error'); } }
async function pjReview() { if (!state.pjCurrent) return; try { const r = await apiPost('/projects/' + state.pjCurrent.id + '/review', {}); toast('Reviewed · ' + (r.overall || 0).toFixed(0) + '/100'); state.pjCurrent = await api('/projects/' + state.pjCurrent.id); renderProjectDetail(state.pjCurrent); await loadProjects(); } catch (e) { toast('Review failed: ' + e.message, 'error'); } }
async function pjExport() {
  if (!state.pjCurrent) return toast('Open a project first.');
  try {
    const res = await fetch('/api/projects/' + state.pjCurrent.id + '/export', { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (state.pjCurrent.slug || 'nexus-project') + '.zip';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) { toast('Export failed: ' + e.message, 'error'); }
}
async function pjDelete() { if (!state.pjCurrent || !confirm('Delete project #' + state.pjCurrent.id + '?')) return; try { await api('/projects/' + state.pjCurrent.id, { method: 'DELETE' }); toast('Deleted'); state.pjCurrent = null; $('pjDetail').classList.add('hidden'); await loadProjects(); } catch (e) { toast('Delete failed: ' + e.message, 'error'); } }
function pjHideDetail() { $('pjDetail').classList.add('hidden'); }

/* ========================================================================
   PLAYGROUND
   ======================================================================== */
function pgLangChanged(force) {
  const ex = { python: "print('sandbox-ok', 6 * 7)\n", javascript: "console.log('sandbox-ok', 6 * 7);\n", php: "<?php echo 'sandbox-ok ' . (6*7);\n", sql: "CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO t VALUES(1,'ada');\nSELECT * FROM t;\n", c: '#include <stdio.h>\nint main(void){printf("sandbox-ok %d\\n", 6*7);return 0;}\n', cpp: '#include <iostream>\nint main(){std::cout << "sandbox-ok " << (6*7) << "\\n";}\n', rust: 'fn main(){println!("sandbox-ok {}", 6 * 7);}\n' };
  const sel = $('pgLang'); const exText = $('pgCode');
  if (!sel || !exText) return;
  state.pgDrafts = state.pgDrafts || {};
  if (force && sel.dataset.prevLang && sel.dataset.prevLang !== sel.value) {
    state.pgDrafts[sel.dataset.prevLang] = exText.value;
  }
  if (force || !exText.value.trim()) {
    exText.value = state.pgDrafts[sel.value] || ex[sel.value] || ex.python;
    const entry = $('pgEntry');
    if (entry) entry.value = '';
  }
  sel.dataset.prevLang = sel.value;
}
function pgExample() { pgLangChanged(true); }

async function pgRun() {
  try {
    const lang = $('pgLang').value;
    const files = {};
    files[($('pgEntry').value || 'main.' + { python: 'py', javascript: 'js', php: 'php', sql: 'sql', c: 'c', cpp: 'cpp', rust: 'rs' }[lang])] = $('pgCode').value || '';
    const r = await apiPost('/playground/run', { language: lang, files, entry: $('pgEntry').value || undefined, args: ($('pgArgs').value || '').trim() ? $('pgArgs').value.split(/\s+/) : [] });
    $('pgOutput').textContent = JSON.stringify({ ok: r.ok, exit_code: r.exit_code, stdout: r.stdout, stderr: r.stderr, duration_ms: r.duration_ms, note: r.note }, null, 2);
    toast('Run ' + (r.ok ? 'passed' : 'failed') + ' · ' + r.duration_ms + ' ms');
  } catch (e) { toast('Run failed: ' + e.message, 'error'); }
}

async function pgSelfCheck() {
  try {
    const r = await api('/playground/self-check');
    $('pgOutput').textContent = JSON.stringify(r, null, 2);
    toast('Self-check ' + (r.ok ? 'PASSED' : 'FAILED'));
  } catch (e) { toast('Self-check failed: ' + e.message, 'error'); }
}

/* ========================================================================
   AI AGENTS
   ======================================================================== */
async function loadAgents() {
  try {
    state.ag = await api('/agents');
    renderAgents();
    await agLoadRuns();
  } catch (e) { toast('Agents load failed: ' + e.message, 'error'); }
}

function renderAgents() {
  const box = $('agentsList'); if (!box) return;
  const catalog = (state.ag && state.ag.agents) || {};
  const by = (state.ag && state.ag.by_agent) || [];
  const counts = {};
  for (const row of by) counts[row.agent] = row;
  const ids = Object.keys(catalog);
  if (!ids.length) { box.innerHTML = '<div class="empty">No agent catalog available.</div>'; return; }
  box.innerHTML = ids.map(function (id) {
    const meta = catalog[id] || { name: id };
    const row = counts[id] || {};
    return '<div class="agent-chip"><div><strong>' + esc(meta.name || id) + '</strong>' +
      '<div class="muted" style="font-size:11px">' + esc(meta.description || '') + '</div>' +
      '<div class="muted" style="font-size:10px;margin-top:3px">' + num(row.n || 0) + ' runs · avg ' +
      (row.score != null ? Number(row.score).toFixed(0) : '—') + '</div></div>' +
      '<span class="badge badge-completed">' + num(row.completed || 0) + ' done</span></div>';
  }).join('');
}

async function agRun() {
  try {
    const r = await apiPost('/agents/run', { agent: $('agAgent').value, task: $('agTask').value });
    $('agOutput').textContent = r.output;
    $('agSteps').textContent = (r.steps || []).map(s => s.step + ': ' + s.detail).join('\n');
    toast('Agent ' + r.status + ' · score ' + r.score);
    await agLoadRuns();
  } catch (e) { toast('Agent run failed: ' + e.message, 'error'); }
}

async function agTeam() {
  try {
    const r = await apiPost('/agents/team', { task: $('agTeamTask').value });
    $('agTeamOutput').textContent = r.output;
    toast('Team complete · score ' + r.score + ' · ' + r.steps.length + ' specialist(s)');
    await agLoadRuns();
  } catch (e) { toast('Team run failed: ' + e.message, 'error'); }
}

async function agLoadRuns() {
  try {
    state.agRuns = await api('/agents/runs?limit=40');
    const tbody = $('agRunsTable'); if (!tbody) return;
    tbody.innerHTML = '';
    for (const r of state.agRuns.runs || []) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + num(r.id) + '</td><td>' + esc(r.agent) + '</td>' +
        '<td><span class="badge badge-' + (r.status || '') + '">' + esc(r.status || '') + '</span></td>' +
        '<td>' + (r.score != null ? r.score.toFixed(0) : '—') + '</td><td>' + when(r.created_at) + '</td>' +
        '<td>' + esc((r.input || '').slice(0, 60)) + '</td>';
      tbody.appendChild(tr);
    }
  } catch (e) { toast('Runs load failed: ' + e.message, 'error'); }
}
function agHideRuns() { $('agRuns').classList.add('hidden'); }

/* ========================================================================
   helpers used by new pages
   ======================================================================== */
async function apiPost(path, body) {
  const response = await fetch('/api' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) { const t = await response.text(); let m = t; try { m = JSON.parse(t).detail || t; } catch { } throw new Error(String(m).slice(0, 500)); }
  return response.json();
}


document.addEventListener('DOMContentLoaded', init);
