'use strict';

const $ = (id) => document.getElementById(id);

// 密码字段名
const PASS = 'password';
const PASS_TYPE = 'password';

const state = { accounts: [], linuxdo: [], github: [], providers: {} };
let builtin = {};
let dataFile = 'accounts.json';
let envLegacyKeys = [];

let selected = -1;
let draft = null;
let isNew = false;
let dirty = false;
let filter = 'all';
let query = '';
const picked = new Set();
let listTimer = null;

let poolEditing = { key: null, index: -1, backup: null };
let addingProvider = false;
let exportTexts = [];

/* ---------- 工具 ---------- */
function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
function clone(v) { return JSON.parse(JSON.stringify(v)); }
function isObj(v) { return v && typeof v === 'object' && !Array.isArray(v); }
function tokenValue(a) {
  if (!a || !a.system_access_token) return '';
  return typeof a.system_access_token === 'string' ? a.system_access_token : JSON.stringify(a.system_access_token);
}
function cookieValue(a) {
  if (!a || !a.cookies) return '';
  if (typeof a.cookies === 'string') return a.cookies;
  return a.cookies.session || '';
}
function hostOf(url) {
  try { return new URL(url).hostname; } catch (e) { return ''; }
}
function hostKey(url) {
  const h = hostOf(url);
  return h ? h.replace(/\./g, '_') : '';
}
function providerOrigin(key) {
  if (builtin[key]) return builtin[key];
  if (state.providers[key] && state.providers[key].origin) return state.providers[key].origin;
  return '';
}
function providerLabel(key) {
  const o = providerOrigin(key);
  return o ? key + ' · ' + hostOf(o) : key;
}
function cookieOf(a) {
  return isObj(a.cookies) ? Object.assign({}, a.cookies) : {};
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

let toastTimer = null;
function toast(msg, isError) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.toggle('error', !!isError);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

/* ---------- 初始化 ---------- */
async function init() {
  bindEvents();
  try {
    const data = await api('/api/state');
    state.accounts = data.accounts || [];
    state.linuxdo = data.linuxdo || [];
    state.github = data.github || [];
    state.providers = data.providers || {};
    builtin = data.builtin || {};
    dataFile = data.data_file || 'accounts.json';
    envLegacyKeys = data.env_legacy_keys || [];
    $('dataFile').textContent = dataFile;
    $('proxyInput').value = data.proxy || '';
    if (envLegacyKeys.length) {
      $('envNote').textContent = '检测到 .env 里还有旧配置键：' + envLegacyKeys.join('、') + '，可以点「同步到 .env」合并。';
    }
    if (state.accounts.length) selectAccount(0);
    else renderAll();
    loadSettings();
  } catch (e) {
    toast('加载失败：' + e.message, true);
  }
}

async function loadSettings() {
  try {
    const r = await api('/api/settings');
    $('onceCb').checked = !!r.check_in_once_per_day;
  } catch (e) { /* ignore */ }
}

/* ---------- 事件 ---------- */
function bindEvents() {
  $('search').addEventListener('input', (e) => {
    query = e.target.value.trim().toLowerCase();
    picked.clear();
    renderList();
  });

  $('filters').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-filter]');
    if (!btn) return;
    filter = btn.dataset.filter;
    picked.clear();
    document.querySelectorAll('#filters .chip').forEach((c) => c.classList.toggle('active', c === btn));
    renderList();
  });

  $('accountList').addEventListener('click', onListClick);
  $('bulkBar').addEventListener('click', onBulkClick);

  $('btnNew').addEventListener('click', newAccount);
  $('btnNewEmpty').addEventListener('click', newAccount);

  $('accountForm').addEventListener('input', onFormInput);
  $('accountForm').addEventListener('change', onFormInput);
  $('fProvider').addEventListener('change', onProviderSelect);
  $('btnAddSite').addEventListener('click', addSite);
  $('siteList').addEventListener('click', onSiteClick);
  $('btnDelete').addEventListener('click', deleteCurrent);

  $('btnSave').addEventListener('click', saveAll);
  $('btnExport').addEventListener('click', () => { setTab('settings'); doExport(); });
  $('btnDoExport').addEventListener('click', doExport);
  $('btnSync').addEventListener('click', doSync);

  $('tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-tab]');
    if (btn) setTab(btn.dataset.tab);
  });
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-goto-tab]');
    if (btn) setTab(btn.dataset.gotoTab);
  });

  document.addEventListener('click', onSecretAction);

  $('poolsWrap').addEventListener('click', onPoolClick);
  $('poolsWrap').addEventListener('input', onPoolInput);
  $('providersWrap').addEventListener('click', onProviderClick);
  $('providersWrap').addEventListener('input', onProviderInput);
  $('providersWrap').addEventListener('change', onProviderInput);
  $('btnAddProvider').addEventListener('click', () => { addingProvider = true; renderProviders(); });

  $('exportWrap').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const item = exportTexts[+btn.dataset.copy];
    if (item) copyText(item[1]).then(() => toast('已复制 ' + item[0]));
  });

  $('onceCb').addEventListener('change', async (e) => {
    try {
      await api('/api/settings', { check_in_once_per_day: e.target.checked });
      toast(e.target.checked ? '已开启：每天只签到一次' : '已关闭：每次运行都签到');
    } catch (err) { toast('保存失败：' + err.message, true); }
  });

  $('proxyInput').addEventListener('input', markDirty);

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      saveAll();
    }
  });

  window.addEventListener('beforeunload', (e) => {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
}

/* ---------- 列表 ---------- */
function matches(a) {
  if (filter === 'on' && a.enabled === false) return false;
  if (filter === 'off' && a.enabled !== false) return false;
  if (!query) return true;
  const hay = ((a.name || '') + ' ' + (a.provider || '') + ' ' + (a.api_user || '') + ' ' + providerOrigin(a.provider || '')).toLowerCase();
  return hay.indexOf(query) !== -1;
}

function authTags(a) {
  const tags = [];
  if (tokenValue(a)) tags.push('<span class="tag">Token</span>');
  if (cookieValue(a)) tags.push('<span class="tag">Session</span>');
  if (a['linux.do']) tags.push('<span class="tag on">Linux.do</span>');
  if (a.github) tags.push('<span class="tag on">GitHub</span>');
  if (Array.isArray(a.site) && a.site.length) tags.push('<span class="tag">站内账号</span>');
  return tags.join('');
}

function scheduleList() {
  clearTimeout(listTimer);
  listTimer = setTimeout(renderList, 120);
}

function renderList() {
  const wrap = $('accountList');
  let html = '';

  if (isNew) {
    html += '<div class="account-item active" data-new="1">' +
      '<div class="ai-main"><div class="ai-top"><span class="dot off"></span><span class="ai-name">' +
      esc(draft && draft.name ? draft.name : '新账号') +
      '</span></div><div class="ai-sub">未保存 · 填写右侧信息</div></div></div>';
  }

  state.accounts.forEach((a, i) => {
    if (!matches(a)) return;
    const enabled = a.enabled !== false;
    html += '<div class="account-item' + (i === selected && !isNew ? ' active' : '') + '" data-i="' + i + '">' +
      '<input type="checkbox" class="pick" data-i="' + i + '"' + (picked.has(i) ? ' checked' : '') + ' aria-label="选择账号">' +
      '<div class="ai-main">' +
        '<div class="ai-top"><span class="dot ' + (enabled ? 'on' : 'off') + '"></span>' +
          '<span class="ai-name">' + esc(a.name || '未命名') + '</span></div>' +
        '<div class="ai-sub">' + esc(providerLabel(a.provider || '')) + ' · ' + esc(a.api_user || '无用户 ID') + '</div>' +
        '<div class="ai-tags">' + authTags(a) + '</div>' +
      '</div></div>';
  });

  if (!html) {
    html = '<div class="empty-list">' + (query || filter !== 'all' ? '没有匹配的账号' : '还没有账号') + '</div>';
  }
  wrap.innerHTML = html;
  updateBulk();
}

function updateBulk() {
  $('bulkBar').hidden = picked.size === 0;
  $('bulkCount').textContent = '已选 ' + picked.size + ' 项';
}

function onListClick(e) {
  const pick = e.target.closest('.pick');
  if (pick) {
    const i = +pick.dataset.i;
    if (pick.checked) picked.add(i); else picked.delete(i);
    updateBulk();
    return;
  }
  const item = e.target.closest('.account-item');
  if (!item) return;
  if (item.dataset.new !== undefined) { $('fName').focus(); return; }
  selectAccount(+item.dataset.i);
}

function onBulkClick(e) {
  const btn = e.target.closest('[data-bulk]');
  if (!btn) return;
  const action = btn.dataset.bulk;
  if (action === 'clear') { picked.clear(); renderList(); return; }
  if (action === 'delete') {
    if (!confirm('删除选中的 ' + picked.size + ' 个账号？')) return;
    const idx = Array.from(picked).sort((a, b) => b - a);
    idx.forEach((i) => state.accounts.splice(i, 1));
    picked.clear(); selected = -1; draft = null; isNew = false;
    markDirty(); renderAll();
    toast('已删除');
    return;
  }
  const enabled = action === 'on';
  picked.forEach((i) => { if (state.accounts[i]) state.accounts[i].enabled = enabled; });
  picked.clear();
  markDirty();
  renderList();
  if (selected >= 0 && draft) {
    draft = clone(state.accounts[selected]);
    renderEditor();
  }
  toast(enabled ? '已启用' : '已停用');
}

function selectAccount(i) {
  if (i === selected && draft && !isNew) return;
  if (isNew) {
    if (draftHasContent(draft) && !confirm('放弃未保存的新账号？')) return;
    isNew = false;
  }
  selected = i;
  draft = clone(state.accounts[i] || {});
  if (isObj(draft.site)) draft.site = [draft.site];
  renderList();
  renderEditor();
}

function newAccount() {
  if (isNew) { $('fName').focus(); return; }
  selected = -1;
  isNew = true;
  draft = { name: '', provider: 'anyrouter', api_user: '', enabled: true };
  renderList();
  renderEditor();
  $('fName').focus();
  markDirty();
}

function draftHasContent(a) {
  return !!(a && (a.name || a.api_user || tokenValue(a) || cookieValue(a) || (Array.isArray(a.site) && a.site.length)));
}

/* ---------- 编辑器 ---------- */
function renderEditor() {
  const form = $('accountForm');
  const empty = $('accountEmpty');
  if (!draft) {
    form.hidden = true;
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  form.hidden = false;

  $('editorTitle').textContent = isNew ? '新建账号' : '编辑账号';
  $('fName').value = draft.name || '';
  $('fUid').value = draft.api_user || '';
  $('fUserAgent').value = draft.user_agent || '';
  $('fEnabled').checked = draft.enabled !== false;
  $('fLinuxdo').checked = !!draft['linux.do'];
  $('fGithub').checked = !!draft.github;

  $('fToken').value = tokenValue(draft);
  $('fToken').type = PASS_TYPE;
  $('fCookie').value = cookieValue(draft);
  $('fCookie').type = PASS_TYPE;
  document.querySelectorAll('[data-toggle-secret]').forEach((b) => { b.textContent = '显示'; });

  renderProviderOptions();
  renderSiteList();
  renderHints();
  updateEditorSub();
}

function updateEditorSub() {
  if (!draft) return;
  const parts = [providerLabel(draft.provider || '')];
  if (draft.api_user) parts.push(draft.api_user);
  if (isNew) parts.push('未保存');
  $('editorSub').textContent = parts.filter(Boolean).join(' · ');
}

function renderHints() {
  $('tokenHint').textContent = tokenValue(draft) ? '已设置' : '';
  $('cookieHint').textContent = cookieValue(draft) ? '已设置' : '';
  $('linuxdoHint').textContent = state.linuxdo.length ? state.linuxdo.length + ' 个可用' : '账号池为空';
  $('githubHint').textContent = state.github.length ? state.github.length + ' 个可用' : '账号池为空';
}

function renderProviderOptions() {
  const sel = $('fProvider');
  const cur = draft.provider || 'anyrouter';
  const opts = [];
  Object.keys(builtin).forEach((k) => {
    opts.push('<option value="' + esc(k) + '">' + esc(k) + ' — ' + esc(hostOf(builtin[k]) || builtin[k]) + '</option>');
  });
  Object.keys(state.providers).forEach((k) => {
    opts.push('<option value="' + esc(k) + '">' + esc(k) + ' — ' + esc(hostOf(state.providers[k].origin || '') || '自定义') + '（自定义）</option>');
  });
  opts.push('<option value="__custom__">自定义站点 URL…</option>');
  sel.innerHTML = opts.join('');

  if (builtin[cur] || state.providers[cur]) {
    sel.value = cur;
    $('fOrigin').value = providerOrigin(cur);
  } else {
    sel.value = '__custom__';
    $('fOrigin').value = /^https?:\/\//i.test(cur) ? cur : '';
  }
  toggleOrigin();
}

function toggleOrigin() {
  $('originWrap').hidden = $('fProvider').value !== '__custom__';
}

function onProviderSelect() {
  if ($('fProvider').value === '__custom__' && !$('fOrigin').value) {
    $('fOrigin').value = providerOrigin(draft.provider || '');
  }
  toggleOrigin();
}

function onFormInput(e) {
  if (!draft) return;
  const t = e.target;
  const id = t.id;

  if (id === 'fName') draft.name = t.value;
  else if (id === 'fUid') draft.api_user = t.value;
  else if (id === 'fUserAgent') {
    if (t.value.trim()) draft.user_agent = t.value.trim(); else delete draft.user_agent;
  } else if (id === 'fToken') {
    if (t.value.trim()) draft.system_access_token = t.value.trim(); else delete draft.system_access_token;
  } else if (id === 'fCookie') {
    const cookies = cookieOf(draft);
    if (t.value.trim()) {
      cookies.session = t.value.trim();
      draft.cookies = cookies;
    } else {
      delete cookies.session;
      if (Object.keys(cookies).length) draft.cookies = cookies; else delete draft.cookies;
    }
  } else if (id === 'fEnabled') draft.enabled = t.checked;
  else if (id === 'fLinuxdo') {
    if (t.checked) draft['linux.do'] = true; else delete draft['linux.do'];
  } else if (id === 'fGithub') {
    if (t.checked) draft.github = true; else delete draft.github;
  } else if (t.dataset.siteIdx !== undefined) {
    const i = +t.dataset.siteIdx;
    if (!draft.site || !draft.site[i]) return;
    draft.site[i][t.dataset.siteField] = t.value;
  } else {
    return;
  }
  commitDraft();
}

function commitDraft() {
  if (!draft) return;
  if (!isNew && selected >= 0) state.accounts[selected] = draft;
  markDirty();
  scheduleList();
  updateEditorSub();
}

function addSite() {
  if (!draft) return;
  if (!Array.isArray(draft.site)) draft.site = [];
  draft.site.push({ username: '', [PASS]: '', mode: 'auto' });
  renderSiteList();
  commitDraft();
  const rows = document.querySelectorAll('#siteList .site-row');
  const last = rows[rows.length - 1];
  if (last) last.querySelector('input').focus();
}

function onSiteClick(e) {
  const btn = e.target.closest('[data-site-remove]');
  if (!btn || !draft || !Array.isArray(draft.site)) return;
  draft.site.splice(+btn.dataset.siteRemove, 1);
  if (!draft.site.length) delete draft.site;
  renderSiteList();
  commitDraft();
}

function renderSiteList() {
  const wrap = $('siteList');
  if (!draft || !Array.isArray(draft.site) || !draft.site.length) {
    wrap.innerHTML = '<div class="site-empty">未添加</div>';
    return;
  }
  wrap.innerHTML = draft.site.map((s, i) =>
    '<div class="site-row">' +
      '<input data-site-idx="' + i + '" data-site-field="username" value="' + esc(s.username || '') + '" placeholder="用户名" autocomplete="off">' +
      '<input type="' + PASS_TYPE + '" data-site-idx="' + i + '" data-site-field="' + PASS + '" value="' + esc(s[PASS] || '') + '" placeholder="密码" autocomplete="new-' + PASS_TYPE + '">' +
      '<select data-site-idx="' + i + '" data-site-field="mode">' +
        '<option value="auto"' + (s.mode === 'auto' || !s.mode ? ' selected' : '') + '>auto</option>' +
        '<option value="api"' + (s.mode === 'api' ? ' selected' : '') + '>api</option>' +
        '<option value="browser"' + (s.mode === 'browser' ? ' selected' : '') + '>browser</option>' +
      '</select>' +
      '<button type="button" class="icon-btn danger" data-site-remove="' + i + '" title="删除">×</button>' +
    '</div>'
  ).join('');
}

function onSecretAction(e) {
  const toggle = e.target.closest('[data-toggle-secret]');
  if (toggle) {
    const input = $(toggle.dataset.toggleSecret);
    const show = input.type === PASS_TYPE;
    input.type = show ? 'text' : PASS_TYPE;
    toggle.textContent = show ? '隐藏' : '显示';
    return;
  }
  const clear = e.target.closest('[data-clear-secret]');
  if (!clear || !draft) return;
  const which = clear.dataset.clearSecret;
  if (which === 'token') {
    delete draft.system_access_token;
    $('fToken').value = '';
  } else if (which === 'cookie') {
    const cookies = cookieOf(draft);
    delete cookies.session;
    if (Object.keys(cookies).length) draft.cookies = cookies; else delete draft.cookies;
    $('fCookie').value = '';
  }
  renderHints();
  commitDraft();
  toast('已清除，记得保存');
}

/* ---------- 保存 ---------- */
function validateDraft() {
  if (!draft) return true;

  const name = (draft.name || '').trim();
  if (!name) { toast('备注名不能为空', true); $('fName').focus(); return false; }
  draft.name = name;

  const sel = $('fProvider').value;
  if (sel === '__custom__') {
    const origin = ($('fOrigin').value || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(origin)) {
      toast('站点 URL 需要以 http:// 或 https:// 开头', true);
      $('fOrigin').focus();
      return false;
    }
    const key = hostKey(origin);
    if (!key) { toast('站点 URL 无效', true); $('fOrigin').focus(); return false; }
    draft.provider = key;
    if (!state.providers[key]) state.providers[key] = { origin };
    else state.providers[key].origin = origin;
  } else {
    if (!sel) { toast('请选择站点', true); return false; }
    draft.provider = sel;
  }

  draft.api_user = (draft.api_user || '').trim();
  if (!draft.api_user) { toast('用户 ID 不能为空', true); $('fUid').focus(); return false; }

  if (Array.isArray(draft.site)) {
    draft.site = draft.site.filter((s) => s && ((s.username || '').trim() || (s[PASS] || '').trim()));
    draft.site.forEach((s) => { s.username = (s.username || '').trim(); });
    if (!draft.site.length) delete draft.site;
  }

  const hasAuth = !!(tokenValue(draft) || cookieValue(draft) || draft['linux.do'] || draft.github ||
    (Array.isArray(draft.site) && draft.site.length));
  if (!hasAuth) {
    toast('至少填一个 Token、Session 或登录方式', true);
    return false;
  }
  return true;
}

async function saveAll() {
  if (draft && !validateDraft()) return false;

  if (isNew) {
    state.accounts.push(draft);
    selected = state.accounts.length - 1;
    isNew = false;
  } else if (selected >= 0 && draft) {
    state.accounts[selected] = draft;
  }

  try {
    await api('/api/save', payload());
    dirty = false;
    updateSaveState();
    renderAll();
    toast('已保存到 ' + dataFile);
    return true;
  } catch (e) {
    toast('保存失败：' + e.message, true);
    return false;
  }
}

function payload() {
  return {
    accounts: state.accounts,
    linuxdo: state.linuxdo,
    github: state.github,
    providers: state.providers,
    proxy: ($('proxyInput').value || '').trim(),
  };
}

function markDirty() {
  dirty = true;
  updateSaveState();
}

function updateSaveState() {
  const el = $('saveState');
  el.textContent = dirty ? '● 未保存' : '✓ 已保存';
  el.className = 'save-state ' + (dirty ? 'dirty' : 'saved');
}

function deleteCurrent() {
  if (isNew) {
    isNew = false; draft = null; selected = -1;
    renderAll();
    return;
  }
  if (selected < 0 || !state.accounts[selected]) return;
  const name = state.accounts[selected].name || '未命名';
  if (!confirm('删除账号「' + name + '」？')) return;
  state.accounts.splice(selected, 1);
  picked.clear(); selected = -1; draft = null;
  markDirty();
  renderAll();
  toast('已删除，记得保存');
}

/* ---------- 账号池 ---------- */
function renderPools() {
  const keys = [
    { key: 'linuxdo', title: 'Linux.do' },
    { key: 'github', title: 'GitHub' },
  ];
  $('poolsWrap').innerHTML = keys.map(({ key, title }) => poolCard(key, title)).join('');
  $('poolCount').textContent = state.linuxdo.length + state.github.length;
  if (draft) renderHints();
}

function poolCard(key, title) {
  const list = state[key] || [];
  let rows = '';
  if (!list.length) {
    rows = '<div class="pool-empty">还没有账号</div>';
  } else {
    rows = list.map((item, i) => {
      if (poolEditing.key === key && poolEditing.index === i) {
        return '<div class="pool-item">' +
          '<input data-pool-key="' + key + '" data-idx="' + i + '" data-pool-field="username" value="' + esc(item.username || '') + '" placeholder="用户名">' +
          '<input type="' + PASS_TYPE + '" data-pool-key="' + key + '" data-idx="' + i + '" data-pool-field="' + PASS + '" value="' + esc(item[PASS] || '') + '" placeholder="密码" autocomplete="new-' + PASS_TYPE + '">' +
          '<button type="button" class="link" data-pool-save="' + key + '">保存</button>' +
          '<button type="button" class="link" data-pool-cancel="' + key + '">取消</button>' +
        '</div>';
      }
      return '<div class="pool-item">' +
        '<span class="pool-user">' + esc(item.username || '未命名') + '</span>' +
        '<span class="pool-pass">' + (item[PASS] ? '••••••' : '无密码') + '</span>' +
        '<button type="button" class="link" data-pool-edit="' + key + '" data-idx="' + i + '">编辑</button>' +
        '<button type="button" class="link danger" data-pool-del="' + key + '" data-idx="' + i + '">删除</button>' +
      '</div>';
    }).join('');
  }
  return '<div class="pool-card">' +
    '<div class="pool-head"><h3>' + title + ' 账号池<span class="count">' + list.length + ' 个</span></h3></div>' +
    '<div class="pool-list">' + rows + '</div>' +
    '<div class="pool-form">' +
      '<input id="poolNew-' + key + '-user" placeholder="用户名" autocomplete="off">' +
      '<input id="poolNew-' + key + '-pass" type="' + PASS_TYPE + '" placeholder="密码" autocomplete="new-' + PASS_TYPE + '">' +
      '<button type="button" class="btn sm" data-pool-add="' + key + '">添加</button>' +
    '</div></div>';
}

function onPoolClick(e) {
  const edit = e.target.closest('[data-pool-edit]');
  if (edit) {
    const key = edit.dataset.poolEdit;
    const i = +edit.dataset.idx;
    poolEditing = { key, index: i, backup: clone(state[key][i]) };
    renderPools();
    return;
  }
  const save = e.target.closest('[data-pool-save]');
  if (save) {
    poolEditing = { key: null, index: -1, backup: null };
    renderPools();
    markDirty();
    toast('已修改，记得保存');
    return;
  }
  const cancel = e.target.closest('[data-pool-cancel]');
  if (cancel) {
    if (poolEditing.key && state[poolEditing.key][poolEditing.index] && poolEditing.backup) {
      state[poolEditing.key][poolEditing.index] = poolEditing.backup;
    }
    poolEditing = { key: null, index: -1, backup: null };
    renderPools();
    return;
  }
  const del = e.target.closest('[data-pool-del]');
  if (del) {
    const key = del.dataset.poolDel;
    const i = +del.dataset.idx;
    if (!confirm('删除账号「' + (state[key][i].username || '未命名') + '」？')) return;
    state[key].splice(i, 1);
    poolEditing = { key: null, index: -1, backup: null };
    renderPools();
    markDirty();
    return;
  }
  const add = e.target.closest('[data-pool-add]');
  if (add) {
    const key = add.dataset.poolAdd;
    const user = $('poolNew-' + key + '-user').value.trim();
    const pass = $('poolNew-' + key + '-pass').value;
    if (!user) { toast('用户名不能为空', true); return; }
    if (!pass) { toast('密码不能为空', true); return; }
    state[key] = state[key].filter((x) => x.username !== user);
    state[key].push({ username: user, [PASS]: pass });
    renderPools();
    markDirty();
    toast('已添加 ' + user);
  }
}

function onPoolInput(e) {
  const t = e.target;
  if (!t.dataset.poolField) return;
  const key = t.dataset.poolKey;
  const i = +t.dataset.idx;
  if (state[key] && state[key][i]) {
    state[key][i][t.dataset.poolField] = t.value;
    markDirty();
  }
}

/* ---------- 自定义站点 ---------- */
function renderProviders() {
  const keys = Object.keys(state.providers);
  $('providerCount').textContent = keys.length;

  let html = '';
  if (addingProvider) {
    html += '<div class="provider-card">' +
      '<div class="provider-head"><h3>添加自定义站点</h3></div>' +
      '<div class="provider-grid">' +
        '<label class="field span-2"><span>站点 URL</span><input id="newProviderOrigin" placeholder="https://example.com" autocomplete="off"></label>' +
        '<label class="field"><span>签到接口 <em>check_in_path</em></span><input id="newProviderCheckin" placeholder="/api/user/sign_in" autocomplete="off"></label>' +
      '</div>' +
      '<div class="provider-foot"><span class="hint">站点 key 会从域名自动生成</span>' +
        '<div class="actions"><button type="button" class="btn sm" data-provider-add-cancel>取消</button>' +
        '<button type="button" class="btn primary sm" data-provider-add-save>添加</button></div></div>' +
    '</div>';
  }
  if (keys.length) {
    html += keys.map((k) => providerCard(k, state.providers[k])).join('');
  } else if (!addingProvider) {
    html = '<div class="panel muted">还没有自定义站点。内置站点无需配置。</div>';
  }
  $('providersWrap').innerHTML = html;
}

function providerCard(key, p) {
  const bypass = p.bypass_method || '';
  return '<div class="provider-card">' +
    '<div class="provider-head">' +
      '<div><h3>' + esc(key) + '</h3><span class="provider-key">' + esc(p.origin || '') + '</span></div>' +
      '<button type="button" class="link danger" data-provider-del="' + esc(key) + '">删除</button>' +
    '</div>' +
    '<div class="provider-grid">' +
      '<label class="field span-2"><span>站点 URL</span><input data-provider-key="' + esc(key) + '" data-provider-field="origin" value="' + esc(p.origin || '') + '" placeholder="https://example.com" autocomplete="off"></label>' +
      '<label class="field"><span>登录接口 <em>login_path</em></span><input data-provider-key="' + esc(key) + '" data-provider-field="login_path" value="' + esc(p.login_path || '') + '" placeholder="/login" autocomplete="off"></label>' +
      '<label class="field"><span>签到接口 <em>check_in_path</em></span><input data-provider-key="' + esc(key) + '" data-provider-field="check_in_path" value="' + esc(p.check_in_path || '') + '" placeholder="/api/user/sign_in" autocomplete="off"></label>' +
      '<label class="field"><span>用户信息 <em>user_info_path</em></span><input data-provider-key="' + esc(key) + '" data-provider-field="user_info_path" value="' + esc(p.user_info_path || '') + '" placeholder="/api/user/self" autocomplete="off"></label>' +
      '<label class="field"><span>充值接口 <em>topup_path</em></span><input data-provider-key="' + esc(key) + '" data-provider-field="topup_path" value="' + esc(p.topup_path || '') + '" placeholder="/api/user/topup" autocomplete="off"></label>' +
      '<label class="field"><span>用户 ID Header <em>api_user_key</em></span><input data-provider-key="' + esc(key) + '" data-provider-field="api_user_key" value="' + esc(p.api_user_key || '') + '" placeholder="new-api-user" autocomplete="off"></label>' +
      '<label class="field"><span>绕过方式 <em>bypass_method</em></span><select data-provider-key="' + esc(key) + '" data-provider-field="bypass_method">' +
        '<option value=""' + (bypass ? '' : ' selected') + '>默认</option>' +
        '<option value="waf_cookies"' + (bypass === 'waf_cookies' ? ' selected' : '') + '>waf_cookies</option>' +
        '<option value="cf_clearance"' + (bypass === 'cf_clearance' ? ' selected' : '') + '>cf_clearance</option>' +
      '</select></label>' +
      '<label class="check" style="align-self:end"><input type="checkbox" data-provider-key="' + esc(key) + '" data-provider-field="auto_add"' + (p.auto_add ? ' checked' : '') + '><span>自动登记 <em>auto_add</em></span></label>' +
    '</div>' +
    '<details class="advanced"><summary>高级：完整 JSON</summary>' +
      '<textarea data-provider-json="' + esc(key) + '" spellcheck="false">' + esc(JSON.stringify(p, null, 2)) + '</textarea>' +
    '</details>' +
  '</div>';
}

function onProviderInput(e) {
  const t = e.target;
  if (t.dataset.providerJson) {
    if (e.type !== 'change') return;
    const key = t.dataset.providerJson;
    try {
      const obj = JSON.parse(t.value);
      if (!isObj(obj)) throw new Error('必须是 JSON 对象');
      state.providers[key] = obj;
      markDirty();
      toast('已更新 ' + key);
    } catch (err) {
      toast('JSON 无效：' + err.message, true);
    }
    return;
  }
  const key = t.dataset.providerKey;
  const field = t.dataset.providerField;
  if (!key || !field || !state.providers[key]) return;
  const p = state.providers[key];
  if (t.type === 'checkbox') {
    if (t.checked) p[field] = true; else delete p[field];
  } else {
    const v = t.value.trim();
    if (v) p[field] = v; else delete p[field];
  }
  markDirty();
}

function onProviderClick(e) {
  const del = e.target.closest('[data-provider-del]');
  if (del) {
    const key = del.dataset.providerDel;
    const used = state.accounts.filter((a) => a.provider === key).length;
    const msg = used
      ? '有 ' + used + ' 个账号正在使用「' + key + '」，删除后这些账号会失效。继续？'
      : '删除自定义站点「' + key + '」？';
    if (!confirm(msg)) return;
    delete state.providers[key];
    renderProviders();
    markDirty();
    return;
  }
  const cancel = e.target.closest('[data-provider-add-cancel]');
  if (cancel) { addingProvider = false; renderProviders(); return; }
  const save = e.target.closest('[data-provider-add-save]');
  if (save) {
    const origin = ($('newProviderOrigin').value || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(origin)) { toast('站点 URL 需要以 http(s):// 开头', true); return; }
    const key = hostKey(origin);
    if (!key) { toast('站点 URL 无效', true); return; }
    const isBuiltin = Object.keys(builtin).some((k) => (builtin[k] || '').replace(/\/+$/, '') === origin);
    if (isBuiltin) { toast('这是内置站点，直接在选择框里选即可', true); return; }
    if (state.providers[key]) { toast('该站点已存在', true); return; }
    const p = { origin };
    const checkin = ($('newProviderCheckin').value || '').trim();
    if (checkin) p.check_in_path = checkin;
    state.providers[key] = p;
    addingProvider = false;
    renderProviders();
    markDirty();
    toast('已添加 ' + key);
  }
}

/* ---------- 设置 / 导出 ---------- */
function setTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach((p) => { p.hidden = p.id !== 'tab-' + name; });
  if (name === 'account') renderEditor();
  if (name === 'pools') renderPools();
  if (name === 'providers') renderProviders();
}

async function doExport() {
  if (dirty || isNew) {
    const ok = await saveAll();
    if (!ok) return;
  }
  try {
    const data = await api('/api/export', payload());
    exportTexts = [
      ['APP_CONFIG（推荐）', data.app_config],
      ['ACCOUNTS', data.accounts],
      ['PROVIDERS', data.providers],
      ['ACCOUNTS_LINUX_DO', data.linuxdo],
      ['ACCOUNTS_GITHUB', data.github],
    ].filter(([, v]) => v);

    $('exportWrap').innerHTML = exportTexts.map(([name, value], i) =>
      '<div class="export-item">' +
        '<div class="export-item-head"><strong>' + esc(name) + '</strong>' +
        '<button type="button" class="btn sm" data-copy="' + i + '">复制</button></div>' +
        '<textarea readonly spellcheck="false">' + esc(value) + '</textarea>' +
      '</div>'
    ).join('');
    $('exportWrap').hidden = false;
    toast('已生成，复制后粘贴到 GitHub Secret');
  } catch (e) {
    toast('导出失败：' + e.message, true);
  }
}

async function doSync() {
  if (dirty || isNew) {
    const ok = await saveAll();
    if (!ok) return;
  }
  if (!confirm('把当前配置写入 .env 的 APP_CONFIG？')) return;
  try {
    await api('/api/sync', payload());
    toast('已同步到 .env');
  } catch (e) {
    toast('同步失败：' + e.message, true);
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (err) { /* ignore */ }
    ta.remove();
  }
}

/* ---------- 渲染全部 ---------- */
function renderAll() {
  renderList();
  renderEditor();
  renderPools();
  renderProviders();
  updateSaveState();
}

init();
