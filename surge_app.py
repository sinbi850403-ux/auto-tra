"""한국주식 폭등 임박 스캐너 전용 진입점 — Railway worker (코인봇 main.py와 분리).

Railway Start Command:  python surge_app.py

- 코인봇(BYBIT) 의존 없음 — BYBIT 키 불필요.
- TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 있으면 알림 발송 (없으면 조용히 미발송).
- 매일 장마감 후(SURGE_SCAN_HOUR, 기본 16시 KST) 전종목 스캔 → 점수 상위 10% 텔레그램.
"""
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("surge_app")

from surge_monitor import surge_monitor


def main():
    log.info("=== 한국주식 폭등 임박 스캐너 시작 (surge 전용) ===")
    surge_monitor.start(force=True)      # 전용 진입점 — 항상 활성
    log.info("일일 스캔 대기 중 — 장마감 후 자동 실행")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
