"""strategy.py v3 단위 테스트 — 합성 캔들로 모든 게이트 검증."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators import ema, atr
from strategy import analyze, current_direction, Signal


class CfgStub:
    ema_fast = 50
    ema_slow = 200
    ema_gap_min_pct = 0.005
    ema_pullback_tol = 0.004
    swing_lookback = 20
    pullback_lookback = 10
    sl_max_pct = 0.05
    max_momentum_pct = 0.04
    sl_buffer_pct = 0.001
    # v3
    atr_period = 14
    atr_sl_floor_mult = 0.8
    atr_vol_gate_pct = 0.03
    vol_floor_ratio = 0.8
    vol_avg_len = 20
    ema_extension_cap_pct = 0.02
    per_loss_buffer_add_pct = 0.0005
    max_sl_buffer_pct = 0.003


def mk(o, h, l, c, v=100.0, ts=0):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def bullish_4h(n=250, start=80.0, step=0.08):
    """꾸준한 상승 — EMA50 > EMA200, 갭 충분."""
    out = []
    for i in range(n):
        p = start + i * step
        out.append(mk(p - 0.04, p + 0.15, p - 0.15, p, ts=i))
    return out


def bearish_4h(n=250, start=120.0, step=0.08):
    out = []
    for i in range(n):
        p = start - i * step
        out.append(mk(p + 0.04, p + 0.15, p - 0.15, p, ts=i))
    return out


def flat_4h(n=250, level=100.0):
    """완전 횡보 — EMA 갭 거의 0."""
    return [mk(level, level + 0.1, level - 0.1, level, ts=i) for i in range(n)]


def long_setup_15m(final_close=100.6, final_vol=200.0, dip_low=None,
                   n_ramp=200, consol_level=100.1):
    """
    롱 셋업: 완만한 상승(96→100) → 20봉 횡보(~100.1) → EMA50 눌림 →
    마지막 봉이 양봉으로 스윙 하이 돌파.
    """
    candles = []
    # 1) 램프: 96 → 100 (+0.02/봉)
    for i in range(n_ramp):
        p = 96.0 + i * (4.0 / n_ramp)
        candles.append(mk(p - 0.01, p + 0.15, p - 0.15, p, ts=i))
    # 2) 횡보 20봉 (스윙 하이 = 100.4)
    for j in range(20):
        candles.append(mk(consol_level - 0.05, min(consol_level + 0.3, 100.4),
                          consol_level - 0.25, consol_level, ts=n_ramp + j))
    # 3) 눌림봉: EMA50 터치 (저점을 EMA50 아래로 충분히)
    ema50_now = ema([c["close"] for c in candles], 50)[-1]
    dip = dip_low if dip_low is not None else ema50_now - 0.05
    candles.append(mk(consol_level, consol_level + 0.1, dip, dip + 0.1,
                      ts=n_ramp + 20))
    # 4) 회복봉 1개 (모멘텀 필터 완화용)
    candles.append(mk(dip + 0.1, consol_level + 0.1, dip + 0.05, consol_level,
                      ts=n_ramp + 21))
    # 5) 신호봉: 양봉, 스윙 하이(100.4) 돌파
    candles.append(mk(consol_level, final_close + 0.05, consol_level - 0.05,
                      final_close, v=final_vol, ts=n_ramp + 22))
    return candles


def short_setup_15m(final_close=99.4, final_vol=200.0,
                    n_ramp=200, consol_level=99.9):
    """숏 셋업 — long_setup의 거울상 (104→100 하락 후 반등→저점 이탈)."""
    candles = []
    for i in range(n_ramp):
        p = 104.0 - i * (4.0 / n_ramp)
        candles.append(mk(p + 0.01, p + 0.15, p - 0.15, p, ts=i))
    # 횡보 20봉 (스윙 로우 = 99.6)
    for j in range(20):
        candles.append(mk(consol_level + 0.05, consol_level + 0.25,
                          max(consol_level - 0.3, 99.6), consol_level,
                          ts=n_ramp + j))
    # 반등봉: EMA50 터치
    ema50_now = ema([c["close"] for c in candles], 50)[-1]
    peak = ema50_now + 0.05
    candles.append(mk(consol_level, peak, consol_level - 0.1, peak - 0.1,
                      ts=n_ramp + 20))
    candles.append(mk(peak - 0.1, peak - 0.05, consol_level - 0.1, consol_level,
                      ts=n_ramp + 21))
    # 신호봉: 음봉, 스윙 로우(99.6) 이탈
    candles.append(mk(consol_level, consol_level + 0.05, final_close - 0.05,
                      final_close, v=final_vol, ts=n_ramp + 22))
    return candles


class TestLongSignal(unittest.TestCase):
    def setUp(self):
        self.cfg = CfgStub()
        self.c4h = bullish_4h()

    def test_happy_path_long(self):
        c15 = long_setup_15m()
        sig = analyze(c15, self.cfg, self.c4h)
        self.assertIsNotNone(sig, "모든 게이트 통과 시 롱 신호가 나와야 함")
        self.assertEqual(sig.direction, "long")
        self.assertLess(sig.sl_price, sig.entry_price)

    def test_sl_respects_atr_floor(self):
        c15 = long_setup_15m()
        sig = analyze(c15, self.cfg, self.c4h)
        self.assertIsNotNone(sig)
        atr_val = atr(c15, self.cfg.atr_period)[-1]
        sl_dist = sig.entry_price - sig.sl_price
        self.assertGreaterEqual(sl_dist, self.cfg.atr_sl_floor_mult * atr_val - 1e-9)

    def test_sl_max_pct_respected(self):
        c15 = long_setup_15m()
        sig = analyze(c15, self.cfg, self.c4h)
        self.assertIsNotNone(sig)
        sl_pct = (sig.entry_price - sig.sl_price) / sig.entry_price
        self.assertLessEqual(sl_pct, self.cfg.sl_max_pct)


class TestShortSignal(unittest.TestCase):
    def setUp(self):
        self.cfg = CfgStub()
        self.c4h = bearish_4h()

    def test_happy_path_short(self):
        c15 = short_setup_15m()
        sig = analyze(c15, self.cfg, self.c4h)
        self.assertIsNotNone(sig, "모든 게이트 통과 시 숏 신호가 나와야 함")
        self.assertEqual(sig.direction, "short")
        self.assertGreater(sig.sl_price, sig.entry_price)


class TestGates(unittest.TestCase):
    """각 게이트가 단독으로 신호를 차단하는지 — 베이스는 happy path."""

    def setUp(self):
        self.cfg = CfgStub()
        self.c4h = bullish_4h()
        # 베이스가 신호를 내는지 먼저 보장
        assert analyze(long_setup_15m(), self.cfg, self.c4h) is not None

    def test_low_volume_blocks(self):
        c15 = long_setup_15m(final_vol=10.0)   # 평균(100)의 10%
        self.assertIsNone(analyze(c15, self.cfg, self.c4h))

    def test_extension_cap_blocks(self):
        # EMA50(~100)에서 3% 위 = 103 → 추격 금지
        c15 = long_setup_15m(final_close=103.0)
        # 가드: 모멘텀 게이트(4%)가 먼저 발동하면 이 테스트는 추격금지를 검증 못 함
        momentum = abs(c15[-1]["close"] - c15[-4]["close"]) / c15[-4]["close"]
        self.assertLess(momentum, self.cfg.max_momentum_pct,
                        "셋업 변경으로 모멘텀 게이트가 먼저 발동 — 테스트 데이터 수정 필요")
        self.assertIsNone(analyze(c15, self.cfg, self.c4h))

    def test_chop_4h_blocks(self):
        c15 = long_setup_15m()
        self.assertIsNone(analyze(c15, self.cfg, flat_4h()))

    def test_wrong_regime_blocks(self):
        # 4H 하락 추세에서 롱 셋업 → 신호 없음
        c15 = long_setup_15m()
        self.assertIsNone(analyze(c15, self.cfg, bearish_4h()))

    def test_no_swing_break_blocks(self):
        # 종가가 스윙 하이(100.4) 아래 → 돌파 실패
        c15 = long_setup_15m(final_close=100.3)
        self.assertIsNone(analyze(c15, self.cfg, self.c4h))

    def test_volatility_gate_blocks(self):
        c15 = long_setup_15m()
        # 최근 20봉의 고저폭을 가격의 8%로 확대 → ATR 폭증
        for c in c15[-20:]:
            mid = c["close"]
            c["high"] = mid * 1.04
            c["low"] = mid * 0.96
        self.assertIsNone(analyze(c15, self.cfg, self.c4h))

    def test_insufficient_candles_blocks(self):
        c15 = long_setup_15m()[:100]
        self.assertIsNone(analyze(c15, self.cfg, self.c4h))
        self.assertIsNone(analyze(long_setup_15m(), self.cfg, self.c4h[:100]))


class TestSlBufferWidening(unittest.TestCase):
    """연속 손절 후 SL 버퍼 확대 — 손절가가 더 멀어져야 함."""

    def setUp(self):
        self.cfg = CfgStub()
        self.c4h = bullish_4h()

    def test_buffer_widens_after_losses(self):
        c15 = long_setup_15m()
        sig0 = analyze(c15, self.cfg, self.c4h, consecutive_losses=0)
        sig2 = analyze(c15, self.cfg, self.c4h, consecutive_losses=2)
        self.assertIsNotNone(sig0)
        self.assertIsNotNone(sig2)
        # 손절 2회 후 SL이 같거나 더 낮아야(멀어야) 함
        self.assertLessEqual(sig2.sl_price, sig0.sl_price)

    def test_buffer_capped(self):
        c15 = long_setup_15m()
        sig10 = analyze(c15, self.cfg, self.c4h, consecutive_losses=10)
        sig4 = analyze(c15, self.cfg, self.c4h, consecutive_losses=4)
        self.assertIsNotNone(sig10)
        # 버퍼 상한(0.3%)에서 멈춤 → 4회나 10회나 동일
        self.assertAlmostEqual(sig10.sl_price, sig4.sl_price, places=6)


class TestCurrentDirection(unittest.TestCase):
    """역신호 감지 — 2캔들 확인으로 휩쏘 방지."""

    def setUp(self):
        self.cfg = CfgStub()

    def _flat_then(self, closes_tail):
        """EMA50이 100 부근으로 수렴한 뒤 closes_tail로 마무리."""
        candles = [mk(100, 100.2, 99.8, 100.0, ts=i) for i in range(100)]
        for k, c in enumerate(closes_tail):
            candles.append(mk(c, c + 0.1, c - 0.1, c, ts=100 + k))
        return candles

    def test_two_closes_below_is_bearish(self):
        c15 = self._flat_then([99.0, 98.8])
        self.assertEqual(current_direction(c15, self.cfg, bearish_4h()), -1)

    def test_single_cross_is_neutral(self):
        # 마지막 1봉만 아래 → 휩쏘 가능성 → 0 (청산 보류)
        c15 = self._flat_then([100.5, 98.8])
        self.assertEqual(current_direction(c15, self.cfg, bearish_4h()), 0)

    def test_htf_disagreement_is_neutral(self):
        # 15M은 하락인데 4H는 상승 → 판단 보류
        c15 = self._flat_then([99.0, 98.8])
        self.assertEqual(current_direction(c15, self.cfg, bullish_4h()), 0)

    def test_two_closes_above_is_bullish(self):
        c15 = self._flat_then([101.2, 101.4])
        self.assertEqual(current_direction(c15, self.cfg, bullish_4h()), 1)

    def test_short_series_neutral(self):
        c15 = self._flat_then([99.0, 98.8])[:30]
        self.assertEqual(current_direction(c15, self.cfg, bearish_4h()), 0)


if __name__ == "__main__":
    unittest.main()
