"""포지션 사이징 + SL/TP 계산 (3분할 TP)."""
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
    qty3: float        # TP3 수량 (나머지)
    sl_price: float
    tp1_price: float   # 1:1
    tp2_price: float   # 1:2
    tp3_price: float   # 1:3
    entry_price: float
    risk_usd: float


def calc_trade(
    signal: Signal,
    balance: float,
    cfg: Config,
    min_qty: float,
    qty_step: float,
) -> "TradeParams | None":
    entry = signal.entry_price
    risk_usd = balance * cfg.risk_pct

    if signal.direction == "long":
        sl = signal.sl_price * (1 - cfg.sl_buffer_pct)
        sl_dist = entry - sl
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 롱 신호 무시")
            return None
        tp1 = entry + sl_dist * 1.0
        tp2 = entry + sl_dist * 2.0
        tp3 = entry + sl_dist * 3.0
        side = "Buy"
    else:
        sl = signal.sl_price * (1 + cfg.sl_buffer_pct)
        sl_dist = sl - entry
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 숏 신호 무시")
            return None
        tp1 = entry - sl_dist * 1.0
        tp2 = entry - sl_dist * 2.0
        tp3 = entry - sl_dist * 3.0
        side = "Sell"

    # 포지션 사이징
    raw_qty = risk_usd / sl_dist
    max_qty = (balance * cfg.leverage) / entry
    qty = min(raw_qty, max_qty)
    qty = _floor_to_step(qty, qty_step)

    if qty < min_qty:
        log.warning("계산 수량 %.6f이 최소 수량 %.6f 미만 — 잔고 부족", qty, min_qty)
        return None

    # 수량 3등분
    qty1 = _floor_to_step(qty / 3, qty_step)
    qty2 = _floor_to_step(qty / 3, qty_step)
    qty3 = _floor_to_step(qty - qty1 - qty2, qty_step)

    # qty3가 최소 수량 미달이면 qty2에 합산
    if qty3 < min_qty:
        qty2 = _floor_to_step(qty2 + qty3, qty_step)
        qty3 = 0.0

    log.info(
        "거래 파라미터 — %s 총qty=%.4f (%.4f/%.4f/%.4f) "
        "SL=%.4f TP1=%.4f TP2=%.4f TP3=%.4f 리스크=$%.2f",
        side, qty, qty1, qty2, qty3, sl, tp1, tp2, tp3, qty * sl_dist,
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
