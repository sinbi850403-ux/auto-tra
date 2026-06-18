"""universe.py 단위 테스트 — 종목 필터 게이트."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge.universe import StockMeta, is_preferred_stock, passes_universe, filter_universe

CFG = SurgeConfig(min_candles=25)   # 테스트용으로 워밍업 완화


def candles(close=5000.0, value=2_000_000_000.0, n=30, prev_close=None):
    out = [{"ts": "20230101", "open": close, "high": close, "low": close,
            "close": close, "volume": int(value / close), "value": value} for _ in range(n)]
    if prev_close is not None:
        out[-2] = dict(out[-2], close=prev_close)
    return out


def meta(**kw):
    base = dict(code="005930", name="삼성전자", market="KOSPI",
                market_cap=400_000_000_000_000, listing_days=9999)
    base.update(kw)
    return StockMeta(**base)


# ---------------- 우선주 판별 ----------------
def test_preferred_detection():
    assert is_preferred_stock("005935") is True
    assert is_preferred_stock("005930") is False


# ---------------- 하드 제외 ----------------
def test_managed_excluded():
    ok, why = passes_universe(meta(is_managed=True), candles(), CFG)
    assert not ok and why == "관리종목"


def test_etf_excluded():
    ok, why = passes_universe(meta(is_etf=True), candles(), CFG)
    assert not ok and why == "ETF/ETN"


def test_spac_excluded():
    ok, why = passes_universe(meta(is_spac=True), candles(), CFG)
    assert not ok and why == "스팩"


def test_preferred_excluded():
    ok, why = passes_universe(meta(code="005935"), candles(), CFG)
    assert not ok and why == "우선주"


def test_new_listing_excluded():
    ok, why = passes_universe(meta(listing_days=30), candles(), CFG)
    assert not ok and why == "신규상장"


# ---------------- 소프트 게이트 ----------------
def test_penny_stock_excluded():
    ok, why = passes_universe(meta(), candles(close=800.0), CFG)
    assert not ok and why == "동전주"


def test_small_cap_excluded():
    ok, why = passes_universe(meta(market_cap=10_000_000_000), candles(), CFG)
    assert not ok and why == "시총미달"


def test_illiquid_excluded():
    ok, why = passes_universe(meta(), candles(value=100_000_000), CFG)  # 1억 < 10억
    assert not ok and why == "거래대금미달"


def test_insufficient_data_excluded():
    ok, why = passes_universe(meta(), candles(n=10), CFG)
    assert not ok and why == "데이터부족"


def test_limit_up_today_excluded():
    # 직전 5000 → 당일 5900 (+18% ≥ 15%) → 추격 금지
    c = candles(close=5900.0, prev_close=5000.0)
    ok, why = passes_universe(meta(), c, CFG)
    assert not ok and why == "당일급등"


# ---------------- 정상 통과 ----------------
def test_clean_stock_passes():
    ok, why = passes_universe(meta(), candles(), CFG)
    assert ok and why == ""


def test_filter_universe_returns_codes():
    items = [
        (meta(code="005930"), candles()),               # 통과
        (meta(code="005935"), candles()),               # 우선주 탈락
        (meta(code="000660", is_managed=True), candles()),  # 관리종목 탈락
    ]
    assert filter_universe(items, CFG) == ["005930"]
