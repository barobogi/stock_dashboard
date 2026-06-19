# daily_report.py 를 매일 오후 7시 실행하는 작업 스케줄러 등록
# 실행: PowerShell -ExecutionPolicy Bypass -File register_daily_report.ps1

$pythonPath = (Get-Command python).Source
$scriptPath = "D:\AI\260619_2_Daily_for_stock_TEMP\daily_report.py"
$logFile    = "D:\AI\260619_2_Daily_for_stock_TEMP\daily_report.log"
$taskName   = "StockDailyReport"

# 기존 태스크 제거 (재등록 방지)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "$scriptPath >> `"$logFile`" 2>&1" `
    -WorkingDirectory "D:\AI\260619_2_Daily_for_stock_TEMP"

$trigger = New-ScheduledTaskTrigger -Daily -At "19:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host "✅ 작업 스케줄러 등록 완료: '$taskName' (매일 오후 7:00)"
Write-Host "   Python: $pythonPath"
Write-Host "   Script: $scriptPath"
Write-Host "   Log:    $logFile"
Write-Host ""
Write-Host "▶ 지금 바로 테스트하려면:"
Write-Host "   Start-ScheduledTask -TaskName '$taskName'"
