"""
BB 스퀴즈 + 거래량 돌파 전략 (4H 추세 필터 + 15M 진입).

진입 조건 (롱):
  1. 4H EMA50 > EMA200 (상승 추세)
  2. 15M 볼린저밴드가 squeeze_min_bars 봉 이상 수축 (스퀴즈)
  3. 현재 확정봉 종가 > 상단BB (돌파)
  4. 현재봉 거래량 ≥ 20봉 평균 × vol_mult
  5. RSI > 50 (상승 모멘텀)
  SL: 하단BB 아래 (ATR 플로어 적용)

진입 조건 (숏):
  1. 4H EMA50 < EMA200 (하락 추세)
  2~4. BB 스퀴즈 후 하단BB 붕괴 + 거래량 확인
  5. RSI < 50
  SL: 상단BB 위 (ATR 플로어 적용)

공통 필터 (v3 유지):
  - 극단 변동성 차단: 15M ATR > 가격 × atr_vol_gate_pct
  - 연속 손절 후 SL 버퍼 점진 확대
"""
import logging
from dataclasses import dataclass
from typing import Optional

from config import Config
from indicators import ema, atr, rsi, adx, bollinger_bands

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str       # "long" | "short"
    entry_price: float
    sl_price: float
    ob: object = None
    fib: object = None


def _sl_buffer(cfg: Config, consecutive_losses: int) -> float:
    """연속 손절 후 SL 버퍼 확대 — 휩쏘 방지."""
    buf = cfg.sl_buffer_pct + cfg.per_loss_buffer_add_pct * max(consecutive_losses, 0)
    return min(buf, cfg.max_sl_buffer_pct)


