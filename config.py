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
    interval: str = "15"          # 15분봉
    candle_limit: int = 300       # 전략 계산에 필요한 캔들 수

    # --- 레버리지 & 리스크 ---
    leverage: int = field(default_factory=lambda: int(os.getenv("LEVERAGE", "20")))
    risk_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PCT", "0.20")))
    rr_ratio: float = 2.0         # 손익비 1:2
    sl_buffer_pct: float = 0.002  # SL을 오더블록 경계보다 0.2% 더 여유

    # --- EMA 파라미터 ---
    ema_fast: int = 20
    ema_slow: int = 50
    ema_trend: int = 200

    # --- 오더블록 파라미터 ---
    ob_lookback: int = 50         # 오더블록 탐색 범위 (캔들 수)
    ob_body_ratio: float = 0.6    # 몸통이 전체 범위의 60% 이상이면 강한 캔들

    # --- 피보나치 파라미터 ---
    fib_swing_lookback: int = 50  # 스윙 고/저점 탐색 범위
    fib_entry_low: float = 0.618
    fib_entry_high: float = 0.786

    # --- 실행 주기 ---
    check_interval_sec: int = 60  # 1분마다 신호 확인

    def validate(self):
        if not self.api_key or not self.api_secret:
            raise ValueError("BYBIT_API_KEY / BYBIT_API_SECRET 환경변수가 설정되지 않았습니다.")
        if self.risk_pct > 0.20:
            import logging
            logging.getLogger(__name__).warning(
                "RISK_PCT=%.0f%% — 1회 리스크가 매우 높습니다. 1~5%% 권장.", self.risk_pct * 100
            )
