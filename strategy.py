"""
EMA50/200 추세 추종 전략 v3 (4H + 15M) — 엘리트 트레이더 패널 합의 반영.

롱 진입 조건 (구조 게이트):
  1. 4H EMA50 > EMA200 (상승 추세) + 가격 > 4H EMA200
  2. 15M에서 EMA50 눌림 후 반등 양봉
  3. 직전 고점 돌파 시 진입
  SL: 눌림 저점 아래 (연속 손절 시 버퍼 확대, ATR 플로어 적용)

숏은 위의 거울상.

v3 품질 게이트 (모두 통과해야 진입):
  - 변동성 게이트: 15M ATR > 가격의 3% → 극단 변동성, 진입 금지
  - 거래량 플로어: 신호봉 거래량 < 0.8×SMA20 → 저유동성 반전 거부
  - 추격 금지: 진입가가 15M EMA50에서 2% 초과 이탈 → 스킵
  - SL ATR 플로어: SL 거리 ≥ 0.8×ATR (노이즈 안에 손절 두지 않기)
  - SL 버퍼 확대: 연속 손절 1회당 +0.05%p (상한 0.3%) — 휩쏘 방지

피하는 구간 (v2 유지):
  - 4H EMA50/200 간격 0.5% 미만 (횡보)
  - 가격이 두 EMA 사이에서 흔들림
  - 최근 3캔들 4% 초과 급등/급락 후 추격
  - SL이 5% 초과로 멀 때
"""
import logging
from dataclasses import dataclass
from typing import Optional

from config import Config
from indicators import (
    ema, atr, swing_high, swing_low,
    find_pullback_low, find_pullback_high,
)

log = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str       # "long" | "short"
    entry_price: float
    sl_price: float
    ob: object = None
    fib: object = None


def _sl_buffer(cfg: Config, consecutive_losses: int) -> float:
    """연속 손절 후 SL 버퍼 확대 — 손절 직후 시장은 타이트한 스탑을 자주 훑는다."""
    buf = cfg.sl_buffer_pct + cfg.per_loss_buffer_add_pct * max(consecutive_losses, 0)
    return min(buf, cfg.max_sl_buffer_pct)


def _volume_ok(candles_15m: list, cfg: Config) -> bool:
    """신호봉 거래량 ≥ vol_floor_ratio × SMA(vol_avg_len) — 저유동성 반전 거부."""
    window = candles_15m[-(cfg.vol_avg_len + 1):-1]
    if not window:
        return True
    avg = sum(c["volume"] for c in window) / len(window)
    if avg <= 0:
        return True   # 거래량 데이터 없으면 게이트 생략
    return candles_15m[-1]["volume"] >= cfg.vol_floor_ratio * avg


