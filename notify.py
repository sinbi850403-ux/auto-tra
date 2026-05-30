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


def _coin(symbol: str) -> str:
    return symbol.replace("USDT", "")


def alert_entry(direction: str, entry: float,
                sl: float, tp1: float, tp2: float, tp3: float,
                qty: float, balance: float, symbol: str = "BTCUSDT"):
    emoji = "🟢" if direction == "롱" else "🔴"
    coin  = _coin(symbol)
    send(
        f"{emoji} <b>진입!</b>  {coin}/USDT  {direction}\n"
        f"진입가: <b>${entry:,.4f}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🛑 SL:  ${sl:,.4f}\n"
        f"🎯 TP1: ${tp1:,.4f}  (1:1)\n"
        f"🎯 TP2: ${tp2:,.4f}  (1:2)\n"
        f"🏆 TP3: ${tp3:,.4f}  (1:3)\n"
        f"━━━━━━━━━━━━━━\n"
        f"수량: {qty} {coin}  |  잔고: ${balance:.2f}"
    )


def alert_tp1(direction: str, symbol: str, entry: float, exit_p: float, pnl: float):
    coin = _coin(symbol)
    send(
        f"🎯 <b>TP1 달성!</b>  {coin}/USDT  {direction}\n"
        f"${entry:,.4f} → ${exit_p:,.4f}\n"
        f"수익: <b>+${pnl:.2f} USDT</b>\n"
        f"✅ SL → 본전 이동 완료 (이제 무손실!)"
    )


def alert_tp2(direction: str, symbol: str, entry: float, exit_p: float, pnl: float):
    coin = _coin(symbol)
    send(
        f"🎯🎯 <b>TP2 달성!</b>  {coin}/USDT  {direction}\n"
        f"${entry:,.4f} → ${exit_p:,.4f}\n"
        f"수익: <b>+${pnl:.2f} USDT</b>\n"
        f"🚀 TP3 향해 달리는 중..."
    )


def alert_tp3(direction: str, symbol: str, entry: float, exit_p: float, pnl: float):
    coin = _coin(symbol)
    send(
        f"🏆 <b>TP3 풀청산!</b>  {coin}/USDT  {direction}\n"
        f"${entry:,.4f} → ${exit_p:,.4f}\n"
        f"수익: <b>+${pnl:.2f} USDT</b> 🎊"
    )


def alert_sl(direction: str, symbol: str, entry: float, exit_p: float, pnl: float):
    coin = _coin(symbol)
    send(
        f"🛑 <b>SL 손절</b>  {coin}/USDT  {direction}\n"
        f"${entry:,.4f} → ${exit_p:,.4f}\n"
        f"손실: <b>${pnl:.2f} USDT</b> 🔴"
    )


def alert_be_sl(direction: str, symbol: str, entry: float):
    """본전 SL에 걸렸을 때 (TP1 이후 SL 이동 후 청산)."""
    coin = _coin(symbol)
    send(
        f"⚡ <b>본전 청산</b>  {coin}/USDT  {direction}\n"
        f"진입가: ${entry:,.4f}\n"
        f"TP1 수익 확보 후 본전 청산 — 손해 없음 ✅"
    )


def alert_counter_close(direction: str, symbol: str,
                        entry: float, exit_p: float, pnl: float):
    """역신호 감지로 인한 즉시 전량 청산 알림."""
    coin  = _coin(symbol)
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    emoji = "🟢" if pnl >= 0 else "🔴"
    send(
        f"🔄 <b>역신호 즉시 청산!</b>  {coin}/USDT  {direction}\n"
        f"진입가: ${entry:,.4f}  →  청산가: ${exit_p:,.4f}\n"
        f"PnL: <b>{pnl_str} USDT</b>  {emoji}\n"
        f"⚡ 반대 방향 신호 감지 → 전량 청산 실행"
    )


def alert_error(msg: str):
    send(f"⚠️ <b>봇 오류</b>\n{msg[:200]}")


def alert_start(symbol: str, leverage: int, risk_pct: float, scan_count: int = 1):
    if scan_count > 1:
        symbol_text = f"상위 {scan_count}종목 스캔"
    else:
        symbol_text = symbol
    send(
        f"🤖 <b>오토선물봇 시작</b>\n"
        f"심볼: {symbol_text}\n"
        f"레버리지: {leverage}x\n"
        f"리스크: {risk_pct*100:.0f}%\n"
        f"전략: MTF 슈퍼트렌드 (1H+15M+EMA200)\n"
        f"TP: 3분할 (1:1 / 1:2 / 1:3) + 본전 SL 이동"
    )
