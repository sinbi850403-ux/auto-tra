"""surge_config 단위 테스트 — 설계서 합의값 + 검증 로직."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from surge.surge_config import SurgeConfig


def test_default_validates():
    SurgeConfig().validate()  # 예외 없어야 함


def test_weights_sum_to_one():
    cfg = SurgeConfig()
    assert abs(sum(cfg.w_short.values()) - 1.0) < 1e-9
    assert abs(sum(cfg.w_mid.values()) - 1.0) < 1e-9


def test_grade_cut_descending():
    cfg = SurgeConfig()
    assert cfg.grade_cut["S"] > cfg.grade_cut["A"] > cfg.grade_cut["B"]


def test_labels_match_design():
    # 제0.3부 합의: 단기 10일/+20%, 중기 30일/+40%
    cfg = SurgeConfig()
    assert (cfg.short_K, cfg.short_X) == (10, 0.20)
    assert (cfg.mid_K, cfg.mid_X) == (30, 0.40)


def test_universe_gates_match_design():
    cfg = SurgeConfig()
    assert cfg.min_avg_value_krw == 1_000_000_000
    assert cfg.min_market_cap_krw == 30_000_000_000
    assert cfg.min_price == 1_000


def test_invalid_short_weights_rejected():
    cfg = SurgeConfig()
    cfg.w_short = {"F1": 0.5, "F2": 0.1, "F3": 0.1, "F4": 0.1}  # 합 0.8
    with pytest.raises(AssertionError):
        cfg.validate()


def test_invalid_grade_order_rejected():
    cfg = SurgeConfig()
    cfg.grade_cut = {"S": 50.0, "A": 70.0, "B": 55.0}  # S < A → 위배
    with pytest.raises(AssertionError):
        cfg.validate()


def test_configs_are_independent():
    """field(default_factory)로 인스턴스마다 독립 dict인지 (mutable default 버그 방지)."""
    a = SurgeConfig()
    b = SurgeConfig()
    key = next(iter(a.w_short))
    original = b.w_short[key]
    a.w_short[key] = 0.99
    assert b.w_short[key] == original
