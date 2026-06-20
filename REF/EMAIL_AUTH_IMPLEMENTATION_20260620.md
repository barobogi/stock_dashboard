# 이메일 인증 구현 가이드 — Daum SMTP 변경
> 작성일: 2026-06-20  
> 대상: daily_report.py  
> 상태: Phase 1 후 구현 예정

---

## 📋 현재 상황

**문제**: Naver SMTP 535 오류 (2단계 인증 활성화)
```
Error: Username and Password not accepted
원인: 네이버 2FA 활성화 시 일반 PW로 SMTP 불가
```

**해결책**: Daum/Kakao 메일로 변경 (2FA 미지원)

---

## 🔧 구현 단계

### Step 1: Daum 계정 준비
```
1. https://www.daum.net 계정 확인 (또는 신규 생성)
2. Daum 메일 활성화 (기본 활성화됨)
3. 이메일 주소: 아이디@daum.net
```

### Step 2: daily_report.py 수정

#### 수정 위치: 13~25번 줄
```python
# ❌ 변경 전
SMTP_HOST  = "smtp.naver.com"
SMTP_PORT  = 465
NAVER_ID = os.environ.get("NAVER_ID", "")
NAVER_PW = os.environ.get("NAVER_PW", "")
FROM_EMAIL = f"{NAVER_ID}@naver.com" if NAVER_ID else ""

# ✅ 변경 후
SMTP_HOST  = "smtp.daum.net"    # ← Daum으로 변경
SMTP_PORT  = 465                # ← 동일 (TLS/SSL)
DAUM_ID = os.environ.get("DAUM_ID", "")      # ← 환경변수명 변경
DAUM_PW = os.environ.get("DAUM_PW", "")      # ← 환경변수명 변경
FROM_EMAIL = f"{DAUM_ID}@daum.net" if DAUM_ID else ""  # ← @daum.net으로 변경
```

#### 추가 수정 위치: 메일 발송 부분
```python
# ❌ 변경 전 (대략 line 190 근처)
server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
server.login(NAVER_ID, NAVER_PW)

# ✅ 변경 후
server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
server.login(DAUM_ID, DAUM_PW)
```

---

### Step 3: 환경변수 등록

**PowerShell (관리자 실행)**:
```powershell
[System.Environment]::SetEnvironmentVariable("DAUM_ID", "your_daum_email", "User")
[System.Environment]::SetEnvironmentVariable("DAUM_PW", "your_daum_password", "User")
```

**확인**:
```powershell
[System.Environment]::GetEnvironmentVariable("DAUM_ID", "User")
```

---

### Step 4: 테스트 실행

```bash
# daily_report.py 직접 실행 (수동 테스트)
python daily_report.py

# 예상 결과:
# ✅ 성공: "이메일 발송 완료"
# ❌ 실패: "535 오류" → 아이디/비번 재확인
```

---

### Step 5: 작업 스케줄러 확인

**이미 등록됨**:
```
작업 이름: StockDailyReport
일정: 매일 19:00 (오후 7시)
실행: python daily_report.py
```

**확인 방법**:
```powershell
Get-ScheduledTask -TaskName "StockDailyReport" | Get-ScheduledTaskInfo
```

---

## ✅ 검증 체크리스트

- [ ] Daum 메일 계정 준비됨
- [ ] daily_report.py 수정 완료
  - [ ] SMTP_HOST = "smtp.daum.net"
  - [ ] 환경변수명 NAVER → DAUM으로 변경
  - [ ] FROM_EMAIL @daum.net으로 변경
- [ ] 환경변수 등록됨
  - [ ] DAUM_ID
  - [ ] DAUM_PW
- [ ] 수동 테스트 성공
- [ ] 작업 스케줄러 확인됨

---

## 🔄 대체안 (필요 시)

### Gmail 신규 계정
```
장점: 국제 표준, 더 안정적
단점: 추가 계정 필요

smtp.gmail.com:587
사용자명: your-email@gmail.com
비밀번호: 앱 비밀번호 (별도 발급 필요, 2FA 미사용 시 일반 PW)
```

### Kakao 메일
```
Daum과 동일 (카카오 인수 후 통합)
smtp.daum.net:465
사용자명: kakao-email@kakao.com
```

---

## 📝 예상 효과

| 항목 | 현재 | 변경 후 |
|------|------|--------|
| 이메일 발송 | ❌ 실패 | ✅ 성공 |
| 일일 보고서 | 미수신 | 매일 7시 자동 수신 |
| 배당금/거래 알림 | 없음 | 자동 이메일 |
| 스냅샷 저장 | ❌ | ✅ daily_snapshot.json |

---

## 🎯 다음: Phase 1 개발 후 구현

1. Phase 1 (히트맵 + 수익률 + 계좌비교) 완성
2. 이메일 인증 구현 (위 가이드)
3. 테스트 + 배포
