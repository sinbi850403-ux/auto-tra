"""폭등 임박 멀티팩터 — DESIGN_KR_SURGE_SCANNER.md 제4부.

각 팩터는 캔들 리스트를 받아 **마지막 시점**의 신호 강도를 0.0~1.0으로 반환한다.
함수에는 신호일까지의 캔들만 넘긴다 (백테스트는 candles[:t+1]을 전달). 따라서
함수는 구조적으로 미래를 볼 수 없다 — 룩어헤드는 test_factors.py에서 봉인한다.

캔들 형식: {"ts","open","high","low","close","volume"} (indicators.py와 동일).
"""
from __future__ import annotations
from typing import List, Optional

from indicators import ema, rsi, sma, obv, bollinger_bands, percentile_rank
from surge.surge_config import SurgeConfig

# F6 상대강도 절대기준 정규화 스케일: rs=±0.3(±30%)에서 점수 1.0/0.0에 도달.
# (1차 구현. 횡단면 percentile 정규화는 P4 튜닝에서 도입 — 설계서 4.B/F6 참조)
_RS_SCALE = 0.6


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ #
# 단기 트랙 (F1~F4)
# ------------------------------------------------------------------ #

def f1_volatility_contraction(candles: list, cfg: SurgeConfig) -> float:
    """F1 변동성 수축(VCP). 밴드폭이 과거 분포 대비 낮을수록(압축) 높은 점수."""
    closes = [c["close"] for c in candles]
    if len(closes) < cfg.bb_period + 5:
        return 0.0
    upper, mid, lower, width = bollinger_bands(closes, cfg.bb_period, cfg.bb_std)
    bw = [w / m if m else 0.0 for w, m in zip(width, mid)]
    lookback = min(cfg.bb_lookback, len(bw))
    window = bw[-lookback:]
    return _clip(1.0 - percentile_rank(bw[-1], window))


def f2_volume_dryup_ignition(candles: list, cfg: SurgeConfig) -> float:
    """F2 거래량 마름→점화. 폭발 직전이 말라 있었고(dryness) 당일 터지면(ignition) 높음."""
    vols = [c["volume"] for c in candles]
    if len(vols) < cfg.vol_dry_lookback + 1:
        return 0.0
    vma = sma(vols, cfg.vol_ma)
    ratio = vols[-1] / vma[-1] if vma[-1] > 0 else 0.0
    ignition = _clip(ratio / cfg.vol_ignition_mult)
    # 폭발 직전(당일 제외 최근 5일) 평균이 과거 평균 대비 말랐는가
    prior = vols[-6:-1] if len(vols) >= 6 else vols[:-1]
    past = vols[-cfg.vol_dry_lookback:-1]
    prior_avg = sum(prior) / len(prior) if prior else 0.0
    past_avg = sum(past) / len(past) if past else 1.0
    dry_ratio = prior_avg / past_avg if past_avg > 0 else 1.0
    dryness = _clip(1.0 - dry_ratio)
    return 0.5 * dryness + 0.5 * ignition


def f3_box_breakout_proximity(candles: list, cfg: SurgeConfig) -> float:
    """F3 박스 상단/신고가 근접. 돌파 직전이면 높고, 너무 멀거나 이미 추격구간이면 낮음."""
    if len(candles) < cfg.box_lookback + 1:
        return 0.0
    highs = [c["high"] for c in candles]
    close = candles[-1]["close"]
    box_high = max(highs[-(cfg.box_lookback + 1):-1])  # 현재봉 제외 직전 박스 상단
    if box_high <= 0:
        return 0.0
    dist = (box_high - close) / box_high            # +면 박스 아래, -면 돌파
    if dist >= 0:
        return _clip(1.0 - dist / cfg.box_near_pct)  # 상단 -near_pct 이내면 만점
    over = -dist
    return _clip(1.0 - over / cfg.box_chase_pct)     # 살짝 위는 유효, 추격은 감점


def f4_momentum_ignition(candles: list, cfg: SurgeConfig) -> float:
    """F4 단기 모멘텀 점화. RSI 50선 상향 + 단기 EMA 위면 높음."""
    closes = [c["close"] for c in candles]
    if len(closes) < cfg.rsi_period + 2:
        return 0.0
    r = rsi(closes, cfg.rsi_period)
    e_short = ema(closes, cfg.ema_short)
    if r[-2] < 50 <= r[-1]:
        turn = 1.0     # 50선 상향 돌파(신선한 점화)
    elif r[-1] > 50:
        turn = 0.5     # 이미 50 위
    else:
        turn = 0.0
    above = 1.0 if closes[-1] > e_short[-1] else 0.0
    return 0.6 * turn + 0.4 * above


# ------------------------------------------------------------------ #
# 중기 트랙 (F5~F8)
# ------------------------------------------------------------------ #

