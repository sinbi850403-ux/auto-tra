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
    interval: str = "240"          # 4시간봉 (진입 타이밍 — 스윙)
    htf_interval: str = "D"       # 일봉 (추세 방향 — 스윙)
    candle_limit: int = 300       # 캔들 수 (EMA200 계산에 충분)

    # --- 멀티 종목 스캐너 ---
    scan_symbols: list = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    ])

    # --- 레버리지 & 리스크 ---
    # 안전 기본값: 레버리지 5x, 1회 리스크 2%. (감사 결과: 20x/20%는 깡통 보장)
    leverage: int = field(default_factory=lambda: int(os.getenv("LEVERAGE", "5")))
    risk_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PCT", "0.02")))
    sl_buffer_pct: float = 0.001  # SL 눌림저점 아래 0.1% 여유

    # 하드 캡 (validate에서 강제). 이 값을 넘으면 봇이 시작을 거부한다.
    risk_pct_hard_cap: float = 0.05            # 1회 리스크 최대 5%
    # 레버리지 × 최대손절폭 < 이 값 이어야 함 (손절 전 강제청산 방지)
    lev_sl_safety_limit: float = 0.5

    # --- 안전장치 (guard.py) ---
    max_consecutive_losses: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3")))
    daily_loss_limit_pct: float = field(
        default_factory=lambda: float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.06")))  # 하루 -6%
    cooldown_after_loss_min: int = field(
        default_factory=lambda: int(os.getenv("COOLDOWN_AFTER_LOSS_MIN", "30")))

    # --- TP 배율 (손절폭 기준) ---
    tp1_r: float = 2.0   # TP1: 손절폭 2배 (스윙 — 충분한 수익 확보)
    tp2_r: float = 5.0   # TP2: 손절폭 5배 (스윙 — 큰 추세 탐)
    # TP3: Chandelier Exit 트레일링 청산 (고점 추종, 무제한)

    # --- Chandelier Exit 트레일링 스탑 (TP3) ---
    ce_period: int = 22      # 고점/저점 + ATR 계산 기간 (표준 22)
    ce_mult: float = 3.0     # ATR 배수 (표준 3.0 — 넓을수록 추세 더 길게 탐)

    # --- EMA 파라미터 ---
    ema_fast: int = 50    # EMA50 (진입 기준선)
    ema_slow: int = 200   # EMA200 (추세 기준선)

    # --- BB 스퀴즈 전략 파라미터 ---
    bb_period: int = 20              # 볼린저밴드 기간
    bb_std: float = 2.0              # 볼린저밴드 표준편차 배수
    squeeze_pct: float = 0.6         # 스퀴즈 임계값 (평균 BB폭의 60% 이하)
    squeeze_min_bars: int = 5        # 스퀴즈 최소 지속 캔들 수 (4H 기준 20시간)
    vol_mult: float = 1.5            # 진입 거래량 배율 (20봉 평균 대비)
    rsi_period: int = 14             # RSI 기간

    # --- 공통 필터 ---
    sl_max_pct: float = 0.05         # SL 최대 거리 5% (스윙 — 4H ATR은 더 큼)

    # --- 추세 추종 필터 ---
    adx_period: int = 14             # ADX 계산 기간
    adx_threshold: float = 25.0      # Daily ADX < 25 → 추세 없음 → 진입 금지 (스윙 기준 강화)

    # --- ATR 손절 ---
    atr_period: int = 20                 # ATR 기간 (사용자 지정)
    atr_sl_mult: float = 2.0             # SL = ATR × 2.0 (스윙 — 더 여유있는 SL)
    atr_vol_gate_pct: float = 0.05       # 4H ATR > 가격 × 5% → 극단 변동성, 진입 금지
    vol_avg_len: int = 20                # 거래량 평균 기간

    # --- v3 손절 버퍼 (연속 손절 후 휩쏘 방지) ---
    per_loss_buffer_add_pct: float = 0.0005  # 연속 손절 1회당 버퍼 +0.05%p
    max_sl_buffer_pct: float = 0.003         # 버퍼 상한 0.3%

    # --- v3 펀딩비 게이트 ---
    funding_gate_abs: float = 0.0005     # 진입 방향에 불리한 펀딩비 0.05% 초과 → 스킵

    # --- v3 수수료 방어 ---
    min_notional_usd: float = 2.0        # 명목가치 $2 미만 거래 거부 (수수료가 엣지 잠식)

    # --- v3 과매매 방지 ---
    max_trades_per_day: int = 2          # UTC 일일 최대 진입 횟수 (스윙 — 선별적 진입)

    # --- v3 시간손절 ---
    time_stop_hours: float = 72.0        # TP1 미달성 72시간(3일) 경과 +
    time_stop_pnl_pct: float = -0.02    # 가격이 진입가 대비 -2% 이하 → 논리 붕괴, 청산

    # --- v3 드로다운 사이징 (기본 OFF — $28 계좌에선 최소 수량 미달 위험) ---
    risk_scale_enabled: bool = field(
        default_factory=lambda: os.getenv("RISK_SCALE_ENABLED", "false").lower() == "true")
    risk_scale_after_loss: float = 0.5   # 연속 손절마다 리스크 ×0.5
    risk_scale_floor: float = 0.25       # 바닥: 기본 리스크의 25%

    # --- 실행 주기 ---
    check_interval_sec: int = 300 # 5분마다 신호 확인 (4H 스윙)

    def validate(self):
        import logging as _log
        _logger = _log.getLogger(__name__)

        if not self.api_key or not self.api_secret:
            raise ValueError("BYBIT_API_KEY / BYBIT_API_SECRET 환경변수가 설정되지 않았습니다.")

        # 1회 리스크 하드 캡
        if self.risk_pct > self.risk_pct_hard_cap:
            raise ValueError(
                f"RISK_PCT={self.risk_pct * 100:.1f}% 가 한도({self.risk_pct_hard_cap * 100:.1f}%)를 "
                f"초과합니다. RISK_PCT를 낮추세요."
            )

        # 레버리지 × 최대손절폭 경고 (차단 아님 — BB SL은 실제로 훨씬 짧음)
        lev_sl = self.leverage * self.sl_max_pct
        if lev_sl >= self.lev_sl_safety_limit:
            _logger.warning(
                "⚠️ 레버리지(%dx) × 최대SL폭(%.1f%%) = %.2f — SL이 BB 안쪽에 잡히면 "
                "청산 전에 손절이 동작하지 않을 수 있습니다. 실제 SL은 보통 2~3%대입니다.",
                self.leverage, self.sl_max_pct * 100, lev_sl
            )

        if self.daily_loss_limit_pct <= 0 or self.max_consecutive_losses <= 0:
            raise ValueError("daily_loss_limit_pct / max_consecutive_losses 는 0보다 커야 합니다.")
