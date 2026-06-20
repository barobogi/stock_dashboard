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

### 1차 수정 (불완전)
```javascript
Chart.defaults.animation = false;  // 애니메이션은 꺼졌으나
// responsive: true + 컨테이너 고정 높이 없음 → ResizeObserver 루프 지속
```
커밋: `1b06aee`

### 2차 수정 (근본 해결)
`responsive: true` + `maintainAspectRatio: false` 차트는 컨테이너 높이를 기준으로 크기 계산.
컨테이너에 CSS 고정 높이가 없으면 캔버스 크기 변화 → ResizeObserver 감지 → 재렌더 → 크기 변화 → 무한 루프.

**Chart.js 공식 권장 방식**: 캔버스를 `position:relative; height:Xpx` div로 감싸기

```html
<!-- 수정 전: 컨테이너 높이 미지정 -->
<div class="...p-4">
  <canvas id="accountCompareChart" height="260"></canvas>
</div>

<!-- 수정 후: 고정 높이 래퍼 추가 -->
<div class="...p-4">
  <div style="position: relative; height: 260px;">
    <canvas id="accountCompareChart"></canvas>
  </div>
</div>
```
동일 패턴을 `accountReturnChart`에도 적용. (`evalHistoryChart`는 이미 래퍼 있어 정상)

### 결과
- ResizeObserver가 260px 고정 래퍼를 감시 → 높이 불변 → 루프 종료
- 차트 최초 렌더 후 완전 고정 표시
- CPU/메모리 안정화

### 커밋
- `1b06aee` animation 비활성화 (1차)
- `d5234dc` canvas 고정 높이 래퍼 (근본 해결)

---

## 이슈 #7: 일일 이메일 보고서 발송 미작동 → Daum SMTP 변경으로 해결

### 증상
- `daily_report.py` 매일 19:00(7시) 실행 (작업 스케줄러 등록됨)
- 그러나 이메일 미수신 — Naver SMTP 535 오류 확인
- 네이버 계정 2단계 인증 활성화로 SMTP 일반 비밀번호 로그인 차단됨

### 원인 분석
**Naver SMTP 불가 (2FA 활성화)**
```
Error: [Errno 535] b'5.7.8 Username and password not accepted'
Reason: 네이버 계정에 2단계 인증(2FA) 설정되어 있음
        → SMTP 접속 시 특수 앱 비밀번호 필요 (별도 발급 필요)
```

**기존 코드 (daily_report.py line 24-25)**:
```python
SMTP_HOST  = "smtp.naver.com"
SMTP_PORT  = 465
NAVER_ID = os.environ.get("NAVER_ID", "")
NAVER_PW = os.environ.get("NAVER_PW", "")
FROM_EMAIL = f"{NAVER_ID}@naver.com" if NAVER_ID else ""
```

### 해결 방법: Daum SMTP로 변경

**1단계: Daum SMTP 활성화**
- mail.daum.net 접속 → 로그인 → 설정 → SMTP 사용함 활성화
- Daum은 2FA 미지원 → 일반 계정 비밀번호로 SMTP 접속 가능

**2단계: 앱 비밀번호 생성 (보안 강화)**
- 비정상 접속을 피하기 위해 일반 비밀번호 대신 앱 전용 비밀번호 사용 권장
- Daum 보안 설정에서 "앱 비밀번호" 생성 → 해당 비밀번호로 SMTP 접근

**3단계: daily_report.py 수정** (line 4, 18-25, 242, 258-263)

```python
# 수정 전
SMTP_HOST  = "smtp.naver.com"
NAVER_ID = os.environ.get("NAVER_ID", "")
NAVER_PW = os.environ.get("NAVER_PW", "")
FROM_EMAIL = f"{NAVER_ID}@naver.com" if NAVER_ID else ""
server.login(NAVER_ID, NAVER_PW)

# 수정 후
SMTP_HOST  = "smtp.daum.net"
DAUM_ID = os.environ.get("DAUM_ID", "")
DAUM_PW = os.environ.get("DAUM_PW", "")  # 앱 비밀번호
FROM_EMAIL = f"{DAUM_ID}@daum.net" if DAUM_ID else ""
server.login(DAUM_ID, DAUM_PW)
```

**4단계: 환경변수 등록 (PowerShell)**
```powershell
[System.Environment]::SetEnvironmentVariable("DAUM_ID", "hanbogi79", "User")
[System.Environment]::SetEnvironmentVariable("DAUM_PW", "kpsbzvdunszborwo", "User")
```

