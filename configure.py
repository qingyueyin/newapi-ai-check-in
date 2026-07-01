import json
import os
import sys
from urllib.parse import urlparse

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

def main():
    clear_screen()
    print("=" * 62)
    print("  NewAPI 自动签到 — 配置生成器")
    print("  适用于 aceHubert/newapi-ai-check-in")
    print("=" * 62)
    print()
    print("  ⚠️  不验证 session，只生成配置 JSON")
    print("      配置完手动触发一次 Actions 就能知道是否生效")
    print()

    accounts = []
    custom_providers = {}

    while True:
        idx = len(accounts) + 1
        print("-" * 40)
        print(f"  第 {idx} 个账号")
        print("-" * 40)

        name = input("  账号备注名: ").strip()
        while not name:
            name = input("  备注名不能为空: ").strip()

        url = input("  站点 URL: ").strip()
        while not url.startswith("http"):
            url = input("  格式不对，以 http:// 开头: ").strip()

        print()
        print("  认证方式:")
        print("    1) Session Cookie")
        print("    2) System Access Token (推荐，更稳定)")
        choice = input("  请选择 (1/2, 默认 2): ").strip()
        use_token = (choice != "1")

        if use_token:
            secret = input("  System Access Token 值: ").strip()
            while not secret:
                secret = input("  Token 不能为空: ").strip()
        else:
            secret = input("  Session Cookie 值: ").strip()
            while not secret:
                secret = input("  Session 不能为空: ").strip()

        print()
        print("  💡 用户 ID 在哪找？")
        print("     登录站点 → F12 → Application → Local Storage →")
        print("     找到键名 user → 点开查看 id 字段的值")
        uid = input("  用户 ID: ").strip()
        while not uid:
            uid = input("  用户 ID 不能为空: ").strip()

        provider_name = match_provider(url)
        if provider_name:
            print(f"  → 匹配内置 provider: {provider_name}")
        else:
            pk = make_provider_key(url)
            if pk not in custom_providers:
                custom_providers[pk] = {
                    "origin": url.rstrip("/"),
                    "check_in_path": "/api/user/checkin",
                    "user_info_path": "/api/user/self",
                    "api_user_key": "new-api-user",
                }
            provider_name = pk

        acct = {"name": name, "provider": provider_name, "api_user": uid}
        if use_token:
            acct["system_access_token"] = secret
        else:
            acct["cookies"] = {"session": secret}
        accounts.append(acct)

        print(f"  ✅ 已添加\n")
        more = input("  继续添加？(y/n, 默认 n): ").strip().lower()
        if more != 'y':
            break

    if not accounts:
        print("\n❌ 没有添加任何账号。")
        return

    clear_screen()
    print("=" * 62)
    print("  ✅ 配置已生成")
    print("=" * 62)
    print()
    print("─" * 62)
    print("  Secret 1:  ACCOUNTS")
    print("─" * 62)
    print()
    print(json.dumps(accounts, indent=2, ensure_ascii=False))
    print()

    if custom_providers:
        print("─" * 62)
        print("  Secret 2:  PROVIDERS")
        print("─" * 62)
        print()
        print(json.dumps(custom_providers, indent=2, ensure_ascii=False))
        print()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env_secrets_backup.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"ACCOUNTS": accounts, "PROVIDERS": custom_providers}, f, indent=2, ensure_ascii=False)
        print(f"  📄 已备份到: {out_path}")
    except:
        pass

    print()
    print("=" * 62)
    print("  配置到 GitHub:")
    print()
    print("  1. 进入 Fork 的仓库")
    print("  2. Settings → Environments → production")
    print("  3. 添加 ACCOUNTS  secret")
    if custom_providers:
        print("  4. 添加 PROVIDERS secret")
    print("  5. Actions → 启用 → Run workflow")
    print("=" * 62)
    print()

    input("按回车退出...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(0)
