import logging
import os
import sys
import time
from datetime import datetime

import schedule

from config import Config
from client import BybitClient
from trader import Trader
from notify import (alert_start, alert_error, alert_counter_close,
                    alert_tp1, alert_tp2, alert_tp3, alert_sl, alert_be_sl)

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

# 대시보드 상태
STATUS = {
    "balance": 0.0, "price": 0.0, "position": None,
    "last_signal": "없음", "last_action": "대기 중",
    "cycle": 0, "errors": 0,
    "prev_position": None,
    # 진입 추적 (3분할 TP 관리용)
    "entry_info": None,      # {symbol, entry_price, entry_qty, tp_count, side}
    "counter_closed": False, # 역신호 청산 중복 알림 방지 플래그
}

GREEN  = "\033[92m"; RED    = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; WHITE  = "\033[97m"; RESET  = "\033[0m"; BOLD = "\033[1m"


def draw_dashboard(cfg):
    os.system("cls" if os.name == "nt" else "clear")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pos = STATUS["position"]
    ei  = STATUS["entry_info"]
    tp_str = f"  TP{ei['tp_count']}달성" if ei and ei["tp_count"] > 0 else ""
    pos_text = (
        f"{pos['side']}  크기:{pos['size']}  PnL:{float(pos.get('unrealisedPnl',0)):+.2f}{tp_str}"
        if pos else f"{YELLOW}없음{RESET}"
    )
    sig = STATUS["last_signal"]
    sig_color = GREEN if "롱" in sig else (RED if "숏" in sig else YELLOW)

    print(f"{BOLD}{CYAN}")
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        바이비트 자동 선물 봇              ║")
    print("  ║  MTF 슈퍼트렌드  |  3분할 TP (0.8/1.5/2.5R) ║")
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


def _handle_partial_close(pos, prev_pos, client, cfg):
    """부분 청산 감지 (TP1 / TP2) → SL 본전 이동."""
    ei = STATUS.get("entry_info")

    # 봇 재시작으로 entry_info가 없으면 포지션 정보로 복구
    if not ei:
        sym = prev_pos.get("symbol", cfg.symbol)
        STATUS["entry_info"] = {
            "symbol":      sym,
            "entry_price": float(prev_pos.get("avgPrice", 0)),
            "entry_qty":   float(prev_pos.get("size", 0)),
            "tp_count":    0,
            "side":        prev_pos.get("side", "Buy"),
        }
        ei = STATUS["entry_info"]
        log.info("봇 재시작 후 포지션 복구 (%s)", sym)

    curr_size  = float(pos["size"])
    entry_qty  = ei["entry_qty"]
    tp_count   = ei["tp_count"]
    sym        = ei["symbol"]
    entry_price = ei["entry_price"]
    direction  = "롱" if ei["side"] == "Buy" else "숏"

    # 현재 마크가격으로 PnL 추정
    try:
        mark = client.get_ticker(sym)
    except Exception:
        mark = entry_price

    closed_qty = entry_qty - curr_size
    pnl_est    = abs(mark - entry_price) * closed_qty

    # TP1: 잔여 수량이 초기의 ~2/3 이하 (33% 청산됨)
    if tp_count == 0 and curr_size < entry_qty * 0.75:
        ei["tp_count"] = 1
        client.set_sl(entry_price, symbol=sym)   # SL → 본전
        alert_tp1(direction, sym, entry_price, mark, pnl_est)
        log.info("TP1 달성 (%s) — SL 본전(%.4f) 이동", sym, entry_price)
        STATUS["last_action"] = f"TP1 달성 → 본전 SL"

    # TP2: 잔여 수량이 초기의 ~1/3 이하 (66% 청산됨)
    elif tp_count == 1 and curr_size < entry_qty * 0.45:
        ei["tp_count"] = 2
        alert_tp2(direction, sym, entry_price, mark, pnl_est)
        log.info("TP2 달성 (%s) — TP3 대기 중", sym)
        STATUS["last_action"] = f"TP2 달성 → TP3 대기"