def analyze(candles_15m: list, cfg: Config,
            candles_4h: list = None,
            consecutive_losses: int = 0) -> Optional[Signal]:

    if len(candles_15m) < 100:
        log.debug("4H 캔들 부족 — 스킵")
        return None
    if not candles_4h or len(candles_4h) < 100:
        log.debug("Daily 캔들 부족 — 스킵")
        return None

    # ── 일봉 추세 필터 ────────────────────────────────────────────
    closes_4h = [c["close"] for c in candles_4h]
    ema50_4h  = ema(closes_4h, cfg.ema_fast)[-1]
    ema200_4h = ema(closes_4h, cfg.ema_slow)[-1]
    adx_4h    = adx(candles_4h, cfg.adx_period)[-1]
    price_4h  = candles_4h[-1]["close"]

    # ADX 추세 강도 확인 — 횡보장 진입 차단
    if adx_4h < cfg.adx_threshold:
        log.debug("Daily ADX=%.1f < %.0f — 추세 없음, 스킵", adx_4h, cfg.adx_threshold)
        return None

    htf_bull = ema50_4h > ema200_4h

    # ── 15분봉 지표 계산 ──────────────────────────────────────────
    closes_15m  = [c["close"] for c in candles_15m]
    volumes_15m = [c["volume"] for c in candles_15m]

    upper_bb, mid_bb, lower_bb, bb_width = bollinger_bands(
        closes_15m, cfg.bb_period, cfg.bb_std
    )
    rsi_vals = rsi(closes_15m, cfg.rsi_period)
    atr_val  = atr(candles_15m, cfg.atr_period)[-1]

    close      = candles_15m[-1]["close"]
    curr_vol   = candles_15m[-1]["volume"]
    curr_rsi   = rsi_vals[-1]
    curr_upper = upper_bb[-1]
    curr_lower = lower_bb[-1]

    # ── v3 극단 변동성 차단 ───────────────────────────────────────
    if atr_val > cfg.atr_vol_gate_pct * close:
        log.debug("ATR %.2f%% > %.0f%% — 극단 변동성 스킵",
                  atr_val / close * 100, cfg.atr_vol_gate_pct * 100)
        return None

    # ── BB 스퀴즈 감지 ────────────────────────────────────────────
    # 최근 40봉의 유효 BB폭 평균
    valid_widths = [w for w in bb_width[-40:] if w > 0]
    if len(valid_widths) < 20:
        log.debug("BB 계산 데이터 부족 — 스킵")
        return None
    avg_width = sum(valid_widths) / len(valid_widths)

    # 직전 squeeze_min_bars 캔들이 모두 스퀴즈였는가 (현재 확정봉 제외)
    pre_widths = [w for w in bb_width[-(cfg.squeeze_min_bars + 1):-1] if w > 0]
    was_squeezed = (
        len(pre_widths) >= cfg.squeeze_min_bars
        and all(w < avg_width * cfg.squeeze_pct for w in pre_widths)
    )
    if not was_squeezed:
        log.debug("BB 스퀴즈 미감지 (임계=avg×%.1f) — 스킵", cfg.squeeze_pct)
        return None

    # ── 거래량 확인 ───────────────────────────────────────────────
    vol_window = volumes_15m[-(cfg.vol_avg_len + 1):-1]
    vol_avg = sum(vol_window) / len(vol_window) if vol_window else 0
    if vol_avg <= 0 or curr_vol < vol_avg * cfg.vol_mult:
        log.debug("거래량 부족 (현재 %.1fx, 필요 %.1fx) — 스킵",
                  curr_vol / vol_avg if vol_avg > 0 else 0, cfg.vol_mult)
        return None

    vol_ratio = curr_vol / vol_avg
    buf = _sl_buffer(cfg, consecutive_losses)

    # ATR 기반 손절 거리 (연속 손절 시 버퍼 소폭 확대)
    sl_dist = atr_val * cfg.atr_sl_mult * (1 + buf)

    # ── 롱: 상단BB 돌파 ───────────────────────────────────────────
    # 가격이 4H EMA50 위에 있어야 추세와 동행
    if htf_bull and price_4h > ema50_4h and close > curr_upper and curr_rsi > 50:
        sl     = close - sl_dist
        sl_pct = sl_dist / close
        if sl_pct > cfg.sl_max_pct:
            log.debug("롱 ATR SL %.2f%% > %.0f%% — 스킵", sl_pct * 100, cfg.sl_max_pct * 100)
            return None
        log.info(
            "🟢 롱 BB돌파 @ %.4f | SL=%.4f(ATR×%.1f=%.2f%%) | RSI=%.1f | Vol=%.1fx | ADX=%.1f | 4H↑",
            close, sl, cfg.atr_sl_mult, sl_pct * 100, curr_rsi, vol_ratio, adx_4h,
        )
        return Signal("long", close, sl)

    # ── 숏: 하단BB 붕괴 ───────────────────────────────────────────
    # 가격이 4H EMA50 아래에 있어야 추세와 동행
    if not htf_bull and price_4h < ema50_4h and close < curr_lower and curr_rsi < 50:
        sl     = close + sl_dist
        sl_pct = sl_dist / close
        if sl_pct > cfg.sl_max_pct:
            log.debug("숏 ATR SL %.2f%% > %.0f%% — 스킵", sl_pct * 100, cfg.sl_max_pct * 100)
            return None
        log.info(
            "🔴 숏 BB붕괴 @ %.4f | SL=%.4f(ATR×%.1f=%.2f%%) | RSI=%.1f | Vol=%.1fx | ADX=%.1f | 4H↓",
            close, sl, cfg.atr_sl_mult, sl_pct * 100, curr_rsi, vol_ratio, adx_4h,
        )
        return Signal("short", close, sl)

    return None


def current_direction(candles_15m: list, cfg: Config,
                      candles_4h: list = None) -> int:
    """
    현재 시장 방향 — 역신호 청산 감지용.
    +1=상승, -1=하락, 0=불명확

    2봉 연속 BB 중심선 반대편 마감이어야 방향 전환으로 인정 (휩쏘 방지).
    """
    if len(candles_15m) < 55:
        return 0

    closes_15m = [c["close"] for c in candles_15m]
    _, mid_bb, _, _ = bollinger_bands(closes_15m, cfg.bb_period, cfg.bb_std)

    above = (closes_15m[-1] > mid_bb[-1] and closes_15m[-2] > mid_bb[-2])
    below = (closes_15m[-1] < mid_bb[-1] and closes_15m[-2] < mid_bb[-2])
    ltf_dir = 1 if above else (-1 if below else 0)
    if ltf_dir == 0:
        return 0

    if candles_4h and len(candles_4h) >= 210:
        closes_4h = [c["close"] for c in candles_4h]
        ema50_4h  = ema(closes_4h, cfg.ema_fast)[-1]
        ema200_4h = ema(closes_4h, cfg.ema_slow)[-1]
        htf_dir   = 1 if ema50_4h > ema200_4h else -1
        if htf_dir != ltf_dir:
            return 0
        return ltf_dir

    return ltf_dir
