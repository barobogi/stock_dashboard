# =============================================================================
# 자동 실행 설정 스크립트 (3가지: 6시마다, 파일 도착 시, 부팅 시)
# =============================================================================

# 관리자 권한 확인
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ 관리자 권한이 필요합니다. 다시 실행해주세요."
    exit 1
}

$batPath = "D:\AI\260619_2_Daily_for_stock_TEMP\start_watcher.bat"
$pythonScript = "D:\AI\260619_2_Daily_for_stock_TEMP\kakao_watcher.py"
$logFolder = "D:\AI\260619_2_Daily_for_stock_TEMP\logs"
if (-not (Test-Path $logFolder)) {
    New-Item -ItemType Directory -Path $logFolder | Out-Null
}

Write-Host "🔧 자동 실행 설정을 시작합니다..." -ForegroundColor Cyan
Write-Host ""

# =============================================================================
# 1️⃣  로그인 시 자동 시작 (기존 유지)
# =============================================================================
Write-Host "1️⃣  [로그인 시 자동 시작] 작업 스케줄러 등록 중..." -ForegroundColor Yellow

$action1 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger1 = New-ScheduledTaskTrigger -AtLogOn
$settings1 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "KakaoStock_Watcher_AtLogOn" `
    -Action $action1 `
    -Trigger $trigger1 `
    -Settings $settings1 `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "   ✅ 로그인 시 워처 시작 등록 완료`n"

# =============================================================================
# 2️⃣  부팅 시 자동 시작
# =============================================================================
Write-Host "2️⃣  [부팅 시 자동 시작] 작업 스케줄러 등록 중..." -ForegroundColor Yellow

$trigger2 = New-ScheduledTaskTrigger -AtStartup
$settings2 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "KakaoStock_Watcher_AtStartup" `
    -Action $action1 `
    -Trigger $trigger2 `
    -Settings $settings2 `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "   ✅ 부팅 시 워처 시작 등록 완료`n"

# =============================================================================
# 3️⃣  매일 오후 6시 자동 실행
# =============================================================================
Write-Host "3️⃣  [매일 6시] 자동 실행 작업 등록 중..." -ForegroundColor Yellow

$logFile = Join-Path $logFolder "auto_6pm_$(Get-Date -Format 'yyyyMMdd').log"
$psCommand = "python `"$pythonScript`" 2>&1 | Tee-Object -FilePath `"$logFile`""

$action3 = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$psCommand`""

# 매일 오후 6시 (18:00)
$trigger3 = New-ScheduledTaskTrigger `
    -Daily `
    -At "18:00"

$settings3 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "KakaoStock_Daily_6PM" `
    -Action $action3 `
    -Trigger $trigger3 `
    -Settings $settings3 `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "   ✅ 매일 오후 6시 자동 실행 등록 완료`n"

# =============================================================================
# 결과 표시
# =============================================================================
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "✅ 모든 자동 실행 설정 완료!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "📋 등록된 작업:" -ForegroundColor Cyan
Write-Host "   1. KakaoStock_Watcher_AtLogOn   → 로그인할 때마다 시작"
Write-Host "   2. KakaoStock_Watcher_AtStartup → 컴퓨터 부팅 시 시작"
Write-Host "   3. KakaoStock_Daily_6PM         → 매일 오후 6시 자동 실행"
Write-Host ""
Write-Host "📂 감시 폴더: G:\내 드라이브\KakaoTalk" -ForegroundColor Cyan
Write-Host "   (카카오톡 → 내보내기 → MYBOX 저장 시 자동 처리)"
Write-Host ""
Write-Host "📊 자동 실행 로그:" -ForegroundColor Cyan
Write-Host "   $logFolder"
Write-Host ""
Write-Host "⚙️  작업 스케줄러 확인:" -ForegroundColor Yellow
Write-Host "   작업 스케줄러 → 작업 라이브러리 → KakaoStock_* 항목 확인"
Write-Host ""
