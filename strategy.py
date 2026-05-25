"""
신호 생성 — EMA + 오더블록 + 피보나치 3중 확인.

롱 진입 조건:
  1. EMA20 > EMA50 (상승 트렌드)
  2. 현재가가 불리시 오더블록 안에 있음
  3. 현재가가 피보나치 0.618~0.786 되돌림 구간 안에 있음

숏 진입 조건:
  1. EMA20 < EMA50 (하락 트렌드)
  2. 현재가가 베어리시 오더블록 안에 있음
  3. 현재가가 피보나치 0.618~0.786 되돌림 구간 안에 있음
"""
import logging
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from config import Config
from indicators import add_emas, trend, calc_fib, price_in_fib_zone
from order_blocks import find_bullish_ob, find_bearish_ob, price_in_ob, OrderBlock
from indicators import FibLevels

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str        # 'long' | 'short'
    entry_price: float
    ob: OrderBlock
    fib: FibLevels


def analyze(df: pd.DataFrame, cfg: Config) -> Optional[Signal]:
    """
    캔들 데이터를 분석해서 진입 신호 반환.
    신호 없으면 None.
    """
    df = add_emas(df, cfg)
    t = trend(df)
    current_price = df["close"].iloc[-1]

    if t == "bull":
        ob = find_bullish_ob(df, cfg)
        if ob is None:
            log.debug("불리시 OB 없음")
            return None

        fib = calc_fib(df, cfg, "bull")
        if fib is None:
            return None

        in_ob = price_in_ob(current_price, ob)
        in_fib = price_in_fib_zone(current_price, fib)

        log.debug(
            "롱 체크 — 가격=%.2f OB=[%.2f~%.2f] in_ob=%s Fib=[%.2f~%.2f] in_fib=%s",
            current_price, ob.low, ob.high, in_ob,
            min(fib.level_618, fib.level_786), max(fib.level_618, fib.level_786), in_fib,
        )

        if in_ob and in_fib:
            log.info("롱 신호 발생 @ %.2f", current_price)
            return Signal("long", current_price, ob, fib)

    elif t == "bear":
        ob = find_bearish_ob(df, cfg)
        if ob is None:
            log.debug("베어리시 OB 없음")
            return None

        fib = calc_fib(df, cfg, "bear")
        if fib is None:
            return None

        in_ob = price_in_ob(current_price, ob)
        in_fib = price_in_fib_zone(current_price, fib)

        log.debug(
            "숏 체크 — 가격=%.2f OB=[%.2f~%.2f] in_ob=%s Fib=[%.2f~%.2f] in_fib=%s",
            current_price, ob.low, ob.high, in_ob,
            min(fib.level_618, fib.level_786), max(fib.level_618, fib.level_786), in_fib,
        )

        if in_ob and in_fib:
            log.info("숏 신호 발생 @ %.2f", current_price)
            return Signal("short", current_price, ob, fib)

    else:
        log.debug("트렌드 없음 (neutral) — 대기")

    return None
