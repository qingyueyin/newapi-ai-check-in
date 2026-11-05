#!/usr/bin/env python3
"""
NewAPI 签到配置 Web 管理页 — 可视化查看/修改已填的配置

运行:
    python web_config.py [端口]      # 默认 8790，自动打开浏览器

前端: static/index.html + static/app.js + static/style.css
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
	env_flag_enabled,
	load_data,
	read_env_config,
	save_data,
	set_check_in_once_per_day,
)

DEFAULT_PORT = 8790
CONFIG_KEYS = ('ACCOUNTS', 'ACCOUNTS_LINUX_DO', 'ACCOUNTS_GITHUB', 'PROVIDERS')
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# Windows 默认 GBK 控制台会让日志里的 emoji 直接抛异常，这里兜底
for _stream in (sys.stdout, sys.stderr):
	try:
		_stream.reconfigure(encoding='utf-8', errors='replace')
	except Exception:
		pass

CONTENT_TYPES = {
	'.html': 'text/html; charset=utf-8',
	'.js': 'text/javascript; charset=utf-8',
	'.css': 'text/css; charset=utf-8',
	'.svg': 'image/svg+xml',
	'.ico': 'image/x-icon',
}


def build_payload(data, env):
	"""根据提交的数据构建完整配置（以页面内容为准，删除才会真正生效）"""
	accounts = data.get('accounts') or []
	linuxdo = data.get('linuxdo') or []
	github = data.get('github') or []
	providers = data.get('providers') or {}
	return accounts, linuxdo, github, providers


def set_env_value(key, value):
	"""写入 .env：有 APP_CONFIG 则并入 JSON，否则写独立行；空值表示删除"""
	lines = []
	if os.path.exists(ENV_FILE):
		with open(ENV_FILE, 'r', encoding='utf-8') as f:
			lines = f.readlines()
	app_idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith('APP_CONFIG=')), None)
	if app_idx is not None:
		out = []
		for i, ln in enumerate(lines):
			if i == app_idx:
				raw = ln.strip()[len('APP_CONFIG=') :]
				try:
					obj = json.loads(raw)
				except json.JSONDecodeError:
					obj = {}
				if not isinstance(obj, dict):
					obj = {}
				if value:
					obj[key] = value
				else:
					obj.pop(key, None)
				out.append('APP_CONFIG=' + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n')
			else:
				out.append(ln)
		lines = out
	else:
		lines = [ln for ln in lines if not ln.strip().startswith(key + '=')]
		if value:
			lines.append(f'{key}={value}\n')
	with open(ENV_FILE, 'w', encoding='utf-8') as f:
		f.writelines(lines)


class Handler(BaseHTTPRequestHandler):
	def log_message(self, fmt, *args):
		pass

	def _send_json(self, obj, status=200):
		body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
		self.send_response(status)
		self.send_header('Content-Type', 'application/json; charset=utf-8')
		self.send_header('Content-Length', str(len(body)))
		self.send_header('Cache-Control', 'no-store')
		self.end_headers()
		self.wfile.write(body)

	def _send_file(self, rel):
		path = os.path.normpath(os.path.join(STATIC_DIR, rel))
		if not path.startswith(STATIC_DIR + os.sep) or not os.path.isfile(path):
			self._send_json({'error': 'not found'}, 404)
			return
		with open(path, 'rb') as f:
			body = f.read()
		ext = os.path.splitext(path)[1].lower()
		self.send_response(200)
		self.send_header('Content-Type', CONTENT_TYPES.get(ext, 'application/octet-stream'))
		self.send_header('Content-Length', str(len(body)))
		self.send_header('Cache-Control', 'no-store')
		self.end_headers()
		self.wfile.write(body)

	def _read_body(self):
		length = int(self.headers.get('Content-Length') or 0)
		if not length:
			return {}
		return json.loads(self.rfile.read(length).decode('utf-8'))

	def do_GET(self):
		path = urlparse(self.path).path
		if path in ('/', '/index.html'):
			self._send_file('index.html')
		elif path.startswith('/static/'):
			self._send_file(path[len('/static/') :])
		elif path == '/api/state':
			data = load_data()
			env = read_env_config()
			legacy = [k for k in CONFIG_KEYS if env.get(k)]
			self._send_json(
				{
					'accounts': data.get('ACCOUNTS', []),
					'linuxdo': data.get('ACCOUNTS_LINUX_DO', []),
					'github': data.get('ACCOUNTS_GITHUB', []),
					'providers': data.get('PROVIDERS', {}),
					'builtin': BUILTIN_PROVIDERS,
					'env_legacy_keys': legacy,
					'proxy': env.get('PROXY', ''),
					'data_file': DATA_FILE,
				}
			)
		elif path == '/api/settings':
			self._send_json({'check_in_once_per_day': env_flag_enabled()})
		else:
			self._send_json({'error': 'not found'}, 404)

	def do_POST(self):
		path = urlparse(self.path).path
		try:
			body = self._read_body()
			if path == '/api/save':
				data = {
					'ACCOUNTS': body.get('accounts') or [],
					'ACCOUNTS_LINUX_DO': body.get('linuxdo') or [],
					'ACCOUNTS_GITHUB': body.get('github') or [],
					'PROVIDERS': body.get('providers') or {},
				}
				save_data(data)
				if 'proxy' in body:
					new_proxy = (body.get('proxy') or '').strip()
					if new_proxy != (read_env_config().get('PROXY') or '').strip():
						set_env_value('PROXY', new_proxy)
				self._send_json({'ok': True})
			elif path == '/api/export':
				env = read_env_config()
				accounts, linuxdo, github, providers = build_payload(body, env)
				unified = {
					k: v
					for k, v in {
						'ACCOUNTS': accounts,
						'ACCOUNTS_LINUX_DO': linuxdo,
						'ACCOUNTS_GITHUB': github,
						'PROVIDERS': providers,
					}.items()
					if v
				}
				proxy = body.get('proxy') or env.get('PROXY') or ''
				if proxy:
					unified['PROXY'] = proxy
				if env.get('CHECK_IN_ONCE_PER_DAY'):
					unified['CHECK_IN_ONCE_PER_DAY'] = env['CHECK_IN_ONCE_PER_DAY']
				self._send_json(
					{
						'app_config': json.dumps(unified, ensure_ascii=False, separators=(',', ':')),
						'accounts': json.dumps(accounts, ensure_ascii=False, separators=(',', ':')) if accounts else '',
						'providers': json.dumps(providers, ensure_ascii=False, separators=(',', ':'))
						if providers
						else '',
						'linuxdo': json.dumps(linuxdo, ensure_ascii=False, separators=(',', ':')) if linuxdo else '',
						'github': json.dumps(github, ensure_ascii=False, separators=(',', ':')) if github else '',
					}
				)
			elif path == '/api/sync':
				from manage_config import CONFIG_KEYS as _CK

				env = read_env_config()
				accounts, linuxdo, github, providers = build_payload(body, env)
				effective = {
					'ACCOUNTS': accounts,
					'ACCOUNTS_LINUX_DO': linuxdo,
					'ACCOUNTS_GITHUB': github,
					'PROVIDERS': providers,
				}
				proxy = body.get('proxy') or env.get('PROXY') or ''
				unified = {k: v for k, v in effective.items() if v}
				if proxy:
					unified['PROXY'] = proxy
				if env.get('CHECK_IN_ONCE_PER_DAY'):
					unified['CHECK_IN_ONCE_PER_DAY'] = env['CHECK_IN_ONCE_PER_DAY']

				lines = []
				if os.path.exists(ENV_FILE):
					with open(ENV_FILE, 'r', encoding='utf-8') as f:
						lines = f.readlines()
				kept = [
					ln
					for ln in lines
					if not ln.strip()
					or ln.strip().startswith('#')
					or '=' not in ln
					or ln.strip().partition('=')[0].strip()
					not in _CK + ('APP_CONFIG', 'PROXY', 'CHECK_IN_ONCE_PER_DAY')
				]
				with open(ENV_FILE, 'w', encoding='utf-8') as f:
					f.writelines(kept)
					if unified:
						f.write(f'APP_CONFIG={json.dumps(unified, ensure_ascii=False, separators=(",", ":"))}\n')
				self._send_json({'ok': True})
			elif path == '/api/settings':
				enabled = bool(body.get('check_in_once_per_day'))
				set_check_in_once_per_day(enabled)
				self._send_json({'ok': True, 'check_in_once_per_day': enabled})
			else:
				self._send_json({'error': 'not found'}, 404)
		except Exception as e:
			self._send_json({'error': str(e)}, 500)


def serve(port: int = DEFAULT_PORT):
	try:
		server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
	except OSError:
		print(f'⚠️ 端口 {port} 被占用，尝试其它端口...')
		for p in range(port + 1, port + 20):
			try:
				server = ThreadingHTTPServer(('127.0.0.1', p), Handler)
				port = p
				break
			except OSError:
				continue
		else:
			print('❌ 找不到可用端口')
			return 1

	url = f'http://127.0.0.1:{port}/'
	print('=' * 50)
	print('  NewAPI 签到配置管理页')
	print(f'  地址: {url}')
	print('  关闭本窗口即可停止服务')
	print('  安全: 仅本机可访问，数据不会上传')
	print('=' * 50)
	try:
		webbrowser.open(url)
	except Exception:
		pass
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	return 0


if __name__ == '__main__':
	port = DEFAULT_PORT
	if len(sys.argv) > 1:
		try:
			port = int(sys.argv[1])
		except ValueError:
			print('用法: python web_config.py [端口]')
			sys.exit(1)
	sys.exit(serve(port))
