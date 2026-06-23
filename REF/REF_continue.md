# REF — 이어서 진행할 AI를 위한 참조 데이터
> 프로젝트: 주식 포트폴리오 대시보드 자동화
> 최종 업데이트: 2026-06-23
> 작성자: Claude Sonnet 4.6

---

## 프로젝트 개요
삼성증권 7개 계좌 포트폴리오를 카카오톡 알림 → 자동 파싱 → GitHub → GitHub Pages 대시보드로 시각화하는 자동화 시스템.

**라이브 URL**: https://barobogi.github.io/stock_dashboard/stock-dashboard.html
**GitHub**: https://github.com/barobogi/stock_dashboard

---

## 핵심 파일 구조
```
D:\AI\260619_2_Daily_for_stock_TEMP\
├── stock-dashboard.html       # 메인 대시보드 (단일 HTML, GitHub Pages 배포)
├── kakao_watcher.py           # 카카오톡 파일 감지 → 파싱 → HTML 업데이트 → git push
├── daily_report.py            # 매일 오후 7시 이메일 보고서 (인증 설정 대기 중)
├── netlify.toml               # Cache-Control 헤더 설정 (Netlify 중단으로 현재 미사용)
├── ticker_map.json            # 국내 ETF 종목코드 매핑 (24개)
├── daily_snapshot.json        # 전일 평가금액 저장 (일간 수익률 비교용)
└── REF\                       # 이 폴더
```

---

