"""신호 생성 — EMA + 오더블록 + 피보나치 3중 확인."""
import logging
from dataclasses import dataclass
from typing import Optional

from config import Config
from indicators import add_emas, trend, calc_fib, price_in_fib_zone, FibLevels
from order_blocks import find_bullish_ob, find_bearish_ob, price_in_ob, OrderBlock

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str
    entry_price: float
    ob: OrderBlock
    fib: FibLevels


def analyze(candles: list, cfg: Config) -> Optional[Signal]:
    candles = add_emas(candles, cfg)
    t = trend(candles)
    price = candles[-1]["close"]

    if t == "bull":
        ob = find_bullish_ob(candles, cfg)
        if not ob:
            return None
        fib = calc_fib(candles, cfg, "bull")
        if not fib:
            return None
        if price_in_ob(price, ob) and price_in_fib_zone(price, fib):
            log.info("롱 신호 @ %.2f", price)
            return Signal("long", price, ob, fib)

    elif t == "bear":
        ob = find_bearish_ob(candles, cfg)
        if not ob:
            return None
        fib = calc_fib(candles, cfg, "bear")
        if not fib:
            return None
        if price_in_ob(price, ob) and price_in_fib_zone(price, fib):
            log.info("숏 신호 @ %.2f", price)
            return Signal("short", price, ob, fib)

    return None
