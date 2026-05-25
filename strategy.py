"""
슈퍼트렌드 + EMA200 전략.

롱 진입:
  - 슈퍼트렌드가 하락(-1) → 상승(+1)으로 전환
  - 현재가 > EMA200 (큰 추세 상승)

숏 진입:
  - 슈퍼트렌드가 상승(+1) → 하락(-1)으로 전환
  - 현재가 < EMA200 (큰 추세 하락)

SL: 슈퍼트렌드 라인 (자동 추적)
TP: SL 거리 × RR 비율
"""
import logging
from dataclasses import dataclass
from typing import Optional

from config import Config
from indicators import supertrend, ema200, ema

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str        # 'long' | 'short'
    entry_price: float
    sl_price: float       # 슈퍼트렌드 라인
    # order_blocks.py 호환용 더미 필드
    ob: object = None
    fib: object = None


def analyze(candles: list, cfg: Config) -> Optional[Signal]:
    if len(candles) < cfg.ema_trend + 10:
        log.debug("캔들 부족 — 분석 스킵")
        return None

    st = supertrend(candles, cfg)
    e200 = ema200(candles, cfg)

    prev_dir = st.direction[-2]
    curr_dir = st.direction[-1]
    close    = candles[-1]["close"]
    sl_line  = st.line[-1]
    ema200_val = e200[-1]

    log.debug("ST방향: %d→%d  가격=%.2f  EMA200=%.2f  ST선=%.2f",
              prev_dir, curr_dir, close, ema200_val, sl_line)

    # 롱: 슈퍼트렌드 상승 전환 + 가격이 EMA200 위
    if prev_dir == -1 and curr_dir == 1 and close > ema200_val:
        log.info("롱 신호 @ %.2f  ST=%.2f  EMA200=%.2f", close, sl_line, ema200_val)
        return Signal("long", close, sl_line)

    # 숏: 슈퍼트렌드 하락 전환 + 가격이 EMA200 아래
    if prev_dir == 1 and curr_dir == -1 and close < ema200_val:
        log.info("숏 신호 @ %.2f  ST=%.2f  EMA200=%.2f", close, sl_line, ema200_val)
        return Signal("short", close, sl_line)

    return None