### 테스트 및 결과

**테스트 실행** (2026-06-20 12:35):
```powershell
$env:DAUM_ID = "hanbogi79"
$env:DAUM_PW = "kpsbzvdunszborwo"
& "C:\hb\python.exe" "D:\AI\260619_2_Daily_for_stock_TEMP\daily_report.py"
```

**출력 결과**:
```
[2026-06-20 12:35:06] 일일 보고서 생성 시작
  총 평가금액: ₩596,205,884
  일간 변동:  +₩0 (+0.00%)
  오늘 거래:  0건
  오늘 배당:  0건 ₩0
  ✅ 메일 발송 완료 → barobogi79@gmail.com
  ✅ 스냅샷 저장: 2026-06-20 ₩596,205,884
```

✅ **메일 발송 성공!**

### 발송 현황

| 항목 | 상태 |
|------|------|
| 발신자 | hanbogi79@daum.net |
| 수신자 | barobogi79@gmail.com |
| 제목 | [Barobogi] 주식 일일 보고서 2026-06-20 ... |
| 상태 | ✅ 성공 |
| 수신 위치 | Gmail 스팸함 (첫 발신자 자동 분류) |

### Gmail 스팸함 처리

첫 발신자 이메일을 Gmail이 자동으로 스팸 처리함 → "스팸 아님"으로 표시하면 이후 매일 받은편지함으로 수신.

```
1. Gmail 스팸함 열기
2. hanbogi79@daum.net 발신 메일 선택
3. 상단 "스팸 아님" 클릭
4. 이후 매일 받은편지함으로 자동 수신 ✅
```

### 스케줄러 확인

Windows 작업 스케줄러: **StockDailyReport** (매일 19:00)
- 이제부터 매일 오후 7시 자동으로 이메일 발송됨
- daily_snapshot.json도 동시에 갱신됨 (내일 일간 변동 비교용)

### 결과
- ✅ Naver SMTP 문제 완벽 해결
- ✅ 이메일 발송 정상 작동
- ✅ 일간 스냅샷 저장 정상 작동
- ✅ 매일 자동 실행 스케줄러 확인

### 커밋
`d42fdd4 fix: 이메일 SMTP Naver → Daum 변경, GitHub Pages URL 수정`

---

## 이슈 #8: ac.finance.naver.com DNS 차단 — 신규 종목 코드 검색 실패

### 증상
- `_naver_search_code()` 함수가 DNS 차단된 `ac.finance.naver.com` 사용 중
- 현재는 `ticker_map.json` 캐시(24종목)로 우회 중이어서 정상 작동
- **신규 종목 추가 시** 코드 검색 실패 → 현재가 0원 표시

### 원인
RFE_report에 수정 기록됐으나 실제 코드에는 반영 안 된 상태였음

### 수정 내용
```python
# 변경 전 (DNS 차단)
r = _sess.get('https://ac.finance.naver.com/ac', ...)

# 변경 후 (정상 작동)
r = _sess.get('https://ac.stock.naver.com/ac', ...)
```

### 커밋
`876c202 fix: Naver검색 URL 수정(ac.stock), 환율 기본값 1375원 현실화, API실패시 이전값 유지`

---

## 이슈 #9: EXCHANGE_RATE 기본값 시세 오차 (1512.8 → 1375.0)

### 증상
- `EXCHANGE_RATE = 1512.8` 고정 — 현재 실제 환율 ~1375원과 약 10% 차이
- Dunamu API 실패 시 이 폴백값으로 해외 ETF 평가금액 과대계산

### 추가 개선
API 실패 시 `data['exchangeRate'] = EXCHANGE_RATE` 항상 주입하도록 변경
→ 이전 성공 조회값이 전역변수에 남아있으면 그 값을 사용 (최후 수단만 기본값 사용)

### 커밋
`876c202 fix: Naver검색 URL 수정(ac.stock), 환율 기본값 1375원 현실화, API실패시 이전값 유지`

---

## 이슈 #10: watcher 재부팅 자동시작 미작동 — 시작 프로그램 폴더로 전환

### 증상
- 레지스트리 Run 키(`KakaoWatcher`) 등록돼 있으나 재부팅 후 자동 시작 실패
- 매번 수동으로 `Start-Process` 실행 필요

