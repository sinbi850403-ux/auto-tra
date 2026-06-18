"""폭등 임박 일일 스캔 모니터 — 장마감 후 1회 전종목 스캔 → 텔레그램.

main.py에서 surge_monitor.start()로 백그라운드 스레드 시작 (kr_stock_monitor 패턴).
SURGE_ENABLED=true 환경변수일 때만 활성화 (검증 후 의식적 투입 안전장치).
일봉 기반이라 장중 폴링 불필요 — 장마감 후 하루 1회면 충분.
"""
import os
import logging
import threading
import time
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

SURGE_ENABLED = os.getenv("SURGE_ENABLED", "false").lower() == "true"
SCAN_HOUR = int(os.getenv("SURGE_SCAN_HOUR", "16"))   # 장마감(15:30) 후 16시


class SurgeMonitor:
    def __init__(self):
        self._running = False
        self._last_scan_date = ""      # 같은 날 중복 스캔 방지

    def _should_scan(self, now: datetime = None) -> bool:
        """평일 + 장마감 후(SCAN_HOUR 이후) + 오늘 아직 안 했으면 True."""
        now = now or datetime.now(KST)
        if now.weekday() >= 5:                       # 주말
            return False
        if now.strftime("%Y-%m-%d") == self._last_scan_date:
            return False
        return now.hour >= SCAN_HOUR

    def _run(self):
        from surge import run_scan
        while self._running:
            try:
                if self._should_scan():
                    self._last_scan_date = datetime.now(KST).strftime("%Y-%m-%d")
                    log.info("[폭등스캔] 일일 전종목 스캔 시작")
                    run_scan.run_daily_scan()
                    log.info("[폭등스캔] 완료")
            except Exception as e:
                log.warning("[폭등스캔] 실패: %s", e)
            time.sleep(600)                          # 10분마다 시각 체크

    def start(self, force: bool = False):
        """force=True면 SURGE_ENABLED 무관하게 켠다 (surge_app.py 전용 진입점용)."""
        if not (force or SURGE_ENABLED):
            log.info("[폭등스캔] SURGE_ENABLED 미설정 — 비활성화")
            return
        if not self._running:
            self._running = True
            threading.Thread(target=self._run, daemon=True).start()
            log.info("[폭등스캔] 일일 스캔 모니터 시작 (장마감 후 %d시 KST)", SCAN_HOUR)

    def stop(self):
        self._running = False


surge_monitor = SurgeMonitor()
