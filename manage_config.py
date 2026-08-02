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
    python manage_config.py sync          # 同步配置到 .env（写成统一变量 APP_CONFIG）

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

DATA_FILE = "accounts.json"
ENV_FILE = ".env"
BACKUP_FILE = "env_secrets_backup.json"

CONFIG_KEYS = ("ACCOUNTS", "ACCOUNTS_LINUX_DO", "ACCOUNTS_GITHUB", "PROVIDERS")

BUILTIN_PROVIDERS = {
    "anyrouter": "https://anyrouter.top",
    "wong": "https://wzw.pp.ua",
    "huan666": "https://ai.huan666.de",
    "x666": "https://x666.me",
    "kfc": "https://kfc-api.sxxe.net",
    "elysiver": "https://elysiver.h-e.top",
    "hotaru": "https://hotaruapi.com",
    "muyuan": "https://muyuan.do",
    "takeapi": "https://codex.661118.xyz",
    "duckcoding": "https://duckcoding.ai",
}


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
            if key not in CONFIG_KEYS:
                continue
            try:
                config[key] = json.loads(value.strip())
            except json.JSONDecodeError:
                pass
    if isinstance(unified, dict):
        for key in CONFIG_KEYS:
            if key in unified:
                config[key] = unified[key]
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


def export_secrets(data):
    """导出合并后的全部 Secret 值（环境变量 + accounts.json）"""
    env = read_env_config()
    accounts = merge_accounts(env.get("ACCOUNTS") or [], data.get("ACCOUNTS") or [])
    linuxdo = merge_pool(env.get("ACCOUNTS_LINUX_DO") or [], data.get("ACCOUNTS_LINUX_DO") or [])
    github = merge_pool(env.get("ACCOUNTS_GITHUB") or [], data.get("ACCOUNTS_GITHUB") or [])
    providers = {**(env.get("PROVIDERS") or {}), **(data.get("PROVIDERS") or {})}
    proxy = env.get("PROXY")

    clear_screen()
    print("=" * 62)
    print("  ✅ Secret 导出（复制下面内容到 GitHub → Settings → Environments → production）")
    print("=" * 62)
    print()

    # 统一变量 APP_CONFIG：一个 Secret 搞定全部，优先推荐
    unified = {key: value for key, value in {
        "ACCOUNTS": accounts,
        "ACCOUNTS_LINUX_DO": linuxdo,
        "ACCOUNTS_GITHUB": github,
        "PROVIDERS": providers,
    }.items() if value}
    if proxy:
        unified["PROXY"] = proxy
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
    print()


def sync_env(data):
    """同步配置到 .env（推荐：写成统一变量 APP_CONFIG，其他设置保留）"""
    env = read_env_config()
    effective = {
        "ACCOUNTS": merge_accounts(env.get("ACCOUNTS") or [], data.get("ACCOUNTS") or []),
        "ACCOUNTS_LINUX_DO": merge_pool(env.get("ACCOUNTS_LINUX_DO") or [], data.get("ACCOUNTS_LINUX_DO") or []),
        "ACCOUNTS_GITHUB": merge_pool(env.get("ACCOUNTS_GITHUB") or [], data.get("ACCOUNTS_GITHUB") or []),
        "PROVIDERS": {**(env.get("PROVIDERS") or {}), **(data.get("PROVIDERS") or {})},
    }
    proxy = env.get("PROXY")
    if proxy:
        effective["PROXY"] = proxy

    unified = {key: effective[key] for key in CONFIG_KEYS if effective.get(key)}
    if proxy:
        unified["PROXY"] = proxy

    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    kept = [
        ln for ln in lines
        if not ln.strip() or ln.strip().startswith("#") or "=" not in ln
        or ln.strip().partition("=")[0].strip() not in CONFIG_KEYS + ("APP_CONFIG", "PROXY")
    ]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(kept)
        if unified:
            f.write(f"APP_CONFIG={json.dumps(unified, ensure_ascii=False, separators=(',', ':'))}\n")
    print(f"✅ 已同步到 {ENV_FILE}（统一变量 APP_CONFIG，其他设置保持不变）")


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
    elif cmd == "export":
        export_secrets(data)
    elif cmd == "sync":
        sync_env(data)
    else:
        print(f"❌ 未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(0)
