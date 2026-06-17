"""
한국 주식 돌파 감지 — hanto-sear API 폴링
장중(09:05~15:30 KST) 5분마다 스캐너 API 체크 → 텔레그램 알림
별도 Railway 변수: HANTO_SEAR_URL
"""
import os
import logging
import threading
import time
import requests
from datetime import datetime, timezone, timedelta

import notify

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

HANTO_SEAR_URL = os.getenv("HANTO_SEAR_URL", "").rstrip("/")


class KRStockMonitor:
    def __init__(self):
        self._alerted: set = set()   # 당일 알림 보낸 종목 코드
        self._running = False
        self._last_reset = ""        # 날짜 바뀌면 _alerted 초기화

    def _is_market_hours(self) -> bool:
        now = datetime.now(KST)
        if now.weekday() >= 5:
            return False
        h, m = now.hour, now.minute
        return (h > 9 or (h == 9 and m >= 5)) and (h < 15 or (h == 15 and m <= 30))

    def _reset_daily(self):
        today = datetime.now(KST).strftime("%Y-%m-%d")
        if today != self._last_reset:
            self._alerted.clear()
            self._last_reset = today

    def _check(self):
        if not HANTO_SEAR_URL:
            return
        try:
            r = requests.get(f"{HANTO_SEAR_URL}/api/breakout-alerts", timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.debug("[KR주식] API 호출 실패: %s", e)
            return

        for alert in data.get("alerts", []):
            code = alert.get("code", "")
            if not code or code in self._alerted:
                continue
            self._alerted.add(code)
            grade    = alert.get("grade", "?")
            name     = alert.get("name", code)
            price    = alert.get("price", 0)
            pivot    = alert.get("pivot", 0)
            pct      = alert.get("pct_above", 0)
            chg      = alert.get("change_pct", 0)
            timing   = alert.get("timing", "")
            det_at   = alert.get("detected_at", "")
            notify.send(
                f"🔥 <b>한국주식 돌파 감지</b>  [{grade}등급]\n"
                f"종목: <b>{name}</b> ({code})\n"
                f"현재가: <b>{price:,}원</b>  ({'+' if chg>=0 else ''}{chg}%)\n"
                f"피봇: {pivot:,}원 초과  +{pct}%\n"
                f"셋업: {timing}  |  {det_at} 감지"
            )
            log.info("[KR주식] 🔥 텔레그램 알림 전송: %s (%s) +%s%%", name, code, pct)

    def _run(self):
        while self._running:
            self._reset_daily()
            if self._is_market_hours():
                self._check()
            time.sleep(300)  # 5분마다

    def start(self):
        if not HANTO_SEAR_URL:
            log.warning("[KR주식] HANTO_SEAR_URL 미설정 — 한국주식 모니터 비활성화")
            return
        if not self._running:
            self._running = True
            t = threading.Thread(target=self._run, daemon=True)
            t.start()
            log.info("[KR주식] 돌파 감지 모니터 시작 → %s", HANTO_SEAR_URL)

    def stop(self):
        self._running = False


kr_monitor = KRStockMonitor()