def _handle_full_close(prev_pos, price, client, cfg):
    """포지션 전량 청산 감지 (TP3 / SL / 본전SL / 역신호)."""
    # 역신호 청산으로 이미 알림 전송됨 → 이중 알림 방지
    if STATUS.get("counter_closed"):
        STATUS["counter_closed"] = False
        STATUS["entry_info"] = None
        log.info("역신호 청산 확인 완료")
        return

    ei  = STATUS.get("entry_info")
    sym = (ei["symbol"] if ei else None) or prev_pos.get("symbol", cfg.symbol)

    closed = client.get_last_closed_pnl(symbol=sym)

    # entry_price: entry_info → closed PnL → prev_pos 순으로 fallback
    entry_price = (
        ei["entry_price"] if ei and ei["entry_price"] > 0
        else float(closed.get("avgEntryPrice", 0)) if closed else
        float(prev_pos.get("avgPrice", price))
    )
    direction = (
        ("롱" if ei["side"] == "Buy" else "숏") if ei
        else ("롱" if prev_pos.get("side") == "Buy" else "숏")
    )
    tp_count = ei["tp_count"] if ei else 0
    pnl        = float(closed.get("closedPnl", 0)) if closed else 0.0
    exit_price = float(closed.get("avgExitPrice", price)) if closed else price

    if tp_count >= 2:
        # TP3 달성
        alert_tp3(direction, sym, entry_price, exit_price, pnl)
        log.info("TP3 풀청산 (%s) — PnL=+$%.2f", sym, pnl)
        STATUS["last_action"] = "TP3 완료 🏆"
    elif tp_count == 1 and abs(pnl) < 0.5:
        # 본전 SL (TP1 이후 SL 이동해서 원금 복구)
        alert_be_sl(direction, sym, entry_price)
        log.info("본전 청산 (%s) — TP1 수익 확보", sym)
        STATUS["last_action"] = "본전 청산 ✅"
    elif tp_count == 1 and pnl >= 0:
        # TP2 최종 청산 (qty3가 qty2에 합산된 케이스)
        alert_tp2(direction, sym, entry_price, exit_price, pnl)
        log.info("TP2 최종청산 (%s) — PnL=+$%.2f", sym, pnl)
        STATUS["last_action"] = "TP2 완료 🎯🎯"
    elif pnl >= 0:
        # TP 조기 청산 (TP1 전에 전량 청산된 경우)
        alert_tp1(direction, sym, entry_price, exit_price, pnl)
        log.info("TP 달성 (%s) — PnL=+$%.2f", sym, pnl)
        STATUS["last_action"] = "TP 달성 🎯"
    else:
        # SL 손절
        alert_sl(direction, sym, entry_price, exit_price, pnl)
        log.info("SL 손절 (%s) — PnL=$%.2f", sym, pnl)
        STATUS["last_action"] = "SL 손절 🛑"

    STATUS["entry_info"] = None


