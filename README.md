# 바이비트 자동 선물 봇

EMA + 오더블록 + 피보나치 전략으로 BTC/USDT 15분봉 자동 매매.

---

## 전략 로직

| 조건 | 롱 | 숏 |
|---|---|---|
| EMA | EMA20 > EMA50 | EMA20 < EMA50 |
| 오더블록 | 불리시 OB 안에 현재가 | 베어리시 OB 안에 현재가 |
| 피보나치 | 0.618~0.786 되돌림 구간 | 0.618~0.786 되돌림 구간 |
| SL | OB 저점 - 0.2% | OB 고점 + 0.2% |
| TP | SL 거리 × 2 (1:2 손익비) | SL 거리 × 2 |

---

## 로컬 설치 & 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일 열어서 API 키 입력

# 3. 테스트넷으로 먼저 실행 (TESTNET=true)
python main.py
```

---

## Railway 클라우드 배포

1. [railway.app](https://railway.app) 회원가입
2. New Project → Deploy from GitHub repo
3. Variables 탭에서 환경변수 추가:
   ```
   BYBIT_API_KEY=...
   BYBIT_API_SECRET=...
   TESTNET=false
   SYMBOL=BTCUSDT
   LEVERAGE=20
   RISK_PCT=0.20
   ```
4. Deploy — 자동으로 24시간 실행

---

## API 키 발급 (바이비트)

1. bybit.com → 우측 상단 프로필 → API Management
2. Create New Key
3. System-generated → 권한: **Unified Trading (Read + Trade)**
4. IP 제한 없음 (클라우드 고정 IP 없을 경우)

---

## ⚠️ 리스크 경고

- 20x 레버리지 + 20% 리스크는 **매우 공격적**입니다
- 연속 5번 손절 시 계좌 소진 가능
- 권장: 레버리지 3~5x, 리스크 1~2%
- 이 봇은 참고용이며, 투자 결과에 대한 책임은 본인에게 있습니다
