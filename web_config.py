#!/usr/bin/env python3
"""
NewAPI 签到配置 Web 管理页 — 可视化查看/修改已填的配置

运行:
    python web_config.py [端口]      # 默认 8790，自动打开浏览器

功能:
    - 查看所有已配置的账号（密钥以掩码显示，如 yFLm****zw==）
    - 精准修改单个账号（token 过期时只重填这一个的密钥）
    - 添加/删除账号、管理 OAuth 账号池、自定义站点
    - 一键导出 APP_CONFIG（粘贴到 GitHub Secret）
    - 一键同步到 .env

安全: 只绑定 127.0.0.1，数据仅在本机处理，不会上传。
"""

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from manage_config import (
    BUILTIN_PROVIDERS,
    DATA_FILE,
    ENV_FILE,
    empty_data,
    env_flag_enabled,
    load_data,
    match_provider,
    make_provider_key,
    read_env_config,
    save_data,
    set_check_in_once_per_day,
)

DEFAULT_PORT = 8790
CONFIG_KEYS = ("ACCOUNTS", "ACCOUNTS_LINUX_DO", "ACCOUNTS_GITHUB", "PROVIDERS")
EXTRA_KEYS = ("CHECK_IN_ONCE_PER_DAY",)

PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NewAPI 签到配置管理</title>
<style>
:root{
  --bg:#0f172a; --surface:#1e293b; --border:#334155; --primary:#6366f1;
  --primary-glow:rgba(99,102,241,0.3); --text:#f1f5f9; --text-muted:#94a3b8;
  --success:#10b981; --danger:#ef4444; --warn:#f59e0b; --radius:10px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);padding:32px 20px;line-height:1.6}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:1.5rem;margin-bottom:4px}
.sub{color:var(--text-muted);font-size:0.9rem;margin-bottom:6px}
.hint{color:var(--text-muted);font-size:0.78rem;margin-bottom:24px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;margin-bottom:16px}
.card-title{font-size:0.8rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--primary);font-weight:700;margin-bottom:14px}
label{display:block;font-size:0.78rem;font-weight:600;color:var(--text-muted);margin-bottom:4px}
input,select{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:9px 11px;color:var(--text);font-size:0.88rem;outline:none;transition:border-color .2s}
input:focus,select:focus{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-glow)}
input[readonly]{opacity:.55}
.btn{display:inline-block;background:var(--surface);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:8px 16px;font-size:0.85rem;cursor:pointer;transition:all .15s}
.btn:hover{border-color:var(--primary);color:var(--primary)}
.btn.primary{background:var(--primary);border-color:var(--primary);color:#fff;font-weight:600}
.btn.primary:hover{filter:brightness(1.1);color:#fff}
.btn.danger{color:var(--danger)}
.btn.danger:hover{border-color:var(--danger)}
.btn.sm{padding:4px 10px;font-size:0.78rem}
table{width:100%;border-collapse:collapse;font-size:0.85rem}
th{text-align:left;color:var(--text-muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:.04em;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:8px;border-bottom:1px solid var(--border)}
tr:hover td{background:rgba(0,0,0,0.15)}
.mask{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text-muted)}
.chip{display:inline-block;font-size:0.7rem;padding:1px 8px;border-radius:10px;border:1px solid var(--border);color:var(--text-muted);margin-right:4px}
.chip.on{border-color:var(--success);color:var(--success)}
.tag{display:inline-block;font-size:0.7rem;padding:1px 8px;border-radius:10px;background:rgba(99,102,241,.15);color:var(--primary);margin-right:4px}
.row-actions{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.col-span-2{grid-column:1/-1}
.pool-item{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:rgba(0,0,0,0.2);border:1px solid var(--border);border-radius:6px;margin-bottom:8px;font-size:0.85rem}
.pool-item .rm{background:none;border:none;color:var(--danger);cursor:pointer;font-size:0.78rem}
.pool-item .rm:hover{text-decoration:underline}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:#111827;border:1px solid var(--border);border-radius:8px;padding:10px 22px;font-size:0.85rem;opacity:0;transition:opacity .25s;pointer-events:none;z-index:99}
.toast.show{opacity:1}
.modal{position:fixed;inset:0;background:rgba(2,6,23,.75);display:none;align-items:center;justify-content:center;z-index:50;padding:20px}
.modal.open{display:flex}
.modal-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);max-width:720px;width:100%;padding:20px 24px;max-height:85vh;overflow:auto}
.modal-box textarea{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.8rem;min-height:160px;resize:vertical;outline:none;white-space:pre-wrap;word-break:break-all}
.empty{color:var(--text-muted);font-size:0.82rem;padding:12px 0}
.warn-line{font-size:0.78rem;color:var(--warn);margin-top:10px}
</style>
</head>
<body>
<div class="wrap">
  <h1>⚙️ NewAPI 签到配置管理</h1>
  <div class="sub" id="envNote"></div>
  <div class="hint">本地管理页 · 只绑定 127.0.0.1 · 数据仅在本机处理。密钥以掩码显示，改谁填谁，其他账号不受影响。</div>

  <div class="card">
    <div class="card-title">账号列表</div>
    <div id="accountTableWrap"><div class="empty">加载中...</div></div>
    <div class="row-actions">
      <button class="btn primary sm" onclick="openForm(-1)">＋ 添加账号</button>
    </div>
  </div>

  <div id="formCard" class="card" style="display:none">
    <div class="card-title" id="formTitle">编辑账号</div>
    <div class="grid">
      <div><label>备注名</label><input id="fName" placeholder="如：薄荷"></div>
      <div><label>站点 URL</label><input id="fUrl" placeholder="https://x666.me" oninput="urlHint()"></div>
      <div class="col-span-2" id="urlHint" style="font-size:0.78rem;color:var(--success)"></div>
      <div class="col-span-2"><label>用户 ID</label><input id="fUid" placeholder="F12 → Local Storage → user → id"></div>
      <div><label>System Access Token <span style="color:var(--text-muted)">(留空保持不变)</span></label><input id="fToken" autocomplete="off"></div>
      <div><label>Session Cookie <span style="color:var(--text-muted)">(留空保持不变)</span></label><input id="fCookie" autocomplete="off"></div>
      <div>
        <label>认证开关</label>
        <div style="display:flex;gap:18px;padding:8px 2px">
          <label style="display:flex;align-items:center;gap:6px;color:var(--text);font-size:0.85rem;cursor:pointer">
            <input type="checkbox" id="fLinuxdo" style="width:auto"> Linux.do
          </label>
          <label style="display:flex;align-items:center;gap:6px;color:var(--text);font-size:0.85rem;cursor:pointer">
            <input type="checkbox" id="fGithub" style="width:auto"> GitHub
          </label>
        </div>
      </div>
    </div>
    <div class="row-actions">
      <button class="btn primary" onclick="submitForm()">保存账号</button>
      <button class="btn" onclick="closeForm()">取消</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">OAuth 账号池</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <label style="margin:0;color:#f59e0b">ACCOUNTS_LINUX_DO</label>
          <button class="btn sm" onclick="addPool('linuxdo')">＋</button>
        </div>
        <div id="linuxdoPool"></div>
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <label style="margin:0;color:#6366f1">ACCOUNTS_GITHUB</label>
          <button class="btn sm" onclick="addPool('github')">＋</button>
        </div>
        <div id="githubPool"></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">自定义站点 PROVIDERS</div>
    <div id="providersWrap"></div>
    <div class="row-actions">
      <button class="btn sm" onclick="addProvider()">＋ 添加自定义站点</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">保存与同步</div>
    <div class="row-actions">
      <button class="btn primary" onclick="saveAll()">💾 保存到 accounts.json</button>
      <button class="btn" onclick="doSync()">🔄 同步到 .env</button>
    </div>
    <div class="warn-line">所有改动都会自动保存到本机 accounts.json（仅本地，不上传）。</div>
    <div class="row-actions" style="margin-top:6px;align-items:center">
      <span id="saveState" style="font-size:0.82rem;color:var(--success)">✔ 已保存到本机 accounts.json</span>
    </div>
    <div class="row-actions" style="margin-top:12px;align-items:center">
      <label style="margin:0;display:inline-flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="onceCb" style="width:16px;height:16px;accent-color:var(--primary)">
        每天只签到一次（已签成功的账号当天跳过，跨天自动重置）
      </label>
      <button class="btn sm" onclick="saveOnceFlag()">保存开关</button>
      <span class="warn-line" style="margin:0">写入 .env，需 sync / 导出同步到 GitHub</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">导出到 GitHub Secrets</div>
    <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:12px;">
      两种方式任选：<b>方式 A</b>（推荐）只需 1 个 Secret，或 <b>方式 B</b> 分开填 4 个 Secret。
    </p>
    <div class="row-actions" style="margin-bottom:12px">
      <button class="btn primary" onclick="doExport()">⚡ 生成并导出</button>
    </div>

    <div id="exportSection" style="display:none">
      <div style="margin-bottom:16px;padding:12px;background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.2);border-radius:8px">
        <div style="font-weight:600;font-size:0.88rem;color:var(--success);margin-bottom:4px">方式 A（推荐）：统一变量 APP_CONFIG</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px">GitHub 只需维护 1 个 Secret，配置全部打包在这一个 JSON 里。</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <code style="font-size:0.82rem;color:var(--primary)">APP_CONFIG</code>
          <button class="btn sm" onclick="copyExport('app_config')">📋 复制</button>
        </div>
        <textarea id="outAppConfig" readonly style="min-height:80px;font-size:0.78rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;width:100%;resize:vertical"></textarea>
      </div>

      <div style="padding:12px;background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.2);border-radius:8px">
        <div style="font-weight:600;font-size:0.88rem;color:var(--primary);margin-bottom:4px">方式 B：分别填写各 Secret</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:12px">适合只想改某一项时单独更新（旧版兼容）。</div>

        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <code style="font-size:0.82rem">ACCOUNTS</code>
            <button class="btn sm" onclick="copyExport('accounts')">📋 复制</button>
          </div>
          <textarea id="outAccounts" readonly style="min-height:60px;font-size:0.78rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;width:100%;resize:vertical" placeholder="无账号"></textarea>
        </div>

        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <code style="font-size:0.82rem">PROVIDERS</code>
            <span style="font-size:0.72rem;color:var(--text-muted)">自定义站点才需要</span>
            <button class="btn sm" onclick="copyExport('providers')">📋 复制</button>
          </div>
          <textarea id="outProviders" readonly style="min-height:50px;font-size:0.78rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;width:100%;resize:vertical" placeholder="无需 PROVIDERS（仅内置站点）"></textarea>
        </div>

        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <code style="font-size:0.82rem">ACCOUNTS_LINUX_DO</code>
            <span style="font-size:0.72rem;color:var(--text-muted)">有 OAuth 才需要</span>
            <button class="btn sm" onclick="copyExport('linuxdo')">📋 复制</button>
          </div>
          <textarea id="outLinuxdo" readonly style="min-height:40px;font-size:0.78rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;width:100%;resize:vertical" placeholder="无需 OAuth 时留空"></textarea>
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <code style="font-size:0.82rem">ACCOUNTS_GITHUB</code>
            <span style="font-size:0.72rem;color:var(--text-muted)">有 OAuth 才需要</span>
            <button class="btn sm" onclick="copyExport('github')">📋 复制</button>
          </div>
          <textarea id="outGithub" readonly style="min-height:40px;font-size:0.78rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;width:100%;resize:vertical" placeholder="无需 OAuth 时留空"></textarea>
        </div>
      </div>

      <div style="margin-top:12px;font-size:0.78rem;color:var(--text-muted)">
        📍 复制后去 GitHub → 仓库 → Settings → Environments → production → 逐个替换对应 Secret 名称即可。
      </div>
    </div>
    <div id="exportStatus"></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let state = { accounts: [], linuxdo: [], github: [], providers: {} };
let builtin = {};
let editIdx = -1;      // -1 = 添加
let editing = null;    // 编辑中的原始账号副本
let dirty = false;     // 是否有未保存更改
let saveTimer = null;  // 自动保存防抖定时器

function updateSaveState() {
  const el = document.getElementById('saveState');
  if (!el) return;
  if (dirty) {
    el.textContent = '● 有未保存更改（自动保存中…）';
    el.style.color = 'var(--warn)';
  } else {
    el.textContent = '✔ 已保存到本机 accounts.json';
    el.style.color = 'var(--success)';
  }
}
function markDirty() {
  dirty = true;
  updateSaveState();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(autoSave, 1200);   // 停止操作 1.2s 后自动保存
}
async function autoSave() {
  if (!dirty) return;
  try {
    await api('/api/save', payload());
    dirty = false;
    updateSaveState();
    toast('✅ 已自动保存到 accounts.json');
  } catch (e) {
    toast('❌ 自动保存失败: ' + e.message);
  }
}
window.addEventListener('beforeunload', (e) => {
  if (dirty) { e.preventDefault(); e.returnValue = ''; }   // 有未保存更改时拦截关闭提醒
});

function mask(v) {
  if (!v) return '';
  const s = String(v);
  if (s.length <= 4) return '****';
  if (s.length <= 10) return s.slice(0, 2) + '****' + s.slice(-2);
  return s.slice(0, 4) + '****' + s.slice(-4);
}
function authChips(a) {
  const chips = [];
  if (a.system_access_token) chips.push('<span class="tag">Token</span>');
  if (a.cookies && a.cookies.session) chips.push('<span class="tag">Cookie</span>');
  if (a['linux.do']) chips.push('<span class="chip on">Linux.do</span>');
  if (a.github) chips.push('<span class="chip on">GitHub</span>');
  return chips.join('') || '<span class="chip">无认证</span>';
}
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function secretMask(a) {
  if (a.system_access_token) return '<span class="mask">' + esc(mask(a.system_access_token)) + '</span>';
  if (a.cookies && a.cookies.session) return '<span class="mask">' + esc(mask(a.cookies.session)) + '</span>';
  return '<span class="chip">—</span>';
}
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}
async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'HTTP ' + res.status);
  return data;
}

