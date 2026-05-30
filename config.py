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

    # --- 멀티 종목 스캐너 ---
    scan_symbols: list = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    ])

    # --- 레버리지 & 리스크 ---
    leverage: int = field(default_factory=lambda: int(os.getenv("LEVERAGE", "20")))
    risk_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PCT", "0.10")))
    sl_buffer_pct: float = 0.002  # SL을 슈퍼트렌드 라인보다 0.2% 더 여유

    # --- TP 배율 (리스크 대비 수익비) ---
    # TP1: 빠른 부분 확보  TP2: 중간 목표  TP3: 추세 극대화
    tp1_r: float = 0.8   # 리스크의 0.8배 — 체결률 높음
    tp2_r: float = 1.5   # 리스크의 1.5배
    tp3_r: float = 2.5   # 리스크의 2.5배 — 추세 극대화

    # --- EMA 파라미터 ---
    ema_trend: int = 200          # 추세 필터용 EMA200

    # --- 슈퍼트렌드 파라미터 ---
    st_atr_period: int = 10       # ATR 기간
    st_multiplier: float = 2.0    # 15분봉 배수
    st_htf_multiplier: float = 3.0  # 1시간봉 배수 (노이즈 필터 강하게)
    htf_interval: str = "60"      # 상위 타임프레임 (1시간봉)

    # --- 오더블록 파라미터 (미사용, 호환성 유지) ---
    ob_lookback: int = 50
    ob_body_ratio: float = 0.6
    fib_swing_lookback: int = 50
    fib_entry_low: float = 0.618
    fib_entry_high: float = 0.786
    ema_fast: int = 20
    ema_slow: int = 50

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
