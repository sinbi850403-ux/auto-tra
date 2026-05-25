"""오더블록 감지 — 순수 Python."""
from dataclasses import dataclass
from typing import Optional, List
from config import Config


@dataclass
class OrderBlock:
    ob_type: str
    high: float
    low: float
    index: int


def _body_ratio(c: dict) -> float:
    rng = c["high"] - c["low"]
    return abs(c["close"] - c["open"]) / rng if rng else 0


def _momentum(candles: list, start: int, n: int = 3) -> float:
    if start + n >= len(candles):
        return 0
    return abs(candles[start + n - 1]["close"] - candles[start]["open"])


def _atr(candles: list) -> float:
    return sum(c["high"] - c["low"] for c in candles) / len(candles)


def find_bullish_ob(candles: list, cfg: Config) -> Optional[OrderBlock]:
    window = candles[-cfg.ob_lookback:]
    price  = window[-1]["close"]
    avg_atr = _atr(window)

    for i in range(len(window) - 4, 0, -1):
        c = window[i]
        if c["close"] >= c["open"]:          # 음봉이어야 함
            continue
        if _body_ratio(c) < cfg.ob_body_ratio:
            continue
        if _momentum(window, i + 1) < avg_atr * 0.5:
            continue
        if price > c["high"]:                # 이미 돌파한 구간
            return OrderBlock("bull", c["high"], c["low"], i)
    return None


def find_bearish_ob(candles: list, cfg: Config) -> Optional[OrderBlock]:
    window = candles[-cfg.ob_lookback:]
    price  = window[-1]["close"]
    avg_atr = _atr(window)

    for i in range(len(window) - 4, 0, -1):
        c = window[i]
        if c["close"] <= c["open"]:          # 양봉이어야 함
            continue
        if _body_ratio(c) < cfg.ob_body_ratio:
            continue
        if _momentum(window, i + 1) < avg_atr * 0.5:
            continue
        if price < c["low"]:
            return OrderBlock("bear", c["high"], c["low"], i)
    return None


def price_in_ob(price: float, ob: OrderBlock) -> bool:
    return ob.low <= price <= ob.high
