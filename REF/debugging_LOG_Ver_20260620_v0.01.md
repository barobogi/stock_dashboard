# Debugging Log — 2026-06-20 v0.01

## 이슈 #1: 대시보드 타임스탬프 업데이트 안 됨

### 증상
- 대시보드 상단 `2026.06.19 20:40 기준 (자동업데이트)` 고정
- kakao_watcher가 매 정시 현재가 갱신 후 HTML pushedAt이 07:00으로 업데이트됐음에도 화면 반영 안 됨
- `Ctrl+Shift+R` (강제 새로고침) 해도 변화 없음

### 원인 분석
**1. localStorage 우선 문제 (주원인 아님)**
- `Ctrl+Shift+R`은 HTTP 캐시(HTML/JS/CSS)만 지움
- `localStorage`는 브라우저 내부 저장소로 강제 새로고침과 무관하게 유지됨

**2. 스냅샷 날아가는 버그 (추가 발견)**
```javascript
// 기존 코드 — KAKAO_PARSED_DATA 로드 시마다 snapshots 초기화됨
snapshots = kd.snapshots || [];  // kd.snapshots는 항상 undefined → [] 로 리셋
```
- 매 페이지 로드 시 localStorage에 누적된 스냅샷이 전부 초기화되는 버그

**3. pushedAt이 localStorage에 저장 안 됨**
```javascript
// 기존 saveToStorage() — pushedAt 누락
localStorage.setItem(STORAGE_KEY, JSON.stringify({ stocks, dividends, deposits, trades, snapshots, exchangeRate }));
```
- KAKAO_PARSED_DATA의 pushedAt과 localStorage의 버전 비교가 불가능했음

### 수정 내용

**파일:** `stock-dashboard.html`

#### 수정 1: KAKAO_PARSED_DATA 로드 시 pushedAt 비교 + snapshots 보존

```javascript
// 수정 후 — DOMContentLoaded 내 KAKAO_PARSED_DATA 블록
if (window.KAKAO_PARSED_DATA) {
  const kd = window.KAKAO_PARSED_DATA;

  // localStorage의 snapshots 보존 (클라이언트에서만 누적되는 데이터)
  const storedRaw = localStorage.getItem(STORAGE_KEY);
  let storedSnapshots = [], storedPushedAt = '';
  if (storedRaw) {
    try {
      const sd = JSON.parse(storedRaw);
      storedSnapshots = sd.snapshots || [];
      storedPushedAt  = sd.pushedAt  || '';
    } catch(e) {}
  }

  // KAKAO_PARSED_DATA가 localStorage보다 최신일 때만 데이터 갱신 (자동 비교)
  const kdPushedAt = kd.pushedAt || '';
  if (!storedPushedAt || kdPushedAt > storedPushedAt) {
    // 최신 데이터 → kd로 갱신
    stocks    = DEFAULT_STOCKS.map(...);
    dividends = kd.dividends || [];
    trades    = kd.trades    || [];
    deposits  = kd.deposits  || [];
    exchangeRate = kd.exchangeRate || 1512.8;
    applyTrades();
    // 현재가 적용
    if (kd.prices) { stocks.forEach(s => { ... }); }
  } else {
    // 같은 버전 → localStorage 데이터 사용 (수동 편집 보존)
    if (storedRaw) loadFromStorage();
  }

  // snapshots는 항상 localStorage 것 우선 (누적 데이터 보존)
  snapshots = storedSnapshots;

  // 타임스탬프 표시
  if (kdPushedAt) {
    const d = kdPushedAt.slice(0,10).replace(/-/g,'.');
    const t = kdPushedAt.slice(11,16);
    document.getElementById('statusText').textContent = `${d} ${t} 기준 (자동업데이트)`;
  }
}
```

#### 수정 2: saveToStorage()에 pushedAt 추가

```javascript
function saveToStorage() {
  const pushedAt = window.KAKAO_PARSED_DATA ? (window.KAKAO_PARSED_DATA.pushedAt || '') : '';
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    stocks, dividends, deposits, trades, snapshots, exchangeRate, pushedAt
  }));
}
```

### 결과
- KAKAO_PARSED_DATA가 갱신될 때마다 자동으로 localStorage 업데이트
- 수동으로 `localStorage.removeItem()` 불필요
- 스냅샷 이력 보존 (기간별 수익률에 영향 없음)
- 타임스탬프 항상 최신 pushedAt 표시

