#!/usr/bin/env python3
"""
每天签到记录管理 — 配合 CHECK_IN_ONCE_PER_DAY 开关使用

开启后，每个账号当天签到成功会写入记录文件（默认 daily_checkin_records.json），
再次运行时若发现今天已签过，则跳过该账号，避免对站点反复请求。

GitHub Actions 场景：本文件会被 workflow 缓存，跨 run 带到下一次运行，
跨天自动失效（记录的日期不是今天即视为未签到）。
"""

import json
import os
from datetime import datetime

DEFAULT_FILE = "daily_checkin_records.json"


def _today_str() -> str:
    """返回今天日期字符串 YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def load_records(file_path: str = DEFAULT_FILE) -> dict:
    """加载每日签到记录

    Returns:
        {account_name: "YYYY-MM-DD"} 记录字典
    """
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Failed to read daily check-in records {file_path}: {e}")
        return {}


def save_records(records: dict, file_path: str = DEFAULT_FILE) -> None:
    """保存每日签到记录"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ Failed to save daily check-in records {file_path}: {e}")


def clean_records(records: dict, today: str = "") -> dict:
    """清理过期记录（只保留今天），避免文件无限增长"""
    today = today or _today_str()
    return {name: date for name, date in records.items() if date == today}