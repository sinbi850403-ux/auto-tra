"""텔레그램 알림 — requests만 사용."""
import logging
import os
import requests

log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                                 "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        log.warning("텔레그램 전송 실패: %s", e)


def alert_entry(direction: str, entry: float, sl: float, tp: float,
                qty: float, balance: float):
    emoji = "🟢" if direction == "롱" else "🔴"
    send(
        f"{emoji} <b>진입 신호</b>\n"
        f"방향: {direction}\n"
        f"진입가: ${entry:,.2f}\n"
        f"SL: ${sl:,.2f}\n"
        f"TP: ${tp:,.2f}\n"
        f"수량: {qty} BTC\n"
        f"잔고: ${balance:.2f} USDT"
    )


def alert_tp(direction: str, entry: float, exit_price: float, pnl: float):
    send(
        f"🎯 <b>TP 달성!</b>\n"
        f"방향: {direction}\n"
        f"진입가: ${entry:,.2f}\n"
        f"청산가: ${exit_price:,.2f}\n"
        f"수익: <b>+${pnl:.2f} USDT</b> 🟢"
    )


def alert_sl(direction: str, entry: float, exit_price: float, pnl: float):
    send(
        f"🛑 <b>SL 손절</b>\n"
        f"방향: {direction}\n"
        f"진입가: ${entry:,.2f}\n"
        f"청산가: ${exit_price:,.2f}\n"
        f"손실: <b>${pnl:.2f} USDT</b> 🔴"
    )


def alert_error(msg: str):
    send(f"⚠️ <b>봇 오류</b>\n{msg[:200]}")


def alert_start(symbol: str, leverage: int, risk_pct: float):
    send(
        f"🤖 <b>오토선물봇 시작</b>\n"
        f"심볼: {symbol}\n"
        f"레버리지: {leverage}x\n"
        f"리스크: {risk_pct*100:.0f}%\n"
        f"전략: 슈퍼트렌드 + EMA200"
    )
