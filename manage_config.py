#!/usr/bin/env python3
"""
账号配置管理器 — 增删改单个账号，无需重写整个 JSON

与 configure.py（一次性向导）不同，本工具加载已有配置，按需修改单个账号，
保存到本地 accounts.json（main.py 会自动读取并合并，改一处只动一处）。

GitHub Actions 场景：
- 运行 `python manage_config.py export` 会输出统一变量 APP_CONFIG（推荐）
  —— 一个 Secret 包含全部配置（账号 + 账号池 + PROVIDERS + PROXY），
  在 GitHub → Settings → Environments → production 只维护这一个 Secret 即可。
- workflow 已支持 `APP_CONFIG: ${{ inputs.config || secrets.APP_CONFIG }}`。

用法:
    python manage_config.py               # 交互式菜单
    python manage_config.py list          # 列出账号
    python manage_config.py add           # 添加账号
    python manage_config.py edit <名称>   # 编辑账号
    python manage_config.py token <名称>  # 精准更新认证密钥（token 过期时只重填这一个）
    python manage_config.py remove <名称> # 删除账号
    python manage_config.py pool          # 管理 OAuth 账号池 (Linux.do / GitHub)
    python manage_config.py export        # 导出 Secret 值（推荐 APP_CONFIG，粘贴到 GitHub）
    python manage_config.py sync           # 同步配置到 .env（写成统一变量 APP_CONFIG）
    python manage_config.py flag           # 开/关「每天只签到一次」（当天签到成功后跳过）
    python manage_config.py web            # 打开本地 Web 管理页（可视化查看/修改）

accounts.json 格式（键名与 GitHub Secret 一致，全部可选）:
{
    "ACCOUNTS": [
        {
            "name": "备注名",
            "provider": "x666",
            "api_user": "用户ID",
            "system_access_token": "Token 或省略",
            "cookies": {"session": "Session 或省略"},
            "linux.do": true,
            "github": true
        }
    ],
    "ACCOUNTS_LINUX_DO": [{"username": "...", "password": "..."}],
    "ACCOUNTS_GITHUB": [{"username": "...", "password": "..."}],
    "PROVIDERS": {
        "custom_site": {
            "origin": "https://example.com",
            "check_in_path": "/api/user/checkin",
            "user_info_path": "/api/user/self",
            "api_user_key": "new-api-user"
        }
    }
}
"""

import json
import os
import sys
from urllib.parse import urlparse

from utils.config import BUILTIN_PROVIDER_ORIGINS as BUILTIN_PROVIDERS

DATA_FILE = "accounts.json"
ENV_FILE = ".env"
BACKUP_FILE = "env_secrets_backup.json"

CONFIG_KEYS = ("ACCOUNTS", "ACCOUNTS_LINUX_DO", "ACCOUNTS_GITHUB", "PROVIDERS")
EXTRA_KEYS = ("CHECK_IN_ONCE_PER_DAY",)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def match_provider(url):
    url = url.rstrip("/")
    for name, origin in BUILTIN_PROVIDERS.items():
        if origin.rstrip("/") == url:
            return name
    return None


def make_provider_key(url):
    return urlparse(url).hostname.replace(".", "_")


def empty_data():
    return {
        "ACCOUNTS": [],
        "ACCOUNTS_LINUX_DO": [],
        "ACCOUNTS_GITHUB": [],
        "PROVIDERS": {},
    }


