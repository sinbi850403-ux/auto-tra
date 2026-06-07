# 바이비트 자동 선물 봇

**4시간봉 EMA50/200 추세 + 15분봉 EMA50 눌림목** 전략으로 BTC·ETH·SOL·XRP·BNB 자동 매매.

> ⚠️ **이 전략은 아직 백테스트로 검증되지 않았습니다.** 과거 데이터에서 수수료를 빼고도
> 수익이 나는지 확인되기 전까지는 **반드시 `TESTNET=true`** 로만 돌리세요. 실거래는
> 검증 후 소액으로만. 투자 결과의 책임은 전적으로 본인에게 있습니다.

---

## 전략 로직 (실제 코드 기준)

| 조건 | 롱 | 숏 |
|---|---|---|
| 추세 (4H) | EMA50 > EMA200 & 가격 > EMA200 | EMA50 < EMA200 & 가격 < EMA200 |
| 진입 (15M) | EMA50 눌림 후 반등 양봉 + 직전 고점 돌파 | EMA50 반등 후 저항 음봉 + 직전 저점 이탈 |
| 필터 | 4H EMA 간격 협소(횡보)/급등락 추격/먼 SL 회피 | 동일 |
| SL | 눌림 저점 아래 | 반등 고점 위 |
| TP | TP1=1R(1/3), TP2=2R(1/3), 나머지 1/3 EMA50 트레일링 | 동일 |
| 손실 관리 | TP1 후 SL 본전 이동 + 역신호 시 전량 청산 | 동일 |

### 안전장치 (guard.py)
- **연속 손절 정지**: `MAX_CONSECUTIVE_LOSSES`(기본 3) 회 연속 손절 시 당일 신규 진입 중단
- **일일 손실 한도**: 하루 누적 `DAILY_LOSS_LIMIT_PCT`(기본 -6%) 도달 시 당일 진입 중단
- **쿨다운**: 손절 직후 `COOLDOWN_AFTER_LOSS_MIN`(기본 30분) 신규 진입 보류
- **레버리지·손절 안전 검증**: `레버리지 × 최대손절폭`이 위험 수준이면 시작 거부
- **상태 영속화**: `bot_state.json`에 포지션/카운터 저장 → 재시작에도 유지

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
   TESTNET=true        # 검증 전까지 반드시 true
   SYMBOL=BTCUSDT
   LEVERAGE=5          # 권장 3~5x (20x 금지)
   RISK_PCT=0.02       # 권장 1~2% (5% 초과 시 시작 거부)
   ```
4. Deploy — 자동으로 24시간 실행
5. (선택) `bot_state.json` 영속화를 위해 **Volume**을 `/app`에 마운트하면
   재배포 후에도 손실 카운터/포지션 상태가 유지됩니다. (없으면 재배포 시 초기화)

---

## API 키 발급 (바이비트)

1. bybit.com → 우측 상단 프로필 → API Management
2. Create New Key
3. System-generated → 권한: **Unified Trading (Read + Trade)**
4. IP 제한 없음 (클라우드 고정 IP 없을 경우)

---

## ⚠️ 리스크 경고

- **선물은 레버리지 때문에 손실이 증폭됩니다. 잃어도 괜찮은 돈으로만 하세요.**
- 20x 레버리지에서는 ~4.5%만 역방향으로 가도 강제청산입니다. 손절보다 청산이 먼저 올 수 있어 **권장 레버리지 3~5x**.
- 1회 리스크는 **1~2%**. 10~20%는 몇 번의 연속 손절로 계좌가 거덜납니다.
- 이 전략은 **수익성이 검증되지 않았습니다.** 백테스트로 양(+)의 기대값을 확인하기 전까지는 테스트넷만.
- 이 봇은 참고용이며, 투자 결과에 대한 책임은 전적으로 본인에게 있습니다.
