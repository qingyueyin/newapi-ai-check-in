#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

chrome_path = r"D:\App\chrome-win\chrome.exe"
storage_dir = Path("storage-states")
storage_dir.mkdir(exist_ok=True)

username = input("输入你的 Linux.do 用户名: ").strip()
port = 9222

# 启动 Chrome 远程调试模式
proc = subprocess.Popen([
    chrome_path,
    f"--remote-debugging-port={port}",
    "--user-data-dir=C:\\Users\\Administrator\\AppData\\Local\\Temp\\chrome_linuxdo",
    "--no-first-run",
    "--no-default-browser-check",
], shell=False)

print("Chrome 已启动，请在浏览器中登录 https://connect.linux.do")
print("登录完成后，按回车继续...")
input()

# 用 Playwright 连接 Chrome 并导出 storage state
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
    context = browser.contexts[0]
    storage = context.storage_state()

    filepath = storage_dir / f"linuxdo_{username[:8]}_storage_state.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(storage, f, ensure_ascii=False, indent=2)

    print(f"✅ Storage state 已保存到: {filepath}")
    print(f"\n打开文件复制全部内容，去 GitHub 添加 secret:")
    print(f"  Name: STORATE_STATES_LINUXDO")
    print(f'  Value: {{"{username}": "上一步复制的内容"}}')

proc.terminate()
