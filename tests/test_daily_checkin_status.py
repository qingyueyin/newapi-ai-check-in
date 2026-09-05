"""CHECK_IN_ONCE_PER_DAY：当天已签要跳过，跨天要自动重置。"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.daily_checkin_status import (
    clean_records,
    is_checked_in_today,
    load_records,
    mark_checked_in,
    save_records,
)


def test_is_checked_in_today_skips_when_recorded_for_today():
    records = {"薄荷": "2026-09-05"}
    assert is_checked_in_today(records, "薄荷", today="2026-09-05") is True


def test_is_checked_in_today_does_not_skip_other_accounts():
    records = {"薄荷": "2026-09-05"}
    assert is_checked_in_today(records, "x666 1", today="2026-09-05") is False


def test_is_checked_in_today_resets_across_days():
    records = {"薄荷": "2026-09-04"}
    assert is_checked_in_today(records, "薄荷", today="2026-09-05") is False


def test_is_checked_in_today_empty_records():
    assert is_checked_in_today({}, "薄荷", today="2026-09-05") is False


def test_mark_checked_in_then_skip_same_day():
    records = {}
    mark_checked_in(records, "薄荷", today="2026-09-05")
    assert records["薄荷"] == "2026-09-05"
    assert is_checked_in_today(records, "薄荷", today="2026-09-05") is True
    assert is_checked_in_today(records, "薄荷", today="2026-09-06") is False


def test_clean_records_keeps_only_today():
    records = {
        "薄荷": "2026-09-05",
        "旧号": "2026-09-04",
        "空号": "",
    }
    cleaned = clean_records(records, today="2026-09-05")
    assert cleaned == {"薄荷": "2026-09-05"}


def test_load_and_save_records_roundtrip(tmp_path):
    path = tmp_path / "daily_checkin_records.json"
    records = {"薄荷": "2026-09-05"}
    save_records(records, str(path))
    loaded = load_records(str(path))
    assert loaded == records
    assert is_checked_in_today(loaded, "薄荷", today="2026-09-05") is True


def test_load_records_missing_file_returns_empty(tmp_path):
    path = tmp_path / "missing.json"
    assert load_records(str(path)) == {}


def test_load_records_invalid_json_returns_empty(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    assert load_records(str(path)) == {}
