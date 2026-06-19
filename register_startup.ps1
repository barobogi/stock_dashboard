# 카카오톡 워처를 로그인 시 자동 시작으로 작업 스케줄러에 등록
$batPath = "D:\AI\260619_2_Daily_for_stock_TEMP\start_watcher.bat"
$taskName = "KakaoStock_Watcher"

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "✅ 작업 스케줄러 등록 완료: $taskName"
Write-Host "   - 로그인할 때마다 워처가 자동 시작됩니다."
Write-Host "   - 지금 바로 시작하려면: Start-ScheduledTask -TaskName $taskName"
