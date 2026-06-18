"""report.py 단위 테스트 — 텔레그램 포맷 + CSV."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge.scanner import ScanResult
from surge.report import format_alert_card, format_telegram, save_csv

CFG = SurgeConfig()


def sr(code="247540", name="에코프로비엠", grade="S", short=88, mid=79, change=2.1,
       reasons=("밴드폭 압축(변동성 수축) (0.95)", "거래량 마름→점화 (0.88)")):
    return ScanResult(code, name, "KOSDAQ", 100000.0, change, 1.2e11,
                      short, mid, max(short, mid), grade, {}, list(reasons), "20260618")


def test_card_contains_core_fields():
    card = format_alert_card(sr())
    assert "에코프로비엠" in card and "247540" in card
    assert "[S]" in card and "+2.1%" in card
    assert "밴드폭 압축" in card


def test_telegram_lists_alerts():
    msg = format_telegram([sr(), sr(code="000660", name="SK하이닉스", grade="A")], CFG, "2026-06-18")
    assert "폭등 임박 스캔" in msg
    assert "에코프로비엠" in msg and "SK하이닉스" in msg
    assert "자동매매 아님" in msg            # 면책 문구


def test_telegram_empty():
    assert "없음" in format_telegram([], CFG, "2026-06-18")


def test_telegram_excludes_non_alert_grades():
    # B등급은 알림에서 빠져야
    msg = format_telegram([sr(code="111111", name="비등급", grade="B")], CFG, "2026-06-18")
    assert "비등급" not in msg


def test_save_csv_writes_all_rows(tmp_path):
    p = str(tmp_path / "scan.csv")
    save_csv([sr(), sr(code="000660", name="하이닉스", grade="A")], p)
    assert os.path.exists(p)
    with open(p, encoding="utf-8-sig") as f:
        content = f.read()
    assert "에코프로비엠" in content and "하이닉스" in content
    assert "code" in content and "grade" in content   # 헤더
