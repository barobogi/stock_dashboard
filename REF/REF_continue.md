# REF — 이어서 진행할 AI를 위한 참조 데이터
> 프로젝트: 주식 포트폴리오 대시보드 자동화
> 생성일: 2026-06-19
> 작성자: Claude Sonnet 4.6

---

## 프로젝트 개요
삼성증권 7개 계좌 포트폴리오를 카카오톡 알림 → 자동 파싱 → GitHub → GitHub Pages 대시보드로 시각화하는 자동화 시스템.

---

## 핵심 파일 구조
```
D:\AI\260619_2_Daily_for_stock_TEMP\
├── stock-dashboard.html       # 메인 대시보드 (단일 HTML, GitHub Pages 배포)
├── kakao_watcher.py           # 카카오톡 파일 감지 → 파싱 → HTML 업데이트 → git push
├── daily_report.py            # 매일 오후 7시 이메일 보고서 + 스냅샷 저장
├── register_daily_report.ps1  # 작업 스케줄러 등록 스크립트 (관리자 실행 필요)
├── ticker_map.json            # 국내 ETF 종목코드 매핑 (24개)
├── build_ticker_map.py        # ticker_map.json 재생성 도구
├── daily_snapshot.json        # 전일 평가금액 저장 (일간 수익률 비교용)
└── REF\                       # 이 폴더
```

---

## 아키텍처
```
카카오톡 내보내기
    → Google Drive MYBOX (G:\내 드라이브\KakaoTalk)
    → kakao_watcher.py (watchdog 감지)
        → parse_kakao() : 거래/배당/입금 파싱
        → fetch_prices() : Naver API(국내) + yfinance(해외)
        → inject_to_html() : <!-- KAKAO_AUTO:START/END --> 블록 갱신
        → git push → GitHub → GitHub Pages 자동 배포
    → 매 정시: refresh_prices_only() 백그라운드 스레드
    → 매일 7시: daily_report.py (작업 스케줄러)
```

---

## 계좌 정의 (ACCOUNTS)
| id | 번호앞5자리 | 유형 | 설명 |
|----|-----------|------|------|
| 1 | 70714 | general | 일반계좌1 |
| 2 | 70871 | general | 일반계좌2 |
| 3 | 71297 | isa | ISA |
| 4 | 70714 | irp | IRP (70714이지만 '퇴직연금' 키워드로 구분) |
| 5 | 71462 | pension | 연금저축1 |
| 6 | 71615 | pension | 연금저축2 |
| 7 | 70868 | pension | 연금저축3 |

---

## 데이터 구조 (window.KAKAO_PARSED_DATA)
```json
{
  "dividends": [{"accountId":1, "stock":"종목명", "amount":10000, "date":"2026-06-19", "tax":0}],
  "trades":    [{"accountId":1, "stockName":"종목명", "type":"매수", "qty":10, "price":9945,
                 "date":"2026-06-19", "total":99450, "applyToPortfolio":true}],
  "deposits":  [{"accountId":1, "amount":1000000, "date":"2026-06-19"}],
  "prices":    {"종목명": 9945},
  "exchangeRate": 1512.8,
  "pushedAt":  "2026-06-19T22:00:13",
  "sourceFile": "KakaoTalk_20260619.txt"
}
```

---

## 주요 기술 사항

### 현재가 조회
- **국내 ETF**: `m.stock.naver.com/api/stock/{code}/basic` → `stockItemTotal.closePrice`
- **해외 주식**: `yfinance` → `Ticker.fast_info.last_price` × 환율
- **종목코드 검색**: `ac.stock.naver.com/ac` (ac.finance.naver.com은 DNS 불가)
- yfinance NumPy 충돌 시 Naver API 폴백 자동 동작

### 카카오톡 파싱 패턴
- 배당(일반): `세후 분배금액 : N원` 또는 `배당금 : N원`
- 배당(IRP): `퇴직연금 이자/배당/상환 안내` → `입금액 : N원`
- 국내 거래: `매수N주 N,NNN원` (주식체결안내 context)
- 해외 거래: `해외주식 매매 체결 안내` 헤더 기반 전진 파싱
- IRP 거래: `체결단가 : N원` + '퇴직연금' context

### 포트폴리오 기준일
- `TRADE_DATE_CUT = "2026-06-19"`, `TRADE_TIME_CUT = "12:50"`
- 기준일 이전 거래 무시, 기준일 12:50 이전 거래는 `applyToPortfolio:false`

### localStorage 키
- `stock_dashboard_v3` : 포트폴리오 전체 데이터 + 스냅샷
- `fire_target` : FIRE 목표 금액

---

## 미완료 / 다음 세션 작업

### 즉시 가능
- [ ] 이메일 발송 설정: 네이버 계정 2단계 인증 이슈 → 대안 필요
  - 네이버 외부서비스 비밀번호 사라짐
  - Daum 메일 or Gmail 신규계정(2FA 없음) 고려

### 데이터 쌓이면 구현
- [ ] 기간별 수익률 그래프 (일간/주간/월간/연간) — 스냅샷 최소 7일치 필요
- [ ] 계좌별 수익률 비교 차트
- [ ] 커버드콜 ETF 분배율 추적

---

## Global_Define 활용 현황
- `D:\AI\Global_Define\config_manager.py` → Logger 클래스 활용 가능 (현재 미사용, print로 대체)
- 향후 kakao_watcher.py 로깅 개선 시 Logger 도입 권장
```python
import sys; sys.path.insert(0, r"D:\AI\Global_Define")
from config_manager import Logger
logger = Logger(Path(r"D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log"))
```

---

## 환경 변수 (Windows 사용자 레벨)
| 변수명 | 용도 | 설정 방법 |
|--------|------|-----------|
| NAVER_ID | 이메일 발송 계정 ID | SetEnvironmentVariable |
| NAVER_PW | 이메일 발송 계정 PW | SetEnvironmentVariable |

---

## Git / 배포
- GitHub: `https://github.com/barobogi/stock_dashboard`
- Branch: `main`
- GitHub Pages: GitHub 연동 자동 배포 (push 후 2~3분)
  URL: https://barobogi.github.io/stock_dashboard/stock-dashboard.html
  (Netlify 중단 이유: 무료 플랜 빌드 크레딧 300분/월 초과)
- 작업 스케줄러: `StockDailyReport` (매일 19:00, daily_report.py 실행)
