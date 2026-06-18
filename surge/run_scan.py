"""일일 폭등 임박 스캔 진입점 — DESIGN_KR_SURGE_SCANNER.md 제1/8부.

데이터 수급은 전부 FinanceDataReader (KRX 직접 접근 pykrx는 해외 IP에서 차단됨).
StockListing으로 종목+시총+거래대금을 받아 1차 필터 → 통과 종목만 일봉 수급 → 스캔.

사용:  python -m surge.run_scan
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from surge.surge_config import SurgeConfig
from surge.datafeed import DataFeed
from surge.universe import StockMeta, prefilter_listings
from surge import scanner, report

log = logging.getLogger(__name__)


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
            listings = feed.fetch_stock_listing(market)        # FDR (pykrx 대체)
        except Exception as e:
            log.warning("[surge] %s 지수/종목 수급 실패: %s", market, e)
            continue

        candidates = prefilter_listings(listings, cfg)
        log.info("[surge] %s: 전체 %d → 1차필터 %d종목", market, len(listings), len(candidates))

        for it in candidates:
            try:
                candles = feed.get_candles(it["code"], start, end)
                if len(candles) < cfg.min_candles:
                    continue
                meta = StockMeta(code=it["code"], name=it["name"],
                                 market=market, market_cap=it["market_cap"])
                metas_candles.append((meta, candles))
            except Exception as e:
                log.debug("[surge] %s 일봉 수급 실패: %s", it["code"], e)

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