/* ---------- 账号列表 ---------- */
function renderAccounts() {
  const w = document.getElementById('accountTableWrap');
  if (!state.accounts.length) {
    w.innerHTML = '<div class="empty">还没有账号，点下方「＋ 添加账号」开始。</div>';
    return;
  }
  let html = '<table><thead><tr><th>备注名</th><th>provider</th><th>用户ID</th><th>密钥</th><th>认证</th><th></th></tr></thead><tbody>';
  state.accounts.forEach((a, i) => {
    const name = esc(a.name || '<未命名>');
    html += '<tr>' +
      '<td>' + name + '</td>' +
      '<td>' + esc(a.provider) + '</td>' +
      '<td>' + esc(a.api_user) + '</td>' +
      '<td>' + secretMask(a) + '</td>' +
      '<td>' + authChips(a) + '</td>' +
      '<td style="white-space:nowrap">' +
        '<button class="btn sm" onclick="openForm(' + i + ')">编辑</button> ' +
        '<button class="btn sm danger" onclick="removeAccount(' + i + ')">删除</button>' +
      '</td></tr>';
  });
  html += '</tbody></table>';
  w.innerHTML = html;
}

/* ---------- 添加/编辑表单 ---------- */
function openForm(idx) {
  editIdx = idx;
  editing = idx >= 0 ? JSON.parse(JSON.stringify(state.accounts[idx])) : null;
  document.getElementById('formCard').style.display = '';
  document.getElementById('formTitle').textContent = idx >= 0 ? '编辑账号 · ' + (editing.name || '') : '添加账号';
  document.getElementById('fName').value = editing ? (editing.name || '') : '';
  document.getElementById('fUid').value = editing ? (editing.api_user || '') : '';
  document.getElementById('fToken').value = '';
  document.getElementById('fToken').placeholder = editing && editing.system_access_token ? '已设置：' + mask(editing.system_access_token) + '（留空保持不变）' : '';
  document.getElementById('fCookie').value = '';
  document.getElementById('fCookie').placeholder = editing && editing.cookies && editing.cookies.session ? '已设置：' + mask(editing.cookies.session) + '（留空保持不变）' : '';
  document.getElementById('fLinuxdo').checked = !!(editing && editing['linux.do']);
  document.getElementById('fGithub').checked = !!(editing && editing.github);
  const url = editing ? editing.provider : '';
  document.getElementById('fUrl').value = builtin[url] ? builtin[url] : url;
  urlHint();
  document.getElementById('formCard').scrollIntoView({ behavior: 'smooth' });
}
function closeForm() {
  document.getElementById('formCard').style.display = 'none';
  editIdx = -1;
  editing = null;
}
function urlHint() {
  const u = document.getElementById('fUrl').value.trim().replace(/\/+$/, '');
  const h = document.getElementById('urlHint');
  if (!u) { h.textContent = ''; return; }
  const name = Object.keys(builtin).find(k => (builtin[k] || '').replace(/\/+$/, '') === u);
  if (name) { h.textContent = '→ 匹配内置 provider: ' + name; h.style.color = 'var(--success)'; }
  else if (/^https?:\/\//.test(u)) { h.textContent = '→ 非内置站点，将自动登记为自定义 provider'; h.style.color = 'var(--warn)'; }
  else h.textContent = '';
}
function submitForm() {
  const name = document.getElementById('fName').value.trim();
  const url = document.getElementById('fUrl').value.trim();
  const uid = document.getElementById('fUid').value.trim();
  if (!name) { toast('⚠️ 备注名不能为空'); return; }
  if (!/^https?:\/\//.test(url)) { toast('⚠️ 站点 URL 以 http(s):// 开头'); return; }
  if (!uid) { toast('⚠️ 用户 ID 不能为空'); return; }
  const token = document.getElementById('fToken').value.trim();
  const cookie = document.getElementById('fCookie').value.trim();
  const linuxdo = document.getElementById('fLinuxdo').checked;
  const github = document.getElementById('fGithub').checked;

  // 编辑模式下留空=保持不变，清除=输入框清空且无原值
  let acct;
  if (editIdx >= 0 && editing) {
    acct = JSON.parse(JSON.stringify(editing));
    acct.name = name;
    acct.api_user = uid;
    if (token !== '') acct.system_access_token = token;
    if (cookie !== '') acct.cookies = { session: cookie };
  } else {
    acct = { name, api_user: uid };
    if (token) acct.system_access_token = token;
    if (cookie) acct.cookies = { session: cookie };
  }
  // provider 解析
  const cleaned = url.replace(/\/+$/, '');
  const built = Object.keys(builtin).find(k => (builtin[k] || '').replace(/\/+$/, '') === cleaned);
  if (built) acct.provider = built;
  else {
    const pk = providerKey(cleaned);
    acct.provider = pk;
    if (!state.providers[pk]) {
      state.providers[pk] = {
        origin: cleaned,
        check_in_path: '/api/user/checkin',
        user_info_path: '/api/user/self',
        api_user_key: 'new-api-user'
      };
    }
  }
  // OAuth 开关
  if (linuxdo) acct['linux.do'] = true; else delete acct['linux.do'];
  if (github) acct.github = true; else delete acct.github;
  // 无任何认证方式
  if (!acct.system_access_token && !(acct.cookies && acct.cookies.session) && !acct['linux.do'] && !acct.github) {
    toast('⚠️ 至少配置一种认证方式（Token/Cookie/OAuth）');
    return;
  }
  if (editIdx >= 0) state.accounts[editIdx] = acct;
  else state.accounts.push(acct);
  closeForm();
  renderAccounts();
  renderProviders();
  markDirty();
  toast('✅ 已更新「' + name + '」');
}
function removeAccount(idx) {
  const a = state.accounts[idx];
  if (!confirm('确认删除账号「' + (a.name || '') + '」？')) return;
  state.accounts.splice(idx, 1);
  renderAccounts();
  markDirty();
  toast('已删除');
}
function providerKey(url) {
  try { return new URL(url).hostname.replace(/\./g, '_'); } catch (e) { return 'custom'; }
}

/* ---------- OAuth 账号池 ---------- */
function renderPools() {
  for (const [key, el] of [['linuxdo', 'linuxdoPool'], ['github', 'githubPool']]) {
    const list = state[key];
    const w = document.getElementById(el);
    if (!list.length) { w.innerHTML = '<div class="empty">空</div>'; continue; }
    w.innerHTML = list.map((x, i) =>
      '<div class="pool-item"><span>' + esc(x.username) +
      '<span style="color:var(--text-muted);font-size:0.75rem;margin-left:6px">(' + (x.password ? '已设密码' : '无密码') + ')</span></span>' +
      '<button class="rm" onclick="removePool(\'' + key + '\',' + i + ')">删除</button></div>'
    ).join('');
  }
}
function removePool(key, idx) {
  if (!confirm('确认删除该 OAuth 账号？')) return;
  state[key].splice(idx, 1);
  renderPools();
  markDirty();
  toast('已删除');
}
function addPool(key) {
  const u = prompt('用户名:');
  if (!u) return;
  const p = prompt('密码:');
  if (!p) return;
  state[key] = state[key].filter(x => x.username !== u);
  state[key].push({ username: u, password: p });
  renderPools();
  markDirty();
  toast('已添加 ' + u);
}

/* ---------- 自定义站点 ---------- */
function renderProviders() {
  const w = document.getElementById('providersWrap');
  const keys = Object.keys(state.providers);
  if (!keys.length) { w.innerHTML = '<div class="empty">无自定义站点</div>'; return; }
  w.innerHTML = keys.map((k, i) =>
    '<div class="pool-item"><span><b>' + esc(k) + '</b> <span style="color:var(--text-muted)">' + esc(state.providers[k].origin) + '</span></span>' +
    '<button class="rm" onclick="removeProvider(' + i + ')">删除</button></div>'
  ).join('');
}
function removeProvider(idx) {
  const key = Object.keys(state.providers)[idx];
  if (!confirm('确认删除自定义站点「' + key + '」？')) return;
  delete state.providers[key];
  renderProviders();
  markDirty();
  toast('已删除');
}
function addProvider() {
  const url = prompt('站点 URL:');
  if (!url || !/^https?:\/\//.test(url)) { toast('⚠️ 格式不对'); return; }
  const cleaned = url.replace(/\/+$/, '');
  if (Object.values(builtin).some(v => v.replace(/\/+$/, '') === cleaned)) {
    toast('⚠️ 这是内置站点，无需添加');
    return;
  }
  const pk = providerKey(cleaned);
  if (state.providers[pk]) { toast('⚠️ 该站点已存在'); return; }
  state.providers[pk] = {
    origin: cleaned,
    check_in_path: '/api/user/checkin',
    user_info_path: '/api/user/self',
    api_user_key: 'new-api-user'
  };
  renderProviders();
  markDirty();
  toast('已添加 ' + pk);
}

/* ---------- 保存 / 导出 / 同步 ---------- */
function payload() {
  return {
    accounts: state.accounts,
    linuxdo: state.linuxdo,
    github: state.github,
    providers: state.providers
  };
}
async function saveAll() {
  try {
    await api('/api/save', payload());
    dirty = false;
    clearTimeout(saveTimer);
    updateSaveState();
    renderAccounts();
    toast('✅ 已保存到 accounts.json');
  } catch (e) { toast('❌ ' + e.message); }
}
function copyText(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta);
}
let _exportData = null;
async function doExport() {
  try {
    const data = await api('/api/export', payload());
    _exportData = data;
    document.getElementById('outAppConfig').value = data.app_config || '';
    document.getElementById('outAccounts').value = data.accounts || '';
    document.getElementById('outProviders').value = data.providers || '';
    document.getElementById('outLinuxdo').value = data.linuxdo || '';
    document.getElementById('outGithub').value = data.github || '';
    document.getElementById('exportSection').style.display = '';
    document.getElementById('exportStatus').innerHTML = '<div style="font-size:0.82rem;color:var(--success);margin-top:8px">✅ 已生成，复制对应 Secret 粘贴到 GitHub 即可</div>';
  } catch (e) { toast('❌ ' + e.message); }
}
function copyExport(key) {
  if (!_exportData) { toast('⚠️ 请先点击「生成并导出」'); return; }
  const map = { app_config: 'app_config', accounts: 'accounts', providers: 'providers', linuxdo: 'linuxdo', github: 'github' };
  const text = _exportData[map[key]] || '';
  if (!text) { toast('⚠️ 该 Secret 无内容，无需复制'); return; }
  copyText(text);
  toast('✅ 已复制 ' + key.toUpperCase());
}
async function doSync() {
  if (!confirm('把当前配置同步成统一变量 APP_CONFIG 写入 .env？（其他设置保留）')) return;
  try {
    await api('/api/sync', payload());
    toast('✅ 已同步到 .env');
  } catch (e) { toast('❌ ' + e.message); }
}
async function saveOnceFlag() {
  try {
    const r = await api('/api/settings', { check_in_once_per_day: document.getElementById('onceCb').checked });
    toast(r.check_in_once_per_day ? '✅ 已开启「每天只签到一次」' : '✅ 已关闭');
  } catch (e) { toast('❌ ' + e.message); }
}
async function loadOnceFlag() {
  try {
    const r = await api('/api/settings');
    document.getElementById('onceCb').checked = !!r.check_in_once_per_day;
  } catch (e) {}
}

/* ---------- 初始化 ---------- */
async function init() {
  try {
    const data = await api('/api/state');
    state = { accounts: data.accounts || [], linuxdo: data.linuxdo || [], github: data.github || [], providers: data.providers || {} };
    builtin = data.builtin || {};
    if (data.env_legacy_keys && data.env_legacy_keys.length) {
      document.getElementById('envNote').innerHTML =
        'ℹ️ 检测到 .env 中还有旧配置键 ' + data.env_legacy_keys.map(esc).join(', ') +
        '，可点下方「🔄 同步到 .env」整合为 APP_CONFIG。';
    }
    renderAccounts();
    renderPools();
    renderProviders();
    loadOnceFlag();
  } catch (e) {
    document.getElementById('accountTableWrap').innerHTML =
      '<div class="empty">加载失败: ' + esc(e.message) + '</div>';
  }
}
init();
</script>
</body>
</html>
"""


def build_payload(data, env):
    """根据提交的数据构建完整配置（以页面内容为准，删除才会真正生效）"""
    accounts = data.get("accounts") or []
    linuxdo = data.get("linuxdo") or []
    github = data.get("github") or []
    providers = data.get("providers") or {}
    return accounts, linuxdo, github, providers


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            data = load_data()
            env = read_env_config()
            legacy = [k for k in CONFIG_KEYS if env.get(k)]
            self._send_json({
                "accounts": data.get("ACCOUNTS", []),
                "linuxdo": data.get("ACCOUNTS_LINUX_DO", []),
                "github": data.get("ACCOUNTS_GITHUB", []),
                "providers": data.get("PROVIDERS", {}),
                "builtin": BUILTIN_PROVIDERS,
                "env_legacy_keys": legacy,
            })
        elif path == "/api/settings":
            self._send_json({"check_in_once_per_day": env_flag_enabled()})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read_body()
            if path == "/api/save":
                data = {
                    "ACCOUNTS": body.get("accounts") or [],
                    "ACCOUNTS_LINUX_DO": body.get("linuxdo") or [],
                    "ACCOUNTS_GITHUB": body.get("github") or [],
                    "PROVIDERS": body.get("providers") or {},
                }
                save_data(data)
                self._send_json({"ok": True})
            elif path == "/api/export":
                env = read_env_config()
                accounts, linuxdo, github, providers = build_payload(body, env)
                unified = {k: v for k, v in {
                    "ACCOUNTS": accounts,
                    "ACCOUNTS_LINUX_DO": linuxdo,
                    "ACCOUNTS_GITHUB": github,
                    "PROVIDERS": providers,
                }.items() if v}
                if env.get("PROXY"):
                    unified["PROXY"] = env["PROXY"]
                if env.get("CHECK_IN_ONCE_PER_DAY"):
                    unified["CHECK_IN_ONCE_PER_DAY"] = env["CHECK_IN_ONCE_PER_DAY"]
                self._send_json({
                    "app_config": json.dumps(unified, ensure_ascii=False, separators=(",", ":")),
                    "accounts": json.dumps(accounts, ensure_ascii=False, separators=(",", ":")) if accounts else "",
                    "providers": json.dumps(providers, ensure_ascii=False, separators=(",", ":")) if providers else "",
                    "linuxdo": json.dumps(linuxdo, ensure_ascii=False, separators=(",", ":")) if linuxdo else "",
                    "github": json.dumps(github, ensure_ascii=False, separators=(",", ":")) if github else "",
                })
            elif path == "/api/sync":
                from manage_config import CONFIG_KEYS as _CK
                env = read_env_config()
                accounts, linuxdo, github, providers = build_payload(body, env)
                effective = {
                    "ACCOUNTS": accounts,
                    "ACCOUNTS_LINUX_DO": linuxdo,
                    "ACCOUNTS_GITHUB": github,
                    "PROVIDERS": providers,
                }
                proxy = env.get("PROXY")
                unified = {k: v for k, v in effective.items() if v}
                if proxy:
                    unified["PROXY"] = proxy
                if env.get("CHECK_IN_ONCE_PER_DAY"):
                    unified["CHECK_IN_ONCE_PER_DAY"] = env["CHECK_IN_ONCE_PER_DAY"]

                lines = []
                if os.path.exists(ENV_FILE):
                    with open(ENV_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                kept = [
                    ln for ln in lines
                    if not ln.strip() or ln.strip().startswith("#") or "=" not in ln
                    or ln.strip().partition("=")[0].strip() not in _CK + ("APP_CONFIG", "PROXY", "CHECK_IN_ONCE_PER_DAY")
                ]
                with open(ENV_FILE, "w", encoding="utf-8") as f:
                    f.writelines(kept)
                    if unified:
                        f.write(f"APP_CONFIG={json.dumps(unified, ensure_ascii=False, separators=(',', ':'))}\n")
                self._send_json({"ok": True})
            elif path == "/api/settings":
                enabled = bool(body.get("check_in_once_per_day"))
                set_check_in_once_per_day(enabled)
                self._send_json({"ok": True, "check_in_once_per_day": enabled})
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def serve(port: int = DEFAULT_PORT):
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"⚠️ 端口 {port} 被占用，尝试其它端口...")
        for p in range(port + 1, port + 20):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
                port = p
                break
            except OSError:
                continue
        else:
            print("❌ 找不到可用端口")
            return 1

    url = f"http://127.0.0.1:{port}/"
    print("=" * 50)
    print("  NewAPI 签到配置管理页")
    print(f"  地址: {url}")
    print("  关闭本窗口即可停止服务")
    print("  安全: 仅本机可访问，数据不会上传")
    print("=" * 50)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("用法: python web_config.py [端口]")
            sys.exit(1)
    sys.exit(serve(port))
