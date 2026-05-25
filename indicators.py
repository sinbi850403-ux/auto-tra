"""EMA + 슈퍼트렌드 — 순수 Python."""
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
# 슈퍼트렌드
# ------------------------------------------------------------------ #

@dataclass
class SupertrendResult:
    direction: List[int]   # +1 = 상승, -1 = 하락
    line: List[float]      # 슈퍼트렌드 라인 값


def supertrend(candles: list, cfg: Config) -> SupertrendResult:
    atr_vals = atr(candles, cfg.st_atr_period)
    n = len(candles)

    upper = [0.0] * n
    lower = [0.0] * n
    direction = [1] * n
    line = [0.0] * n

    for i in range(n):
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        basic_upper = hl2 + cfg.st_multiplier * atr_vals[i]
        basic_lower = hl2 - cfg.st_multiplier * atr_vals[i]

        if i == 0:
            upper[i] = basic_upper
            lower[i] = basic_lower
        else:
            prev_close = candles[i - 1]["close"]
            upper[i] = basic_upper if basic_upper < upper[i-1] or prev_close > upper[i-1] else upper[i-1]
            lower[i] = basic_lower if basic_lower > lower[i-1] or prev_close < lower[i-1] else lower[i-1]

        if i == 0:
            direction[i] = 1
        else:
            prev_dir = direction[i - 1]
            close = candles[i]["close"]
            if prev_dir == -1:
                direction[i] = 1 if close > upper[i] else -1
            else:
                direction[i] = -1 if close < lower[i] else 1

        line[i] = lower[i] if direction[i] == 1 else upper[i]

    return SupertrendResult(direction=direction, line=line)


# ------------------------------------------------------------------ #
# EMA200 추세 필터
# ------------------------------------------------------------------ #

def ema200(candles: list, cfg: Config) -> List[float]:
    closes = [c["close"] for c in candles]
    return ema(closes, cfg.ema_trend)


# ------------------------------------------------------------------ #
# 호환성 유지 (order_blocks.py 등이 사용)
# ------------------------------------------------------------------ #

def add_emas(candles: list, cfg: Config) -> list:
    closes = [c["close"] for c in candles]
    fast_vals = ema(closes, cfg.ema_fast)
    slow_vals = ema(closes, cfg.ema_slow)
    trend_vals = ema(closes, cfg.ema_trend)
    for i, c in enumerate(candles):
        c["ema_fast"]  = fast_vals[i]
        c["ema_slow"]  = slow_vals[i]
        c["ema_trend"] = trend_vals[i]
    return candles


def trend(candles: list) -> str:
    last = candles[-1]
    if last.get("ema_fast", 0) > last.get("ema_slow", 0) and last["close"] > last.get("ema_fast", 0):
        return "bull"
    if last.get("ema_fast", 0) < last.get("ema_slow", 0) and last["close"] < last.get("ema_fast", 0):
        return "bear"
    return "neutral"


@dataclass
class FibLevels:
    swing_high: float
    swing_low: float
    direction: str
    level_618: float
    level_786: float
    level_500: float


def calc_fib(candles: list, cfg: Config, direction: str) -> Optional[FibLevels]:
    window = candles[-cfg.fib_swing_lookback:]
    high = max(c["high"] for c in window)
    low  = min(c["low"]  for c in window)
    rng  = high - low
    if rng == 0:
        return None
    if direction == "bull":
        return FibLevels(high, low, "bull",
                         high - rng * 0.618, high - rng * 0.786, high - rng * 0.500)
    return FibLevels(high, low, "bear",
                     low + rng * 0.618, low + rng * 0.786, low + rng * 0.500)


def price_in_fib_zone(price: float, fib: FibLevels) -> bool:
    lo = min(fib.level_618, fib.level_786)
    hi = max(fib.level_618, fib.level_786)
    return lo <= price <= hi