def read_env_config():
    """读取 .env 中的配置（JSON 值解析，支持统一变量 APP_CONFIG）

    APP_CONFIG 是一个包含全部配置键的 JSON 对象:
    {"ACCOUNTS": [...], "ACCOUNTS_LINUX_DO": [...], "ACCOUNTS_GITHUB": [...], "PROVIDERS": {...}}
    设置后优先于各独立键。
    """
    config = {}
    unified = None
    if not os.path.exists(ENV_FILE):
        return config
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key == "APP_CONFIG":
                try:
                    unified = json.loads(value.strip())
                except json.JSONDecodeError:
                    pass
                continue
            if key == "PROXY":
                config["PROXY"] = value.strip()
                continue
            if key not in CONFIG_KEYS + EXTRA_KEYS:
                continue
            try:
                config[key] = json.loads(value.strip())
            except json.JSONDecodeError:
                config[key] = value.strip()
    if isinstance(unified, dict):
        for key in CONFIG_KEYS + EXTRA_KEYS:
            if key in unified:
                config[key] = unified[key]
        if "PROXY" in unified:
            config["PROXY"] = unified["PROXY"]
    return config


def import_from_env():
    """从 .env 导入已有配置（首次运行时调用）"""
    env = read_env_config()
    if not env:
        return None
    data = empty_data()
    for key in CONFIG_KEYS:
        if key in env:
            data[key] = env[key]
    return data


def load_data():
    data = empty_data()
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key in data:
                    data[key] = loaded.get(key, data[key])
            else:
                print(f"⚠️ {DATA_FILE} 内容不是 JSON 对象，将创建新配置")
        except Exception as e:
            print(f"⚠️ 读取 {DATA_FILE} 失败: {e}")
    else:
        imported = import_from_env()
        if imported:
            data = imported
            save_data(data)
            print(f"✅ 已从 {ENV_FILE} 导入现有配置到 {DATA_FILE}")
        else:
            print(f"ℹ️ 未找到 {DATA_FILE}，将创建新的配置文件")
    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 已保存到 {DATA_FILE}")


def find_account(data, name):
    for acct in data.get("ACCOUNTS") or []:
        if acct.get("name") == name:
            return acct
    return None


def describe_auth(acct):
    auths = []
    if acct.get("system_access_token"):
        auths.append("Token")
    if acct.get("cookies"):
        auths.append("Cookie")
    if acct.get("linux.do"):
        auths.append("Linux.do")
    if acct.get("github"):
        auths.append("GitHub")
    if acct.get("site"):
        auths.append("Site")
    return "+".join(auths) if auths else "无认证"


def list_accounts(data):
    accounts = data.get("ACCOUNTS") or []
    if not accounts:
        print("📭 还没有任何账号，运行 add 或直接编辑 accounts.json")
        return
    print(f"{'#':<3}{'备注名':<16}{'provider':<16}{'用户ID':<10}认证方式")
    print("-" * 66)
    for i, acct in enumerate(accounts):
        name = acct.get("name") or f"<未命名 {i + 1}>"
        print(f"{i + 1:<3}{name:<16}{str(acct.get('provider', '')):<16}{str(acct.get('api_user', '')):<10}{describe_auth(acct)}")
    print("-" * 66)
    print(f"共 {len(accounts)} 个账号")
    pools = data.get("ACCOUNTS_LINUX_DO") or []
    print(f"OAuth 账号池: Linux.do {len(pools)} 个, GitHub {len(data.get('ACCOUNTS_GITHUB') or [])} 个")
    if data.get("PROVIDERS"):
        print(f"自定义站点: {', '.join(data['PROVIDERS'].keys())}")


def ensure_custom_provider(data, url):
    """返回 provider 名称；自定义站点自动登记到 PROVIDERS"""
    pk = make_provider_key(url)
    if pk not in data["PROVIDERS"]:
        data["PROVIDERS"][pk] = {
            "origin": url.rstrip("/"),
            "check_in_path": "/api/user/checkin",
            "user_info_path": "/api/user/self",
            "api_user_key": "new-api-user",
        }
        print(f"  → 已登记自定义 provider: {pk}")
    return pk


