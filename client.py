"""Bybit V5 API 래퍼 — 봇에 필요한 기능만 노출."""
import logging
import time
from typing import Optional
from pybit.unified_trading import HTTP
from config import Config

log = logging.getLogger(__name__)


def _safe_call(fn, retries=3, delay=5):
    """Rate Limit 오류 시 재시도."""
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower() or "x-bapi-limit" in msg.lower() or "10006" in msg:
                log.warning("Rate Limit — %d초 후 재시도 (%d/%d)", delay, i+1, retries)
                time.sleep(delay)
            else:
                raise
    raise Exception("Rate Limit 재시도 초과")


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
        for sym in self.cfg.scan_symbols:
            try:
                self.session.set_leverage(
                    category="linear",
                    symbol=sym,
                    buyLeverage=str(self.cfg.leverage),
                    sellLeverage=str(self.cfg.leverage),
                )
                log.debug("레버리지 %dx 설정 (%s)", self.cfg.leverage, sym)
            except Exception:
                pass
        log.info("레버리지 %dx 설정 완료 (전 종목)", self.cfg.leverage)

    # ------------------------------------------------------------------ #
    # 시세 데이터
    # ------------------------------------------------------------------ #

    def get_klines(self, interval: str = None, symbol: str = None) -> list:
        """캔들 list[dict] 반환. 키: ts, open, high, low, close, volume."""
        iv  = interval or self.cfg.interval
        sym = symbol   or self.cfg.symbol
        resp = _safe_call(lambda: self.session.get_kline(
            category="linear",
            symbol=sym,
            interval=iv,
            limit=self.cfg.candle_limit,
        ))
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
                resp = _safe_call(lambda: self.session.get_wallet_balance(accountType=account_type, coin="USDT"))
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

    def get_position(self, symbol: str = None) -> Optional[dict]:
        """현재 열린 포지션 반환. 없으면 None."""
        sym = symbol or self.cfg.symbol
        resp = self.session.get_positions(category="linear", symbol=sym)
        for p in resp["result"]["list"]:
            if float(p["size"]) > 0:
                return p
        return None

    def get_any_position(self) -> Optional[dict]:
        """전체 종목 중 열린 포지션 하나 반환."""
        for sym in self.cfg.scan_symbols:
            pos = self.get_position(sym)
            if pos:
                return pos
        return None

    # ------------------------------------------------------------------ #
    # 주문
    # ------------------------------------------------------------------ #

    def place_order(self, side: str, qty: float, sl_price: float, tp_price: float,
                    symbol: str = None) -> dict:
        """
        시장가 주문 + SL/TP 동시 설정.
        side: "Buy" | "Sell"
        """
        sym = symbol or self.cfg.symbol
        resp = self.session.place_order(
            category="linear",
            symbol=sym,
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

    def get_ticker(self, symbol: str = None) -> float:
        """현재 마크 가격 반환."""
        sym = symbol or self.cfg.symbol
        resp = _safe_call(lambda: self.session.get_tickers(category="linear", symbol=sym))
        return float(resp["result"]["list"][0]["markPrice"])

    def get_last_closed_pnl(self) -> Optional[dict]:
        """가장 최근 청산된 포지션 정보 반환."""
        try:
            resp = _safe_call(lambda: self.session.get_closed_pnl(
                category="linear",
                symbol=self.cfg.symbol,
                limit=1,
            ))
            items = resp["result"]["list"]
            if items:
                return items[0]
        except Exception as e:
            log.warning("청산 내역 조회 실패: %s", e)
        return None

    def get_min_qty(self, symbol: str = None) -> float:
        """심볼의 최소 주문 수량 반환."""
        sym = symbol or self.cfg.symbol
        resp = self.session.get_instruments_info(category="linear", symbol=sym)
        lot = resp["result"]["list"][0]["lotSizeFilter"]
        return float(lot["minOrderQty"])

    def get_qty_step(self, symbol: str = None) -> float:
        """수량 스텝 (소수점 자릿수) 반환."""
        sym = symbol or self.cfg.symbol
        resp = self.session.get_instruments_info(category="linear", symbol=sym)
        lot = resp["result"]["list"][0]["lotSizeFilter"]
        return float(lot["qtyStep"])
