"""
멀티 타임프레임 슈퍼트렌드 + EMA200 전략.

진입 조건 (3중 확인):
  1. 1시간봉 슈퍼트렌드 방향 확인 (큰 흐름)
  2. 15분봉 슈퍼트렌드가 같은 방향으로 전환 (진입 타이밍)
  3. 현재가가 EMA200 기준 올바른 방향 (추세 필터)

롱:  1H ST 상승 + 15M ST 하락→상승 전환 + 가격 > EMA200
숏:  1H ST 하락 + 15M ST 상승→하락 전환 + 가격 < EMA200
"""
import logging
from dataclasses import dataclass
from typing import Optional

from config import Config
from indicators import supertrend, ema200, SupertrendResult

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str
    entry_price: float
    sl_price: float
    ob: object = None
    fib: object = None


def _htf_direction(candles_1h: list, cfg: Config) -> int:
    """1시간봉 슈퍼트렌드 현재 방향. +1=상승, -1=하락."""
    cfg_copy = _cfg_with_htf(cfg)
    st = supertrend(candles_1h, cfg_copy)
    return st.direction[-1]


def _cfg_with_htf(cfg: Config):
    """1시간봉용 설정 (배수만 다르게)."""
    import copy
    c = copy.copy(cfg)
    c.st_multiplier = cfg.st_htf_multiplier
    return c


def analyze(candles_15m: list, cfg: Config,
            candles_1h: list = None) -> Optional[Signal]:

    if len(candles_15m) < cfg.ema_trend + 10:
        log.debug("15분봉 캔들 부족 — 스킵")
        return None

    # 1시간봉 방향
    htf_dir = 1  # 기본값 (1시간봉 없으면 필터 생략)
    if candles_1h and len(candles_1h) >= cfg.st_atr_period + 5:
        htf_dir = _htf_direction(candles_1h, cfg)
        log.debug("1H 슈퍼트렌드 방향: %s", "상승" if htf_dir == 1 else "하락")

    # 15분봉 슈퍼트렌드 + EMA200
    st    = supertrend(candles_15m, cfg)
    e200  = ema200(candles_15m, cfg)

    prev_dir   = st.direction[-2]
    curr_dir   = st.direction[-1]
    close      = candles_15m[-1]["close"]
    sl_line    = st.line[-1]
    ema200_val = e200[-1]

    log.debug(
        "15M ST: %d→%d | 1H ST: %d | 가격=%.2f | EMA200=%.2f",
        prev_dir, curr_dir, htf_dir, close, ema200_val
    )

    # 롱: 3중 확인
    if (htf_dir == 1 and          # 1시간봉 상승
            prev_dir == -1 and    # 15분봉 전환
            curr_dir == 1 and
            close > ema200_val):  # EMA200 위
        log.info("🟢 롱 신호 @ %.2f (1H↑ 15M↑전환 EMA200위)", close)
        return Signal("long", close, sl_line)

    # 숏: 3중 확인
    if (htf_dir == -1 and         # 1시간봉 하락
            prev_dir == 1 and     # 15분봉 전환
            curr_dir == -1 and
            close < ema200_val):  # EMA200 아래
        log.info("🔴 숏 신호 @ %.2f (1H↓ 15M↓전환 EMA200아래)", close)
        return Signal("short", close, sl_line)

    return None


def current_direction(candles_15m: list, cfg: Config,
                      candles_1h: list = None) -> int:
    """
    현재 시장 방향 반환 — 크로스오버 불필요.
    두 타임프레임이 일치할 때만 방향 반환, 불일치 시 0.

    +1 = 상승(롱 유리), -1 = 하락(숏 유리), 0 = 불명확
    역신호 청산 감지에 사용.
    """
    if len(candles_15m) < cfg.st_atr_period + 5:
        return 0

    st_15m  = supertrend(candles_15m, cfg)
    ltf_dir = st_15m.direction[-1]

    if candles_1h and len(candles_1h) >= cfg.st_atr_period + 5:
        cfg_htf = _cfg_with_htf(cfg)
        st_1h   = supertrend(candles_1h, cfg_htf)
        htf_dir = st_1h.direction[-1]
        if htf_dir != ltf_dir:
            return 0   # 두 TF 불일치 → 판단 보류
        return ltf_dir

    return ltf_dir
