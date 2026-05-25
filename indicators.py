"""EMA + 피보나치 계산."""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from config import Config


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_emas(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = ema(df["close"], cfg.ema_fast)
    df["ema_slow"] = ema(df["close"], cfg.ema_slow)
    df["ema_trend"] = ema(df["close"], cfg.ema_trend)
    return df


# ------------------------------------------------------------------ #
# 트렌드 판단
# ------------------------------------------------------------------ #

def trend(df: pd.DataFrame) -> str:
    """
    마지막 캔들 기준 트렌드 반환.
    'bull' | 'bear' | 'neutral'
    """
    last = df.iloc[-1]
    if last["ema_fast"] > last["ema_slow"] and last["close"] > last["ema_fast"]:
        return "bull"
    if last["ema_fast"] < last["ema_slow"] and last["close"] < last["ema_fast"]:
        return "bear"
    return "neutral"


# ------------------------------------------------------------------ #
# 피보나치 스윙 감지 + 레벨 계산
# ------------------------------------------------------------------ #

@dataclass
class FibLevels:
    swing_high: float
    swing_low: float
    direction: str   # 'bull' (저점→고점) | 'bear' (고점→저점)
    level_618: float
    level_786: float
    level_500: float


def _find_swing_high(series: pd.Series) -> float:
    return series.max()


def _find_swing_low(series: pd.Series) -> float:
    return series.min()


def calc_fib(df: pd.DataFrame, cfg: Config, direction: str) -> Optional[FibLevels]:
    """
    최근 N캔들에서 스윙 고/저를 찾아 피보나치 레벨 계산.
    direction: 'bull' | 'bear'
    """
    window = df.tail(cfg.fib_swing_lookback)
    high = _find_swing_high(window["high"])
    low = _find_swing_low(window["low"])
    rng = high - low
    if rng == 0:
        return None

    if direction == "bull":
        # 상승 추세: 고점→저점 되돌림 구간이 매수 진입대
        return FibLevels(
            swing_high=high,
            swing_low=low,
            direction="bull",
            level_618=high - rng * 0.618,
            level_786=high - rng * 0.786,
            level_500=high - rng * 0.500,
        )
    else:
        # 하락 추세: 저점→고점 되돌림 구간이 매도 진입대
        return FibLevels(
            swing_high=high,
            swing_low=low,
            direction="bear",
            level_618=low + rng * 0.618,
            level_786=low + rng * 0.786,
            level_500=low + rng * 0.500,
        )


def price_in_fib_zone(price: float, fib: FibLevels) -> bool:
    """현재 가격이 0.618~0.786 진입 구간 안에 있는지 확인."""
    lo = min(fib.level_618, fib.level_786)
    hi = max(fib.level_618, fib.level_786)
    return lo <= price <= hi
