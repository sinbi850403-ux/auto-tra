"""거래 안전장치 + 상태 영속화.

- 일일 손실 한도(daily loss limit)
- 연속 손절 정지(max consecutive losses)
- 손절 후 쿨다운(cooldown)
- entry_info / guard 카운터를 디스크에 저장해 재시작에도 유지

이 모듈이 없으면 봇은 5연패해도 멈추지 않고, 재시작 시 포지션 상태를 잘못
복구한다. (감사 결과 치명적 #2, 높음: 재시작 복구 깨짐 대응)
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_state() -> dict:
    """디스크에서 상태 로드. 없거나 깨졌으면 빈 dict."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.warning("상태 파일 로드 실패 — 새로 시작: %s", e)
        return {}


def save_state(state: dict):
    """원자적 저장 (tmp 파일 후 교체)."""
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log.warning("상태 저장 실패: %s", e)


def infer_tp_count(resting_tp: int) -> int:
    """남은 TP 지정가 수로 tp_count 추정 (재시작 복구용).

    2개 잔존 = 아무것도 체결 안 됨(0), 1개 = TP1 체결(1), 0개 = 별도 처리.
    3개 이상 = 구버전(3분할 TP)이 깔아둔 잔존 주문 → 체결 없음(0)으로 간주.
    음수가 나오면 안 된다 — tp_count<0이면 본전 SL 이동·시간손절이 모두 비활성화된다.
    """
    if resting_tp <= 0:
        return 0
    return max(0, 2 - resting_tp)


def sanitize_entry_info(ei) -> "dict | None":
    """디스크에서 복구한 entry_info 정합성 보정.

    과거 버그로 저장된 tp_count=-1 등이 그대로 복원되면 상태 머신이 죽는다.
    tp_count는 [0, 2] 정수로 클램프, entry_ts 음수는 0으로.
    """
    if not isinstance(ei, dict):
        return None
    try:
        ei["tp_count"] = max(0, min(2, int(ei.get("tp_count", 0))))
    except (TypeError, ValueError):
        ei["tp_count"] = 0
    try:
        ei["entry_ts"] = max(0.0, float(ei.get("entry_ts", 0.0)))
    except (TypeError, ValueError):
        ei["entry_ts"] = 0.0
    return ei


class TradeGuard:
    """신규 진입을 손실 상황에 따라 차단하는 안전장치."""

    def __init__(self, cfg, state: dict):
        self.cfg = cfg
        self._state = state
        g = state.get("guard", {})
        self.utc_date = g.get("utc_date", _utc_today())
        self.day_start_balance = float(g.get("day_start_balance", 0.0))
        self.day_realized_pnl = float(g.get("day_realized_pnl", 0.0))
        self.consecutive_losses = int(g.get("consecutive_losses", 0))
        self.halted_until = float(g.get("halted_until", 0.0))
        self.trades_today = int(g.get("trades_today", 0))

    def _roll_day(self, balance: float):
        today = _utc_today()
        if today != self.utc_date:
            self.utc_date = today
            self.day_start_balance = balance
            self.day_realized_pnl = 0.0
            self.consecutive_losses = 0
            self.halted_until = 0.0
            self.trades_today = 0
            log.info("UTC 날짜 변경 — 일일 손익/연속손절/진입횟수 카운터 리셋")
            self.persist()
        if self.day_start_balance <= 0 and balance > 0:
            self.day_start_balance = balance
            self.persist()

    def can_trade(self, balance: float):
        """(허용여부, 사유) 반환."""
        self._roll_day(balance)
        now = time.time()

        if now < self.halted_until:
            mins = int((self.halted_until - now) / 60) + 1
            return False, f"손절 후 쿨다운 중 (약 {mins}분 남음)"

        if self.consecutive_losses >= self.cfg.max_consecutive_losses:
            return False, (f"연속 {self.consecutive_losses}회 손절 — 신규 진입 정지 "
                           f"(다음 UTC 날짜에 자동 해제)")

        if self.day_start_balance > 0:
            loss_pct = -self.day_realized_pnl / self.day_start_balance
            if loss_pct >= self.cfg.daily_loss_limit_pct:
                return False, (f"일일 손실 한도(-{self.cfg.daily_loss_limit_pct * 100:.0f}%) "
                               f"도달 — 오늘 진입 정지")

        max_trades = getattr(self.cfg, "max_trades_per_day", 0)
        if max_trades > 0 and self.trades_today >= max_trades:
            return False, (f"일일 진입 한도({max_trades}회) 도달 — 과매매 방지, "
                           f"다음 UTC 날짜에 자동 해제")

        return True, "ok"

    def record_entry(self):
        """진입 1건 기록 — 일일 진입 횟수 카운터."""
        self.trades_today += 1
        log.info("진입 기록 — 오늘 %d회째", self.trades_today)
        self.persist()

    def record_result(self, pnl: float, balance: float):
        """청산 결과 1건 기록. pnl<0이면 연속손절 +1 및 쿨다운."""
        self._roll_day(balance)
        self.day_realized_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
            self.halted_until = time.time() + self.cfg.cooldown_after_loss_min * 60
            log.warning("손절 기록 — 연속 %d회, 일일 실현손익 $%.2f, 쿨다운 %d분",
                        self.consecutive_losses, self.day_realized_pnl,
                        self.cfg.cooldown_after_loss_min)
        else:
            self.consecutive_losses = 0
            log.info("수익 청산 기록 — 연속손절 리셋, 일일 실현손익 $%.2f",
                     self.day_realized_pnl)
        self.persist()

    def persist(self):
        self._state["guard"] = {
            "utc_date": self.utc_date,
            "day_start_balance": self.day_start_balance,
            "day_realized_pnl": self.day_realized_pnl,
            "consecutive_losses": self.consecutive_losses,
            "halted_until": self.halted_until,
            "trades_today": self.trades_today,
        }
        save_state(self._state)
