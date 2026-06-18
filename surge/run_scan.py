"""일일 폭등 임박 스캔 진입점 — DESIGN_KR_SURGE_SCANNER.md 제1/8부.

실제 네트워크 수급을 묶는 오케스트레이션. 단위테스트는 scanner/report 쪽에서 하고,
이 모듈의 실행 검증은 T9(실데이터 백테스트/스캔)에서 한다.

사용:  python -m surge.run_scan
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from surge.surge_config import SurgeConfig
from surge.datafeed import DataFeed
from surge.universe import StockMeta
from surge import scanner, report

log = logging.getLogger(__name__)


def _build_meta(code: str, market: str, feed: DataFeed, cap_df) -> StockMeta:
    """시총·관리종목 등 메타 구성. 관리/ETF/스팩 플래그는 T9에서 KRX 소스로 보강 예정."""
    name = ""
    market_cap = 0.0
    try:
        from pykrx import stock
        name = stock.get_market_ticker_name(code)
    except Exception:
        pass
    try:
        if cap_df is not None and code in cap_df.index:
            market_cap = float(cap_df.loc[code, "시가총액"])
    except Exception:
        pass
    return StockMeta(code=code, name=name or code, market=market, market_cap=market_cap)


def run_daily_scan(cfg: Optional[SurgeConfig] = None) -> list:
    cfg = cfg or SurgeConfig()
    feed = DataFeed(cfg)
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=cfg.history_years * 365)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y%m%d")

    metas_candles = []
    index_by_market = {}
    for market in cfg.markets:
        try:
            index_by_market[market] = feed.fetch_index(market, start, end)
            cap_df = feed.fetch_market_cap(today)
            codes = feed.fetch_ticker_list(market)
        except Exception as e:
            log.warning("[surge] %s 메타/지수 수급 실패: %s", market, e)
            continue
        for code in codes:
            try:
                candles = feed.get_candles(code, start, end)
                if len(candles) < cfg.min_candles:
                    continue
                meta = _build_meta(code, market, feed, cap_df)
                metas_candles.append((meta, candles))
            except Exception as e:
                log.debug("[surge] %s 수급 실패: %s", code, e)

    results = scanner.scan_universe(metas_candles, cfg, index_by_market)
    date_str = datetime.now().strftime("%Y-%m-%d")
    report.send_report(results, cfg, date_str)
    report.save_csv(results, f"scan_{today}.csv")
    log.info("[surge] 스캔 완료 — 후보 %d종목, 알림 %d종목",
             len(results), len(scanner.top_alerts(results, cfg)))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_daily_scan()
