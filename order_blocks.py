"""
오더블록(Order Block) 감지.

오더블록 정의:
  - 불리시 OB: 강한 상승 이동 직전의 마지막 음봉 (수요 구간)
  - 베어리시 OB: 강한 하락 이동 직전의 마지막 양봉 (공급 구간)

가격이 OB 구간 안으로 되돌아올 때 진입 신호로 사용.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd
from config import Config


@dataclass
class OrderBlock:
    ob_type: str   # 'bull' | 'bear'
    high: float
    low: float
    index: int     # 캔들 인덱스


def _candle_body_ratio(row: pd.Series) -> float:
    rng = row["high"] - row["low"]
    if rng == 0:
        return 0
    return abs(row["close"] - row["open"]) / rng


def _is_bullish(row: pd.Series) -> bool:
    return row["close"] > row["open"]


def _is_bearish(row: pd.Series) -> bool:
    return row["close"] < row["open"]


def _momentum_score(df: pd.DataFrame, start_idx: int, n: int = 3) -> float:
    """start_idx 이후 n개 캔들의 총 이동 거리 (절댓값)."""
    if start_idx + n >= len(df):
        return 0
    chunk = df.iloc[start_idx:start_idx + n]
    return abs(chunk["close"].iloc[-1] - chunk["open"].iloc[0])


def find_bullish_ob(df: pd.DataFrame, cfg: Config) -> Optional[OrderBlock]:
    """
    최근 ob_lookback 캔들 안에서 가장 최신의 불리시 오더블록 반환.
    조건:
      1. 음봉이면서 몸통 비율 >= ob_body_ratio
      2. 이후 3캔들의 모멘텀이 현재 ATR보다 클 것
      3. 현재 가격이 OB 고점보다 위에 있을 것 (이미 돌파)
    """
    window = df.tail(cfg.ob_lookback).reset_index(drop=True)
    current_price = window["close"].iloc[-1]
    atr = (window["high"] - window["low"]).mean()

    for i in range(len(window) - 4, 0, -1):
        row = window.iloc[i]
        if not _is_bearish(row):
            continue
        if _candle_body_ratio(row) < cfg.ob_body_ratio:
            continue
        momentum = _momentum_score(window, i + 1, 3)
        if momentum < atr * 0.5:
            continue
        # 현재가가 OB 고점 위에 있어야 유효 (이미 돌파한 구간)
        if current_price > row["high"]:
            return OrderBlock(
                ob_type="bull",
                high=row["high"],
                low=row["low"],
                index=i,
            )
    return None


def find_bearish_ob(df: pd.DataFrame, cfg: Config) -> Optional[OrderBlock]:
    """
    최근 ob_lookback 캔들 안에서 가장 최신의 베어리시 오더블록 반환.
    조건:
      1. 양봉이면서 몸통 비율 >= ob_body_ratio
      2. 이후 3캔들 모멘텀이 ATR보다 클 것
      3. 현재 가격이 OB 저점보다 아래에 있을 것
    """
    window = df.tail(cfg.ob_lookback).reset_index(drop=True)
    current_price = window["close"].iloc[-1]
    atr = (window["high"] - window["low"]).mean()

    for i in range(len(window) - 4, 0, -1):
        row = window.iloc[i]
        if not _is_bullish(row):
            continue
        if _candle_body_ratio(row) < cfg.ob_body_ratio:
            continue
        momentum = _momentum_score(window, i + 1, 3)
        if momentum < atr * 0.5:
            continue
        if current_price < row["low"]:
            return OrderBlock(
                ob_type="bear",
                high=row["high"],
                low=row["low"],
                index=i,
            )
    return None


def price_in_ob(price: float, ob: OrderBlock) -> bool:
    """현재 가격이 오더블록 구간 안에 있는지 확인."""
    return ob.low <= price <= ob.high
