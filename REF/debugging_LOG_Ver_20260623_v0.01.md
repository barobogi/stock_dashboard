# Debugging Log — 2026-06-23 v0.01

---

## 이슈 #1: 계좌 ID 순서 변경으로 전체 데이터 매핑 깨짐

### 증상
- 일반계좌3(71417), 일반계좌4(71661) 추가 후 ISA/IRP 계좌 데이터가 사라지고
  일반계좌3/4에 잘못 표시됨
- 포트폴리오, 배당금, 거래내역 탭 전부 영향

### 원인 분석
신규 계좌를 기존 id 순서 중간에 삽입:

```
변경 전:  id1=일반1, id2=일반2, id3=ISA, id4=IRP, id5~7=연금저축
변경 후:  id1=일반1, id2=일반2, id3=일반계좌3(신규), id4=일반계좌4(신규), id5=ISA, id6=IRP ...
```

stocks/trades/dividends 데이터는 `accountId(숫자)` 로 계좌를 참조하므로,
기존 `accountId: 3` (ISA 데이터)이 새 `id 3` (일반계좌3)으로 잘못 매핑됨.

### 수정 내용
신규 계좌를 기존 id 뒤에 추가 (id 8, 9):

```python
# kakao_watcher.py ACCOUNTS_DEFAULT
{"id": 3, "num": "71297", "type": "isa",     "name": "ISA"},       # 기존 유지
{"id": 4, "num": "70714", "type": "irp",     "name": "IRP"},       # 기존 유지
...
{"id": 8, "num": "71417", "type": "general", "name": "일반계좌3"}, # 신규 — 뒤에 추가
{"id": 9, "num": "71661", "type": "general", "name": "일반계좌4"}, # 신규 — 뒤에 추가
```

stock-dashboard.html JS ACCOUNTS 동일하게 수정.

### 교훈
> **계좌 id는 한 번 부여하면 절대 변경/삽입 금지.**
> 신규 계좌는 항상 기존 최대 id + 1 부터 부여.
> id 1~7은 영구 고정.

---

## 이슈 #2: 환율 API 전부 사망 — 1,375원 고정

### 증상
- 대시보드 평가금액이 삼성증권과 크게 차이남
- 환율이 1,375원으로 고정 (실제 환율 ~1,537원)

### 원인 분석
kakao_watcher.py 환율 폴백 순서:
1. Dunamu API → DNS 실패 (서비스 종료)
2. Naver Finance → HTTP 409 (API 변경)
3. 하드코딩 기본값 `1375.0` 사용됨

### 수정 내용
Yahoo Finance + ExchangeRate-API 폴백 추가:

```python
# 3순위: Yahoo Finance
r = _sess.get('https://query1.finance.yahoo.com/v8/finance/chart/USDKRW=X?interval=1d&range=1d')
rate = float(r.json()['chart']['result'][0]['meta']['regularMarketPrice'])  # ~1536원

# 4순위: ExchangeRate-API (무료)
r = _sess.get('https://open.er-api.com/v6/latest/USD')
rate = float(r.json()['rates']['KRW'])  # ~1537원
```

### 현재 상태
Yahoo Finance 폴백으로 정상 작동 중. 실제 환율 반영됨.
