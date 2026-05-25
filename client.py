"""Bybit V5 API 래퍼 — 봇에 필요한 기능만 노출."""
import logging
from typing import Optional
from pybit.unified_trading import HTTP
from config import Config

log = logging.getLogger(__name__)


class BybitClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = HTTP(
            testnet=cfg.testnet,
            api_key=cfg.api_key,
            api_secret=cfg.api_secret,
        )
        self._init_leverage()

    # ------------------------------------------------------------------ #
    # 초기 설정
    # ------------------------------------------------------------------ #

    def _init_leverage(self):
        try:
            self.session.set_leverage(
                category="linear",
                symbol=self.cfg.symbol,
                buyLeverage=str(self.cfg.leverage),
                sellLeverage=str(self.cfg.leverage),
            )
            log.info("레버리지 %dx 설정 완료 (%s)", self.cfg.leverage, self.cfg.symbol)
        except Exception as e:
            # 이미 설정된 경우 Bybit이 에러를 반환하므로 무시
            log.debug("레버리지 설정 스킵 (이미 설정됨): %s", e)

    # ------------------------------------------------------------------ #
    # 시세 데이터
    # ------------------------------------------------------------------ #

    def get_klines(self) -> list:
        """15분봉 캔들 list[dict] 반환. 키: ts, open, high, low, close, volume."""
        resp = self.session.get_kline(
            category="linear",
            symbol=self.cfg.symbol,
            interval=self.cfg.interval,
            limit=self.cfg.candle_limit,
        )
        raw = resp["result"]["list"]
        candles = [
            {
                "ts":     int(r[0]),
                "open":   float(r[1]),
                "high":   float(r[2]),
                "low":    float(r[3]),
                "close":  float(r[4]),
                "volume": float(r[5]),
            }
            for r in raw
        ]
        candles.sort(key=lambda c: c["ts"])
        return candles

    def get_balance(self) -> float:
        """USDT 사용 가능 잔고 반환. 계정 타입 자동 감지."""
        for account_type in ("UNIFIED", "CONTRACT"):
            try:
                resp = self.session.get_wallet_balance(accountType=account_type, coin="USDT")
                coins = resp["result"]["list"][0]["coin"]
                for c in coins:
                    if c["coin"] == "USDT":
                        # 빈 문자열 방어 처리
                        for field in ("availableToWithdraw", "availableBalance", "walletBalance"):
                            val = c.get(field, "")
                            if val != "":
                                return float(val)
            except Exception:
                continue
        return 0.0

    # ------------------------------------------------------------------ #
    # 포지션
    # ------------------------------------------------------------------ #

    def get_position(self) -> Optional[dict]:
        """현재 열린 포지션 반환. 없으면 None."""
        resp = self.session.get_positions(
            category="linear",
            symbol=self.cfg.symbol,
        )
        positions = resp["result"]["list"]
        for p in positions:
            if float(p["size"]) > 0:
                return p
        return None

    # ------------------------------------------------------------------ #
    # 주문
    # ------------------------------------------------------------------ #

    def place_order(self, side: str, qty: float, sl_price: float, tp_price: float) -> dict:
        """
        시장가 주문 + SL/TP 동시 설정.
        side: "Buy" | "Sell"
        """
        resp = self.session.place_order(
            category="linear",
            symbol=self.cfg.symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=str(round(sl_price, 2)),
            takeProfit=str(round(tp_price, 2)),
            tpslMode="Full",
            slTriggerBy="MarkPrice",
            tpTriggerBy="MarkPrice",
            timeInForce="GoodTillCancel",
            reduceOnly=False,
        )
        log.info("주문 실행 — side=%s qty=%s SL=%.2f TP=%.2f", side, qty, sl_price, tp_price)
        return resp

    def close_position(self, side: str, qty: float):
        """현재 포지션 강제 청산 (reduceOnly)."""
        close_side = "Sell" if side == "Buy" else "Buy"
        self.session.place_order(
            category="linear",
            symbol=self.cfg.symbol,
            side=close_side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
            timeInForce="GoodTillCancel",
        )
        log.info("포지션 청산 — %s %s", close_side, qty)

    def get_ticker(self) -> float:
        """현재 마크 가격 반환."""
        resp = self.session.get_tickers(category="linear", symbol=self.cfg.symbol)
        return float(resp["result"]["list"][0]["markPrice"])

    def get_min_qty(self) -> float:
        """심볼의 최소 주문 수량 반환."""
        resp = self.session.get_instruments_info(category="linear", symbol=self.cfg.symbol)
        lot = resp["result"]["list"][0]["lotSizeFilter"]
        return float(lot["minOrderQty"])

    def get_qty_step(self) -> float:
        """수량 스텝 (소수점 자릿수) 반환."""
        resp = self.session.get_instruments_info(category="linear", symbol=self.cfg.symbol)
        lot = resp["result"]["list"][0]["lotSizeFilter"]
        return float(lot["qtyStep"])
