@echo off
chcp 65001 > nul
title 카카오톡 자동 업데이트 워처
cd /d "D:\AI\260619_2_Daily_for_stock_TEMP"
echo ============================================
echo  카카오톡 → MYBOX → 대시보드 자동 업데이트
echo ============================================
echo.

:: Python 설치 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    pause
    exit /b
)

:: watchdog 설치 확인 및 자동 설치
python -c "import watchdog" > nul 2>&1
if errorlevel 1 (
    echo watchdog 라이브러리 설치 중...
    pip install -r requirements.txt
    echo.
)

echo 워처를 시작합니다. 이 창을 닫지 마세요.
echo.
python kakao_watcher.py
pause
