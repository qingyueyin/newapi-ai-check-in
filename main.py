#!/usr/bin/env python3
"""
自动签到脚本
"""

import asyncio
import hashlib
import json
import sys
from datetime import datetime
from dotenv import load_dotenv
from utils.config import AppConfig
from utils.notify import notify
from utils.balance_hash import load_balance_hash, save_balance_hash
from utils.daily_checkin_status import (
    DEFAULT_FILE as DAILY_CHECKIN_FILE,
    load_records as load_daily_records,
    save_records as save_daily_records,
    clean_records as clean_daily_records,
)
from checkin import CheckIn

load_dotenv(override=True)

BALANCE_HASH_FILE = "balance_hash.txt"


def generate_balance_hash(balances: dict) -> str:
    """生成余额数据的hash"""
    # 将包含 quota 和 used 的结构转换为 {account_name: [quota]} 格式用于 hash 计算
    simple_balances = {}
    if balances:
        for account_key, account_balances in balances.items():
            quota_list = []
            for _, balance_info in account_balances.items():
                quota_list.append(balance_info["quota"])
            simple_balances[account_key] = quota_list

    balance_json = json.dumps(simple_balances, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(balance_json.encode("utf-8")).hexdigest()[:16]


async def main():
    """运行签到流程

    Returns:
            退出码: 0 表示至少有一个账号成功, 1 表示全部失败
    """

    print("🚀 newapi.ai multi-account auto check-in script started (using Camoufox)")
    print(f'🕒 Execution time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    app_config = AppConfig.load_from_env()
    print(f"⚙️ Loaded {len(app_config.providers)} provider(s)")

    # 检查账号配置
    if not app_config.accounts:
        print("❌ Unable to load account configuration, program exits")
        return 1
    
    print(f"⚙️ Found {len(app_config.accounts)} account(s)")

    # 加载余额hash
    last_balance_hash = load_balance_hash(BALANCE_HASH_FILE)

    # 每天只签到一次开关：加载当日记录，已签过的账号跳过
    daily_records = {}
    if app_config.check_in_once_per_day:
        daily_records = load_daily_records()
        daily_records = clean_daily_records(daily_records)
        print(f"⚙️ CHECK_IN_ONCE_PER_DAY enabled: {len(daily_records)} account(s) already checked in today")

    # 为每个账号执行签到
    success_count = 0
    skipped_count = 0
    total_count = 0
    notification_content = []
    current_balances = {}

    for i, account_config in enumerate(app_config.accounts):
        account_key = f"account_{i + 1}"
        account_name = account_config.get_display_name(i)

        # 每天只签到一次：今天已签过则跳过
        if app_config.check_in_once_per_day and daily_records.get(account_name):
            skipped_count += 1
            print(f"⏭️ {account_name}: Already checked in today, skipping (CHECK_IN_ONCE_PER_DAY)")
            continue

        # 启用/禁用开关
        if not getattr(account_config, 'enabled', True):
            skipped_count += 1
            total_count += 1
            print(f"⏸️ {account_name}: Account disabled, skipping")
            if notification_content:
                notification_content.append("\n-------------------------------")
            notification_content.append(f"⏸️ {account_name}\n   Account disabled (skipped)")
            continue

        if len(notification_content) > 0:
            notification_content.append("\n-------------------------------")

        try:
            provider_config = app_config.get_provider(account_config.provider)
            if not provider_config:
                print(f"❌ {account_name}: Provider '{account_config.provider}' configuration not found")
                notification_content.append(
                    f"[FAIL] {account_name}: Provider '{account_config.provider}' configuration not found"
                )
                continue

            print(f"🌀 Processing {account_name} using provider '{account_config.provider}'")
            checkin = CheckIn(account_name, account_config, provider_config, global_proxy=app_config.global_proxy)
            results = await checkin.execute()

            total_count += len(results)

            # 处理多个认证方式的结果
            account_success = False
            successful_methods = []
            failed_methods = []

            this_account_balances = {}
            # 构建精简的结果报告
            account_lines = []
            for auth_method, success, user_info in results:
                if success and user_info and user_info.get("already_checked_in"):
                    # 今日已签到
                    account_success = True
                    success_count += 1
                    successful_methods.append(auth_method)
                    quota = user_info.get("quota", 0) if user_info.get("success") else 0
                    used = user_info.get("used_quota", 0) if user_info.get("success") else 0
                    quota_str = f" | 额度: {quota:,} / 已用: {used:,}" if quota or used else ""
                    account_lines.append(f"⏭️ {account_name} — 今日已签到{quota_str}")
                    if user_info.get("success"):
                        this_account_balances[auth_method] = {
                            "quota": user_info.get("quota", 0),
                            "used": user_info.get("used_quota", 0),
                            "bonus": user_info.get("bonus_quota", 0),
                        }
                elif success and user_info and user_info.get("success"):
                    # 签到成功
                    account_success = True
                    success_count += 1
                    successful_methods.append(auth_method)
                    current_quota = user_info["quota"]
                    current_used = user_info["used_quota"]
                    current_bonus = user_info["bonus_quota"]
                    this_account_balances[auth_method] = {
                        "quota": current_quota,
                        "used": current_used,
                        "bonus": current_bonus,
                    }
                    account_lines.append(f"✅ {account_name} — 签到成功 | 额度: {current_quota:,} / 已用: {current_used:,}")
                else:
                    # 失败
                    failed_methods.append(auth_method)
                    error_msg = user_info.get("error", "Unknown error") if user_info else "Unknown error"
                    account_lines.append(f"❌ {account_name} — {error_msg}")

            # 合并同一账号的多行输出
            if account_lines:
                notification_content.append("\n".join(account_lines))

            if account_success:
                current_balances[account_key] = this_account_balances
                # 每天只签到一次：仅「真正签到成功」才记录今天已签，失败/异常不记（下次会重试）
                if app_config.check_in_once_per_day:
                    from datetime import date as _today

                    daily_records[account_name] = _today().strftime("%Y-%m-%d")
                    print(f"📝 {account_name}: Recorded check-in for today (CHECK_IN_ONCE_PER_DAY)")

            # 如果所有认证方式都失败，需要通知
            if not account_success and results:
                print(f"🔔 {account_name} all authentication methods failed, will send notification")

            # 如果有失败的认证方式，也通知
            if failed_methods and successful_methods:
                print(f"🔔 {account_name} has some failed authentication methods, will send notification")

        except Exception as e:
            print(f"❌ {account_name} processing exception: {e}")
            notification_content.append(f"❌ {account_name} Exception: {str(e)[:100]}...")

    # 每天只签到一次：保存当日记录（供下次运行跳过）
    if app_config.check_in_once_per_day and daily_records:
        cleaned = clean_daily_records(daily_records)
        save_daily_records(cleaned)

    # 检查余额变化
    current_balance_hash = generate_balance_hash(current_balances) if current_balances else None
    print(f"\n\nℹ️ Current balance hash: {current_balance_hash}, Last balance hash: {last_balance_hash}")
    if current_balance_hash:
        if last_balance_hash is None:
            print("🔔 First run detected")
        elif current_balance_hash != last_balance_hash:
            print("🔔 Balance changes detected")
        else:
            print("ℹ️ No balance changes detected")

    # 保存当前余额hash
    if current_balance_hash:
        save_balance_hash(BALANCE_HASH_FILE, current_balance_hash)

    if notification_content:
        # 构建精简通知
        failed_count = total_count - success_count
        summary_lines = []
        if success_count > 0:
            summary_lines.append(f"✅ 成功: {success_count}")
        if failed_count > 0:
            summary_lines.append(f"❌ 失败: {failed_count}")
        if skipped_count > 0:
            summary_lines.append(f"⏭️ 跳过: {skipped_count}")
        summary = " | ".join(summary_lines)

        if success_count == total_count:
            verdict = "🎉 全部签到成功！"
        elif success_count > 0:
            verdict = "⚠️ 部分签到成功"
        else:
            verdict = "❌ 全部签到失败"

        time_info = f'🕓 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        header = f"{verdict}  {summary}"

        notify_content = "\n\n".join([time_info, header, "\n".join(notification_content)])

        print(notify_content)
        notify.push_message("Check-in Alert", notify_content, msg_type="text")
        print("🔔 Notification sent")
    else:
        # 全部账号被 CHECK_IN_ONCE_PER_DAY 跳过时也通知，确保每次运行都有反馈
        if skipped_count > 0:
            notify_content = (
                f'🕓 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
                f"⏭️ 全部 {skipped_count} 个账号已签过，跳过"
            )
            print(notify_content)
            notify.push_message("Check-in Alert", notify_content, msg_type="text")
            print("🔔 Notification sent (all skipped)")
        else:
            print("ℹ️ No notification content")

    # 设置退出码：全部为"今天已跳过"时也算成功（不触发失败通知）
    if success_count > 0 or (skipped_count > 0 and skipped_count == len(app_config.accounts)):
        sys.exit(0)
    else:
        sys.exit(1)


def run_main():
    """运行主函数的包装函数"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Program interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error occurred during program execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_main()
