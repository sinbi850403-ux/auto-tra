"""backtest.py 단위 테스트 — 라벨링/지표/분위/룩어헤드 봉인."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig
from surge.backtest import (
    label_surge, aggregate, decile_hit_rate, split_oos, check_pass,
    evaluate_symbol, run_backtest,
)


def mk(c, h=None, l=None, v=100.0, ts="20230101"):
    return {"ts": ts, "open": c, "high": c if h is None else h,
            "low": c if l is None else l, "close": c, "volume": v}


def rising_series(n=60, step=0.01, ts="20230101"):
    out, p = [], 1000.0
    for _ in range(n):
        p *= (1 + step)
        out.append(mk(p, p * 1.002, p * 0.998, 100.0, ts))
    return out


def rec(score, grade, label, mfe=0.1, mae=0.05, ts="20230101"):
    return {"t": 0, "ts": ts, "score": score, "grade": grade,
            "label": label, "mfe": mfe, "mae": mae}


# ---------------- label_surge ----------------
def test_label_hit_exact_threshold():
    # entry=100, K=3, X=0.2 → 미래 고가 max=120 → mfe=0.2 → label 1
    candles = [mk(100), mk(110, 110, 100), mk(100, 120, 95), mk(100, 115, 100)]
    r = label_surge(candles, 0, 3, 0.2)
    assert r.valid and r.label == 1
    assert abs(r.mfe - 0.20) < 1e-9
    assert abs(r.mae - 0.05) < 1e-9     # 미래 저가 min=95


def test_label_miss_just_below():
    candles = [mk(100), mk(110, 119, 100), mk(100, 118, 100), mk(100, 115, 100)]
    r = label_surge(candles, 0, 3, 0.2)
    assert r.label == 0 and abs(r.mfe - 0.19) < 1e-9


def test_label_invalid_when_future_short():
    candles = [mk(100), mk(110, 115, 100)]   # K=3 인데 미래 1봉뿐
    assert label_surge(candles, 0, 3, 0.2).valid is False


# ---------------- aggregate ----------------
def test_aggregate_base_rate_and_lift():
    cfg = SurgeConfig()  # alert_grades=("S","A")
    records = [rec(90, "S", 1), rec(88, "A", 1), rec(80, "A", 0),
               rec(40, "C", 0), rec(30, "C", 0), rec(20, "C", 0), rec(10, "C", 0)]
    agg = aggregate(records, cfg)
    assert abs(agg["base_rate"] - 2 / 7) < 1e-9        # 폭등 2건 / 7건
    assert abs(agg["top_precision"] - 2 / 3) < 1e-9    # S/A 3건 중 2건 적중
    assert abs(agg["lift"] - (2 / 3) / (2 / 7)) < 1e-9  # ≈ 2.33


def test_aggregate_empty_safe():
    agg = aggregate([], SurgeConfig())
    assert agg["n"] == 0 and agg["lift"] is None and agg["base_rate"] is None


def test_mfe_mae_ratio():
    cfg = SurgeConfig()
    records = [rec(50, "A", 1, mfe=0.30, mae=0.10), rec(50, "A", 0, mfe=0.10, mae=0.10)]
    agg = aggregate(records, cfg)
    assert abs(agg["avg_mfe"] - 0.20) < 1e-9
    assert abs(agg["avg_mae"] - 0.10) < 1e-9
    assert abs(agg["mfe_mae"] - 2.0) < 1e-9


# ---------------- decile ----------------
def test_decile_monotonic_increasing():
    records = [rec(i, "A", 1 if i >= 70 else 0) for i in range(100)]
    d = decile_hit_rate(records)
    assert d[0] == 0.0 and d[-1] == 1.0
    vals = [x for x in d if x is not None]
    assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))


# ---------------- split_oos / check_pass ----------------
def test_split_oos_by_date():
    records = [rec(50, "A", 1, ts="20231231"), rec(50, "A", 1, ts="20240101"),
               rec(50, "A", 0, ts="20250101")]
    ins, oos = split_oos(records, "20240101")
    assert len(ins) == 1 and len(oos) == 2


def test_check_pass_thresholds():
    cfg = SurgeConfig()  # pass_lift=2.0, pass_mfe_mae=1.5
    assert check_pass({"lift": 2.5, "mfe_mae": 1.8}, cfg) is True
    assert check_pass({"lift": 1.5, "mfe_mae": 1.8}, cfg) is False
    assert check_pass({"lift": 2.5, "mfe_mae": 1.0}, cfg) is False
    assert check_pass({"lift": None, "mfe_mae": None}, cfg) is False


# ---------------- 룩어헤드 봉인 (핵심) ----------------
def test_evaluate_symbol_score_ignores_future():
    """미래 캔들을 조작해도, 과거만 본 t의 점수는 불변이어야 한다 (시점 경계 증명)."""
    cfg = SurgeConfig(min_candles=40, short_K=3, short_X=0.2, bb_lookback=30)
    candles = rising_series(60)
    base = {r["t"]: r["score"] for r in evaluate_symbol(candles, cfg, "short")}

    tampered = [dict(c) for c in candles]
    for i in range(len(tampered) - 5, len(tampered)):       # 마지막 5봉 폭등 조작
        for k in ("open", "high", "low", "close"):
            tampered[i][k] *= 3
    after = {r["t"]: r["score"] for r in evaluate_symbol(tampered, cfg, "short")}

    for t in base:
        if t + 1 <= len(candles) - 5:        # 조작분이 점수 입력에 안 들어간 t만
            assert abs(base[t] - after[t]) < 1e-9


# ---------------- run_backtest 스모크 ----------------
def test_run_backtest_smoke():
    cfg = SurgeConfig(min_candles=40, short_K=3, short_X=0.2, bb_lookback=30,
                      oos_split_date="2024-01-01")
    sc = {
        "AAA": rising_series(60, ts="20230601"),   # In-sample 구간
        "BBB": rising_series(60, ts="20250601"),   # OOS 구간
    }
    res = run_backtest(sc, cfg, "short")
    assert res["track"] == "short"
    assert res["n_total"] > 0
    assert res["in_sample"]["n"] > 0 and res["out_sample"]["n"] > 0
    assert isinstance(res["passed"], bool)
