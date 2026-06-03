import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # --- API ---
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = field(default_factory=lambda: os.getenv("TESTNET", "true").lower() == "true")

    # --- 거래 대상 ---
    symbol: str = field(default_factory=lambda: os.getenv("SYMBOL", "BTCUSDT"))
    interval: str = "15"          # 15분봉 (진입 타이밍)
    htf_interval: str = "240"     # 4시간봉 (추세 방향)
    candle_limit: int = 300       # 캔들 수 (EMA200 계산에 충분)

    # --- 멀티 종목 스캐너 ---
    scan_symbols: list = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    ])

    # --- 레버리지 & 리스크 ---
    leverage: int = field(default_factory=lambda: int(os.getenv("LEVERAGE", "50")))
    risk_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PCT", "0.10")))
    sl_buffer_pct: float = 0.001  # SL 눌림저점 아래 0.1% 여유

    # --- TP 배율 (손절폭 기준) ---
    tp1_r: float = 1.0   # TP1: 손절폭 1배
    tp2_r: float = 2.0   # TP2: 손절폭 2배
    # TP3: EMA50 이탈 시 트레일링 청산 (지정가 없음)

    # --- EMA 파라미터 ---
    ema_fast: int = 50    # EMA50 (진입 기준선)
    ema_slow: int = 200   # EMA200 (추세 기준선)

    # --- 전략 필터 파라미터 ---
    ema_gap_min_pct: float = 0.005   # 4H EMA50/200 최소 간격 (0.5% 미만 = 횡보)
    ema_pullback_tol: float = 0.004  # EMA50 눌림 허용 오차 (0.4%)
    swing_lookback: int = 20         # 직전 고점/저점 탐색 캔들 수
    pullback_lookback: int = 10      # 눌림/반등 감지 캔들 수
    sl_max_pct: float = 0.05         # SL 최대 거리 5% 초과 시 진입 금지
    max_momentum_pct: float = 0.04   # 최근 3캔들 급등/급락 4% 초과 시 추격 금지

    # --- 실행 주기 ---
    check_interval_sec: int = 60  # 1분마다 신호 확인

    def validate(self):
        if not self.api_key or not self.api_secret:
            raise ValueError("BYBIT_API_KEY / BYBIT_API_SECRET 환경변수가 설정되지 않았습니다.")
        if self.risk_pct > 0.20:
            import logging
            logging.getLogger(__name__).warning(
                "RISK_PCT=%.0f%% — 1회 리스크가 높습니다. 5~10%% 권장.", self.risk_pct * 100
            )