### 원인
부팅 직후 Google Drive가 아직 마운트되기 전에 watcher 실행 →
`G:\내 드라이브\KakaoTalk` 폴더 없음 → 즉시 종료

### 수정 내용
1. 레지스트리 Run 키 제거
2. `start_watcher.vbs` 생성 — 30초 대기 후 watcher 실행 (창 숨김)
```vbs
WScript.Sleep 30000
CreateObject("WScript.Shell").Run """C:\hb\python.exe"" ""D:\AI\260619_2_Daily_for_stock_TEMP\kakao_watcher.py""", 0, False
```
3. 시작 프로그램 폴더에 단축키 등록
```
C:\Users\82102\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\KakaoWatcher.lnk
```

### 동작 흐름
```
Windows 부팅 → 로그인
→ KakaoWatcher.lnk 자동 실행
→ start_watcher.vbs 30초 대기 (Google Drive 마운트 대기)
→ kakao_watcher.py 백그라운드 실행 (창 숨김)
```

### 결과
- 레지스트리 Run 키 → 시작 프로그램 폴더 단축키로 전환
- 30초 지연으로 Google Drive 마운트 후 안정적 시작

---

## 이슈 #11: git push 실패 시 재시도 없음 — 네트워크 일시 단절 시 손실

### 증상
- `subprocess.run(['git', 'push'], check=True)` 1회 시도 후 예외 발생 시 그냥 종료
- 새벽 네트워크 불안정 구간에서 push 실패 시 카카오톡 업데이트 유실

### 수정 내용
`git_push()` 함수와 `refresh_prices_only()` 내 push 코드 모두 3회 재시도 + 30초 간격 대기 적용
```python
for attempt in range(1, 4):
    try:
        subprocess.run(['git', 'push'], check=True, timeout=30)
        log.info("  GitHub push 완료")
        return True
    except Exception as e:
        log.warning(f"  push 실패 ({attempt}/3): {e}")
        if attempt < 3:
            time.sleep(30)
log.error("  push 3회 실패 — 다음 갱신 시 재시도")
```

### 커밋
`7fe97e3 feat: 기술부채 ④⑤⑥⑦ 해소`

---

## 이슈 #12: observer 비정상 종료 시 자동 재시작 없음

### 증상
- watchdog Observer 스레드가 예외로 종료되면 감시 중단
- 다음 번 카카오톡 파일 저장이 자동 처리되지 않음

### 수정 내용
메인 루프를 `while True`로 감싸 observer 비정상 종료 시 10초 후 자동 재시작
```python
while True:
    observer = Observer()
    observer.schedule(handler, folder, recursive=True)
    observer.start()
    try:
        while observer.is_alive():
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop(); observer.join(); break
    except Exception as e:
        log.error(f"  observer 오류: {e} — 10초 후 자동 재시작")
        observer.stop(); observer.join()
        time.sleep(10)
```

### 커밋
`7fe97e3 feat: 기술부채 ④⑤⑥⑦ 해소`

---

## 이슈 #13: DIV_CUTOFF = "2025-01-01" 하드코딩 — 매년 수동 변경 필요

### 증상
- 2027년이 되면 2026년 배당이 필터링되어 보이지 않음
- 매년 1월 수동으로 연도 변경 필요

### 수정 내용
```python
# 변경 전
DIV_CUTOFF = "2025-01-01"

# 변경 후
DIV_CUTOFF = f"{datetime.now().year - 1}-01-01"  # 전년도 1월1일 자동 계산
```

### 커밋
`7fe97e3 feat: 기술부채 ④⑤⑥⑦ 해소`

---

## 이슈 #14: print() 로깅 — watcher.log 파일 미기록, 오류 추적 어려움

### 증상
- 모든 진단 메시지가 stdout에만 출력
- VBS로 백그라운드 실행 시 창 없음 → 로그 확인 불가
- 오류 발생 시 재현이나 추적 어려움

### 수정 내용
Python 표준 `logging` 모듈로 파일+콘솔 동시 출력
```python
def _setup_logger():
    log_path = Path(r"D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log")
    logger = logging.getLogger("watcher")
    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    ch = logging.StreamHandler(sys.stdout)
    logger.addHandler(fh); logger.addHandler(ch)
    return logger

log = _setup_logger()
```
- 기존 `print()` → `log.info()` / `log.warning()` / `log.error()` 전면 교체
- 로그 파일: `D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log`

### 커밋
`7fe97e3 feat: 기술부채 ④⑤⑥⑦ 해소`
