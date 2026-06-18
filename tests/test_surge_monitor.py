"""surge_monitor 스케줄 로직 테스트 — 장마감 판정/주말/중복 방지."""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from surge_monitor import SurgeMonitor, KST, SCAN_HOUR


def test_scan_after_close_on_weekday():
    # 2026-06-18 목요일 16시(장마감 후) → 스캔
    now = datetime(2026, 6, 18, SCAN_HOUR, 0, tzinfo=KST)
    assert SurgeMonitor()._should_scan(now) is True


def test_no_scan_before_close():
    # 평일 11시(장중) → 스캔 안 함
    now = datetime(2026, 6, 18, 11, 0, tzinfo=KST)
    assert SurgeMonitor()._should_scan(now) is False


def test_no_scan_on_weekend():
    # 2026-06-20 토요일 → 스캔 안 함
    now = datetime(2026, 6, 20, SCAN_HOUR, 0, tzinfo=KST)
    assert SurgeMonitor()._should_scan(now) is False


def test_no_duplicate_scan_same_day():
    m = SurgeMonitor()
    now = datetime(2026, 6, 18, SCAN_HOUR, 0, tzinfo=KST)
    m._last_scan_date = "2026-06-18"
    assert m._should_scan(now) is False


def test_scan_next_day_after_previous():
    m = SurgeMonitor()
    m._last_scan_date = "2026-06-17"
    now = datetime(2026, 6, 18, SCAN_HOUR, 0, tzinfo=KST)   # 다음날
    assert m._should_scan(now) is True