def analyze(candles_15m: list, cfg: Config,
            candles_4h: list = None,
            consecutive_losses: int = 0) -> Optional[Signal]:

    if len(candles_15m) < 210:
        log.debug("15M 캔들 부족 — 스킵")
        return None
    if not candles_4h or len(candles_4h) < 210:
        log.debug("4H 캔들 부족 — 스킵")
        return None

    # ── 4시간봉 EMA ──────────────────────────────────────────────
    closes_4h  = [c["close"] for c in candles_4h]
    ema50_4h   = ema(closes_4h, cfg.ema_fast)[-1]
    ema200_4h  = ema(closes_4h, cfg.ema_slow)[-1]

    # 필터: 4H EMA 간격 너무 좁으면 횡보 → 스킵
    gap_pct = abs(ema50_4h - ema200_4h) / ema200_4h
    if gap_pct < cfg.ema_gap_min_pct:
        log.debug("4H EMA 간격 %.2f%% — 횡보 스킵", gap_pct * 100)
        return None

    # ── 15분봉 EMA + ATR ────────────────────────────────────────
    closes_15m   = [c["close"] for c in candles_15m]
    ema50_series = ema(closes_15m, cfg.ema_fast)
    ema50_15m    = ema50_series[-1]
    close        = candles_15m[-1]["close"]
    curr         = candles_15m[-1]
    atr_val      = atr(candles_15m, cfg.atr_period)[-1]

    # 필터: 급등/급락 후 추격 금지
    if len(candles_15m) >= 4:
        recent_move = abs(close - candles_15m[-4]["close"]) / candles_15m[-4]["close"]
        if recent_move > cfg.max_momentum_pct:
            log.debug("급등/급락 %.2f%% — 추격 스킵", recent_move * 100)
            return None

    # v3 변동성 게이트: 극단 변동성 구간(뉴스 직후 등) 진입 금지
    if atr_val > cfg.atr_vol_gate_pct * close:
        log.debug("ATR %.2f%% > %.0f%% — 극단 변동성 스킵",
                  atr_val / close * 100, cfg.atr_vol_gate_pct * 100)
        return None

    htf_bullish = ema50_4h > ema200_4h
    buf = _sl_buffer(cfg, consecutive_losses)

    log.debug("4H EMA50=%.4f EMA200=%.4f(%s) | 15M EMA50=%.4f ATR=%.4f | 가격=%.4f",
              ema50_4h, ema200_4h, "상승" if htf_bullish else "하락",
              ema50_15m, atr_val, close)

    # ── 롱 조건 ──────────────────────────────────────────────────
    if htf_bullish and close > ema200_4h:
        # 가격이 4H 두 EMA 사이에서 흔들리면 스킵 (노이즈 구간)
        if ema200_4h < close < ema50_4h * 0.998:
            log.debug("가격이 4H EMA 사이 — 롱 스킵")
            return None

        pullback_low = find_pullback_low(
            candles_15m, ema50_series,
            lookback=cfg.pullback_lookback,
            tol=cfg.ema_pullback_tol,
        )
        if pullback_low is None:
            return None

        # 현재 캔들: 반등 양봉 + EMA50 위 마감
        if curr["close"] <= curr["open"] or curr["close"] <= ema50_15m:
            return None

        # v3 거래량 플로어
        if not _volume_ok(candles_15m, cfg):
            log.debug("신호봉 거래량 부족 — 롱 스킵")
            return None

        # v3 추격 금지: EMA50에서 너무 멀어진 진입 거부
        ext = (close - ema50_15m) / ema50_15m
        if ext > cfg.ema_extension_cap_pct:
            log.debug("EMA50 이탈 %.2f%% > %.1f%% — 추격 스킵",
                      ext * 100, cfg.ema_extension_cap_pct * 100)
            return None

        # 직전 고점 돌파
        s_high = swing_high(candles_15m, cfg.swing_lookback)
        if close <= s_high:
            return None

        # SL = 눌림 저점 아래 버퍼, 단 ATR 플로어 이상 (노이즈 안 손절 방지)
        struct_sl = pullback_low * (1 - buf)
        sl_dist   = max(close - struct_sl, cfg.atr_sl_floor_mult * atr_val)
        sl        = close - sl_dist
        sl_pct    = sl_dist / close
        if sl_pct > cfg.sl_max_pct:
            log.debug("롱 SL 거리 %.2f%% 너무 멀음 — 스킵", sl_pct * 100)
            return None

        log.info("🟢 롱 신호 @ %.4f | SL=%.4f (버퍼 %.2f%%, ATR플로어 %s) | 4H↑ EMA50눌림 반등 고점돌파",
                 close, sl, buf * 100,
                 "적용" if sl_dist > close - struct_sl + 1e-12 else "미적용")
        return Signal("long", close, sl)

    # ── 숏 조건 ──────────────────────────────────────────────────
    if not htf_bullish and close < ema200_4h:
        # 가격이 4H 두 EMA 사이에서 흔들리면 스킵
        if ema50_4h * 1.002 < close < ema200_4h:
            log.debug("가격이 4H EMA 사이 — 숏 스킵")
            return None

        pullback_high = find_pullback_high(
            candles_15m, ema50_series,
            lookback=cfg.pullback_lookback,
            tol=cfg.ema_pullback_tol,
        )
        if pullback_high is None:
            return None

        # 현재 캔들: 저항 음봉 + EMA50 아래 마감
        if curr["close"] >= curr["open"] or curr["close"] >= ema50_15m:
            return None

        # v3 거래량 플로어
        if not _volume_ok(candles_15m, cfg):
            log.debug("신호봉 거래량 부족 — 숏 스킵")
            return None

        # v3 추격 금지
        ext = (ema50_15m - close) / ema50_15m
        if ext > cfg.ema_extension_cap_pct:
            log.debug("EMA50 이탈 %.2f%% > %.1f%% — 추격 스킵",
                      ext * 100, cfg.ema_extension_cap_pct * 100)
            return None

        # 직전 저점 이탈
        s_low = swing_low(candles_15m, cfg.swing_lookback)
        if close >= s_low:
            return None

        # SL = 반등 고점 위 버퍼, ATR 플로어 이상
        struct_sl = pullback_high * (1 + buf)
        sl_dist   = max(struct_sl - close, cfg.atr_sl_floor_mult * atr_val)
        sl        = close + sl_dist
        sl_pct    = sl_dist / close
        if sl_pct > cfg.sl_max_pct:
            log.debug("숏 SL 거리 %.2f%% 너무 멀음 — 스킵", sl_pct * 100)
            return None

        log.info("🔴 숏 신호 @ %.4f | SL=%.4f (버퍼 %.2f%%, ATR플로어 %s) | 4H↓ EMA50반등 저항 저점이탈",
                 close, sl, buf * 100,
                 "적용" if sl_dist > struct_sl - close + 1e-12 else "미적용")
        return Signal("short", close, sl)

    return None


def current_direction(candles_15m: list, cfg: Config,
                      candles_4h: list = None) -> int:
    """
    현재 시장 방향 — 역신호 청산 감지용.
    +1=상승(롱 유리), -1=하락(숏 유리), 0=불명확

    v3: 휩쏘 방지를 위해 마지막 '2개 확정봉'이 모두 EMA50 반대편에서
    마감해야 방향 전환으로 인정 (1캔들 교차로 전량 청산하지 않음).
    """
    if len(candles_15m) < 55:
        return 0

    closes_15m   = [c["close"] for c in candles_15m]
    ema50_series = ema(closes_15m, cfg.ema_fast)

    above = (closes_15m[-1] > ema50_series[-1] and
             closes_15m[-2] > ema50_series[-2])
    below = (closes_15m[-1] < ema50_series[-1] and
             closes_15m[-2] < ema50_series[-2])
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
