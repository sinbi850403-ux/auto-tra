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
    consecutive_losses: int = 0,
) -> "TradeParams | None":
    entry = signal.entry_price

    # 드로다운 축소 사이징 — "최악일 때 가장 작게 베팅" (Paul Tudor Jones).
    # 연속 손절마다 리스크 절반, 바닥은 기본 리스크의 25%. 수익 청산 시 원복.
    # 단, 소액 계좌에선 축소된 수량이 최소 주문수량 미달 → 거래 불능이 되므로
    # 기본 OFF (설계 패널 만장일치). 잔고가 커지면 RISK_SCALE_ENABLED=true 권장.
    scale = 1.0
    if getattr(cfg, "risk_scale_enabled", False):
        scale = max(cfg.risk_scale_after_loss ** max(consecutive_losses, 0),
                    cfg.risk_scale_floor)
        if scale < 1.0:
            log.info("드로다운 사이징 — 연속손절 %d회 → 리스크 %.2f%% (기본의 %.0f%%)",
                     consecutive_losses, cfg.risk_pct * scale * 100, scale * 100)
    risk_usd = balance * cfg.risk_pct * scale

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

    # 수수료 방어 — 명목가치가 너무 작으면 왕복 수수료(0.11%)가 엣지를 잠식
    min_notional = getattr(cfg, "min_notional_usd", 0.0)
    if min_notional > 0 and qty * entry < min_notional:
        log.warning("명목가치 $%.2f < 최소 $%.2f — 수수료 잠식 방지로 진입 거부",
                    qty * entry, min_notional)
        return None

    # 수량 3등분 (1/3 TP1, 1/3 TP2, 나머지 트레일링)
    qty1 = _floor_to_step(qty / 3, qty_step)
    qty2 = _floor_to_step(qty / 3, qty_step)
    # 나머지는 '반올림'으로 스텝에 맞춤 — floor를 쓰면 부동소수점 오차로
    # 한 스텝이 유실되어 합계가 총수량과 어긋난다 (먼지 수량 발생)
    qty3 = _floor_to_step(qty - qty1 - qty2 + qty_step / 2, qty_step)

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


# ------------------------------------------------------------------ #
# 순수 게이트 함수 (main.py에서 호출, 단위 테스트 가능)
# ------------------------------------------------------------------ #

def funding_blocks(direction: str, funding_rate: float, threshold: float) -> bool:
    """진입 방향에 불리한 펀딩비면 True (진입 차단).

    펀딩비 양수 = 롱이 숏에게 지불. 멀티 시간 보유 시 R의 상당 부분을
    펀딩비로 잠식당하므로, 불리한 쪽이 한도를 넘으면 진입하지 않는다.
    """
    if direction == "long":
        return funding_rate > threshold
    return funding_rate < -threshold


def time_stop_hit(entry_ts: float, now_ts: float, tp_count: int,
                  entry_price: float, mark_price: float, side: str,
                  cfg) -> bool:
    """시간손절 발동 여부 — "제대로 안 가는 트레이드는 잘라라".

    TP1도 못 간 채 time_stop_hours 경과 + 가격이 진입가 대비
    time_stop_pnl_pct(-0.5%) 이하로 밀려 있으면 True.
    """
    if tp_count != 0 or entry_ts <= 0 or entry_price <= 0:
        return False
    hours = getattr(cfg, "time_stop_hours", 0.0)
    if hours <= 0 or (now_ts - entry_ts) < hours * 3600:
        return False
    move = (mark_price - entry_price) / entry_price
    if side == "Sell":
        move = -move
    return move <= cfg.time_stop_pnl_pct
