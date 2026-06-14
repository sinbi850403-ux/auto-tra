"""EMA + 슈퍼트렌드 + 스윙 고점/저점 — 순수 Python."""
from dataclasses import dataclass
from typing import List, Optional
from config import Config


# ------------------------------------------------------------------ #
# EMA
# ------------------------------------------------------------------ #

def ema(values: List[float], period: int) -> List[float]:
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


# ------------------------------------------------------------------ #
# ATR (Average True Range)
# ------------------------------------------------------------------ #

def _true_range(candles: list) -> List[float]:
    tr = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def atr(candles: list, period: int) -> List[float]:
    tr = _true_range(candles)
    # Wilder's smoothing (RMA)
    result = [sum(tr[:period]) / period]
    k = 1 / period
    for v in tr[period:]:
        result.append(v * k + result[-1] * (1 - k))
    # 앞부분 패딩 (길이 맞추기)
    pad = [result[0]] * (period - 1)
    return pad + result


# ------------------------------------------------------------------ #
# RSI (Wilder)
# ------------------------------------------------------------------ #

def rsi(values: List[float], period: int = 14) -> List[float]:
    """Wilder RSI. 워밍업 구간(데이터 부족)은 중립 50.0으로 패딩."""
    n = len(values)
    if n < period + 1:
        return [50.0] * n

    gains, losses = [], []
    for i in range(1, n):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / l)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out = [50.0] * period
    out.append(_rsi(avg_gain, avg_loss))
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out.append(_rsi(avg_gain, avg_loss))
    return out


# ------------------------------------------------------------------ #
# ADX (Wilder) — 추세 강도
# ------------------------------------------------------------------ #

def adx(candles: list, period: int = 14) -> List[float]:
    """Wilder ADX. 워밍업 구간은 0.0 패딩 (0 = 추세 없음으로 보수적 처리)."""
    n = len(candles)
    if n < 2 * period + 1:
        return [0.0] * n

    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = candles[i]["high"] - candles[i - 1]["high"]
        dn = candles[i - 1]["low"] - candles[i]["low"]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    def _dx(sp: float, sm: float, st: float) -> float:
        if st == 0:
            return 0.0
        di_p = 100.0 * sp / st
        di_m = 100.0 * sm / st
        den = di_p + di_m
        return 0.0 if den == 0 else 100.0 * abs(di_p - di_m) / den

    # Wilder 누적합 평활
    s_pdm = sum(plus_dm[:period])
    s_mdm = sum(minus_dm[:period])
    s_tr  = sum(trs[:period])
    dxs = [_dx(s_pdm, s_mdm, s_tr)]
    for i in range(period, len(trs)):
        s_pdm = s_pdm - s_pdm / period + plus_dm[i]
        s_mdm = s_mdm - s_mdm / period + minus_dm[i]
        s_tr  = s_tr  - s_tr  / period + trs[i]
        dxs.append(_dx(s_pdm, s_mdm, s_tr))

    adx_val = sum(dxs[:period]) / period
    out = [adx_val]
    for i in range(period, len(dxs)):
        adx_val = (adx_val * (period - 1) + dxs[i]) / period
        out.append(adx_val)

    return [0.0] * (n - len(out)) + out


# ------------------------------------------------------------------ #
# Chandelier Exit (샹들리에 트레일링 스탑)
# ------------------------------------------------------------------ #

def chandelier_exit(
    candles: list,
    period: int = 22,
    mult: float = 3.0,
):
    """
    Chandelier Exit 트레일링 스탑 계산.

    ce_long  = highest_high(period) - ATR(period) × mult
    ce_short = lowest_low(period)   + ATR(period) × mult

    롱 청산 조건: 가격 < ce_long
    숏 청산 조건: 가격 > ce_short
    """
    atr_vals = atr(candles, period)
    n = len(candles)
    ce_long, ce_short = [], []

    for i in range(n):
        if i < period - 1:
            ce_long.append(candles[i]["high"])
            ce_short.append(candles[i]["low"])
        else:
            window   = candles[i - period + 1: i + 1]
            h_high   = max(c["high"] for c in window)
            l_low    = min(c["low"]  for c in window)
            ce_long.append(h_high - mult * atr_vals[i])
            ce_short.append(l_low  + mult * atr_vals[i])

    return ce_long, ce_short


# ------------------------------------------------------------------ #
# 볼린저밴드
# ------------------------------------------------------------------ #

from typing import Tuple

def bollinger_bands(
    closes: List[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[List[float], List[float], List[float], List[float]]:
    """
    Returns (upper, middle, lower, width).
    period 미만 인덱스는 closes[i]로 패딩 (width=0).
    """
    upper, middle, lower, width = [], [], [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(closes[i])
            middle.append(closes[i])
            lower.append(closes[i])
            width.append(0.0)
        else:
            window = closes[i - period + 1: i + 1]
            mean = sum(window) / period
            std = (sum((x - mean) ** 2 for x in window) / period) ** 0.5
            u = mean + std_dev * std
            l = mean - std_dev * std
            upper.append(u)
            middle.append(mean)
            lower.append(l)
            width.append(u - l)
    return upper, middle, lower, width


# ------------------------------------------------------------------ #
# 스윙 고점 / 저점
# ------------------------------------------------------------------ #

def swing_high(candles: list, lookback: int = 20) -> float:
    """직전 lookback 캔들의 최고점 (현재 캔들 제외)."""
    window = candles[-(lookback + 1):-1]
    return max(c["high"] for c in window) if window else 0.0


def swing_low(candles: list, lookback: int = 20) -> float:
    """직전 lookback 캔들의 최저점 (현재 캔들 제외)."""
    window = candles[-(lookback + 1):-1]
    return min(c["low"] for c in window) if window else float("inf")


def find_pullback_low(candles: list, ema50_series: List[float],
                      lookback: int = 10, tol: float = 0.004) -> Optional[float]:
    """
    최근 lookback 캔들에서 EMA50 눌림 저점 찾기.
    캔들 저점이 EMA50 ± tol 이내이거나 EMA50을 하향 터치하면 저점 반환.
    """
    window_c   = candles[-(lookback + 1):-1]
    window_e50 = ema50_series[-(lookback + 1):-1]
    for c, e50 in zip(window_c, window_e50):
        near = abs(c["low"] - e50) / e50 <= tol
        touch = c["low"] <= e50 <= c["high"]
        if near or touch:
            return c["low"]
    return None


def find_pullback_high(candles: list, ema50_series: List[float],
                       lookback: int = 10, tol: float = 0.004) -> Optional[float]:
    """
    최근 lookback 캔들에서 EMA50 반등 고점 찾기.
    캔들 고점이 EMA50 ± tol 이내이거나 EMA50을 상향 터치하면 고점 반환.
    """
    window_c   = candles[-(lookback + 1):-1]
    window_e50 = ema50_series[-(lookback + 1):-1]
    for c, e50 in zip(window_c, window_e50):
        near = abs(c["high"] - e50) / e50 <= tol
        touch = c["low"] <= e50 <= c["high"]
        if near or touch:
            return c["high"]
    return None


