"""포지션 사이징 + SL/TP 계산."""
import logging
import math
from dataclasses import dataclass
from config import Config
from strategy import Signal

log = logging.getLogger(__name__)


@dataclass
class TradeParams:
    side: str          # 'Buy' | 'Sell'
    qty: float         # 주문 수량 (코인 단위)
    sl_price: float
    tp_price: float
    risk_usd: float    # 실제 위험 금액


def calc_trade(
    signal: Signal,
    balance: float,
    cfg: Config,
    min_qty: float,
    qty_step: float,
) -> TradeParams | None:
    """
    신호와 잔고를 받아 주문 파라미터 계산.
    최소 수량 미달 시 None 반환.
    """
    entry = signal.entry_price
    risk_usd = balance * cfg.risk_pct

    if signal.direction == "long":
        # SL: 오더블록 저점 - 버퍼
        sl = signal.ob.low * (1 - cfg.sl_buffer_pct)
        sl_dist = entry - sl
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 롱 신호 무시")
            return None
        tp = entry + sl_dist * cfg.rr_ratio
        side = "Buy"
    else:
        # SL: 오더블록 고점 + 버퍼
        sl = signal.ob.high * (1 + cfg.sl_buffer_pct)
        sl_dist = sl - entry
        if sl_dist <= 0:
            log.warning("SL 거리가 0 이하 — 숏 신호 무시")
            return None
        tp = entry - sl_dist * cfg.rr_ratio
        side = "Sell"

    # 포지션 사이징: 리스크 금액 / SL 거리 = 코인 수량
    raw_qty = risk_usd / sl_dist

    # 레버리지로 살 수 있는 최대 수량
    max_qty = (balance * cfg.leverage) / entry
    qty = min(raw_qty, max_qty)

    # 스텝 단위로 내림
    qty = _floor_to_step(qty, qty_step)

    if qty < min_qty:
        log.warning(
            "계산 수량 %.6f이 최소 수량 %.6f 미만 — 잔고 부족 또는 SL 너무 가까움",
            qty, min_qty,
        )
        return None

    log.info(
        "거래 파라미터 — %s qty=%.4f entry=%.2f SL=%.2f TP=%.2f 리스크=$%.2f",
        side, qty, entry, sl, tp, qty * sl_dist,
    )
    return TradeParams(side=side, qty=qty, sl_price=sl, tp_price=tp, risk_usd=qty * sl_dist)


def _floor_to_step(value: float, step: float) -> float:
    """step 단위 미만 버림."""
    if step <= 0:
        return value
    precision = max(0, -int(math.floor(math.log10(step))))
    return round(math.floor(value / step) * step, precision)