def make_job(trader, client, cfg):
    from strategy import analyze

    def job():
        STATUS["cycle"] += 1
        try:
            price   = client.get_ticker()
            balance = client.get_balance()
            pos     = client.get_any_position()
            prev    = STATUS["prev_position"]
            STATUS.update({"price": price, "balance": balance,
                           "position": pos, "prev_position": pos})

            prev_size = float(prev["size"]) if prev else 0.0
            curr_size = float(pos["size"])  if pos  else 0.0

            # ── 케이스 1: 포지션 전량 청산 ──────────────────────────────
            if prev and not pos:
                _handle_full_close(prev, price, client, cfg)

            # ── 케이스 2: 부분 청산 (TP1 또는 TP2 체결) ─────────────────
            elif prev and pos and curr_size < prev_size * 0.85:
                _handle_partial_close(pos, prev, client, cfg)

            # ── 케이스 3: 포지션 없음 → 스캔 ────────────────────────────
            elif not pos:
                found = False
                for sym in cfg.scan_symbols:
                    try:
                        c15m = client.get_klines(symbol=sym)
                        c1h  = client.get_klines(interval=cfg.htf_interval, symbol=sym)
                        sig  = analyze(c15m, cfg, c1h)
                    except Exception as e:
                        log.warning("스캔 실패 (%s): %s", sym, e)
                        continue

                    if sig:
                        direction = "롱" if sig.direction == "long" else "숏"
                        STATUS["last_signal"] = f"{sym} {direction} @ ${sig.entry_price:,.4f}"
                        STATUS["last_action"] = "주문 진행 중"
                        params = trader.run_cycle(sig, balance, symbol=sym)
                        if params:
                            # 진입 성공 → entry_info 저장
                            STATUS["entry_info"] = {
                                "symbol":      sym,
                                "entry_price": sig.entry_price,
                                "entry_qty":   params.qty,
                                "tp_count":    0,
                                "side":        params.side,
                            }
                            STATUS["last_action"] = f"진입 완료 ({sym})"
                        found = True
                        break

                if not found:
                    STATUS["last_signal"] = f"없음 ({len(cfg.scan_symbols)}종목 스캔 완료)"
                    STATUS["last_action"] = "대기 중"
                    if not IS_TTY:
                        log.info("신호 없음 — BTC=%.2f  잔고=$%.2f", price, balance)

            # ── 케이스 4: 포지션 홀딩 중 ────────────────────────────────
            else:
                ei = STATUS.get("entry_info")
                tp_label = f" (TP{ei['tp_count']} 달성)" if ei and ei["tp_count"] > 0 else ""
                STATUS["last_action"] = f"홀딩 중{tp_label}"

                # 역신호 감지 → 즉시 전량 청산
                if ei:
                    try:
                        from strategy import current_direction
                        sym      = ei["symbol"]
                        c15m_cs  = client.get_klines(symbol=sym)
                        c1h_cs   = client.get_klines(interval=cfg.htf_interval, symbol=sym)
                        curr_dir = current_direction(c15m_cs, cfg, c1h_cs)
                        pos_dir  = 1 if ei["side"] == "Buy" else -1

                        if curr_dir != 0 and curr_dir != pos_dir:
                            direction  = "롱" if ei["side"] == "Buy" else "숏"
                            mark       = client.get_ticker(sym)
                            remaining  = float(pos["size"])
                            pnl_est    = (mark - ei["entry_price"]) * remaining
                            if ei["side"] == "Sell":
                                pnl_est = -pnl_est

                            log.warning(
                                "🔄 역신호 감지 (%s) — dir=%+d, pos=%+d → 전량 청산",
                                sym, curr_dir, pos_dir,
                            )
                            client.cancel_all_orders(symbol=sym)         # TP 지정가 취소
                            client.close_position(ei["side"], remaining, symbol=sym)
                            alert_counter_close(direction, sym,
                                                ei["entry_price"], mark, pnl_est)
                            STATUS["counter_closed"] = True
                            STATUS["entry_info"]     = None
                            STATUS["last_action"]    = "역신호 청산 🔄"
                    except Exception as e:
                        log.warning("역신호 체크 실패: %s", e)

                if not IS_TTY:
                    log.info("포지션 유지 — %s %s  size=%s  잔고=$%.2f",
                             pos["symbol"], pos["side"], pos["size"], balance)

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

    # 시작 시 기존 포지션 감지 → entry_info 복구 (재시작 대비)
    existing = client.get_any_position()
    if existing:
        STATUS["entry_info"] = {
            "symbol":      existing["symbol"],
            "entry_price": float(existing.get("avgPrice", 0)),
            "entry_qty":   float(existing["size"]),
            "tp_count":    0,
            "side":        existing["side"],
        }
        log.info("기존 포지션 감지 — %s %s @ %.4f (재시작 복구)",
                 existing["symbol"], existing["side"],
                 float(existing.get("avgPrice", 0)))

    job = make_job(trader, client, cfg)
    job()

    schedule.every(cfg.check_interval_sec).seconds.do(job)
    log.info("스케줄러 시작 — %d초마다 실행", cfg.check_interval_sec)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
