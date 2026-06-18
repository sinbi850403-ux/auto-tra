"""factors.py 단위 테스트 — 합성 캔들로 각 팩터의 방향성 + 룩어헤드 봉인."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge import factors

CFG = SurgeConfig()


def mk(o, h, l, c, v=100.0):
    return {"ts": 0, "open": o, "high": h, "low": l, "close": c, "volume": v}


# ---------------- 합성 캔들 생성기 ----------------
def squeeze_series(n=160):
    """변동성이 단계적으로 축소되는 시리즈 (마지막 밴드폭이 최저)."""
    out = []
    p = 1000.0
    for i in range(n):
        amp = max(1.0, 50.0 * (1 - i / n))
        c = p + (amp * 0.2 if i % 2 else -amp * 0.2)
        out.append(mk(p, p + amp, p - amp, c, 100))
    return out


def constant_vol_series(n=160):
    """변동성이 일정한 시리즈 (압축 아님)."""
    return [mk(1000, 1020, 980, 1000 + (i % 2) * 4, 100) for i in range(n)]


def rising_series(n=260, step=0.01, vol=100.0):
    out = []
    p = 1000.0
    for _ in range(n):
        p *= (1 + step)
        out.append(mk(p / (1 + step), p * 1.002, p * 0.998, p, vol))
    return out


def falling_series(n=260, step=0.01):
    out = []
    p = 5000.0
    for _ in range(n):
        p *= (1 - step)
        out.append(mk(p / (1 - step), p * 1.002, p * 0.998, p, 100))
    return out


def flat_series(n=60, price=1000.0):
    return [mk(price, price * 1.01, price * 0.99, price + (i % 3 - 1) * 2, 100) for i in range(n)]


# ---------------- F1 변동성 수축 ----------------
def test_f1_high_on_squeeze():
    assert factors.f1_volatility_contraction(squeeze_series(), CFG) > 0.7


def test_f1_low_on_constant_vol():
    assert factors.f1_volatility_contraction(constant_vol_series(), CFG) < 0.3


# ---------------- F2 거래량 마름→점화 ----------------
def test_f2_high_on_dryup_then_burst():
    candles = [mk(1000, 1010, 990, 1000, 200) for _ in range(40)]      # 과거 활발
    candles += [mk(1000, 1003, 997, 1000, 40) for _ in range(39)]      # 최근 마름
    candles.append(mk(1000, 1060, 1000, 1050, 250))                    # 폭발
    assert factors.f2_volume_dryup_ignition(candles, CFG) > 0.6


def test_f2_low_on_steady_volume():
    candles = [mk(1000, 1005, 995, 1000, 100) for _ in range(80)]
    assert factors.f2_volume_dryup_ignition(candles, CFG) < 0.3


# ---------------- F3 박스 상단 근접 ----------------
def _box(last_close):
    out = [mk(950, 1000, 900, 950, 100) for _ in range(65)]  # 박스 상단 1000
    out.append(mk(last_close, last_close + 5, last_close - 5, last_close, 100))
    return out


def test_f3_high_near_box_top():
    assert factors.f3_box_breakout_proximity(_box(985), CFG) > 0.5


def test_f3_low_mid_box():
    assert factors.f3_box_breakout_proximity(_box(900), CFG) < 0.2


def test_f3_low_when_chasing():
    # 박스 상단(1000) 대비 +10% 추격 구간
    assert factors.f3_box_breakout_proximity(_box(1100), CFG) < 0.2


# ---------------- F4 모멘텀 ----------------
def test_f4_high_on_uptrend():
    assert factors.f4_momentum_ignition(rising_series(40), CFG) >= 0.5


def test_f4_low_on_downtrend():
    assert factors.f4_momentum_ignition(falling_series(40), CFG) < 0.3


# ---------------- F5 베이스 성숙도 ----------------
def test_f5_high_on_long_flat():
    assert factors.f5_base_maturity(flat_series(60), CFG) > 0.5


def test_f5_low_on_volatile():
    out = []
    p = 1000.0
    for i in range(60):
        p *= 1.2 if i % 2 else 0.83   # ±20% 출렁 → 베이스 아님
        out.append(mk(p, p, p, p, 100))
    assert factors.f5_base_maturity(out, CFG) < 0.3


# ---------------- F6 상대강도 ----------------
def test_f6_high_when_beats_index():
    stock = rising_series(65, step=0.005)   # +약 38%
    index = flat_series(65)
    assert factors.f6_relative_strength(stock, index, CFG) > 0.6


def test_f6_low_when_lags_index():
    stock = flat_series(65)
    index = rising_series(65, step=0.005)
    assert factors.f6_relative_strength(stock, index, CFG) < 0.4


# ---------------- F7 추세 토대 ----------------
def test_f7_high_on_strong_uptrend():
    assert factors.f7_trend_foundation(rising_series(260), CFG) > 0.8


def test_f7_low_on_downtrend():
    assert factors.f7_trend_foundation(falling_series(260), CFG) < 0.2


# ---------------- F8 수급 매집 ----------------
def test_f8_high_on_accumulation():
    # 가격 횡보, 상승일 거래량(300) > 하락일(100) → OBV 매집
    out = []
    for i in range(40):
        if i % 2:
            out.append(mk(1000, 1006, 995, 1002, 300))
        else:
            out.append(mk(1002, 1006, 995, 1000, 100))
    assert factors.f8_supply_accumulation(out, CFG) > 0.3


def test_f8_low_on_distribution():
    # 가격 횡보, 하락일 거래량(300) > 상승일(100) → OBV 분배
    out = []
    for i in range(40):
        if i % 2:
            out.append(mk(1000, 1006, 995, 1002, 100))
        else:
            out.append(mk(1002, 1006, 995, 1000, 300))
    assert factors.f8_supply_accumulation(out, CFG) == 0.0


# ---------------- 룩어헤드 봉인 ----------------
def test_no_lookahead_compute_factors():
    """candles[:t]가 같으면 t 이후 캔들을 어떻게 바꾸든 점수가 동일해야 한다."""
    candles = rising_series(160)
    t = 130
    base = factors.compute_factors(candles[:t], CFG)
    tampered = [dict(c) for c in candles]
    for i in range(t, len(tampered)):       # 미래를 폭등으로 조작
        for k in ("open", "high", "low", "close"):
            tampered[i][k] *= 5
        tampered[i]["volume"] *= 10
    after = factors.compute_factors(tampered[:t], CFG)
    assert base == after


def test_compute_factors_does_not_mutate_input():
    candles = rising_series(120)
    snapshot = [dict(c) for c in candles]
    factors.compute_factors(candles, CFG)
    assert candles == snapshot


def test_all_factors_in_unit_range():
    for series in (squeeze_series(), rising_series(260), falling_series(260), flat_series(60)):
        f = factors.compute_factors(series, CFG, index_candles=flat_series(260))
        for k, v in f.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of range"
