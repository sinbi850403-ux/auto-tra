"""리포트 — 텔레그램 카드(notify.send 재사용) + CSV — DESIGN_KR_SURGE_SCANNER.md 제7부."""
from __future__ import annotations
from typing import List

from surge.surge_config import SurgeConfig
from surge.scanner import ScanResult, top_alerts


def format_alert_card(r: ScanResult) -> str:
    sign = "+" if r.change_pct >= 0 else ""
    reasons = "\n".join(f"   · {x}" for x in r.reasons)
    card = (f"[{r.grade}] <b>{r.name}</b> ({r.code})  {sign}{r.change_pct:.1f}%\n"
            f"   단기 {r.short_score:.0f} / 중기 {r.mid_score:.0f}")
    return f"{card}\n{reasons}" if reasons else card


def format_telegram(results: List[ScanResult], cfg: SurgeConfig, date_str: str) -> str:
    alerts = top_alerts(results, cfg)
    if not alerts:
        return f"🚀 <b>폭등 임박 스캔</b> — {date_str}\n조건 충족 종목 없음"
    lines = [f"🚀 <b>폭등 임박 스캔</b> — {date_str} (장마감)", "━━━━━━━━━━━━━━━━"]
    for r in alerts:
        lines.append(format_alert_card(r))
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("※ 발굴 알림 — 자동매매 아님. 투자 판단·책임은 본인.")
    return "\n".join(lines)


def send_report(results: List[ScanResult], cfg: SurgeConfig, date_str: str) -> None:
    import notify
    notify.send(format_telegram(results, cfg, date_str))


def save_csv(results: List[ScanResult], path: str) -> None:
    import pandas as pd
    rows = [{
        "code": r.code, "name": r.name, "market": r.market, "close": r.close,
        "change_pct": round(r.change_pct, 2), "value_krw": r.value_krw,
        "short": round(r.short_score, 1), "mid": round(r.mid_score, 1),
        "total": round(r.total_score, 1), "grade": r.grade,
        "reasons": " | ".join(r.reasons),
    } for r in results]
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
