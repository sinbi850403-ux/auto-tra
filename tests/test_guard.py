"""guard.py 단위 테스트 — 안전장치 + 일일 진입 한도 + 영속화."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import guard as guard_mod
from guard import TradeGuard, load_state, save_state


class CfgStub:
    max_consecutive_losses = 3
    daily_loss_limit_pct = 0.06
    cooldown_after_loss_min = 30
    max_trades_per_day = 4


class GuardTestBase(unittest.TestCase):
    def setUp(self):
        # 실제 bot_state.json을 건드리지 않도록 임시 파일로 교체
        fd, self.tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.tmp_path)
        self._orig_state_file = guard_mod.STATE_FILE
        guard_mod.STATE_FILE = self.tmp_path
        self.cfg = CfgStub()

    def tearDown(self):
        guard_mod.STATE_FILE = self._orig_state_file
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def make_guard(self, state=None):
        return TradeGuard(self.cfg, state if state is not None else {})


class TestConsecutiveLosses(GuardTestBase):
    def test_blocks_after_max_losses(self):
        g = self.make_guard()
        for _ in range(3):
            g.record_result(-1.0, 100.0)
        g.halted_until = 0  # 쿨다운 제거하고 연속손절만 검사
        ok, reason = g.can_trade(100.0)
        self.assertFalse(ok)
        self.assertIn("연속", reason)

    def test_win_resets_streak(self):
        g = self.make_guard()
        g.record_result(-1.0, 100.0)
        g.record_result(-1.0, 100.0)
        g.record_result(+2.0, 100.0)
        self.assertEqual(g.consecutive_losses, 0)


class TestCooldown(GuardTestBase):
    def test_cooldown_after_loss(self):
        g = self.make_guard()
        g.record_result(-1.0, 100.0)
        ok, reason = g.can_trade(100.0)
        self.assertFalse(ok)
        self.assertIn("쿨다운", reason)

    def test_cooldown_expires(self):
        g = self.make_guard()
        g.record_result(-1.0, 100.0)
        g.halted_until = time.time() - 1
        ok, _ = g.can_trade(100.0)
        self.assertTrue(ok)


class TestDailyLossLimit(GuardTestBase):
    def test_blocks_at_daily_limit(self):
        g = self.make_guard()
        g.day_start_balance = 100.0
        g.record_result(-6.5, 93.5)
        g.halted_until = 0
        ok, reason = g.can_trade(93.5)
        self.assertFalse(ok)
        self.assertIn("일일", reason)


class TestMaxTradesPerDay(GuardTestBase):
    def test_blocks_after_max_entries(self):
        g = self.make_guard()
        for _ in range(4):
            g.record_entry()
        ok, reason = g.can_trade(100.0)
        self.assertFalse(ok)
        self.assertIn("진입 한도", reason)

    def test_allows_below_max(self):
        g = self.make_guard()
        for _ in range(3):
            g.record_entry()
        ok, _ = g.can_trade(100.0)
        self.assertTrue(ok)


class TestDayRoll(GuardTestBase):
    def test_new_day_resets_counters(self):
        g = self.make_guard()
        g.record_result(-1.0, 100.0)
        g.record_entry()
        g.record_entry()
        g.utc_date = "2000-01-01"   # 과거 날짜로 강제 → 롤 발생
        ok, _ = g.can_trade(100.0)
        self.assertTrue(ok)
        self.assertEqual(g.consecutive_losses, 0)
        self.assertEqual(g.trades_today, 0)
        self.assertEqual(g.day_realized_pnl, 0.0)


class TestPersistence(GuardTestBase):
    def test_counters_survive_restart(self):
        state = load_state()
        g = self.make_guard(state)
        g.record_result(-1.0, 100.0)
        g.record_entry()
        # 재시작 시뮬레이션: 디스크에서 다시 로드
        state2 = load_state()
        g2 = self.make_guard(state2)
        self.assertEqual(g2.consecutive_losses, 1)
        self.assertEqual(g2.trades_today, 1)
        self.assertGreater(g2.halted_until, time.time() - 5)

    def test_corrupt_state_file_safe(self):
        with open(self.tmp_path, "w", encoding="utf-8") as f:
            f.write("{ broken json")
        self.assertEqual(load_state(), {})


if __name__ == "__main__":
    unittest.main()
