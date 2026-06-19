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
