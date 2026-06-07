"""주문 실행 — 진입 + 3분할 TP 지정가 주문 배치."""
import logging
from client import BybitClient
from strategy import Signal
from risk import TradeParams, calc_trade
from config import Config

log = logging.getLogger(__name__)


class Trader:
    def __init__(self, client: BybitClient, cfg: Config):
        self.client = client
        self.cfg = cfg
        # 심볼별 instrument info 캐시
        self._instrument_cache: dict = {}

    def _get_instrument_info(self, symbol: str):
        if symbol not in self._instrument_cache:
            min_qty  = self.client.get_min_qty(symbol)
            qty_step = self.client.get_qty_step(symbol)
            self._instrument_cache[symbol] = (min_qty, qty_step)
        return self._instrument_cache[symbol]

    def run_cycle(self, signal: Signal = None, balance: float = 0.0,
                  symbol: str = None) -> "TradeParams | None":
        """
        포지션 확인 → 진입 주문 → TP1/TP2/TP3 지정가 배치.
        성공 시 TradeParams 반환, 실패/스킵 시 None.
        """
        sym = symbol or self.cfg.symbol

        pos = self.client.get_position(sym)
        if pos:
            log.info("기존 포지션 유지 중 — %s side=%s size=%s", sym, pos["side"], pos["size"])
            return None

        if signal is None:
            log.info("진입 신호 없음 — 대기")
            return None

        if balance < 5:
            log.warning("잔고 $%.2f — 최소 $5 미만, 거래 중단", balance)
            return None

        min_qty, qty_step = self._get_instrument_info(sym)
        params: TradeParams | None = calc_trade(
            signal, balance, self.cfg, min_qty, qty_step
        )
        if params is None:
            return None

        # 1. 시장가 진입 (SL 포함). 실패하면 포지션이 없으므로 None 반환.
        try:
            resp = self.client.place_order(
                side=params.side,
                qty=params.qty,
                sl_price=params.sl_price,
                symbol=sym,
            )
            order_id = resp["result"].get("orderId", "?")
            log.info("진입 완료 orderId=%s (%s)", order_id, sym)
        except Exception as e:
            log.error("진입 주문 실패 (%s): %s", sym, e)
            return None

        # 여기 도달 = 포지션이 SL과 함께 열렸다. 이후 단계가 실패하더라도
        # params를 반환해 상위(main)가 entry_info를 저장하고 포지션을 계속
        # 관리하게 한다. (감사 높음: TP 배치 실패 시 포지션 방치 방지)

        # 2. TP1 / TP2 지정가 배치 (TP3는 EMA50 트레일링). 실패해도 포지션 유지.
        close_side = "Sell" if params.side == "Buy" else "Buy"
        try:
            if params.qty1 > 0:
                self.client.place_reduce_only_limit(
                    close_side, params.qty1, params.tp1_price, symbol=sym)
            if params.qty2 > 0:
                self.client.place_reduce_only_limit(
                    close_side, params.qty2, params.tp2_price, symbol=sym)
        except Exception as e:
            log.error("TP 주문 배치 실패 (%s) — 포지션은 SL과 함께 유지, 재시작 시 TP 복구: %s",
                      sym, e)

        # 3. 진입 알림 (실패 무시)
        try:
            from notify import alert_entry
            direction = "롱" if params.side == "Buy" else "숏"
            alert_entry(direction, signal.entry_price,
                        params.sl_price,
                        params.tp1_price, params.tp2_price, params.tp3_price,
                        params.qty, balance, symbol=sym)
        except Exception as e:
            log.warning("진입 알림 실패 (%s): %s", sym, e)

        return params  # main.py에서 entry_info 저장용
