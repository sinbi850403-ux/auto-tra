"""일일 전종목 스캔 → 랭킹 — DESIGN_KR_SURGE_SCANNER.md 제1/7부.

유니버스 통과 → 점수 → 게이트 통과분만 total_score 내림차순 정렬.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from surge.surge_config import SurgeConfig
from surge.universe import StockMeta, passes_universe
from surge.score import compute_score


@dataclass
class ScanResult:
    code: str
    name: str
    market: str
    close: float
    change_pct: float
    value_krw: float
    short_score: float
    mid_score: float
    total_score: float
    grade: str
    factors: dict
    reasons: List[str] = field(default_factory=list)
    ts: str = ""


def scan_one(meta: StockMeta, candles: list, cfg: SurgeConfig,
             index_candles: Optional[list] = None) -> Optional[ScanResult]:
    """단일 종목 스캔. 유니버스/점수 게이트 미통과면 None."""
    ok, _ = passes_universe(meta, candles, cfg)
    if not ok:
        return None
    sr = compute_score(candles, cfg, index_candles)
    if not sr.passed_gate:
        return None
    close = candles[-1]["close"]
    prev = candles[-2]["close"] if len(candles) >= 2 else close
    change_pct = (close / prev - 1.0) * 100 if prev > 0 else 0.0
    return ScanResult(
        code=meta.code, name=meta.name, market=meta.market,
        close=close, change_pct=change_pct, value_krw=candles[-1].get("value", 0.0),
        short_score=sr.short_score, mid_score=sr.mid_score, total_score=sr.total_score,
        grade=sr.grade, factors=sr.factors, reasons=sr.reasons,
        ts=candles[-1].get("ts", ""),
    )


def scan_universe(metas_candles, cfg: SurgeConfig,
                  index_by_market: Optional[dict] = None) -> List[ScanResult]:
    """[(meta, candles), ...] → ScanResult 리스트 (total_score 내림차순)."""
    index_by_market = index_by_market or {}
    results = []
    for meta, candles in metas_candles:
        r = scan_one(meta, candles, cfg, index_by_market.get(meta.market))
        if r:
            results.append(r)
    results.sort(key=lambda r: -r.total_score)
    return results


def top_alerts(results: List[ScanResult], cfg: SurgeConfig) -> List[ScanResult]:
    """알림 대상: 지정 등급(S/A) 중 상위 N개."""
    picked = [r for r in results if r.grade in cfg.alert_grades]
    return picked[:cfg.top_n_alert]
