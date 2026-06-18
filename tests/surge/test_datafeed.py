"""datafeed.py 단위 테스트 — 변환/병합/캐시 (네트워크 없이)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from surge.datafeed import df_to_candles, merge_incremental, save_candles, load_candles


def test_df_to_candles_basic():
    df = pd.DataFrame(
        {"Open": [100.0], "High": [110.0], "Low": [95.0], "Close": [105.0], "Volume": [1000]},
        index=pd.to_datetime(["2023-01-02"]),
    )
    c = df_to_candles(df)
    assert len(c) == 1
    assert c[0]["ts"] == "20230102"
    assert c[0]["close"] == 105.0
    assert c[0]["value"] == 105.0 * 1000     # 거래대금 = close*volume


def test_df_to_candles_preserves_order():
    df = pd.DataFrame(
        {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
         "Close": [1.0, 2.0], "Volume": [10, 20]},
        index=pd.to_datetime(["2023-01-02", "2023-01-03"]),
    )
    c = df_to_candles(df)
    assert [x["ts"] for x in c] == ["20230102", "20230103"]


def test_merge_incremental_dedup_new_wins():
    old = [{"ts": "20230101", "close": 1}, {"ts": "20230102", "close": 2}]
    new = [{"ts": "20230102", "close": 99}, {"ts": "20230103", "close": 3}]
    m = merge_incremental(old, new)
    assert [x["ts"] for x in m] == ["20230101", "20230102", "20230103"]
    assert m[1]["close"] == 99            # 같은 날짜는 new 우선


def test_merge_incremental_empty_old():
    new = [{"ts": "20230103", "close": 3}, {"ts": "20230101", "close": 1}]
    assert [x["ts"] for x in merge_incremental([], new)] == ["20230101", "20230103"]


def test_cache_roundtrip(tmp_path):
    candles = [
        {"ts": "20230102", "open": 100.0, "high": 110.0, "low": 95.0,
         "close": 105.0, "volume": 1000, "value": 105000.0},
        {"ts": "20230103", "open": 105.0, "high": 112.0, "low": 104.0,
         "close": 111.0, "volume": 2000, "value": 222000.0},
    ]
    p = str(tmp_path / "005930.parquet")
    save_candles(p, candles)
    loaded = load_candles(p)
    assert loaded == candles             # 타입·값 보존


def test_load_missing_returns_none(tmp_path):
    assert load_candles(str(tmp_path / "nope.parquet")) is None
