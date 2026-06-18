"""폭등 임박 점수 합성 — DESIGN_KR_SURGE_SCANNER.md 제4.C부.

흐름: compute_factors → 필수 게이트 → 단기/중기 가중합 → 종합 → 등급(S/A/B/C).
combine_scores / grade_for 는 순수함수로 분리해 정밀 단위테스트가 가능하다.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from indicators import ema
from surge.surge_config import SurgeConfig
from surge.factors import compute_factors

_FACTOR_LABEL = {
    "F1": "밴드폭 압축(변동성 수축)",
    "F2": "거래량 마름→점화",
    "F3": "박스상단/신고가 근접",
    "F4": "단기 모멘텀 점화",
    "F5": "베이스 성숙(장기 횡보)",
    "F6": "지수 대비 강함(상대강도)",
    "F7": "추세 토대(정배열)",
    "F8": "수급 매집(OBV)",
}


@dataclass
class ScoreResult:
    short_score: float
    mid_score: float
    total_score: float
    grade: str
    factors: dict
    passed_gate: bool
    reasons: List[str] = field(default_factory=list)


def combine_scores(f: dict, cfg: SurgeConfig) -> Tuple[float, float, float]:
    """팩터 dict → (단기, 중기, 종합) 0~100. 종합 = max + 0.2·min (한쪽만 강해도 부각)."""
    short = 100.0 * sum(cfg.w_short[k] * f[k] for k in cfg.w_short)
    mid = 100.0 * sum(cfg.w_mid[k] * f[k] for k in cfg.w_mid)
    total = min(max(short, mid) + 0.2 * min(short, mid), 100.0)
    return short, mid, total


def grade_for(score: float, cfg: SurgeConfig) -> str:
    if score >= cfg.grade_cut["S"]:
        return "S"
    if score >= cfg.grade_cut["A"]:
        return "A"
    if score >= cfg.grade_cut["B"]:
        return "B"
    return "C"


def _passes_gate(candles: list, f: dict, cfg: SurgeConfig) -> Tuple[bool, str]:
    """필수 게이트: 데이터 충분 + (추세토대 위 OR 베이스 형성). '말이 되는 후보'만 통과."""
    if len(candles) < cfg.min_candles:
        return False, "데이터 부족"
    closes = [c["close"] for c in candles]
    e_slow = ema(closes, cfg.ema_periods[-1])[-1]
    above_trend = closes[-1] > e_slow
    has_base = f["F5"] >= 0.5
    if not (above_trend or has_base):
        return False, "추세토대·베이스 모두 미충족"
    return True, ""


def _build_reasons(f: dict, top: int = 4) -> List[str]:
    items = sorted(f.items(), key=lambda kv: -kv[1])
    return [f"{_FACTOR_LABEL[k]} ({v:.2f})" for k, v in items if v >= 0.5][:top]


def compute_score(candles: list, cfg: SurgeConfig,
                  index_candles: Optional[list] = None) -> ScoreResult:
    """종목 캔들(신호일까지) → ScoreResult. 게이트 미통과면 0점/C등급."""
    f = compute_factors(candles, cfg, index_candles)
    passed, reason = _passes_gate(candles, f, cfg)
    if not passed:
        return ScoreResult(0.0, 0.0, 0.0, "C", f, False, [reason])
    short, mid, total = combine_scores(f, cfg)
    return ScoreResult(short, mid, total, grade_for(total, cfg), f, True, _build_reasons(f))
