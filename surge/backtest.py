"""백테스트 검증 — DESIGN_KR_SURGE_SCANNER.md 제5부.

핵심 원칙(룩어헤드 차단): 평가일 t의 점수는 candles[:t+1]로만 계산하고,
폭등 라벨은 candles[t+1:] (미래)로만 계산한다. 이 경계를 evaluate_symbol에서
코드로 강제하며 test_backtest.py가 봉인한다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple

from surge.surge_config import SurgeConfig
from surge.score import compute_score


@dataclass
class LabelResult:
    label: int          # 1=폭등(미래 K봉 내 +X% 도달)
    mfe: float          # 최대 상승률 (entry 기준, 양수)
    mae: float          # 최대 하락률 (entry 기준, 양수 절댓값)
    valid: bool         # 미래 K봉이 확보됐는가


def label_surge(candles: list, t: int, K: int, X: float) -> LabelResult:
    """t 시점 종가 기준, 향후 K거래일 내 고가가 +X% 이상이면 label=1. MFE/MAE 동반."""
    entry = candles[t]["close"]
    future = candles[t + 1: t + 1 + K]
    if entry <= 0 or len(future) < K:
        return LabelResult(0, 0.0, 0.0, False)
    mfe = max(c["high"] for c in future) / entry - 1.0
    mae = 1.0 - min(c["low"] for c in future) / entry
    # 경계(정확히 +X%) 도달도 폭등으로 인정 — 부동소수점 누락 방지
    return LabelResult(1 if mfe >= X - 1e-9 else 0, mfe, mae, True)


def _track_params(cfg: SurgeConfig, track: str) -> Tuple[int, float]:
    return (cfg.short_K, cfg.short_X) if track == "short" else (cfg.mid_K, cfg.mid_X)


def evaluate_symbol(candles: list, cfg: SurgeConfig, track: str = "short",
                    index_candles: Optional[list] = None,
                    step: int = 1, start: Optional[int] = None) -> List[dict]:
    """한 종목 시계열을 훑으며 (t, score, grade, label, mfe, mae) 레코드 생성.
    점수는 candles[:t+1], 라벨은 미래 — 시점 경계를 여기서 강제한다."""
    K, _X = _track_params(cfg, track)
    X = _X
    start = cfg.min_candles if start is None else start
    out: List[dict] = []
    for t in range(start, len(candles) - K):
        lab = label_surge(candles, t, K, X)
        if not lab.valid:
            continue
        pit = candles[:t + 1]                         # 신호일까지만!
        idx_pit = index_candles[:t + 1] if index_candles else None
        sr = compute_score(pit, cfg, idx_pit)
        score = sr.short_score if track == "short" else sr.mid_score
        out.append({
            "t": t, "ts": candles[t].get("ts", ""), "score": score,
            "grade": sr.grade, "label": lab.label, "mfe": lab.mfe, "mae": lab.mae,
        })
    return out[::step] if step > 1 else out


def _mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def decile_hit_rate(records: List[dict]) -> List[Optional[float]]:
    """점수 오름차순 10분위별 폭등 적중률. 건강하면 우상향(단조 증가)."""
    rs = sorted(records, key=lambda r: r["score"])
    n = len(rs)
    out: List[Optional[float]] = []
    for d in range(10):
        seg = rs[d * n // 10:(d + 1) * n // 10]
        out.append(_mean([x["label"] for x in seg]) if seg else None)
    return out


def aggregate(records: List[dict], cfg: SurgeConfig) -> dict:
    """레코드 집계 → base_rate / 등급별 precision / lift / 분위 / MFE·MAE."""
    n = len(records)
    if n == 0:
        return {"n": 0, "base_rate": None, "top_precision": None, "lift": None,
                "grade_precision": {}, "deciles": [], "avg_mfe": None,
                "avg_mae": None, "mfe_mae": None}
    base_rate = sum(r["label"] for r in records) / n
    grade_prec = {}
    for g in ("S", "A", "B", "C"):
        gr = [r for r in records if r["grade"] == g]
        grade_prec[g] = (sum(r["label"] for r in gr) / len(gr), len(gr)) if gr else (None, 0)
    top = [r for r in records if r["grade"] in cfg.alert_grades]
    top_prec = sum(r["label"] for r in top) / len(top) if top else None
    lift = (top_prec / base_rate) if (top_prec is not None and base_rate > 0) else None
    avg_mfe = _mean([r["mfe"] for r in records])
    avg_mae = _mean([r["mae"] for r in records])
    mfe_mae = (avg_mfe / avg_mae) if (avg_mae and avg_mae > 0) else None
    return {"n": n, "base_rate": base_rate, "top_precision": top_prec, "lift": lift,
            "grade_precision": grade_prec, "deciles": decile_hit_rate(records),
            "avg_mfe": avg_mfe, "avg_mae": avg_mae, "mfe_mae": mfe_mae}


def _to_yyyymmdd(date_str: str) -> str:
    return date_str.replace("-", "")


def split_oos(records: List[dict], split_yyyymmdd: str) -> Tuple[List[dict], List[dict]]:
    ins = [r for r in records if str(r["ts"]) < split_yyyymmdd]
    oos = [r for r in records if str(r["ts"]) >= split_yyyymmdd]
    return ins, oos


def check_pass(oos_agg: dict, cfg: SurgeConfig) -> bool:
    """OOS 통과 기준: lift ≥ pass_lift AND MFE/MAE ≥ pass_mfe_mae."""
    lift = oos_agg.get("lift")
    mfe_mae = oos_agg.get("mfe_mae")
    return (lift is not None and lift >= cfg.pass_lift
            and mfe_mae is not None and mfe_mae >= cfg.pass_mfe_mae)


def run_backtest(symbol_candles: dict, cfg: SurgeConfig, track: str = "short",
                 index_candles: Optional[list] = None) -> dict:
    """전종목 워크포워드 백테스트 → In/OOS 집계 + 통과 여부.
    symbol_candles: {code: candles}."""
    K, _ = _track_params(cfg, track)
    all_records: List[dict] = []
    for code, candles in symbol_candles.items():
        if len(candles) < cfg.min_candles + K:
            continue
        recs = evaluate_symbol(candles, cfg, track, index_candles)
        for r in recs:
            r["code"] = code
        all_records.extend(recs)
    ins, oos = split_oos(all_records, _to_yyyymmdd(cfg.oos_split_date))
    oos_agg = aggregate(oos, cfg)
    return {"track": track, "n_total": len(all_records),
            "in_sample": aggregate(ins, cfg), "out_sample": oos_agg,
            "passed": check_pass(oos_agg, cfg), "records": all_records}