def f5_base_maturity(candles: list, cfg: SurgeConfig) -> float:
    """F5 베이스 성숙도. 현재가 ±base_band 박스를 오래 유지(maturity)하고
    후반부 변동성이 줄었으면(contraction) 높음."""
    closes = [c["close"] for c in candles]
    n = len(closes)
    if n < 20:
        return 0.0
    pivot = closes[-1]
    if pivot <= 0:
        return 0.0
    length = 0
    for i in range(n - 1, -1, -1):
        if abs(closes[i] - pivot) / pivot <= cfg.base_band_pct:
            length += 1
        else:
            break
    maturity = _clip(length / cfg.base_min_days)
    contraction = 0.0
    if length >= 10:
        seg = closes[-length:]
        half = len(seg) // 2
        first_rng = max(seg[:half]) - min(seg[:half])
        second_rng = max(seg[half:]) - min(seg[half:])
        if first_rng > 0:
            contraction = _clip(1.0 - second_rng / first_rng)
    return 0.6 * maturity + 0.4 * contraction


def f6_relative_strength(candles: list, index_candles: Optional[list],
                         cfg: SurgeConfig) -> float:
    """F6 상대강도. 지수 대비 초과수익(rs)을 절대기준으로 0~1화. rs=0 → 0.5."""
    closes = [c["close"] for c in candles]
    lb = cfg.rs_lookback
    if len(closes) < lb + 1 or closes[-1 - lb] <= 0:
        return 0.0
    ret_stock = closes[-1] / closes[-1 - lb] - 1.0
    ret_index = 0.0
    if index_candles and len(index_candles) >= lb + 1:
        idx = [c["close"] for c in index_candles]
        if idx[-1 - lb] > 0:
            ret_index = idx[-1] / idx[-1 - lb] - 1.0
    rs = ret_stock - ret_index
    return _clip(0.5 + rs / _RS_SCALE)


def f7_trend_foundation(candles: list, cfg: SurgeConfig) -> float:
    """F7 추세 토대. EMA200 위 + 정배열(60>120>200) + 52주 고가 근접의 평균."""
    closes = [c["close"] for c in candles]
    if len(closes) < cfg.ema_short + 2:
        return 0.0
    e = {p: ema(closes, p) for p in cfg.ema_periods}
    close = closes[-1]
    slow = cfg.ema_periods[-1]
    parts = [1.0 if close > e[slow][-1] else 0.0]
    if all(p in e for p in (60, 120, 200)):
        parts.append(1.0 if e[60][-1] > e[120][-1] > e[200][-1] else 0.0)
    hp = min(cfg.high_52w_period, len(candles))
    high_52w = max(c["high"] for c in candles[-hp:])
    parts.append(1.0 if high_52w > 0 and close / high_52w >= cfg.high_52w_near else 0.0)
    return sum(parts) / len(parts)


def f8_supply_accumulation(candles: list, cfg: SurgeConfig) -> float:
    """F8 수급 매집(1차: OBV만). 가격은 횡보/하락인데 OBV가 오르면 매집 다이버전스.
    외국인·기관 순매수는 P2 후반에 합산 예정 (설계서 4.B/F8)."""
    lb = cfg.obv_div_lookback
    if len(candles) < lb + 5:
        return 0.0
    o = obv(candles)
    closes = [c["close"] for c in candles]
    obv_chg = o[-1] - o[-1 - lb]
    denom = max(abs(o[-1]), abs(o[-1 - lb]), 1.0)
    obv_trend = _clip(obv_chg / denom, -1.0, 1.0)
    price_chg = closes[-1] / closes[-1 - lb] - 1.0 if closes[-1 - lb] > 0 else 0.0
    if obv_trend <= 0:
        return 0.0
    # OBV 상승 + 가격 정체(≤+5%)면 강한 매집, 가격도 많이 오르면 약한 가점
    return obv_trend if price_chg <= 0.05 else obv_trend * 0.5


# ------------------------------------------------------------------ #
# 통합
# ------------------------------------------------------------------ #

def compute_factors(candles: list, cfg: SurgeConfig,
                    index_candles: Optional[list] = None) -> dict:
    """8개 팩터를 한 번에 계산해 {"F1":..,"F8":..} (각 0~1)로 반환.
    candles는 '신호일까지'의 캔들이어야 한다 (룩어헤드 금지)."""
    return {
        "F1": f1_volatility_contraction(candles, cfg),
        "F2": f2_volume_dryup_ignition(candles, cfg),
        "F3": f3_box_breakout_proximity(candles, cfg),
        "F4": f4_momentum_ignition(candles, cfg),
        "F5": f5_base_maturity(candles, cfg),
        "F6": f6_relative_strength(candles, index_candles, cfg),
        "F7": f7_trend_foundation(candles, cfg),
        "F8": f8_supply_accumulation(candles, cfg),
    }
