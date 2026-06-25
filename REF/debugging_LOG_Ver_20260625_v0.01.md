# Debugging Log — 2026-06-25 v0.01

---

## 이슈 #1: 거래시간 전부 00:00 표시

### 증상
- 거래내역 탭에서 모든 거래의 시간이 `00:00`으로 표시됨
- 날짜는 정상이나 시간 정보 없음

### 원인 분석
`kakao_watcher.py`의 `parse_datetime()`이 카카오톡 메시지 포맷을 처리 못 함.

카카오톡 내보내기 파일 구조:
```
2026년 6월 24일 화요일          ← 날짜만 있는 줄
[미래에셋대우] [오후 2:30] 주식체결안내 ...  ← 시간만 있는 줄 (날짜 없음)
```

기존 정규식은 `연 월 일 오전/오후 시:분`이 한 줄에 있어야 매치됨.
날짜와 시간이 분리된 카카오 포맷에서 시간 줄은 매치 실패 → `cur_time`이 초기값 `'00:00'` 유지.

### 수정 내용 (`kakao_watcher.py`)
시간전용 줄 `(오전|오후) \d+:\d+` 을 별도로 처리하는 로직 추가:

```python
def parse_datetime(line):
    # 기존: 날짜+시간 동시 패턴
    m = re.search(r'(\d{4})년\s+(\d+)월\s+(\d+)일\s+(오전|오후)\s+(\d+):(\d+)', line)
    if m: ...

    # 추가: 시간만 있는 줄 처리 (카카오 메시지 헤더 포맷)
    tm = re.search(r'(오전|오후)\s+(\d+):(\d+)', line)
    if tm:
        ap, h, mi = tm.group(1), int(tm.group(2)), int(tm.group(3))
        if ap == '오후' and h != 12: h += 12
        elif ap == '오전' and h == 12: h = 0
        return parse_date(line), f"{h:02d}:{mi:02d}"
```

### 교훈
> 카카오톡 내보내기는 날짜/시간이 항상 별도 줄. 날짜 파싱과 시간 파싱을 독립적으로 처리해야 함.

---

## 이슈 #2: 히트맵이 51개 타일 (같은 종목 계좌별 분리 표시)

### 증상
- 포트폴리오 히트맵에 같은 종목이 계좌 수만큼 별도 타일로 표시
- 예: 삼성전자가 일반계좌1/일반계좌2/ISA 각각 1개씩 → 3개 타일

### 원인 분석
`renderHeatmap()`이 `stocks` 배열을 그대로 순회.
`stocks`는 계좌 × 종목 단위로 저장되므로, 동일 종목도 계좌마다 별도 항목.

### 수정 내용 (`stock-dashboard.html`)
종목명 기준으로 먼저 합산 후 렌더링:

```js
const map = {};
stocks.filter(s => (s.evalAmount || 0) > 0).forEach(s => {
  if (!map[s.name]) map[s.name] = { name: s.name, evalAmount: 0, buyAmount: 0, accs: [] };
  map[s.name].evalAmount += s.evalAmount || 0;
  map[s.name].buyAmount  += s.buyAmount  || 0;
  const acc = ACCOUNTS.find(a => a.id === s.accountId);
  if (acc) map[s.name].accs.push(acc.name);
});
const active = Object.values(map);
```

tooltip에 보유 계좌 목록도 표시됨.

---

## 이슈 #3: 포트폴리오 평가금액 추이 차트 데이터 소멸

### 증상
- 포트폴리오 탭 추이 차트가 "스냅샷 데이터가 2개 이상 있어야 합니다" 메시지만 표시
- 이전에 쌓인 추이 데이터가 사라짐

### 원인 분석
스냅샷 데이터가 `localStorage`에만 저장됨.
브라우저 localStorage 초기화 시 전체 소멸. 복구 불가.

### 수정 내용 (`stock-dashboard.html`)
새 카카오 데이터 수신 시 자동으로 '자동' 타입 스냅샷 생성:

```js
if (kdPushedAt) {
  const pushDate = kdPushedAt.slice(0, 10);
  const pushTime = kdPushedAt.slice(11, 16);
  if (!snapshots.some(s => s.date === pushDate && s.type === '자동')) {
    const totalEval = stocks.reduce((s, x) => s + (x.evalAmount || 0), 0);
    ...
    snapshots.push({ date: pushDate, time: pushTime, type: '자동', ... });
  }
}
```

### 한계
- 이전 데이터는 복구 불가, 오늘부터 새로 누적됨
- localStorage 의존 근본 문제는 미해결 (GitHub HTML에 snapshots 포함하면 해결 가능 — 향후 과제)

### 교훈
> localStorage만 의존하는 중요 데이터는 반드시 서버 측(GitHub HTML)에도 백업 경로 필요.

---

## 이슈 #4: 소형 카카오 파일 수신 시 배당 855건 소멸

### 증상
- `kakao_auto_export.py` (12:30/22:00 스케줄) 파일 처리 후 배당 0건으로 초기화
- 직전까지 855건 배당 정상 표시

### 원인 분석
파일 크기 비교:
| 파일 유형 | 크기 | 배당 |
|-----------|------|------|
| 전체 이력 (`06250500_bogi.txt` 류) | ~1274 KB | 855건 |
| 자동 내보내기 (`260625_1230.txt`) | 30 KB | 0건 |

`kakao_auto_export.py`가 KakaoTalk 창에서 최근 대화만 내보냄 (전체 스크롤 포함 안 됨).
소형 파일 파싱 결과로 전체 데이터를 덮어쓰면서 배당 소멸.

### 수정 내용 (`kakao_watcher.py`)
기존 HTML에서 데이터 추출 후, 새 파일 배당이 기존 80% 미만이면 기존 배당 보존:

```python
def _extract_existing_data():
    html = Path(DASHBOARD_HTML).read_text(encoding='utf-8')
    m = re.search(r'window\.KAKAO_PARSED_DATA=(\{.*?\});</script>', html, re.DOTALL)
    if m: return json.loads(m.group(1))
    return None

# process_file() 내:
existing = _extract_existing_data()
if existing:
    ex_div = existing.get('dividends', [])
    if len(new_div) < len(ex_div) * 0.8:
        data['dividends'] = ex_div  # 기존 보존
```

---

## 이슈 #5: watcher 미실행으로 당일 거래 반영 안 됨

### 증상
- 오늘(25일) 거래 내역이 대시보드에 없음
- watcher 프로세스가 종료된 상태였음

### 원인
`kakao_watcher.py`가 실행 중이 아니면 Google Drive 파일 감지 불가.
12:30 자동내보내기 파일이 왔지만 처리되지 않음.

### 처리 방법
watcher `on_created` 이벤트만 감지하므로 기존 파일은 재감지 안 됨.
→ 파일 복사 트릭으로 수동 트리거:
```powershell
Copy-Item "G:\내 드라이브\KakaoTalk\260625_1230.txt" "G:\내 드라이브\KakaoTalk\260625_1230_r.txt"
```

### 예방
부팅 시 watcher 자동시작 설정 필요 (이미 VBS 등록되어 있어야 함 — 상태 재확인 필요).

---

## 이슈 #6: 거래내역 날짜만 기준 정렬 (시간 무시)

### 증상
- 같은 날 여러 거래가 시간 순서 무관하게 표시됨

### 수정 내용 (`stock-dashboard.html`)
```js
// Before
.sort((a, b) => (b.date || '').localeCompare(a.date || ''))

// After
.sort((a, b) => ((b.date||'')+(b.time||'')).localeCompare((a.date||'')+(a.time||'')))
```
