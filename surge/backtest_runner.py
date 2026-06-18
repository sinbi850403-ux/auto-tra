"""실데이터 워크포워드 백테스트 러너 — DESIGN_KR_SURGE_SCANNER.md 제5부 / T9·P4 게이트.

핵심 로직(evaluate_symbol/aggregate/split_oos)은 test_backtest.py에서 검증됨.
이 모듈은 네트워크 수급 + 집계 오케스트레이션 (run_scan과 동일 성격, 러너로 격리).

사용:  python -m surge.backtest_runner
"""
from __future__ import annotations
import logging
from typing import List, Tuple

from surge.surge_config import SurgeConfig
from surge.datafeed import DataFeed
from surge.backtest import (
    evaluate_symbol, aggregate, split_oos, check_pass, _to_yyyymmdd, _track_params,
)

log = logging.getLogger(__name__)

# 대표 표본 (코스피 대형 + 코스닥 변동성주). 생존편향 한계는 리포트에 명시.
SYMBOLS: List[Tuple[str, str]] = [
    # KOSPI
    ("005930", "KOSPI"), ("000660", "KOSPI"), ("005380", "KOSPI"), ("005490", "KOSPI"),
    ("035420", "KOSPI"), ("035720", "KOSPI"), ("051910", "KOSPI"), ("006400", "KOSPI"),
    ("207940", "KOSPI"), ("068270", "KOSPI"), ("012330", "KOSPI"), ("066570", "KOSPI"),
    ("003670", "KOSPI"), ("096770", "KOSPI"), ("015760", "KOSPI"), ("055550", "KOSPI"),
    # KOSDAQ
    ("247540", "KOSDAQ"), ("086520", "KOSDAQ"), ("066970", "KOSDAQ"), ("028300", "KOSDAQ"),
    ("196170", "KOSDAQ"), ("263750", "KOSDAQ"), ("293490", "KOSDAQ"), ("240810", "KOSDAQ"),
    ("058470", "KOSDAQ"), ("112040", "KOSDAQ"), ("095340", "KOSDAQ"), ("357780", "KOSDAQ"),
]


def run_real_backtest(cfg: SurgeConfig, start: str, end: str,
                      symbols=None, step: int = 2, tracks=("short", "mid")) -> dict:
    symbols = symbols or SYMBOLS
    feed = DataFeed(cfg)
    idx = {}
    for m in cfg.markets:
        try:
            idx[m] = feed.fetch_index(m, start, end)
        except Exception as e:
            log.warning("지수 수급 실패 %s: %s", m, e)
            idx[m] = None

    symbol_candles, market_of = {}, {}
    need = cfg.min_candles + max(cfg.short_K, cfg.mid_K)
    for code, market in symbols:
        try:
            c = feed.fetch_ohlcv(code, start, end)
        except Exception as e:
            log.warning("수급 실패 %s: %s", code, e)
            continue
        if len(c) >= need:
            symbol_candles[code] = c
            market_of[code] = market

    out = {"n_symbols": len(symbol_candles), "tracks": {}}
    for track in tracks:
        recs = []
        for code, c in symbol_candles.items():
            rr = evaluate_symbol(c, cfg, track, idx.get(market_of[code]), step=step)
            for r in rr:
                r["code"] = code
            recs += rr
        ins, oos = split_oos(recs, _to_yyyymmdd(cfg.oos_split_date))
        oos_agg = aggregate(oos, cfg)
        out["tracks"][track] = {
            "n": len(recs), "in": aggregate(ins, cfg), "oos": oos_agg,
            "passed": check_pass(oos_agg, cfg),
        }
    return out


def _fmt(x, pct=False):
    if x is None:
        return "n/a"
    return f"{x * 100:.1f}%" if pct else f"{x:.2f}"


def format_report(out: dict, cfg: SurgeConfig) -> str:
    lines = [
        "# 폭등 임박 백테스트 리포트",
        f"- 표본 종목: {out['n_symbols']}개 | OOS 기준일: {cfg.oos_split_date}",
        f"- 통과선: lift ≥ {cfg.pass_lift}, MFE/MAE ≥ {cfg.pass_mfe_mae}",
        "- ⚠️ 생존편향: 현존 종목 표본 → 낙관 편향 가능. 개념 검증용.",
        "",
    ]
    for track, d in out["tracks"].items():
        K, X = _track_params(cfg, track)
        i, o = d["in"], d["oos"]
        lines += [
            f"## {track} 트랙  (K={K}일, X=+{X * 100:.0f}%)",
            f"- 평가 표본: {d['n']}  (In {i['n']} / OOS {o['n']})",
            f"- Base rate: In {_fmt(i['base_rate'], True)} / OOS {_fmt(o['base_rate'], True)}",
            f"- Top(S/A) precision (OOS): {_fmt(o['top_precision'], True)}",
            f"- **Lift (OOS): {_fmt(o['lift'])}**  / In {_fmt(i['lift'])}",
            f"- MFE/MAE (OOS): {_fmt(o['mfe_mae'])}",
            f"- 분위 적중률 OOS(낮은점수→높은점수): "
            + ", ".join(_fmt(x, True) for x in o["deciles"]),
            f"- 통과: {'✅ PASS' if d['passed'] else '❌ FAIL'}",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _cfg = SurgeConfig()
    _out = run_real_backtest(_cfg, "2019-01-01", "2026-06-01")
    _report = format_report(_out, _cfg)
    print(_report)
    with open("backtest_report.md", "w", encoding="utf-8") as f:
        f.write(_report)