def select_pool_account(data, key, label):
    """选择 OAuth 账号池账号，或新增一个到池中"""
    pool = data.get(key) or []
    print(f"  当前 {label} 账号池:")
    if pool:
        for i, acct in enumerate(pool):
            print(f"    {i + 1}) {acct.get('username')}")
    else:
        print("    (空)")
    choice = input(f"  选择已有账号编号，或输入 n 新增 (默认新增): ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(pool):
            print(f"  → 使用 {label} 账号: {pool[idx].get('username')}")
            return
    username = input(f"  {label} 用户名: ").strip()
    while not username:
        username = input(f"  {label} 用户名不能为空: ").strip()
    password = input(f"  {label} 密码: ").strip()
    while not password:
        password = input(f"  {label} 密码不能为空: ").strip()
    # 去重：同名覆盖
    data[key] = [a for a in pool if a.get("username") != username]
    data[key].append({"username": username, "password": password})
    print(f"  → 已添加 {label} 账号: {username}")


def add_account(data):
    print("-" * 40)
    print("  添加账号（只改当前配置，不影响其他账号）")
    print("-" * 40)

    name = input("  备注名: ").strip()
    while not name:
        name = input("  备注名不能为空: ").strip()
    existing = find_account(data, name)
    if existing:
        if input(f"  ⚠️ 已存在同名账号「{name}」，继续会覆盖，确认？(y/n): ").strip().lower() != "y":
            print("  已取消")
            return
        data["ACCOUNTS"] = [a for a in (data.get("ACCOUNTS") or []) if a.get("name") != name]

    url = input("  站点 URL: ").strip()
    while not url.startswith("http"):
        url = input("  格式不对，以 http:// 开头: ").strip()

    provider = match_provider(url)
    if provider:
        print(f"  → 匹配内置 provider: {provider}")
    else:
        provider = ensure_custom_provider(data, url)

    uid = input("  用户 ID (登录站点 → F12 → Local Storage → user → id): ").strip()
    while not uid:
        uid = input("  用户 ID 不能为空: ").strip()

    print("  认证方式:")
    print("    1) System Access Token (推荐)")
    print("    2) Session Cookie")
    print("    3) 仅用 OAuth (Linux.do / GitHub)")
    choice = input("  请选择 (1/2/3, 默认 1): ").strip()
    acct = {"name": name, "provider": provider, "api_user": uid}

    if choice == "3":
        pass
    elif choice == "2":
        secret = input("  Session Cookie 值: ").strip()
        while not secret:
            secret = input("  Session 不能为空: ").strip()
        acct["cookies"] = {"session": secret}
    else:
        secret = input("  System Access Token 值: ").strip()
        while not secret:
            secret = input("  Token 不能为空: ").strip()
        acct["system_access_token"] = secret

    if input("  同时启用 Linux.do OAuth？(y/n, 默认 n): ").strip().lower() == "y":
        select_pool_account(data, "ACCOUNTS_LINUX_DO", "Linux.do")
        acct["linux.do"] = True
    if input("  同时启用 GitHub OAuth？(y/n, 默认 n): ").strip().lower() == "y":
        select_pool_account(data, "ACCOUNTS_GITHUB", "GitHub")
        acct["github"] = True

    data["ACCOUNTS"].append(acct)
    save_data(data)
    print(f"  ✅ 已添加「{name}」")


def edit_account(data, name):
    acct = find_account(data, name)
    if not acct:
        print(f"❌ 未找到账号「{name}」，运行 list 查看现有账号")
        return

    while True:
        print()
        print(f"  编辑账号: {acct.get('name')} | {acct.get('provider')} | uid={acct.get('api_user')} | {describe_auth(acct)}")
        print("    1) 改备注名")
        print("    2) 改站点 provider")
        print("    3) 改用户 ID")
        print("    4) 重填认证密钥 (Token / Cookie)")
        print("    5) 切换 Linux.do OAuth")
        print("    6) 切换 GitHub OAuth")
        print("    7) 完成")
        choice = input("  请选择: ").strip()

        if choice == "1":
            new_name = input(f"  新备注名 (当前 {acct.get('name')}, 留空不修改): ").strip()
            if new_name:
                acct["name"] = new_name
        elif choice == "2":
            url = input("  站点 URL (留空不修改): ").strip()
            if url.startswith("http"):
                provider = match_provider(url)
                if provider:
                    acct["provider"] = provider
                    print(f"  → 匹配内置 provider: {provider}")
                else:
                    acct["provider"] = ensure_custom_provider(data, url)
            elif url:
                print("  ⚠️ 格式不对，忽略")
        elif choice == "3":
            uid = input(f"  新用户 ID (当前 {acct.get('api_user')}, 留空不修改): ").strip()
            if uid:
                acct["api_user"] = uid
        elif choice == "4":
            print("    1) System Access Token   2) Session Cookie   3) 清除认证密钥")
            sub = input("  请选择: ").strip()
            if sub == "1":
                secret = input("  System Access Token 值: ").strip()
                if secret:
                    acct["system_access_token"] = secret
                    acct.pop("cookies", None)
            elif sub == "2":
                secret = input("  Session Cookie 值: ").strip()
                if secret:
                    acct["cookies"] = {"session": secret}
                    acct.pop("system_access_token", None)
            elif sub == "3":
                acct.pop("system_access_token", None)
                acct.pop("cookies", None)
                print("  已清除 Token / Cookie")
        elif choice == "5":
            if acct.get("linux.do"):
                del acct["linux.do"]
                print("  已关闭 Linux.do OAuth")
            else:
                select_pool_account(data, "ACCOUNTS_LINUX_DO", "Linux.do")
                acct["linux.do"] = True
        elif choice == "6":
            if acct.get("github"):
                del acct["github"]
                print("  已关闭 GitHub OAuth")
            else:
                select_pool_account(data, "ACCOUNTS_GITHUB", "GitHub")
                acct["github"] = True
        elif choice == "7":
            save_data(data)
            print("  ✅ 已保存")
            return
        else:
            print("  ⚠️ 无效选择")


def remove_account(data, name):
    acct = find_account(data, name)
    if not acct:
        print(f"❌ 未找到账号「{name}」")
        return
    if input(f"  确认删除「{name}」？(y/n): ").strip().lower() != "y":
        print("  已取消")
        return
    data["ACCOUNTS"] = [a for a in (data.get("ACCOUNTS") or []) if a.get("name") != name]
    save_data(data)
    print(f"  ✅ 已删除「{name}」")


def update_token(data, name):
    """精准更新单个账号的认证密钥（token 过期/失效时只重填这一个）"""
    acct = find_account(data, name)
    if not acct:
        print(f"❌ 未找到账号「{name}」")
        return
    print(f"  账号: {acct.get('name')} | {acct.get('provider')} | uid={acct.get('api_user')} | 当前: {describe_auth(acct)}")

    has_token = bool(acct.get("system_access_token"))
    has_cookie = bool(acct.get("cookies"))
    if has_token and has_cookie:
        print("  1) System Access Token   2) Session Cookie")
        kind = input("  该账号有多个认证，更新哪个 (1/2): ").strip()
    elif has_cookie:
        kind = "2"
    else:
        kind = "1"

    if kind == "2":
        secret = input("  新的 Session Cookie 值: ").strip()
        while not secret:
            secret = input("  Session 不能为空: ").strip()
        acct["cookies"] = {"session": secret}
    else:
        secret = input("  新的 System Access Token 值: ").strip()
        while not secret:
            secret = input("  Token 不能为空: ").strip()
        acct["system_access_token"] = secret

    save_data(data)
    print(f"  ✅ 「{acct.get('name')}」认证密钥已更新（其他账号不受影响）")
    print()
    print("  💡 下一步同步 GitHub: python manage_config.py export")
    print("     复制输出的 APP_CONFIG 值，替换 GitHub 里的同名 Secret 即可")


def manage_pool(data, key, label):
    pool = data.get(key) or []
    print(f"\n  {label} 账号池 ({len(pool)} 个):")
    for i, acct in enumerate(pool):
        print(f"    {i + 1}) {acct.get('username')}")
    print("    1) 添加  2) 删除  0) 返回")
    choice = input("  请选择: ").strip()
    if choice == "1":
        select_pool_account(data, key, label)
        save_data(data)
    elif choice == "2":
        if not pool:
            print("  池为空")
            return
        idx_str = input("  输入要删除的账号编号: ").strip()
        if idx_str.isdigit():
            idx = int(idx_str) - 1
            if 0 <= idx < len(pool):
                removed = pool.pop(idx)
                save_data(data)
                print(f"  ✅ 已删除 {removed.get('username')}")
    elif choice == "0":
        return
    else:
        print("  ⚠️ 无效选择")


def manage_providers(data):
    providers = data.get("PROVIDERS") or {}
    print(f"\n  自定义站点 ({len(providers)} 个):")
    for name, cfg in providers.items():
        print(f"    {name} → {cfg.get('origin')}")
    print("    1) 添加  2) 删除  0) 返回")
    choice = input("  请选择: ").strip()
    if choice == "1":
        url = input("  站点 URL: ").strip()
        while not url.startswith("http"):
            url = input("  格式不对，以 http:// 开头: ").strip()
        ensure_custom_provider(data, url)
        save_data(data)
    elif choice == "2":
        if not providers:
            print("  无自定义站点")
            return
        name = input("  输入要删除的站点名: ").strip()
        if name in providers:
            del providers[name]
            save_data(data)
            print(f"  ✅ 已删除 {name}")
    elif choice == "0":
        return
    else:
        print("  ⚠️ 无效选择")


def merge_accounts(env_accounts, file_accounts):
    """环境变量 + 文件合并，同名(有 name)以文件为准"""
    if not isinstance(file_accounts, list):
        return env_accounts
    file_names = {a.get("name") for a in file_accounts if a.get("name")}
    merged = [a for a in env_accounts if not (a.get("name") and a.get("name") in file_names)]
    merged.extend(file_accounts)
    return merged


def merge_pool(env_pool, file_pool):
    """账号池合并，同名(username)以文件为准"""
    if not isinstance(file_pool, list):
        return env_pool
    file_names = {a.get("username") for a in file_pool if a.get("username")}
    merged = [a for a in env_pool if a.get("username") not in file_names]
    merged.extend(file_pool)
    return merged


def copy_to_clipboard(text):
    """复制文本到系统剪贴板（Windows PowerShell，失败静默忽略）"""
    try:
        import base64
        import subprocess
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        cmd = ("$b=[Convert]::FromBase64String('" + payload + "');"
               "$s=[Text.Encoding]::UTF8.GetString($b);Set-Clipboard -Value $s")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            creationflags=flags, timeout=10, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _env_orphan_counts(env, data):
    """返回 .env 中有但本地文件没有（会从导出中消失）的条目数量"""
    report = []
    for key, name_field in (
        ("ACCOUNTS", "name"),
        ("ACCOUNTS_LINUX_DO", "username"),
        ("ACCOUNTS_GITHUB", "username"),
    ):
        names = {a.get(name_field) for a in (data.get(key) or [])
                 if isinstance(a, dict) and a.get(name_field)}
        missing = [a for a in (env.get(key) or [])
                   if isinstance(a, dict) and a.get(name_field) and a.get(name_field) not in names]
        if missing:
            report.append(f"{key} {len(missing)} 个")
    return report


def env_flag_enabled():
    """读取「每天只签到一次」开关当前值（来自 .env / APP_CONFIG）"""
    value = read_env_config().get("CHECK_IN_ONCE_PER_DAY")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def set_check_in_once_per_day(enabled):
    """开/关「每天只签到一次」。写入 .env：有 APP_CONFIG 则并入 JSON，否则写独立行"""
    key = "CHECK_IN_ONCE_PER_DAY"
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    app_idx = next((i for i, ln in enumerate(lines)
                    if ln.strip().startswith("APP_CONFIG=")), None)
    if app_idx is not None:
        out = []
        for i, ln in enumerate(lines):
            if i == app_idx:
                raw = ln.strip()[len("APP_CONFIG="):]
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    obj = {}
                if not isinstance(obj, dict):
                    obj = {}
                if enabled:
                    obj[key] = True
                else:
                    obj.pop(key, None)
                out.append("APP_CONFIG=" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
            else:
                out.append(ln)
        lines = out
    else:
        lines = [ln for ln in lines if not ln.strip().startswith(key + "=")]
        if enabled:
            lines.append(f"{key}=true\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return enabled


def export_secrets(data):
    """导出全部 Secret 值（以本地 accounts.json 为准，删除才会真正生效）"""
    env = read_env_config()
    accounts = data.get("ACCOUNTS") or []
    linuxdo = data.get("ACCOUNTS_LINUX_DO") or []
    github = data.get("ACCOUNTS_GITHUB") or []
    providers = data.get("PROVIDERS") or {}
    proxy = env.get("PROXY")

    clear_screen()
    print("=" * 62)
    print("  ✅ 导出（复制到 GitHub → Settings → Environments → production）")
    print("=" * 62)
    print()

    orphans = _env_orphan_counts(env, data)
    if orphans:
        print("  ⚠️ 以下数据只存在于 .env，不在本地文件，导出不会包含:")
        for o in orphans:
            print(f"     · {o}")
        print("     如需保留请在 manage_config / Web 页中添加。")
        print()

    # 统一变量 APP_CONFIG：一个 Secret 搞定全部，优先推荐
    once_per_day = env.get("CHECK_IN_ONCE_PER_DAY")
    unified = {key: value for key, value in {
        "ACCOUNTS": accounts,
        "ACCOUNTS_LINUX_DO": linuxdo,
        "ACCOUNTS_GITHUB": github,
        "PROVIDERS": providers,
    }.items() if value}
    if proxy:
        unified["PROXY"] = proxy
    if once_per_day:
        unified["CHECK_IN_ONCE_PER_DAY"] = once_per_day
    print("─" * 62)
    print("  推荐 Secret:  APP_CONFIG（一个变量包含全部配置，GitHub 只需维护这一个）")
    print("─" * 62)
    print()
    print(json.dumps(unified, ensure_ascii=False, separators=(",", ":")))
    print()

    if accounts:
        print("─" * 62)
        print("  旧版 Secret 1:  ACCOUNTS（兼容旧配置，无需再更新）")
        print("─" * 62)
        print()
        print(json.dumps(accounts, ensure_ascii=False, separators=(",", ":")))
        print()
    if providers:
        print("─" * 62)
        print("  旧版 Secret 2:  PROVIDERS（兼容旧配置，无需再更新）")
        print("─" * 62)
        print()
        print(json.dumps(providers, ensure_ascii=False, separators=(",", ":")))
        print()
    if linuxdo:
        print("─" * 62)
        print("  旧版 Secret 3:  ACCOUNTS_LINUX_DO（兼容旧配置，无需再更新）")
        print("─" * 62)
        print()
        print(json.dumps(linuxdo, ensure_ascii=False, separators=(",", ":")))
        print()
    if github:
        print("─" * 62)
        print("  旧版 Secret 4:  ACCOUNTS_GITHUB（兼容旧配置，无需再更新）")
        print("─" * 62)
        print()
        print(json.dumps(github, ensure_ascii=False, separators=(",", ":")))
        print()

    backup = {
        "ACCOUNTS": accounts,
        "ACCOUNTS_LINUX_DO": linuxdo,
        "ACCOUNTS_GITHUB": github,
        "PROVIDERS": providers,
    }
    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2, ensure_ascii=False)
        print(f"📄 已备份到: {BACKUP_FILE}")
    except Exception:
        pass

    if unified and copy_to_clipboard(json.dumps(unified, ensure_ascii=False, separators=(",", ":"))):
        print("📋 已自动复制到剪贴板，直接去 GitHub 粘贴即可")
    print()


def sync_env(data):
    """同步配置到 .env（以本地 accounts.json 为准，删除才会真正生效）"""
    env = read_env_config()
    effective = {
        "ACCOUNTS": data.get("ACCOUNTS") or [],
        "ACCOUNTS_LINUX_DO": data.get("ACCOUNTS_LINUX_DO") or [],
        "ACCOUNTS_GITHUB": data.get("ACCOUNTS_GITHUB") or [],
        "PROVIDERS": data.get("PROVIDERS") or {},
    }
    proxy = env.get("PROXY")
    if proxy:
        effective["PROXY"] = proxy

    unified = {key: effective[key] for key in CONFIG_KEYS if effective.get(key)}
    if proxy:
        unified["PROXY"] = proxy
    if env.get("CHECK_IN_ONCE_PER_DAY"):
        unified["CHECK_IN_ONCE_PER_DAY"] = env["CHECK_IN_ONCE_PER_DAY"]

    if not effective["ACCOUNTS"] and (env.get("ACCOUNTS")):
        print(f"  ⚠️ 本地文件没有账号，但 .env 里还有 {len(env['ACCOUNTS'])} 个。同步后它们会从 APP_CONFIG 中移除（删除生效）。")
    if not effective["ACCOUNTS_LINUX_DO"] and (env.get("ACCOUNTS_LINUX_DO")):
        print(f"  ⚠️ 本地没有 Linux.do 账号池，而 .env 里还有 {len(env['ACCOUNTS_LINUX_DO'])} 个。已移除。")

    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    kept = [
        ln for ln in lines
        if not ln.strip() or ln.strip().startswith("#") or "=" not in ln
        or ln.strip().partition("=")[0].strip() not in CONFIG_KEYS + EXTRA_KEYS + ("APP_CONFIG", "PROXY")
    ]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(kept)
        if unified:
            f.write(f"APP_CONFIG={json.dumps(unified, ensure_ascii=False, separators=(',', ':'))}\n")
    print(f"✅ 已同步到 {ENV_FILE}（统一变量 APP_CONFIG，其他设置保持不变）")


def open_web(port: int = 8790):
    """启动本地 Web 管理页（web_config.py）"""
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_config.py")
    print(f"🌐 正在启动 Web 管理页 (http://127.0.0.1:{port}/)...")
    subprocess.Popen([sys.executable, script, str(port)])


def menu():
    data = load_data()
    while True:
        clear_screen()
        print("=" * 50)
        print("  NewAPI 自动签到 — 配置管理器")
        print("  修改账号无需重写整个 JSON")
        print("=" * 50)
        print()
        print("  1) 列出账号")
        print("  2) 添加账号")
        print("  3) 编辑账号")
        print("  4) 删除账号")
        print("  5) OAuth 账号池 (Linux.do / GitHub)")
        print("  6) 自定义站点 (PROVIDERS)")
        print("  7) 导出 Secret 值 (GitHub)")
        print("  8) 同步到 .env")
        print("  9) 打开 Web 管理页（可视化查看/修改）")
        print("  10) 每天只签到一次 开关")
        print("  0) 退出")
        print()
        choice = input("  请选择: ").strip()

        if choice == "1":
            clear_screen()
            list_accounts(data)
            input("\n按回车返回...")
        elif choice == "2":
            clear_screen()
            add_account(data)
            input("\n按回车返回...")
        elif choice == "3":
            clear_screen()
            list_accounts(data)
            print()
            name = input("  输入要编辑的账号备注名: ").strip()
            edit_account(data, name)
            input("\n按回车返回...")
        elif choice == "4":
            clear_screen()
            list_accounts(data)
            print()
            name = input("  输入要删除的账号备注名: ").strip()
            remove_account(data, name)
            input("\n按回车返回...")
        elif choice == "5":
            clear_screen()
            print("  1) Linux.do 账号池   2) GitHub 账号池   0) 返回")
            sub = input("  请选择: ").strip()
            if sub == "1":
                manage_pool(data, "ACCOUNTS_LINUX_DO", "Linux.do")
            elif sub == "2":
                manage_pool(data, "ACCOUNTS_GITHUB", "GitHub")
            input("\n按回车返回...")
        elif choice == "6":
            clear_screen()
            manage_providers(data)
            input("\n按回车返回...")
        elif choice == "7":
            export_secrets(data)
            input("按回车返回...")
        elif choice == "8":
            sync_env(data)
            input("\n按回车返回...")
        elif choice == "9":
            open_web()
            input("\n按回车返回...")
        elif choice == "10":
            clear_screen()
            print("  每天只签到一次: 开启后当天签到成功一次，其余账号自动跳过（跨天自动重置）")
            print(f"  当前状态: {'✅ 已开启' if env_flag_enabled() else '⛔ 已关闭'}")
            ans = input("  开启输入 y，关闭输入 n，返回输入 q: ").strip().lower()
            if ans == "y":
                set_check_in_once_per_day(True)
                print("  ✅ 已开启（记得 sync/export 同步到 GitHub Secret）")
            elif ans == "n":
                set_check_in_once_per_day(False)
                print("  ✅ 已关闭")
            input("\n按回车返回...")
        elif choice == "0":
            break
        else:
            print("  ⚠️ 无效选择")
            input("按回车继续...")


def main():
    args = sys.argv[1:]
    if not args:
        menu()
        return

    data = load_data()
    cmd = args[0].lower()

    if cmd == "list":
        list_accounts(data)
    elif cmd == "add":
        add_account(data)
    elif cmd == "edit":
        if len(args) < 2:
            list_accounts(data)
            name = input("输入要编辑的账号备注名: ").strip()
        else:
            name = args[1]
        edit_account(data, name)
    elif cmd == "token":
        if len(args) < 2:
            list_accounts(data)
            name = input("输入要更新密钥的账号备注名: ").strip()
        else:
            name = args[1]
        update_token(data, name)
    elif cmd == "remove":
        if len(args) < 2:
            list_accounts(data)
            name = input("输入要删除的账号备注名: ").strip()
        else:
            name = args[1]
        remove_account(data, name)
    elif cmd == "pool":
        if len(args) >= 2 and args[1].lower() in ("github", "gh"):
            manage_pool(data, "ACCOUNTS_GITHUB", "GitHub")
        else:
            manage_pool(data, "ACCOUNTS_LINUX_DO", "Linux.do")
    elif cmd == "sync":
        sync_env(data)
    elif cmd == "flag":
        print(f"每天只签到一次 当前状态: {'✅ 已开启' if env_flag_enabled() else '⛔ 已关闭'}")
        if len(args) >= 2:
            ans = args[1].lower()
        else:
            ans = input("开启 y / 关闭 n (q 退出): ").strip().lower()
        if ans in ("y", "yes", "on", "1"):
            set_check_in_once_per_day(True)
            print("✅ 已开启（记得 export/sync 同步到 GitHub Secret）")
        elif ans in ("n", "no", "off", "0"):
            set_check_in_once_per_day(False)
            print("✅ 已关闭")
        elif ans != "q":
            print("用法: python manage_config.py flag [on|off]")
    elif cmd in ("web", "serve"):
        open_web(int(args[1]) if len(args) > 1 and args[1].isdigit() else 8790)
    else:
        print(f"❌ 未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(0)
