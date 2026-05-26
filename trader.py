"""주문 실행 — 신호와 TradeParams를 받아 실제 API 호출."""
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

    def run_cycle(self, signal: Signal = None, balance: float = 0.0, symbol: str = None):
        """1 사이클: 포지션 확인 → 주문."""
        sym = symbol or self.cfg.symbol

        pos = self.client.get_position(sym)
        if pos:
            log.info("기존 포지션 유지 중 — %s side=%s size=%s", sym, pos["side"], pos["size"])
            return

        if signal is None:
            log.info("진입 신호 없음 — 대기")
            return

        if balance < 5:
            log.warning("잔고 $%.2f — 최소 $5 미만, 거래 중단", balance)
            return

        min_qty, qty_step = self._get_instrument_info(sym)
        params: TradeParams | None = calc_trade(
            signal, balance, self.cfg, min_qty, qty_step
        )
        if params is None:
            return

        try:
            resp = self.client.place_order(
                side=params.side,
                qty=params.qty,
                sl_price=params.sl_price,
                tp_price=params.tp_price,
                symbol=sym,
            )
            order_id = resp["result"].get("orderId", "?")
            log.info("주문 완료 orderId=%s (%s)", order_id, sym)
            from notify import alert_entry
            direction = "롱" if params.side == "Buy" else "숏"
            alert_entry(direction, signal.entry_price, params.sl_price,
                        params.tp_price, params.qty, balance, symbol=sym)
        except Exception as e:
            log.error("주문 실패 (%s): %s", sym, e)
