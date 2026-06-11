"""indicators.py 단위 테스트 — EMA / ATR / RSI / ADX / 스윙 고저점.

순수 표준 라이브러리(unittest)로 작성 — pytest로도 실행 가능.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators import ema, atr, rsi, adx, swing_high, swing_low


def mk(o, h, l, c, v=100.0, ts=0):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def up_trend_candles(n=60, start=100.0, step=1.0):
    """봉마다 고/저/종가가 step씩 꾸준히 오르는 강한 상승 추세."""
    out = []
    for i in range(n):
        base = start + i * step
        out.append(mk(base, base + 1.0, base - 0.2, base + 0.8, ts=i))
    return out


def zigzag_candles(n=60, center=100.0, amp=2.0):
    """위아래로 똑같이 흔들리는 횡보(추세 없음)."""
    out = []
    for i in range(n):
        if i % 2 == 0:
            out.append(mk(center, center + amp, center - 0.5, center + amp * 0.8, ts=i))
        else:
            out.append(mk(center + amp * 0.8, center + 0.5, center - amp, center - amp * 0.8, ts=i))
    return out


class TestEma(unittest.TestCase):
    def test_constant_series(self):
        vals = [50.0] * 30
        out = ema(vals, 10)
        self.assertEqual(len(out), 30)
        for v in out:
            self.assertAlmostEqual(v, 50.0)

    def test_tracks_rising_series_below_price(self):
        vals = [float(i) for i in range(1, 101)]
        out = ema(vals, 20)
        self.assertLess(out[-1], vals[-1])      # EMA는 상승 시 가격 아래
        self.assertGreater(out[-1], out[-30])   # 그래도 우상향


class TestAtr(unittest.TestCase):
    def test_length_and_positive(self):
        candles = up_trend_candles(50)
        out = atr(candles, 14)
        self.assertEqual(len(out), 50)
        self.assertTrue(all(v > 0 for v in out))

    def test_constant_range(self):
        # 모든 봉의 진폭이 1.2 → ATR ≈ 1.2 수렴
        candles = up_trend_candles(100)
        out = atr(candles, 14)
        self.assertAlmostEqual(out[-1], 1.2, delta=0.15)


class TestRsi(unittest.TestCase):
    def test_length_matches(self):
        vals = [100.0 + i * 0.5 for i in range(40)]
        self.assertEqual(len(rsi(vals, 14)), 40)

    def test_all_up_is_100(self):
        vals = [100.0 + i for i in range(40)]
        self.assertAlmostEqual(rsi(vals, 14)[-1], 100.0)

    def test_all_down_is_0(self):
        vals = [100.0 - i for i in range(40)]
        self.assertAlmostEqual(rsi(vals, 14)[-1], 0.0)

    def test_flat_is_50(self):
        vals = [100.0] * 40
        self.assertAlmostEqual(rsi(vals, 14)[-1], 50.0)

    def test_balanced_zigzag_near_50(self):
        vals = []
        for i in range(60):
            vals.append(100.0 + (1.0 if i % 2 == 0 else 0.0))
        r = rsi(vals, 14)[-1]
        self.assertGreater(r, 40.0)
        self.assertLess(r, 60.0)

    def test_short_series_neutral(self):
        self.assertEqual(rsi([100.0, 101.0], 14), [50.0, 50.0])


class TestAdx(unittest.TestCase):
    def test_length_matches(self):
        candles = up_trend_candles(80)
        self.assertEqual(len(adx(candles, 14)), 80)

    def test_strong_trend_high_adx(self):
        candles = up_trend_candles(80)
        self.assertGreater(adx(candles, 14)[-1], 25.0)

    def test_chop_low_adx(self):
        candles = zigzag_candles(80)
        self.assertLess(adx(candles, 14)[-1], 20.0)

    def test_bounds(self):
        for candles in (up_trend_candles(80), zigzag_candles(80)):
            for v in adx(candles, 14):
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 100.0)

    def test_short_series_zero(self):
        candles = up_trend_candles(10)
        self.assertEqual(adx(candles, 14), [0.0] * 10)


class TestSwing(unittest.TestCase):
    def test_swing_high_excludes_current(self):
        candles = up_trend_candles(30)
        # 마지막(현재) 봉 제외한 직전 20봉의 최고가
        expect = max(c["high"] for c in candles[-21:-1])
        self.assertEqual(swing_high(candles, 20), expect)

    def test_swing_low_excludes_current(self):
        candles = up_trend_candles(30)
        expect = min(c["low"] for c in candles[-21:-1])
        self.assertEqual(swing_low(candles, 20), expect)


if __name__ == "__main__":
    unittest.main()
