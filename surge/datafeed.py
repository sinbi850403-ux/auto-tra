"""데이터 수급 + 캐시 — DESIGN_KR_SURGE_SCANNER.md 제2부.

- 실제 FDR/pykrx 호출은 함수 내부 import로 격리 (모듈 로딩 가볍게, 네트워크 없이 테스트 가능).
- 변환(df_to_candles) / 병합(merge_incremental) / 캐시(save·load)는 순수 로직 → mock 테스트.

캔들 형식: {"ts":"YYYYMMDD","open","high","low","close","volume","value"}.
"""
from __future__ import annotations
import os
from typing import List, Optional

from surge.surge_config import SurgeConfig

# FDR 지수 코드
INDEX_CODE = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


# ------------------------------------------------------------------ #
# 순수 변환 / 병합 / 캐시
# ------------------------------------------------------------------ #

def df_to_candles(df) -> List[dict]:
    """FDR DataReader 결과(DataFrame: Open/High/Low/Close/Volume, index=날짜) → Candle 리스트."""
    out = []
    for idx, row in df.iterrows():
        ts = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx).replace("-", "")[:8]
        close = float(row["Close"])
        vol = int(row["Volume"])
        out.append({
            "ts": ts, "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": close, "volume": vol,
            "value": close * vol,
        })
    return out


def merge_incremental(old: List[dict], new: List[dict]) -> List[dict]:
    """ts 기준 병합(중복 제거, new 우선) 후 날짜순 정렬."""
    by_ts = {c["ts"]: c for c in old}
    for c in new:
        by_ts[c["ts"]] = c
    return [by_ts[t] for t in sorted(by_ts)]


def save_candles(path: str, candles: List[dict]) -> None:
    import pandas as pd
    df = pd.DataFrame(candles)
    try:
        df.to_parquet(path, index=False)
    except Exception:
        df.to_csv(path, index=False)


def load_candles(path: str) -> Optional[List[dict]]:
    if not os.path.exists(path):
        return None
    import pandas as pd
    try:
        df = pd.read_parquet(path)
    except Exception:
        df = pd.read_csv(path, dtype={"ts": str})
    recs = df.to_dict("records")
    for r in recs:                       # parquet/csv 왕복 후 타입 정규화
        r["ts"] = str(r["ts"])
        r["volume"] = int(r["volume"])
        for k in ("open", "high", "low", "close", "value"):
            if k in r:
                r[k] = float(r[k])
    return recs


# ------------------------------------------------------------------ #
# DataFeed — 실제 수급 + 캐시 (네트워크; T9 실데이터에서 검증)
# ------------------------------------------------------------------ #

class DataFeed:
    def __init__(self, cfg: SurgeConfig):
        self.cfg = cfg
        self.ohlcv_dir = os.path.join(cfg.cache_dir, "ohlcv")
        os.makedirs(self.ohlcv_dir, exist_ok=True)

    def cache_path(self, code: str) -> str:
        return os.path.join(self.ohlcv_dir, f"{code}.parquet")

    # --- 원격 수급 (얇은 래퍼) ---
    def fetch_ohlcv(self, code: str, start: str, end: str) -> List[dict]:
        import FinanceDataReader as fdr
        return df_to_candles(fdr.DataReader(code, start, end))

    def fetch_index(self, market: str, start: str, end: str) -> List[dict]:
        import FinanceDataReader as fdr
        return df_to_candles(fdr.DataReader(INDEX_CODE[market], start, end))

    def fetch_ticker_list(self, market: str, date: Optional[str] = None) -> List[str]:
        from pykrx import stock
        return stock.get_market_ticker_list(date, market=market) if date \
            else stock.get_market_ticker_list(market=market)

    def fetch_market_cap(self, date: str):
        """pykrx 시가총액 DataFrame (index=종목코드, '시가총액' 컬럼 포함). [deprecated: 해외 IP 차단]"""
        from pykrx import stock
        return stock.get_market_cap_by_ticker(date)

    def fetch_stock_listing(self, market: str) -> List[dict]:
        """FDR StockListing → [{code,name,market,market_cap,amount,close}].
        pykrx 대체 — KRX 직접 접근이 해외 IP(Railway)에서 차단되므로 FDR 사용."""
        import FinanceDataReader as fdr
        df = fdr.StockListing(market)
        out = []
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip().zfill(6)
            if not code or len(code) != 6 or code == "000000":
                continue
            out.append({
                "code": code,
                "name": str(row.get("Name", code)),
                "market": market,
                "market_cap": float(row.get("Marcap", 0) or 0),
                "amount": float(row.get("Amount", 0) or 0),    # 당일 거래대금
                "close": float(row.get("Close", 0) or 0),
            })
        return out

    # --- 캐시 결합 조회 (증분) ---
    def get_candles(self, code: str, start: str, end: str) -> List[dict]:
        """캐시 우선. 캐시 마지막 날짜 이후만 증분 수급해 병합·저장."""
        cached = load_candles(self.cache_path(code)) or []
        fetch_start = start
        if cached:
            fetch_start = cached[-1]["ts"]      # 마지막 캐시일부터(겹치면 dedup)
        fresh = self.fetch_ohlcv(code, fetch_start, end)
        merged = merge_incremental(cached, fresh)
        if merged:
            save_candles(self.cache_path(code), merged)
        return merged
