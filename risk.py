"""포지션 사이징 + SL/TP 계산 (2분할 지정가 + 트레일링)."""
import logging
import math
from dataclasses import dataclass
from config import Config
from strategy import Signal

log = logging.getLogger(__name__)


@dataclass
class TradeParams:
    side: str
    qty: float         # 총 수량
    qty1: float        # TP1 수량 (≈1/3)
    qty2: float        # TP2 수량 (≈1/3)
    qty3: float        # 나머지 (EMA50 트레일링 청산)
    sl_price: float
    tp1_price: float   # 손절폭 × 1배
    tp2_price: float   # 손절폭 × 2배
    tp3_price: float   # 미사용 (트레일링으로 관리)
    entry_price: float
    risk_usd: float


def calc_trade(
    signal: Signal,
    balance: float,
    cfg: Config,
    min_qty: float,
    qty_step: float,
) -> "TradeParams | None":
    entry    = signal.entry_price
    risk_usd = balance * cfg.risk_pct

    # SL은 strategy에서 이미 계산된 값 사용 (sl_buffer_pct는 strategy에서 적용됨)
    if signal.direction == "long":
        sl      = signal.sl_price
        sl_dist = entry - sl
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 롱 신호 무시")
            return None
        tp1  = entry + sl_dist * cfg.tp1_r
        tp2  = entry + sl_dist * cfg.tp2_r
        tp3  = tp2   # 트레일링 — 실제 미사용
        side = "Buy"
    else:
        sl      = signal.sl_price
        sl_dist = sl - entry
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 숏 신호 무시")
            return None
        tp1  = entry - sl_dist * cfg.tp1_r
        tp2  = entry - sl_dist * cfg.tp2_r
        tp3  = tp2   # 트레일링 — 실제 미사용
        side = "Sell"

    # 포지션 사이징
    raw_qty = risk_usd / sl_dist
    max_qty = (balance * cfg.leverage) / entry
    qty     = min(raw_qty, max_qty)
    qty     = _floor_to_step(qty, qty_step)

    if qty < min_qty:
        log.warning("계산 수량 %.6f이 최소 수량 %.6f 미만 — 잔고 부족", qty, min_qty)
        return None

    # 수량 3등분 (1/3 TP1, 1/3 TP2, 나머지 트레일링)
    qty1 = _floor_to_step(qty / 3, qty_step)
    qty2 = _floor_to_step(qty / 3, qty_step)
    qty3 = _floor_to_step(qty - qty1 - qty2, qty_step)

    if qty3 < min_qty:
        qty2 = _floor_to_step(qty2 + qty3, qty_step)
        qty3 = 0.0

    log.info(
        "거래 파라미터 — %s 총qty=%.4f (%.4f/%.4f/%.4f) "
        "SL=%.4f TP1=%.4f(%.1fR) TP2=%.4f(%.1fR) 나머지=트레일링 리스크=$%.2f",
        side, qty, qty1, qty2, qty3,
        sl, tp1, cfg.tp1_r, tp2, cfg.tp2_r,
        qty * sl_dist,
    )

    return TradeParams(
        side=side, qty=qty,
        qty1=qty1, qty2=qty2, qty3=qty3,
        sl_price=sl,
        tp1_price=tp1, tp2_price=tp2, tp3_price=tp3,
        entry_price=entry,
        risk_usd=qty * sl_dist,
    )


def _floor_to_step(value: float, step: float) -> float:
    """step 단위 미만 버림."""
    if step <= 0:
        return value
    precision = max(0, -int(math.floor(math.log10(step))))
    return round(math.floor(value / step) * step, precision)
