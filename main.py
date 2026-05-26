import logging
import os
import sys
import time
from datetime import datetime

import schedule

from config import Config
from client import BybitClient
from trader import Trader
from notify import alert_start, alert_error, alert_tp, alert_sl

# TTY 여부 감지 — 클라우드 서버는 터미널 없음
IS_TTY = sys.stdout.isatty()

# 로깅 설정
log_handlers = [logging.StreamHandler(sys.stdout)]
if IS_TTY:
    os.makedirs("logs", exist_ok=True)
    log_handlers.append(logging.FileHandler("logs/bot.log", encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=log_handlers,
)
log = logging.getLogger("main")

# 대시보드 상태 (TTY 모드 전용)
STATUS = {
    "balance": 0.0, "price": 0.0, "position": None,
    "last_signal": "없음", "last_action": "대기 중",
    "cycle": 0, "errors": 0,
    "prev_position": None,   # 직전 사이클 포지션 상태
}

GREEN  = "\033[92m"; RED    = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; WHITE  = "\033[97m"; RESET  = "\033[0m"; BOLD = "\033[1m"


def draw_dashboard(cfg):
    os.system("cls" if os.name == "nt" else "clear")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pos = STATUS["position"]
    pos_text = f"{pos['side']}  크기:{pos['size']}  PnL:{float(pos.get('unrealisedPnl',0)):+.2f}" if pos else f"{YELLOW}없음{RESET}"
    sig = STATUS["last_signal"]
    sig_color = GREEN if "롱" in sig else (RED if "숏" in sig else YELLOW)

    print(f"{BOLD}{CYAN}")
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        바이비트 자동 선물 봇              ║")
    print("  ║     BTC/USDT  15분봉  |  EMA+OB+Fib      ║")
    print("  ╚══════════════════════════════════════════╝")
    print(f"{RESET}")
    print(f"  {WHITE}현재 시각  {RESET} {now}")
    print(f"  {WHITE}BTC 가격   {RESET} {CYAN}${STATUS['price']:,.2f}{RESET}")
    print(f"  {WHITE}잔고       {RESET} {GREEN}${STATUS['balance']:.2f} USDT{RESET}")
    print()
    print(f"  {WHITE}포지션     {RESET} {pos_text}")
    print(f"  {WHITE}마지막신호 {RESET} {sig_color}{sig}{RESET}")
    print(f"  {WHITE}마지막동작 {RESET} {STATUS['last_action']}")
    print()
    print(f"  레버리지 {cfg.leverage}x  |  리스크 {cfg.risk_pct*100:.0f}%  |  체크 {STATUS['cycle']}회  |  오류 {STATUS['errors']}회")
    print(f"\n  {YELLOW}[ 창을 닫으면 봇이 중지됩니다 ]{RESET}\n")


def make_job(trader, client, cfg):
    from strategy import analyze

    def job():
        STATUS["cycle"] += 1
        try:
            price   = client.get_ticker()        # BTC 기준 가격 표시용
            balance = client.get_balance()
            pos     = client.get_any_position()  # 전체 종목 포지션 확인
            prev    = STATUS["prev_position"]
            STATUS.update({"price": price, "balance": balance,
                           "position": pos, "prev_position": pos})

            # 포지션이 사라졌을 때 → TP 또는 SL 판단
            if prev and not pos:
                closed = client.get_last_closed_pnl()
                if closed:
                    pnl         = float(closed.get("closedPnl", 0))
                    exit_price  = float(closed.get("avgExitPrice", price))
                    entry_price = float(closed.get("avgEntryPrice", price))
                    direction   = "롱" if closed.get("side") == "Buy" else "숏"
                    if pnl >= 0:
                        alert_tp(direction, entry_price, exit_price, pnl)
                        log.info("TP 달성 — PnL=+$%.2f", pnl)
                    else:
                        alert_sl(direction, entry_price, exit_price, pnl)
                        log.info("SL 손절 — PnL=$%.2f", pnl)

            # 이미 포지션 있으면 스캔 생략
            if pos:
                STATUS["last_signal"] = f"포지션 유지 ({pos['symbol']} {pos['side']})"
                STATUS["last_action"] = "홀딩 중"
                if not IS_TTY:
                    log.info("포지션 유지 — %s %s  잔고=$%.2f",
                             pos["symbol"], pos["side"], balance)
            else:
                # 상위 10종목 스캔 — 첫 신호 종목 진입
                found_signal = False
                for sym in cfg.scan_symbols:
                    try:
                        candles_15m = client.get_klines(symbol=sym)
                        candles_1h  = client.get_klines(interval=cfg.htf_interval, symbol=sym)
                        signal      = analyze(candles_15m, cfg, candles_1h)
                    except Exception as scan_err:
                        log.warning("스캔 실패 (%s): %s", sym, scan_err)
                        continue

                    if signal:
                        direction = "롱" if signal.direction == "long" else "숏"
                        STATUS["last_signal"] = f"{sym} {direction} @ ${signal.entry_price:,.2f}"
                        STATUS["last_action"] = "주문 진행 중"
                        log.info("신호 발견 — %s %s @ %.2f", sym, direction, signal.entry_price)
                        trader.run_cycle(signal, balance, symbol=sym)
                        STATUS["last_action"] = "주문 완료"
                        found_signal = True
                        break   # 한 종목만 진입

                if not found_signal:
                    STATUS["last_signal"] = f"없음 (10종목 스캔 완료)"
                    STATUS["last_action"] = "대기 중"
                    if not IS_TTY:
                        log.info("신호 없음 — BTC=%.2f  잔고=$%.2f  포지션=없음",
                                 price, balance)

        except Exception as e:
            STATUS["errors"] += 1
            STATUS["last_action"] = f"오류: {str(e)[:50]}"
            log.error("사이클 오류: %s", e, exc_info=True)
            alert_error(str(e))

        if IS_TTY:
            draw_dashboard(cfg)

    return job


def main():
    cfg = Config()
    try:
        cfg.validate()
    except ValueError as e:
        log.error(str(e))
        sys.exit(1)

    log.info("=== 바이비트 자동 선물 봇 시작 ===")
    log.info("심볼=%s  레버리지=%dx  리스크=%.0f%%  테스트넷=%s",
             cfg.symbol, cfg.leverage, cfg.risk_pct * 100, cfg.testnet)
    alert_start(cfg.symbol, cfg.leverage, cfg.risk_pct, scan_count=len(cfg.scan_symbols))

    if cfg.testnet:
        log.warning("TESTNET 모드 — 실제 거래 아님")

    if IS_TTY and os.name == "nt":
        os.system("color")

    client = BybitClient(cfg)
    trader = Trader(client, cfg)

    job = make_job(trader, client, cfg)
    job()

    schedule.every(cfg.check_interval_sec).seconds.do(job)
    log.info("스케줄러 시작 — %d초마다 실행", cfg.check_interval_sec)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
