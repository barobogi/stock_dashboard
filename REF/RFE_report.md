# RFE — 주요 이슈 개선 리포트
> 프로젝트: 주식 포트폴리오 대시보드 자동화
> 기간: 2026-06-19 (1일 세션)
> 작성자: Claude Sonnet 4.6

---

## 1. 해결된 주요 이슈

### 🐛 Bug #1: 국내 ETF 현재가 0원
- **원인**: `ac.finance.naver.com` DNS 차단
- **해결**: `ac.stock.naver.com/ac` API로 교체
- **결과**: 23개 국내 ETF 전체 코드 매핑 완료 → 35/35 현재가 성공

### 🐛 Bug #2: IRP 배당금 파싱 누락
- **원인**: IRP 배당은 일반 배당과 포맷이 완전히 다름
  - 일반: `세후 분배금액 : N원`
  - IRP: `퇴직연금 이자/배당/상환 안내` + `입금액 : N원`
- **해결**: IRP 전용 파서 추가
- **결과**: 728건 → 838건 (+110건 IRP 배당 복구)

### 🐛 Bug #3: 삼성전자 종목별 수익률 차트 2개 표시
- **원인**: pnlChart가 계좌별로 각각 표시 (같은 종목 중복)
- **해결**: `byName` 객체로 종목명 기준 집계 후 렌더링

### 🐛 Bug #4: 손실 종목이 수익률 Top10에 포함
- **원인**: `Math.abs()` 정렬로 큰 손실이 상위 노출
- **해결**: `.filter(d => d.profit > 0)` 추가

### 🐛 Bug #5: SOL 팔란티어OTM 매수금액 오류
- **원인**: 총 매수금액(2,014,024)을 주당 가격으로 잘못 입력
- **해결**: 10,003원 × 2,008주 = 20,086,024원으로 수정

### 🐛 Bug #6: checkAutoSnapshot() 미호출
- **원인**: 함수 정의는 있었으나 updateAll()에서 호출 누락
- **해결**: updateAll() 마지막에 호출 추가

---

## 2. 신규 구현 기능

| 기능 | 설명 |
|------|------|
| 월 평균 배당 카드 | 연간 배당 ÷ 12 표시 |
| FIRE 진행도 | 목표 금액 대비 현재 평가금액 진행바 + 배당 기준 소요 연수 |
| BEP 컬럼 | 포트폴리오 테이블에 손익분기점 가격 표시 (수익/손실 색상 구분) |
| 계좌별 세후 실수익 | 계좌 요약에 세금 유형(15.4%/9.9%/16.5%) + 배당 + 손익 표시 |
| 다음 달 예상 분배금 | 최근 6개월 월평균 기반 종목별 예측 |
| 매 정시 현재가 갱신 | kakao_watcher 백그라운드 스레드, 카카오톡 파일 없이도 타임스탬프 업데이트 |
| 일일 이메일 보고서 | daily_report.py — 매일 7시 HTML 이메일 발송 (인증 설정 pending) |

---

## 3. 미해결 이슈

### ⚠️ 이메일 발송 인증 실패
- **증상**: Naver SMTP `535 Username and Password not accepted`
- **원인**: 네이버 2단계 인증 활성화 시 일반 PW로 SMTP 불가, 외부서비스 비밀번호 메뉴 삭제됨
- **현황**: 환경변수(`NAVER_ID`, `NAVER_PW`) 등록 완료, 스케줄러 등록 완료
- **권장 해결책**:
  1. Daum/Kakao 메일 SMTP (smtp.daum.net:465) 시도
  2. Gmail 신규 계정 생성 (2FA 없이) → 앱 비밀번호 발급

### ⚠️ yfinance / NumPy ABI 충돌
- **증상**: `AttributeError: _ARRAY_API not found` (간헐적)
- **원인**: NumPy 2.x와 구버전으로 컴파일된 pyarrow 충돌
- **현황**: Naver API 폴백으로 국내 ETF는 정상, 해외 주식은 간헐적 실패
- **권장 해결책**: `pip install --force-reinstall pyarrow` 또는 `numpy<2`로 다운그레이드

---

## 4. 기술 부채 / 개선 권장 사항

### 코드 품질
- `kakao_watcher.py`의 로깅을 `print()` → `Global_Define/config_manager.Logger`로 교체 권장
- `daily_report.py`의 DEFAULT_STOCKS 파싱이 JS 파싱 재구현 — 별도 JSON 파일로 분리하면 유지보수 용이

### 기능 확장 (데이터 축적 후)
- 기간별 수익률 그래프 (일간/주간/월간/연간) — 스냅샷 7일+ 필요
- 커버드콜 ETF 분배율 추적 — 분배금 이력 분석
- 계좌별 수익률 비교 차트

### 안정성
- kakao_watcher.py 비정상 종료 시 자동 재시작 로직 없음 (Windows 서비스 또는 Task Scheduler로 감시 권장)
- git push 실패 시 재시도 로직 없음

---

## 5. 커밋 이력 요약

| 커밋 | 내용 |
|------|------|
| 688c0ce | ISA buyAmount 수정, pnlChart 집계, IRP배당파서 |
| 2df9e68 | 손실 종목 수익차트 제외 |
| bf8fe1d | 7개 신규 기능 추가 |
| 4c51ee1 | daily_report.py 이메일 보고서 |
| b71b681 | Gmail→네이버 SMTP 변경 |
| 1a4d1d0 | ticker_map 완성 + 스냅샷 |
| 231df85 | 매 정시 현재가 자동 갱신 |
