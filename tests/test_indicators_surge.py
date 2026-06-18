"""indicators.py 확장 함수 테스트 — surge 스캐너용 sma / obv / percentile_rank."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators import sma, obv, percentile_rank


def mk(c, v=100.0):
    return {"ts": 0, "open": c, "high": c, "low": c, "close": c, "volume": v}


# ---------------- SMA ----------------
def test_sma_constant():
    assert sma([5.0] * 10, 3)[-1] == 5.0


def test_sma_length_matches():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert len(sma(vals, 3)) == len(vals)


def test_sma_value():
    # 마지막 3개 평균 = (3+4+5)/3 = 4
    assert sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)[-1] == 4.0


def test_sma_warmup_partial_average():
    # 첫 값은 자기 자신
    assert sma([10.0, 20.0], 5)[0] == 10.0


# ---------------- OBV ----------------
def test_obv_rising_accumulates():
    candles = [mk(10, 100), mk(11, 100), mk(12, 100)]  # 계속 상승
    assert obv(candles) == [0.0, 100.0, 200.0]


def test_obv_falling_subtracts():
    candles = [mk(12, 100), mk(11, 100), mk(10, 100)]  # 계속 하락
    assert obv(candles) == [0.0, -100.0, -200.0]


def test_obv_flat_holds():
    candles = [mk(10, 100), mk(10, 100)]  # 보합
    assert obv(candles) == [0.0, 0.0]


def test_obv_accumulation_divergence():
    # 상승일 거래량(500) > 하락일 거래량(100) → 가격 제자리여도 OBV 순매집(+)
    candles = [mk(10, 100), mk(11, 500), mk(10, 100), mk(11, 500)]
    assert obv(candles)[-1] > 0


# ---------------- percentile_rank ----------------
def test_pct_rank_lowest():
    assert percentile_rank(1, [1, 2, 3, 4, 5]) == 0.2  # 자신만 <=1


def test_pct_rank_highest():
    assert percentile_rank(5, [1, 2, 3, 4, 5]) == 1.0


def test_pct_rank_median():
    assert percentile_rank(3, [1, 2, 3, 4, 5]) == 0.6  # 1,2,3 <=3


def test_pct_rank_empty_neutral():
    assert percentile_rank(5, []) == 0.5


def test_pct_rank_squeeze_logic():
    # F1: 현재 밴드폭이 최저면 1-rank ≈ 1 (강한 압축)
    bw = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1.0]  # 마지막이 최저
    score = 1 - percentile_rank(bw[-1], bw)
    assert score >= 0.8
