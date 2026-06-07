"""Bybit V5 API 래퍼 — 봇에 필요한 기능만 노출."""
import logging
import math
import time
from typing import Optional
from pybit.unified_trading import HTTP
from config import Config

log = logging.getLogger(__name__)


def _safe_call(fn, retries=5, delay=10):
    """Rate Limit / Timeout 오류 시 재시도."""
    import requests.exceptions as req_exc
    for i in range(retries):
        try:
            return fn()
        except KeyError as e:
            # pybit 내부 버그: X-Bapi-Limit-Reset-Timestamp 헤더 없을 때 KeyError
            if "bapi" in str(e).lower() or "limit" in str(e).lower():
                log.warning("Rate Limit (KeyError) — %d초 후 재시도 (%d/%d)", delay, i+1, retries)
                time.sleep(delay)
            else:
                raise
        except (req_exc.ReadTimeout, req_exc.ConnectTimeout, req_exc.Timeout) as e:
            # 네트워크 타임아웃 — 재시도
            wait = delay * (i + 1)  # 점진적 대기 (10s, 20s, 30s...)
            log.warning("API 타임아웃 — %d초 후 재시도 (%d/%d): %s", wait, i+1, retries, e)
            time.sleep(wait)
        except Exception as e:
            msg = str(e)
            if ("rate limit" in msg.lower() or "x-bapi-limit" in msg.lower()
                    or "10006" in msg or "timed out" in msg.lower()
                    or "timeout" in msg.lower() or "connectionpool" in msg.lower()):
                wait = delay * (i + 1)
                log.warning("API 오류 (재시도 가능) — %d초 후 재시도 (%d/%d): %s", wait, i+1, retries, e)
                time.sleep(wait)
            else:
                raise
    raise Exception("API 재시도 초과 (Rate Limit / Timeout)")


def _round_price(price: float) -> str:
    """tickSize를 모를 때의 fallback (가격 크기 기반 추정)."""
    if price >= 100:
        return str(round(price, 2))
    elif price >= 1:
        return str(round(price, 3))
    else:
        return str(round(price, 4))


def _round_to_tick(price: float, tick: float) -> str:
    """가격을 거래소 호가단위(tickSize)의 배수로 반올림해 문자열로 반환.

    tickSize를 안 맞추면 Bybit가 주문을 거부한다(예: BTCUSDT tick=0.1).
    """
    if not tick or tick <= 0:
        return _round_price(price)
    steps = round(price / tick)
    val = steps * tick
    precision = max(0, -int(math.floor(math.log10(tick))))
    return f"{val:.{precision}f}"


class BybitClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = HTTP(
            testnet=cfg.testnet,
            api_key=cfg.api_key,
            api_secret=cfg.api_secret,
            recv_window=10000,   # 서버 수신 허용 창 (ms)
        )
        # 기본 HTTP timeout을 30초로 확장 (기본값 10초 → 타임아웃 빈발)
        try:
            self.session.client.timeout = 30
        except Exception:
            pass
        self._tick_cache: dict = {}   # symbol -> tickSize
        self._init_leverage()

    def get_tick_size(self, symbol: str = None) -> float:
        """심볼의 호가단위(priceFilter.tickSize) 반환. 캐시됨."""
        sym = symbol or self.cfg.symbol
        if sym not in self._tick_cache:
            try:
                resp = _safe_call(lambda: self.session.get_instruments_info(
                    category="linear", symbol=sym))
                pf = resp["result"]["list"][0]["priceFilter"]
                self._tick_cache[sym] = float(pf["tickSize"])
            except Exception as e:
                log.warning("tickSize 조회 실패 (%s) — fallback 사용: %s", sym, e)
                self._tick_cache[sym] = 0.0
        return self._tick_cache[sym]

    def fmt_price(self, price: float, symbol: str = None) -> str:
        """호가단위에 맞춰 가격을 문자열로 변환."""
        return _round_to_tick(price, self.get_tick_size(symbol))

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
            except Exception as e:
                # 110043 = leverage not modified (이미 같은 값) → 정상
                if "110043" in str(e) or "not modified" in str(e).lower():
                    log.debug("레버리지 이미 %dx (%s)", self.cfg.leverage, sym)
                else:
                    log.warning("레버리지 설정 실패 (%s) — 사이징/청산 가정과 다를 수 있음: %s", sym, e)
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
        # ⚠️ 핵심: Bybit는 '아직 닫히지 않은(forming) 현재 캔들'을 최신봉으로 준다.
        # 정렬 후 마지막 원소가 그 미완성 봉이므로 제거한다. 이걸 안 하면 봉이
        # 만들어지는 중에 신호/청산이 깜빡거리는 리페인팅이 발생한다(감사 치명적 #1).
        # 제거 후에는 candles[-1] = 마지막으로 '확정된' 봉이 된다.
        if len(candles) >= 2:
            candles = candles[:-1]
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
        resp = _safe_call(lambda: self.session.get_positions(category="linear", symbol=sym))
        for p in resp["result"]["list"]:
            if float(p["size"]) > 0:
                return p
        return None

    def get_any_position(self) -> Optional[dict]:
        """전체 종목 중 열린 포지션 하나 반환."""
        for sym in self.cfg.scan_symbols:
            try:
                pos = self.get_position(sym)
                if pos:
                    return pos
            except Exception as e:
                log.warning("포지션 조회 실패 (%s): %s", sym, e)
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
        sl_str = self.fmt_price(sl_price, sym)
        # ⚠️ 진입(시장가)은 절대 자동 재시도하지 않는다. 타임아웃 시 주문이 실제로는
        # 체결됐는데 응답만 유실될 수 있어, 재시도하면 포지션이 2배로 열린다(중복 진입).
        # 한 번만 시도하고 실패하면 상위에서 None 처리 → 그 사이클은 진입 포기(안전).
        resp = self.session.place_order(
            category="linear",
            symbol=sym,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=sl_str,
            slTriggerBy="MarkPrice",
            tpslMode="Full",
            timeInForce="GoodTillCancel",
            reduceOnly=False,
            positionIdx=0,   # one-way 모드 (헤지모드에서 거부 방지)
        )
        log.info("진입 주문 — side=%s qty=%s SL=%s (%s)", side, qty, sl_str, sym)
        return resp

    def place_reduce_only_limit(self, side: str, qty: float, price: float,
                                symbol: str = None) -> dict:
        """분할 TP용 리듀스온리 지정가 주문."""
        sym = symbol or self.cfg.symbol
        price_str = self.fmt_price(price, sym)
        # 재시도 안 함: 타임아웃 후 재전송 시 중복 지정가가 쌓일 수 있음 (reduceOnly라 영향은 제한적이나 회피)
        resp = self.session.place_order(
            category="linear",
            symbol=sym,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=price_str,
            reduceOnly=True,
            timeInForce="GTC",
            positionIdx=0,
        )
        log.info("TP 지정가 — %s %s @ %s (%s)", side, qty, price_str, sym)
        return resp

    def set_sl(self, sl_price: float, symbol: str = None):
        """포지션 SL 업데이트 (TP1 달성 후 본전 이동용)."""
        sym = symbol or self.cfg.symbol
        sl_str = self.fmt_price(sl_price, sym)
        try:
            self.session.set_trading_stop(
                category="linear",
                symbol=sym,
                stopLoss=sl_str,
                slTriggerBy="MarkPrice",
                tpslMode="Full",
                positionIdx=0,
            )
            log.info("SL 본전 이동 → %s (%s)", sl_str, sym)
        except Exception as e:
            log.warning("SL 업데이트 실패 (%s): %s", sym, e)

    def get_open_orders(self, symbol: str = None) -> list:
        """미체결 주문 목록 반환."""
        sym = symbol or self.cfg.symbol
        try:
            resp = _safe_call(lambda: self.session.get_open_orders(
                category="linear", symbol=sym))
            return resp["result"]["list"]
        except Exception as e:
            log.warning("미체결 주문 조회 실패 (%s): %s", sym, e)
            return []

    def cancel_all_orders(self, symbol: str = None):
        """미체결 주문 전체 취소 (TP 지정가 주문 포함)."""
        sym = symbol or self.cfg.symbol
        try:
            self.session.cancel_all_orders(category="linear", symbol=sym)
            log.info("미체결 주문 전체 취소 완료 (%s)", sym)
        except Exception as e:
            log.warning("주문 취소 실패 (%s): %s", sym, e)

    def close_position(self, side: str, qty: float, symbol: str = None):
        """현재 포지션 강제 청산 (reduceOnly)."""
        sym = symbol or self.cfg.symbol
        close_side = "Sell" if side == "Buy" else "Buy"
        # 재시도 안 함: 타임아웃 후 재전송 시 중복 청산 시도 가능. reduceOnly라
        # 포지션이 역전되진 않지만, 실패 시 다음 사이클에서 자연히 재시도됨(SL은 유지).
        self.session.place_order(
            category="linear",
            symbol=sym,
            side=close_side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
            timeInForce="GoodTillCancel",
            positionIdx=0,
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
