import logging
import os
import sys
import time
from datetime import datetime

import schedule

from config import Config
from client import BybitClient
from trader import Trader

# ── 로그는 파일에만 저장, 화면엔 대시보드만 표시 ──
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.FileHandler("logs/bot.log", encoding="utf-8")],
)

# 상태 공유 딕셔너리
STATUS = {
    "balance": 0.0,
    "price": 0.0,
    "position": None,
    "last_signal": "없음",
    "last_check": "--:--:--",
    "last_action": "대기 중",
    "cycle": 0,
    "errors": 0,
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def draw_dashboard(cfg: Config):
    clear()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pos = STATUS["position"]

    # 포지션 색상
    if pos:
        side = pos["side"]
        pnl  = float(pos.get("unrealisedPnl", 0))
        pos_color = GREEN if pnl >= 0 else RED
        pos_text  = f"{side}  |  크기: {pos['size']} BTC  |  미실현손익: {pos_color}{pnl:+.2f} USDT{RESET}"
    else:
        pos_text = f"{YELLOW}없음{RESET}"

    # 마지막 신호 색상
    sig = STATUS["last_signal"]
    if "롱" in sig:
        sig_display = f"{GREEN}{sig}{RESET}"
    elif "숏" in sig:
        sig_display = f"{RED}{sig}{RESET}"
    else:
        sig_display = f"{YELLOW}{sig}{RESET}"

    print(f"{BOLD}{CYAN}")
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        바이비트 자동 선물 봇              ║")
    print("  ║     BTC/USDT  15분봉  |  EMA+OB+Fib      ║")
    print("  ╚══════════════════════════════════════════╝")
    print(f"{RESET}")
    print(f"  {WHITE}현재 시각   {RESET}  {now}")
    print(f"  {WHITE}BTC 가격    {RESET}  {CYAN}${STATUS['price']:,.2f}{RESET}")
    print(f"  {WHITE}잔고        {RESET}  {GREEN}${STATUS['balance']:.2f} USDT{RESET}")
    print()
    print(f"  {WHITE}포지션      {RESET}  {pos_text}")
    print(f"  {WHITE}마지막 신호 {RESET}  {sig_display}")
    print(f"  {WHITE}마지막 동작 {RESET}  {STATUS['last_action']}")
    print()
    print(f"  {WHITE}레버리지    {RESET}  {cfg.leverage}x    "
          f"  {WHITE}리스크      {RESET}  {cfg.risk_pct*100:.0f}%")
    print(f"  {WHITE}체크 횟수   {RESET}  {STATUS['cycle']}회    "
          f"  {WHITE}오류 횟수   {RESET}  {RED if STATUS['errors'] else WHITE}{STATUS['errors']}회{RESET}")
    print()
    print(f"  {YELLOW}[ 창을 닫으면 봇이 중지됩니다 ]{RESET}")
    print(f"  다음 체크: {STATUS['last_check']}")
    print()


def make_job(trader: Trader, client: BybitClient, cfg: Config):
    def job():
        STATUS["cycle"] += 1
        try:
            STATUS["price"]   = client.get_ticker()
            STATUS["balance"] = client.get_balance()
            STATUS["position"] = client.get_position()

            from strategy import analyze
            df  = client.get_klines()
            sig = analyze(df, cfg)

            if sig:
                STATUS["last_signal"] = f"{'롱' if sig.direction == 'long' else '숏'} @ ${sig.entry_price:,.2f}"
                STATUS["last_action"] = "주문 시도 중..."
                trader.run_cycle()
                STATUS["last_action"] = "주문 완료"
            else:
                STATUS["last_signal"] = "없음 (조건 미충족)"
                STATUS["last_action"] = "대기 중"

        except Exception as e:
            STATUS["errors"] += 1
            STATUS["last_action"] = f"오류: {str(e)[:40]}"
            logging.getLogger("main").error("사이클 오류: %s", e, exc_info=True)

        next_t = datetime.now().strftime("%H:%M:%S")
        STATUS["last_check"] = next_t
        draw_dashboard(cfg)

    return job


def main():
    cfg = Config()
    try:
        cfg.validate()
    except ValueError as e:
        print(f"{RED}설정 오류: {e}{RESET}")
        sys.exit(1)

    # Windows 콘솔 컬러 활성화
    if os.name == "nt":
        os.system("color")

    client = BybitClient(cfg)
    trader = Trader(client, cfg)

    draw_dashboard(cfg)
    print(f"  {YELLOW}봇 시작 중...{RESET}")

    job = make_job(trader, client, cfg)
    job()  # 즉시 1회 실행

    schedule.every(cfg.check_interval_sec).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
