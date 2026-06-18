"""유니버스 필터 — DESIGN_KR_SURGE_SCANNER.md 제3부.

종목 메타(StockMeta) + 캔들을 받아 순수 함수로 필터한다.
관리/경고/스팩/ETF 지정 여부는 datafeed가 채워주고(T9), 여기선 판정만 한다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple

from surge.surge_config import SurgeConfig


@dataclass
class StockMeta:
    code: str
    name: str
    market: str                  # "KOSPI" / "KOSDAQ"
    market_cap: float            # 시가총액(원)
    is_managed: bool = False     # 관리/투자위험/거래정지
    is_etf: bool = False         # ETF/ETN/리츠
    is_spac: bool = False        # 스팩
    listing_days: int = 9999     # 상장 경과일


def is_preferred_stock(code: str) -> bool:
    """우선주 판별(1차: 코드 끝자리 규칙). 보통주는 끝자리 '0'.
    예: 005930(보통주) vs 005935(우선주). 종목명 '우' 보조판별은 datafeed에서."""
    return len(code) == 6 and not code.endswith("0")


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def passes_universe(meta: StockMeta, candles: list, cfg: SurgeConfig) -> Tuple[bool, str]:
    """단일 종목 유니버스 통과 여부 + 탈락 사유."""
    # --- 하드 제외 ---
    if meta.is_managed:
        return False, "관리종목"
    if meta.is_etf:
        return False, "ETF/ETN"
    if meta.is_spac:
        return False, "스팩"
    if is_preferred_stock(meta.code):
        return False, "우선주"
    if meta.listing_days < cfg.new_listing_min_days:
        return False, "신규상장"

    # --- 데이터/가격/시총 게이트 ---
    if len(candles) < cfg.min_candles:
        return False, "데이터부족"
    close = candles[-1]["close"]
    if close < cfg.min_price:
        return False, "동전주"
    if cfg.max_price is not None and close > cfg.max_price:
        return False, "고가제외"
    if meta.market_cap < cfg.min_market_cap_krw:
        return False, "시총미달"

    # --- 유동성(거래대금) 게이트 ---
    avg_value = _mean([c["value"] for c in candles[-cfg.value_ma_period:]])
    if avg_value < cfg.min_avg_value_krw:
        return False, "거래대금미달"

    # --- 당일 급등 추격 금지 ---
    if cfg.exclude_limit_up_today and len(candles) >= 2:
        prev = candles[-2]["close"]
        if prev > 0 and (close / prev - 1.0) >= cfg.limit_up_today_pct:
            return False, "당일급등"

    return True, ""


def filter_universe(metas_candles: List[Tuple[StockMeta, list]],
                    cfg: SurgeConfig) -> List[str]:
    """[(meta, candles), ...] → 통과 종목코드 리스트."""
    out = []
    for meta, candles in metas_candles:
        ok, _ = passes_universe(meta, candles, cfg)
        if ok:
            out.append(meta.code)
    return out