### 커밋
`7223ad8 fix: KAKAO_PARSED_DATA 최신여부 자동 비교 — localStorage 자동갱신 + snapshots 보존`

---

## 이슈 #2: TRADE_DATE_CUT 하드코딩 (코드 품질 이슈)

### 증상
- `stock-dashboard.html`과 `kakao_watcher.py` 양쪽에 `'2026-06-19'`, `'12:50'` 문자열 하드코딩
- 포트폴리오 기준일 변경 시 양쪽 모두 수동으로 수정해야 하는 유지보수 위험

### 원인 분석
- kakao_watcher.py → 데이터 파싱 시 필터링 기준으로 사용
- HTML JS → 거래 적용/실현손익 계산 시 별도로 하드코딩
- 두 파일이 독립적으로 관리되어 동기화 실패 가능성 있음

### 수정 내용
**kakao_watcher.py**: `tradeDateCut`, `tradeTimeCut` 필드를 KAKAO_PARSED_DATA에 주입
```python
'tradeDateCut': TRADE_DATE_CUT,
'tradeTimeCut': TRADE_TIME_CUT,
```

**stock-dashboard.html**: 상수를 KAKAO_PARSED_DATA에서 읽도록 변경 (폴백: 기존 하드코딩값)
```javascript
const BASELINE_DATE = (window.KAKAO_PARSED_DATA && window.KAKAO_PARSED_DATA.tradeDateCut)
  ? window.KAKAO_PARSED_DATA.tradeDateCut : '2026-06-19';
const BASELINE_TIME = (window.KAKAO_PARSED_DATA && window.KAKAO_PARSED_DATA.tradeTimeCut)
  ? window.KAKAO_PARSED_DATA.tradeTimeCut : '12:50';
```
- 이후 모든 `'2026-06-19'`, `'12:50'` 하드코딩 → `BASELINE_DATE`, `BASELINE_TIME` 으로 교체

### 결과
- kakao_watcher.py 한 곳만 수정하면 HTML도 자동 반영
- KAKAO_PARSED_DATA 미존재 환경(로컬 테스트 등)에서도 폴백값으로 정상 동작

### 커밋
`5952932 feat: TRADE_DATE_CUT 상수화, 환율 자동갱신, 포트폴리오 추이 차트`

---

## 이슈 #3: 환율 고정값 사용 (기능 개선)

### 증상
- `EXCHANGE_RATE = 1512.8` 고정값 사용 → 환율 변동 시 해외 ETF 평가금액 오차

### 수정 내용
**kakao_watcher.py**: `fetch_exchange_rate()` 함수 추가
- Dunamu API (카카오 계열) 우선 조회
- 실패 시 Naver Finance 폴백
- `process_file()` 및 `refresh_prices_only()` 에서 현재가 조회 전 환율 먼저 갱신
- 갱신된 환율을 KAKAO_PARSED_DATA에 포함해 HTML에도 반영

### 주기
- 매 정시 현재가 갱신(09:00~22:00)과 동일 주기로 환율도 자동 갱신
- 카카오톡 파일 처리 시에도 갱신

### 커밋
`5952932 feat: TRADE_DATE_CUT 상수화, 환율 자동갱신, 포트폴리오 추이 차트`

---

## 이슈 #4: Netlify CDN 캐시로 인한 타임스탬프 미갱신 (배포 인프라 이슈)

### 증상
- watcher가 매 정시 HTML 갱신 후 GitHub push 성공
- git 로컬/원격 모두 최신 pushedAt = "2026-06-20T09:00:26" 확인됨
- 브라우저에는 "2026.06.19 20:40 기준 (자동업데이트)" 표시 (어제 시간)

### 원인 분석
```
watcher → HTML 업데이트 → GitHub push → Netlify 빌드
                                               ↓
                                        CDN 엣지 노드에 캐시 저장
                                               ↓
                      브라우저 요청 → CDN이 캐시된 구버전 HTML 반환 ❌
```
- Netlify는 HTML 파일을 CDN에 캐싱
- 새 배포 후에도 CDN 캐시 만료 전까지 구버전 HTML 서빙
- `Cache-Control` 헤더 미설정 시 Netlify 기본 캐시 정책 적용

### 수정 내용
**신규 파일: `netlify.toml`**
```toml
[[headers]]
  for = "/*.html"
  [headers.values]
    Cache-Control = "no-cache, no-store, must-revalidate"
    Pragma = "no-cache"
    Expires = "0"
```
- 모든 HTML에 `no-cache` 헤더 적용 → CDN이 항상 최신 HTML 요청

