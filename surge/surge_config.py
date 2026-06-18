"""폭등 임박 스캐너 설정 — DESIGN_KR_SURGE_SCANNER.md 부록 A 코드화.

모든 임계값·가중치·백테스트 라벨을 한곳에 모아 백테스트 민감도 분석을 쉽게 한다.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SurgeConfig:
    # ---------------- 데이터 수급 (제2부) ----------------
    history_years: int = 5
    markets: tuple = ("KOSPI", "KOSDAQ")
    cache_dir: str = field(default_factory=lambda: os.getenv("SURGE_CACHE_DIR", "data"))

    # ---------------- 유니버스 게이트 (제3부) ----------------
    min_avg_value_krw: float = 1_000_000_000      # 20일 평균 거래대금 ≥ 10억
    min_market_cap_krw: float = 30_000_000_000    # 시총 ≥ 300억
    min_price: int = 1_000                         # 동전주 제외
    max_price: Optional[int] = None
    new_listing_min_days: int = 60                 # 신규 상장 N일 미만 제외
    value_ma_period: int = 20
    exclude_limit_up_today: bool = True
    limit_up_today_pct: float = 0.15               # 당일 +15%↑ 추격 금지

    # ---------------- 팩터 파라미터 (제4부) ----------------
    # F1 변동성 수축
    bb_period: int = 20
    bb_std: float = 2.0
    bb_lookback: int = 126            # 밴드폭 분위 기준 (≈6개월)
    # F2 거래량
    vol_ma: int = 20
    vol_dry_lookback: int = 60
    vol_ignition_mult: float = 3.0    # 당일 거래량 ≥ 3배 → 만점
    # F3 박스 상단
    box_lookback: int = 60
    box_near_pct: float = 0.05        # 박스상단 -5% 이내 → 만점
    box_chase_pct: float = 0.03       # 박스상단 +3%↑ 돌파는 추격 → 감점
    # F4 모멘텀
    rsi_period: int = 14
    ema_short: int = 20
    # F5 베이스
    base_band_pct: float = 0.15       # ±15% 박스 = 베이스
    base_min_days: int = 35           # 7주
    # F6 상대강도
    rs_lookback: int = 60
    # F7 추세 토대
    ema_periods: tuple = (20, 60, 120, 200)
    high_52w_period: int = 252
    high_52w_near: float = 0.75       # 52주고가의 75%↑
    # F8 수급 매집
    obv_div_lookback: int = 20

    # ---------------- 점수 가중치 (제4.C부) ----------------
    # 진단(backtest factor_diagnosis) 기반 재설계:
    # F6 상대강도(lift 1.99)·F7 추세토대(1.87)가 주력, F2 거래량·F4 모멘텀 보조.
    # F1/F5 미미·F3(0.78)/F8(0.64) 역효과 → 가중치에서 제외.
    w_short: dict = field(default_factory=lambda: {
        "F6": 0.30, "F7": 0.25, "F2": 0.20, "F4": 0.25})
    w_mid: dict = field(default_factory=lambda: {
        "F6": 0.35, "F7": 0.30, "F2": 0.15, "F4": 0.20})
    grade_cut: dict = field(default_factory=lambda: {
        "S": 85.0, "A": 70.0, "B": 55.0})

    # ---------------- 백테스트 라벨 (제0.3부, 합의값) ----------------
    short_K: int = 10                 # 단기: 10거래일 내
    short_X: float = 0.20             #        +20%
    mid_K: int = 30                   # 중기: 30거래일 내
    mid_X: float = 0.40               #        +40%
    oos_split_date: str = "2024-01-01"
    pass_lift: float = 2.0            # 통과선: lift ≥ 2.0
    pass_mfe_mae: float = 1.5         # 통과선: MFE/MAE ≥ 1.5

    # ---------------- 출력 (제7부) ----------------
    top_n_alert: int = 10
    alert_grades: tuple = ("S", "A")
    alert_top_pct: float = 0.10        # 점수 상위 10%를 알림/통과 기준 (실전 운용과 일치)

    # 지표 워밍업: 이보다 짧은 종목은 스캔 제외 (1년)
    min_candles: int = 252

    def validate(self) -> None:
        assert abs(sum(self.w_short.values()) - 1.0) < 1e-9, \
            f"w_short 합이 1.0이 아님: {sum(self.w_short.values())}"
        assert abs(sum(self.w_mid.values()) - 1.0) < 1e-9, \
            f"w_mid 합이 1.0이 아님: {sum(self.w_mid.values())}"
        assert self.grade_cut["S"] > self.grade_cut["A"] > self.grade_cut["B"], \
            "등급컷은 S>A>B 내림차순이어야 함"
        assert self.short_K > 0 and self.mid_K > 0, "라벨 기간 K는 양수"
        assert self.short_X > 0 and self.mid_X > 0, "라벨 상승률 X는 양수"
        assert self.min_price > 0, "최소 가격은 양수"
        assert self.bb_lookback > self.bb_period, "밴드폭 분위 기준은 BB기간보다 길어야 함"


DEFAULT = SurgeConfig()
