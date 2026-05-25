"""EMA + 피보나치 — 순수 Python (pandas/numpy 없음)."""
from dataclasses import dataclass
from typing import Optional, List
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


def add_emas(candles: list, cfg: Config) -> list:
    closes = [c["close"] for c in candles]
    fast = ema(closes, cfg.ema_fast)
    slow = ema(closes, cfg.ema_slow)
    trend_ema = ema(closes, cfg.ema_trend)
    for i, c in enumerate(candles):
        c["ema_fast"]  = fast[i]
        c["ema_slow"]  = slow[i]
        c["ema_trend"] = trend_ema[i]
    return candles


def trend(candles: list) -> str:
    last = candles[-1]
    if last["ema_fast"] > last["ema_slow"] and last["close"] > last["ema_fast"]:
        return "bull"
    if last["ema_fast"] < last["ema_slow"] and last["close"] < last["ema_fast"]:
        return "bear"
    return "neutral"


# ------------------------------------------------------------------ #
# 피보나치
# ------------------------------------------------------------------ #

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
        return FibLevels(
            swing_high=high, swing_low=low, direction="bull",
            level_618=high - rng * 0.618,
            level_786=high - rng * 0.786,
            level_500=high - rng * 0.500,
        )
    else:
        return FibLevels(
            swing_high=high, swing_low=low, direction="bear",
            level_618=low + rng * 0.618,
            level_786=low + rng * 0.786,
            level_500=low + rng * 0.500,
        )


def price_in_fib_zone(price: float, fib: FibLevels) -> bool:
    lo = min(fib.level_618, fib.level_786)
    hi = max(fib.level_618, fib.level_786)
    return lo <= price <= hi
