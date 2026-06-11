"""risk.py 단위 테스트 — 사이징 + 드로다운 축소(옵트인) + 게이트 함수."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk import calc_trade, _floor_to_step, funding_blocks, time_stop_hit
from strategy import Signal


class CfgStub:
    risk_pct = 0.02
    leverage = 5
    tp1_r = 1.0
    tp2_r = 2.0
    risk_scale_enabled = False
    risk_scale_after_loss = 0.5
    risk_scale_floor = 0.25
    min_notional_usd = 2.0
    time_stop_hours = 8.0
    time_stop_pnl_pct = -0.005


def long_signal(entry=100.0, sl=99.0):
    return Signal("long", entry, sl)


def short_signal(entry=100.0, sl=101.0):
    return Signal("short", entry, sl)


class TestSizing(unittest.TestCase):
    def setUp(self):
        self.cfg = CfgStub()

    def test_base_qty_risk_constant(self):
        # 잔고 1000, 리스크 2% = $20, SL 거리 1 → qty 20
        p = calc_trade(long_signal(), 1000.0, self.cfg, 0.001, 0.001)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p.qty, 20.0, places=3)
        self.assertAlmostEqual(p.risk_usd, 20.0, delta=0.1)

    def test_leverage_caps_qty(self):
        p = calc_trade(long_signal(sl=99.9), 1000.0, self.cfg, 0.001, 0.001)
        self.assertIsNotNone(p)
        max_qty = 1000.0 * 5 / 100.0
        self.assertLessEqual(p.qty, max_qty + 1e-9)

    def test_below_min_qty_returns_none(self):
        self.assertIsNone(calc_trade(long_signal(), 10.0, self.cfg, 1.0, 0.001))

    def test_min_notional_rejected(self):
        # 잔고 50 → 리스크 $1 → qty 1 → 명목 1×1.0(엔트리 1.0)=... 엔트리 1.0, SL 0.98
        sig = Signal("long", 1.0, 0.98)
        p = calc_trade(sig, 50.0, self.cfg, 0.1, 0.1)
        # qty = 1.0/0.02 = 50 → lev cap = 50*5/1 = 250 → qty 50 → 명목 $50 → 통과
        self.assertIsNotNone(p)
        # 명목가치를 $2 아래로: 잔고 2 → 리스크 $0.04 → qty 2 → 명목 $2 경계
        p2 = calc_trade(sig, 1.0, self.cfg, 0.1, 0.1)
        # qty = 0.02/0.02 = 1 → 명목 $1 < $2 → 거부
        self.assertIsNone(p2)


class TestDrawdownScaling(unittest.TestCase):
    """드로다운 사이징은 옵트인 — 켰을 때만 축소, 기본은 변화 없음."""

    def _qty(self, losses, enabled):
        cfg = CfgStub()
        cfg.risk_scale_enabled = enabled
        p = calc_trade(long_signal(), 1000.0, cfg, 0.001, 0.001,
                       consecutive_losses=losses)
        return p.qty

    def test_disabled_by_default_no_scaling(self):
        self.assertAlmostEqual(self._qty(3, False), self._qty(0, False), places=3)

    def test_enabled_one_loss_halves(self):
        self.assertAlmostEqual(self._qty(1, True), self._qty(0, True) / 2, places=3)

    def test_enabled_floor_at_quarter(self):
        # 0.5^3 = 0.125 < floor 0.25 → 0.25로 고정
        self.assertAlmostEqual(self._qty(5, True), self._qty(0, True) / 4, places=3)


class TestTpPrices(unittest.TestCase):
    def setUp(self):
        self.cfg = CfgStub()

    def test_long_tp_above_entry(self):
        p = calc_trade(long_signal(100.0, 99.0), 1000.0, self.cfg, 0.001, 0.001)
        self.assertAlmostEqual(p.tp1_price, 101.0)
        self.assertAlmostEqual(p.tp2_price, 102.0)
        self.assertAlmostEqual(p.sl_price, 99.0)

    def test_short_tp_below_entry(self):
        p = calc_trade(short_signal(100.0, 101.0), 1000.0, self.cfg, 0.001, 0.001)
        self.assertAlmostEqual(p.tp1_price, 99.0)
        self.assertAlmostEqual(p.tp2_price, 98.0)

    def test_invalid_sl_returns_none(self):
        self.assertIsNone(calc_trade(long_signal(100.0, 100.5), 1000.0, self.cfg, 0.001, 0.001))
        self.assertIsNone(calc_trade(short_signal(100.0, 99.5), 1000.0, self.cfg, 0.001, 0.001))


class TestSplits(unittest.TestCase):
    def setUp(self):
        self.cfg = CfgStub()

    def test_splits_sum_to_total(self):
        p = calc_trade(long_signal(), 1000.0, self.cfg, 0.001, 0.001)
        self.assertAlmostEqual(p.qty1 + p.qty2 + p.qty3, p.qty, places=6)

    def test_floor_to_step(self):
        self.assertAlmostEqual(_floor_to_step(0.0019, 0.001), 0.001)
        self.assertAlmostEqual(_floor_to_step(5.6789, 0.01), 5.67)
        self.assertAlmostEqual(_floor_to_step(7.0, 1.0), 7.0)


class TestFundingGate(unittest.TestCase):
    """펀딩비 양수 = 롱이 지불. 불리한 쪽만 차단."""

    def test_long_blocked_on_high_positive_funding(self):
        self.assertTrue(funding_blocks("long", 0.0008, 0.0005))

    def test_long_ok_on_negative_funding(self):
        self.assertFalse(funding_blocks("long", -0.0008, 0.0005))

    def test_short_blocked_on_high_negative_funding(self):
        self.assertTrue(funding_blocks("short", -0.0008, 0.0005))

    def test_short_ok_on_positive_funding(self):
        self.assertFalse(funding_blocks("short", 0.0008, 0.0005))

    def test_neutral_funding_ok_both(self):
        self.assertFalse(funding_blocks("long", 0.0001, 0.0005))
        self.assertFalse(funding_blocks("short", -0.0001, 0.0005))


class TestTimeStop(unittest.TestCase):
    """8시간 경과 + TP1 미달성 + 진입가 대비 -0.5% 이하 → 발동."""

    def setUp(self):
        self.cfg = CfgStub()
        self.t0 = 1_000_000.0

    def _after(self, hours):
        return self.t0 + hours * 3600

    def test_triggers_after_8h_underwater(self):
        self.assertTrue(time_stop_hit(self.t0, self._after(8.1), 0,
                                      100.0, 99.0, "Buy", self.cfg))

    def test_no_trigger_before_8h(self):
        self.assertFalse(time_stop_hit(self.t0, self._after(7.9), 0,
                                       100.0, 99.0, "Buy", self.cfg))

    def test_no_trigger_if_breakeven(self):
        # -0.5%보다 얕으면 (본전 부근) 발동 안 함
        self.assertFalse(time_stop_hit(self.t0, self._after(9), 0,
                                       100.0, 99.8, "Buy", self.cfg))

    def test_no_trigger_after_tp1(self):
        self.assertFalse(time_stop_hit(self.t0, self._after(9), 1,
                                       100.0, 99.0, "Buy", self.cfg))

    def test_short_direction_mirrored(self):
        # 숏: 가격이 올라가면 손실
        self.assertTrue(time_stop_hit(self.t0, self._after(9), 0,
                                      100.0, 101.0, "Sell", self.cfg))
        self.assertFalse(time_stop_hit(self.t0, self._after(9), 0,
                                       100.0, 99.0, "Sell", self.cfg))

    def test_missing_entry_ts_safe(self):
        self.assertFalse(time_stop_hit(0.0, self._after(9), 0,
                                       100.0, 90.0, "Buy", self.cfg))


if __name__ == "__main__":
    unittest.main()
