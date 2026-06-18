"""scanner.py 단위 테스트 — 스캔/정렬/알림 필터."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge.universe import StockMeta
from surge.scanner import ScanResult, scan_one, scan_universe, top_alerts

CFG = SurgeConfig()


def rising_v(n=260, step=0.01, value=2_000_000_000.0):
    out, p = [], 1000.0
    for _ in range(n):
        p *= (1 + step)
        out.append({"ts": "20260101", "open": p / (1 + step), "high": p * 1.002,
                    "low": p * 0.998, "close": p, "volume": int(value / p), "value": value})
    return out


def falling_v(n=260, step=0.01, value=2_000_000_000.0):
    out, p = [], 50000.0
    for _ in range(n):
        p *= (1 - step)
        out.append({"ts": "20260101", "open": p / (1 - step), "high": p * 1.002,
                    "low": p * 0.998, "close": p, "volume": int(value / p), "value": value})
    return out


def flat_v(n=260, price=1000.0, value=2_000_000_000.0):
    return [{"ts": "20260101", "open": price, "high": price * 1.01, "low": price * 0.99,
             "close": price, "volume": int(value / price), "value": value} for _ in range(n)]


def meta(code="005930", market="KOSPI"):
    return StockMeta(code=code, name="테스트", market=market,
                     market_cap=400_000_000_000_000)


def test_scan_one_strong_passes():
    r = scan_one(meta(), rising_v(260), CFG, flat_v(260))
    assert r is not None
    assert r.grade in ("S", "A", "B", "C")
    assert r.total_score > 0


def test_scan_one_downtrend_filtered():
    # 하락추세는 점수 게이트(추세토대·베이스 미충족)에서 탈락
    assert scan_one(meta(), falling_v(260), CFG, flat_v(260)) is None


def test_scan_one_universe_fail_filtered():
    # 우선주(005935)는 유니버스에서 탈락
    assert scan_one(meta(code="005935"), rising_v(260), CFG, flat_v(260)) is None


def test_scan_universe_sorted_desc():
    items = [
        (meta(code="000001"), rising_v(260)),
        (meta(code="000002"), rising_v(260, step=0.005)),
        (meta(code="000003"), flat_v(260)),
    ]
    results = scan_universe(items, CFG, {"KOSPI": flat_v(260)})
    totals = [r.total_score for r in results]
    assert totals == sorted(totals, reverse=True)   # 내림차순 정렬 보장


def test_top_alerts_top_pct():
    rs = [
        ScanResult("A1", "s", "KOSPI", 1, 1, 1, 90, 80, 90, "S", {}, []),
        ScanResult("A2", "a", "KOSPI", 1, 1, 1, 75, 60, 75, "A", {}, []),
        ScanResult("A3", "b", "KOSPI", 1, 1, 1, 60, 50, 60, "B", {}, []),
    ]
    # 3종목 × 상위 10% → 최상위 1종목만
    picked = top_alerts(rs, CFG)
    assert [r.code for r in picked] == ["A1"]


def test_top_alerts_respects_top_n_cap():
    cfg = SurgeConfig(top_n_alert=1, alert_top_pct=1.0)  # 전체가 분위여도 top_n=1로 캡
    rs = [
        ScanResult("A1", "s", "KOSPI", 1, 1, 1, 90, 80, 90, "S", {}, []),
        ScanResult("A2", "a", "KOSPI", 1, 1, 1, 75, 60, 75, "A", {}, []),
    ]
    assert len(top_alerts(rs, cfg)) == 1