### 결과
- watcher 갱신 시 브라우저에 즉시 최신 타임스탬프 반영
- `Ctrl+Shift+R` 없이도 자동 갱신

### 커밋
`dbc7820 fix: HTML 캐시 비활성화 (Netlify CDN 캐시 문제 해결)`

---

## 이슈 #5: Netlify 빌드 크레딧 초과 → GitHub Pages 전환

### 증상
- Netlify Deploy 목록에서 "Skipped due to account credit usage exceeded" 표시
- 어제 20:40 이후 모든 배포 skip — 브라우저에 구버전 지속 표시
- Trigger deploy 수동 시도도 skip

### 원인 분석
- Netlify 무료 플랜: 빌드 크레딧 **300분/월** 제한
- kakao_watcher가 매 정시 push → 하루 최대 24번 Netlify 빌드 트리거
- 누적 빌드 시간이 300분 초과 → 모든 배포 자동 skip

### 해결 방법
**GitHub Pages로 전환** (완전 무료, 크레딧 제한 없음)
1. GitHub → stock_dashboard 저장소 → Settings → Pages
2. Source: Deploy from a branch / Branch: main / Folder: / (root) → Save

**변경 사항:**
- 대시보드 URL: `https://barobogi-stock-dashboard.netlify.app/` → `https://barobogi.github.io/stock_dashboard/stock-dashboard.html`
- kakao_watcher.py 알림 메시지: "Netlify 배포 중" → "GitHub Pages 반영 중"
- REF_continue.md, IMPROVEMENT_PROPOSAL 내 URL 전체 업데이트

### 결과
- GitHub Pages 정상 작동 확인: "2026.06.20 09:29 기준 (자동업데이트)" 표시
- 빌드 크레딧 제한 없이 매 정시 자동 갱신 가능

### 커밋
`4b2a9eb fix: Netlify → GitHub Pages URL 전환`

---

## 이슈 #6: 계좌비교 탭 차트 연속 애니메이션 → 메모리 과소비

### 증상
- 계좌비교 탭의 "계좌별 평가금액 vs 매수금액" 바 차트가 고정되지 않고 계속 움직임
- 탭 열어둘수록 브라우저 메모리 사용량이 점진적으로 증가

### 원인 분석
Chart.js는 기본적으로 `animation` 활성화 상태.  
`responsive: true` 옵션이 ResizeObserver를 등록해 캔버스 크기 변화를 감지하는데,
애니메이션 → 레이아웃 미세 변화 → ResizeObserver 트리거 → 재렌더 → 애니메이션 반복의
**무한 루프**가 발생해 CPU/메모리 점유가 지속적으로 증가.

추가 위험: `Chart.getChart()` 없이 변수 참조만으로 destroy 시 canvas에 Chart 인스턴스가
잔류하는 경우 메모리 누수 발생 가능.

### 수정 내용

**파일:** `stock-dashboard.html`

**수정 1: Chart.js 전역 애니메이션 비활성화 (모든 차트 일괄 적용)**
```javascript
// BASELINE_DATE/TIME 상수 선언 직후 추가
Chart.defaults.animation = false;
```

**수정 2: 계좌비교 두 차트에 `animation: false` + `Chart.getChart()` 안전 정리**
```javascript
// accountCompareChart
const ex1 = Chart.getChart(canvas1); if (ex1) ex1.destroy();
if (_accCompareChart) { _accCompareChart.destroy(); _accCompareChart = null; }
_accCompareChart = new Chart(canvas1, {
  ...
  options: { animation: false, responsive: true, ... }
});

// accountReturnChart
const ex2 = Chart.getChart(canvas2); if (ex2) ex2.destroy();
if (_accReturnChart) { _accReturnChart.destroy(); _accReturnChart = null; }
_accReturnChart = new Chart(canvas2, {
  ...
  options: { animation: false, indexAxis: 'y', ... }
});
```

### 결과
- 차트 최초 렌더 후 고정 표시 (움직임 없음)
- ResizeObserver 루프 차단 → CPU/메모리 안정화
- 전역 설정(`Chart.defaults.animation = false`)으로 기존 탭 모든 차트에도 동일 효과 적용

### 커밋
`1b06aee fix: 계좌비교 차트 애니메이션 루프 → 메모리 과소비 수정 (Chart.defaults.animation=false)`