## 아키텍처
```
카카오톡 내보내기
    → Google Drive MYBOX (G:\내 드라이브\KakaoTalk)
    → kakao_watcher.py (watchdog 감지)
        → fetch_exchange_rate() : Dunamu API → Naver 폴백
        → parse_kakao() : 거래/배당/입금 파싱
        → fetch_prices() : Naver API(국내) + yfinance(해외)
        → inject_to_html() : <!-- KAKAO_AUTO:START/END --> 블록 갱신
        → git push → GitHub → GitHub Pages 자동 배포 (2~3분)
    → 매 정시: refresh_prices_only() 백그라운드 스레드 (환율 + 현재가 동시 갱신)
    → 매일 7시: daily_report.py (작업 스케줄러, 이메일 인증 대기)
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
| 8 | 71417 | general | 일반계좌3 (해외주식) |
| 9 | 71661 | general | 일반계좌4 |

> ⚠️ **id 1~7 영구 고정 — 절대 순서 변경 금지.** 신규 계좌는 항상 id 10부터 순서대로 추가.
> EXCLUDED_NUMS = {71374} — 가족 계좌, 자동 등록 차단.

---

## 데이터 구조 (window.KAKAO_PARSED_DATA)
```json
{
  "dividends":    [{"accountId":1, "stock":"종목명", "amount":10000, "date":"2026-06-19", "tax":0}],
  "trades":       [{"accountId":1, "stockName":"종목명", "type":"매수", "qty":10, "price":9945,
                    "date":"2026-06-19", "total":99450}],
  "deposits":     [{"accountId":1, "amount":1000000, "date":"2026-06-19"}],
  "prices":       {"종목명": 9945},
  "exchangeRate": 1374.5,
  "tradeDateCut": "2026-06-19",
  "tradeTimeCut": "12:50",
  "pushedAt":     "2026-06-20T09:00:26.347085",
  "sourceFile":   "KakaoTalk_20260619.txt"
}
```

---

## 주요 기술 사항

### 현재가 조회
- **국내 ETF**: `m.stock.naver.com/api/stock/{code}/basic` → `stockItemTotal.closePrice`
- **해외 주식**: `yfinance` → `Ticker.fast_info.last_price` × 환율
- **환율(USD/KRW)**: Dunamu API 우선 → Naver Finance 폴백 (매 정시 자동 갱신)
- yfinance NumPy 충돌 시 Naver API 폴백 자동 동작

### 카카오톡 파싱 패턴
- 배당(일반): `세후 분배금액 : N원` 또는 `배당금 : N원`
- 배당(IRP): `퇴직연금 이자/배당/상환 안내` → `입금액 : N원`
- 국내 거래: `매수N주 N,NNN원` (주식체결안내 context)
- 해외 거래: `해외주식 매매 체결 안내` 헤더 기반 전진 파싱

### 포트폴리오 기준일 (동적 상수)
- `kakao_watcher.py`: `TRADE_DATE_CUT = "2026-06-19"`, `TRADE_TIME_CUT = "12:50"`
- `stock-dashboard.html`: `BASELINE_DATE`, `BASELINE_TIME` 상수로 KAKAO_PARSED_DATA에서 읽음
- **수정 시 kakao_watcher.py 한 곳만 변경하면 HTML에 자동 반영**

### localStorage 키
- `stock_dashboard_v3` : 포트폴리오 전체 데이터 + 스냅샷 + pushedAt
- `fire_target` : FIRE 목표 금액

### localStorage ↔ KAKAO_PARSED_DATA 동기화
- `pushedAt` 비교로 최신 여부 판단
- KAKAO_PARSED_DATA가 최신이면 데이터 갱신, 아니면 localStorage 사용
- `snapshots`는 항상 localStorage 우선 (클라이언트 누적 데이터)

---

## 구현된 기능 (2026-06-23 기준, v1.2)

### 대시보드 탭
- 요약 카드 (총 평가/매수/손익/배당금/연간배당/월평균/세금/배당수익률)
- FIRE 목표 달성률 + 예상 소요 연수
- 계좌별 요약 + 계좌별 비중 파이차트
- 종목별 비중/수익률/배당 Top10 차트
- **포트폴리오 히트맵** (타일 크기=평가금액, 색=수익률, 호버 상세) ← Phase 1 신규

### 종목 Study 탭 ← v1.2 신규
- 🔍 A모드: Google News RSS + CORS 프록시 — 오늘 뉴스 최대 5개
- 🤖 B모드: Firebase → 데몬 → Claude AI 분석 (당일 캐시)

### 계좌비교 탭 ← Phase 1 신규
- 7계좌 요약 카드 (평가금액, 수익률, 배당금)
- 계좌별 평가 vs 매수 그룹 바차트
- 계좌별 수익률 가로 바차트
- 계좌별 TOP3 수익 종목

### 수익률 탭
- 기간별 수익률 테이블 (일/주/월/연)
- **포트폴리오 평가금액 추이 라인차트** (스냅샷 2개↑ 시 자동 표시) ← Phase 1 신규
- 스냅샷 이력 + 실현 손익 내역

### 배당금 탭
- 종목별/계좌별 배당 내역
- 월별 배당 추이 차트

---

## 자동화 상태

### watcher (kakao_watcher.py)
- 실행 방법: `"C:\hb\python.exe" "D:\AI\260619_2_Daily_for_stock_TEMP\kakao_watcher.py"`
- **자동 시작**: 시작 프로그램 폴더 `KakaoWatcher.lnk` → `start_watcher.vbs` 30초 대기 후 실행 (Google Drive 마운트 대기)
- 매 정시 환율 + 현재가 갱신 후 GitHub push (push 실패 시 3회 재시도 + 30초 간격)
- observer 비정상 종료 시 10초 후 자동 재시작
- 실행 로그: `D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log`

### Claude Desktop MCP 연동
- 설정 파일: `C:\Users\82102\AppData\Roaming\Claude\claude_desktop_config.json`
- 연동 폴더: `D:\AI\260619_2_Daily_for_stock_TEMP`
- Claude Desktop(Cowork) ↔ Claude Code 동일 파일 공유 가능

---

## 미완료 / 다음 세션 작업

### Holding (사용자 별도 언급 시 재개)
- [ ] 이메일 발송: 네이버 2FA 이슈, Gmail 계정 한도 초과 → 대안 미정

### Phase 2 후보 (IMPROVEMENT_PROPOSAL_20260620.md 참조)
- [ ] 위험도 분석 (변동성, 베타, 샤프지수)
- [ ] 세금 최적화 도구
- [ ] 배당 일정 관리 달력

### 기술 부채
- [x] kakao_watcher.py: print() → logging 모듈 교체 (watcher.log 파일 기록)
- [x] watcher 비정상 종료 시 자동 재시작 로직 (observer while True 래퍼)
- [x] git push 실패 시 3회 재시도 로직
- [x] 레지스트리 자동 시작 → VBS + 시작 프로그램 폴더 방식으로 전환
- [x] DIV_CUTOFF 하드코딩 → datetime.now().year-1 자동 계산

---

## Global_Define 활용 현황
`D:\AI\Global_Define\` 에 아래 모듈 존재:
- `config_manager.py` : ConfigManager(JSON 설정), Logger(파일 로거)
- `anthropic_admin_api.py` : Anthropic Admin API 래퍼
- `anthropic_console_scraper.py` : 콘솔 스크래퍼

현재 프로젝트 미사용 (print로 대체). 향후 Logger 도입 권장:
```python
import sys; sys.path.insert(0, r"D:\AI\Global_Define")
from config_manager import Logger
logger = Logger(Path(r"D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log"))
```

---

## 환경 변수 (Windows 사용자 레벨)
| 변수명 | 용도 |
|--------|------|
| DAUM_ID | 이메일 발송 계정 ID (hanbogi79) |
| DAUM_PW | Daum 앱 비밀번호 (mail.daum.net 발급) |

---

## Git / 배포
- GitHub: `https://github.com/barobogi/stock_dashboard` (branch: main)
- **GitHub Pages**: push 후 2~3분 자동 배포
  - URL: https://barobogi.github.io/stock_dashboard/stock-dashboard.html
- Netlify 중단: 무료 플랜 빌드 크레딧 300분/월 초과 (2026-06-20)
- 작업 스케줄러: `StockDailyReport` (매일 19:00, daily_report.py)
- **Cowork/CLI 자동 배포**: `watch_cowork_changes.py` 상시 실행 → 파일 변경 시 12초 후 자동 push
