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


def _round_price(price: float) -> str:
    """가격 크기에 따라 소수점 자릿수 자동 조정."""
    if price >= 100:
        return str(round(price, 2))
    elif price >= 1:
        return str(round(price, 3))
    else:
        return str(round(price, 4))


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

    def place_order(self, side: str, qty: float, sl_price: float,
                    symbol: str = None) -> dict:
        """
        시장가 진입 + SL 설정. TP는 별도 지정가 주문으로 처리.
        side: "Buy" | "Sell"
        """
        sym = symbol or self.cfg.symbol
        resp = self.session.place_order(
            category="linear",
            symbol=sym,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=_round_price(sl_price),
            slTriggerBy="MarkPrice",
            tpslMode="Full",
            timeInForce="GoodTillCancel",
            reduceOnly=False,
        )
        log.info("진입 주문 — side=%s qty=%s SL=%s (%s)", side, qty, _round_price(sl_price), sym)
        return resp

    def place_reduce_only_limit(self, side: str, qty: float, price: float,
                                symbol: str = None) -> dict:
        """분할 TP용 리듀스온리 지정가 주문."""
        sym = symbol or self.cfg.symbol
        resp = self.session.place_order(
            category="linear",
            symbol=sym,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=_round_price(price),
            reduceOnly=True,
            timeInForce="GoodTillCancel",
        )
        log.info("TP 지정가 — %s %s @ %s (%s)", side, qty, _round_price(price), sym)
        return resp

    def set_sl(self, sl_price: float, symbol: str = None):
        """포지션 SL 업데이트 (TP1 달성 후 본전 이동용)."""
        sym = symbol or self.cfg.symbol
        try:
            self.session.set_trading_stop(
                category="linear",
                symbol=sym,
                stopLoss=_round_price(sl_price),
                slTriggerBy="MarkPrice",
                tpslMode="Full",
                positionIdx=0,
            )
            log.info("SL 본전 이동 → %s (%s)", _round_price(sl_price), sym)
        except Exception as e:
            log.warning("SL 업데이트 실패 (%s): %s", sym, e)

    def close_position(self, side: str, qty: float, symbol: str = None):
        """현재 포지션 강제 청산 (reduceOnly)."""
        sym = symbol or self.cfg.symbol
        close_side = "Sell" if side == "Buy" else "Buy"
        self.session.place_order(
            category="linear",
            symbol=sym,
            side=close_side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
            timeInForce="GoodTillCancel",
        )
        log.info("포지션 청산 — %s %s (%s)", close_side, qty, sym)

    def get_ticker(self, symbol: str = None) -> float:
        """현재 마크 가격 반환."""
        sym = symbol or self.cfg.symbol
        resp = _safe_call(lambda: self.session.get_tickers(category="linear", symbol=sym))
        return float(resp["result"]["list"][0]["markPrice"])

    def get_last_closed_pnl(self, symbol: str = None) -> Optional[dict]:
        """가장 최근 청산된 포지션 정보 반환. symbol 미지정 시 전체 조회."""
        try:
            kwargs = dict(category="linear", limit=1)
            if symbol:
                kwargs["symbol"] = symbol
            resp = _safe_call(lambda: self.session.get_closed_pnl(**kwargs))
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
        """수량 스텝 반환."""
        sym = symbol or self.cfg.symbol
        resp = self.session.get_instruments_info(category="linear", symbol=sym)
        lot = resp["result"]["list"][0]["lotSizeFilter"]
        return float(lot["qtyStep"])
