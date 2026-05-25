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
        self._min_qty: float | None = None
        self._qty_step: float | None = None

    def _get_instrument_info(self):
        if self._min_qty is None:
            self._min_qty = self.client.get_min_qty()
            self._qty_step = self.client.get_qty_step()

    def run_cycle(self, signal=None, balance=0.0):
        """1 사이클: 포지션 확인 → 주문. signal이 주어지면 분석 생략."""
        from strategy import analyze

        pos = self.client.get_position()
        if pos:
            log.info("기존 포지션 유지 중 — side=%s size=%s", pos["side"], pos["size"])
            return

        if signal is None:
            df = self.client.get_klines()
            signal: Signal | None = analyze(df, self.cfg)

        if signal is None:
            log.info("진입 신호 없음 — 대기")
            return

        balance = self.client.get_balance()
        if balance < 5:
            log.warning("잔고 $%.2f — 최소 $5 미만, 거래 중단", balance)
            return

        self._get_instrument_info()
        params: TradeParams | None = calc_trade(
            signal, balance, self.cfg, self._min_qty, self._qty_step
        )
        if params is None:
            return

        try:
            resp = self.client.place_order(
                side=params.side,
                qty=params.qty,
                sl_price=params.sl_price,
                tp_price=params.tp_price,
            )
            order_id = resp["result"].get("orderId", "?")
            log.info("주문 완료 orderId=%s", order_id)
            from notify import alert_entry
            direction = "롱" if params.side == "Buy" else "숏"
            alert_entry(direction, signal.entry_price, params.sl_price,
                        params.tp_price, params.qty, balance)
        except Exception as e:
            log.error("주문 실패: %s", e)
