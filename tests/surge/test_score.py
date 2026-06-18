"""score.py 단위 테스트 — 가중합/등급 경계/게이트."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge.score import combine_scores, grade_for, compute_score

CFG = SurgeConfig()
ALL = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]


def mk(o, h, l, c, v=100.0):
    return {"ts": 0, "open": o, "high": h, "low": l, "close": c, "volume": v}


def rising_series(n=260, step=0.01, vol=100.0):
    out, p = [], 1000.0
    for _ in range(n):
        p *= (1 + step)
        out.append(mk(p / (1 + step), p * 1.002, p * 0.998, p, vol))
    return out


def falling_series(n=260, step=0.01):
    out, p = [], 5000.0
    for _ in range(n):
        p *= (1 - step)
        out.append(mk(p / (1 - step), p * 1.002, p * 0.998, p, 100))
    return out


def flat_series(n=60, price=1000.0):
    return [mk(price, price * 1.01, price * 0.99, price + (i % 3 - 1) * 2, 100) for i in range(n)]


# ---------------- combine_scores ----------------
def test_combine_all_ones_caps_at_100():
    f = {k: 1.0 for k in ALL}
    short, mid, total = combine_scores(f, CFG)
    assert short == 100.0 and mid == 100.0
    assert total == 100.0  # max(100,100)+0.2*100 = 120 → 캡 100


def test_combine_short_only():
    f = {k: (1.0 if k in ("F1", "F2", "F3", "F4") else 0.0) for k in ALL}
    short, mid, total = combine_scores(f, CFG)
    assert short == 100.0 and mid == 0.0
    assert total == 100.0  # max(100,0)+0.2*0


def test_combine_weighted_single_factor():
    f = {k: (1.0 if k == "F1" else 0.0) for k in ALL}
    short, mid, total = combine_scores(f, CFG)
    assert abs(short - 30.0) < 1e-9   # w_short[F1]=0.30 → 30점
    assert mid == 0.0


def test_combine_zero():
    f = {k: 0.0 for k in ALL}
    assert combine_scores(f, CFG) == (0.0, 0.0, 0.0)


# ---------------- grade_for 경계 ----------------
def test_grade_boundaries():
    assert grade_for(85.0, CFG) == "S"
    assert grade_for(84.99, CFG) == "A"
    assert grade_for(70.0, CFG) == "A"
    assert grade_for(69.99, CFG) == "B"
    assert grade_for(55.0, CFG) == "B"
    assert grade_for(54.99, CFG) == "C"
    assert grade_for(0.0, CFG) == "C"


# ---------------- compute_score 통합 ----------------
def test_gate_fail_on_downtrend():
    r = compute_score(falling_series(260), CFG)
    assert r.passed_gate is False
    assert r.total_score == 0.0 and r.grade == "C"


def test_gate_fail_on_insufficient_data():
    r = compute_score(rising_series(50), CFG)
    assert r.passed_gate is False
    assert "데이터 부족" in r.reasons[0]


def test_strong_uptrend_passes_and_scores():
    r = compute_score(rising_series(260), CFG, index_candles=flat_series(260))
    assert r.passed_gate is True
    assert r.total_score > 0.0
    assert r.grade in ("S", "A", "B", "C")
    assert 0.0 <= r.short_score <= 100.0 and 0.0 <= r.mid_score <= 100.0


def test_reasons_are_human_readable():
    r = compute_score(rising_series(260), CFG, index_candles=flat_series(260))
    assert isinstance(r.reasons, list)
    for s in r.reasons:
        assert isinstance(s, str) and "(" in s  # "라벨 (0.93)" 형태
