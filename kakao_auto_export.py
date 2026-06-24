#!/usr/bin/env python3
"""
kakao_auto_export.py  v1.0
삼성증권 카카오톡 대화 자동 내보내기
매일 12:30, 22:00 Windows 작업 스케줄러로 실행
흐름: 카카오톡 시작 → 삼성증권 채팅방 → Ctrl+S → 저장 → 종료
"""

import subprocess
import time
import sys
import os
import pyautogui
import win32gui
import win32con
import pyperclip
from datetime import datetime

# ── 설정 ───────────────────────────────────────────────────────
KAKAO_EXE    = r"C:\Program Files\Kakao\KakaoTalk\KakaoTalk.exe"
SAVE_FOLDER  = r"G:\내 드라이브\KakaoTalk"
CHAT_NAME    = "삼성증권"

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.2

# ── 유틸 ───────────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_save_path():
    now = datetime.now()
    fname = f"{now.strftime('%y%m%d')}_{now.strftime('%H%M')}.txt"
    return os.path.join(SAVE_FOLDER, fname)

def find_window(title_part):
    found = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and title_part in win32gui.GetWindowText(hwnd):
            found.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None

def activate(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.8)
    except Exception as e:
        log(f"  activate 실패: {e}")

def wait_window(title_part, timeout=12):
    for _ in range(timeout * 2):
        h = find_window(title_part)
        if h:
            return h
        time.sleep(0.5)
    return None

def paste_text(text):
    """클립보드 경유로 붙여넣기 (한글 포함 경로 대응)"""
    old = pyperclip.paste()
    pyperclip.copy(text)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyperclip.copy(old)

# ── 메인 ───────────────────────────────────────────────────────
def main():
    save_path = get_save_path()
    log(f"=== 카카오톡 자동 내보내기 시작 ===")
    log(f"저장 경로: {save_path}")

    # 1. 카카오톡 실행 여부 확인
    kakao_hwnd  = find_window("카카오톡")
    was_running = kakao_hwnd is not None

    if not kakao_hwnd:
        log("카카오톡 시작 중...")
        subprocess.Popen([KAKAO_EXE])
        kakao_hwnd = wait_window("카카오톡", timeout=20)
        if not kakao_hwnd:
            log("ERROR: 카카오톡 시작 실패")
            return False
        time.sleep(3)   # 로그인 대기

    log("카카오톡 창 활성화")
    activate(kakao_hwnd)

    # 2. 삼성증권 채팅방 창 확인 / 검색으로 열기
    chat_hwnd = find_window(CHAT_NAME)

    if not chat_hwnd:
        log(f"'{CHAT_NAME}' 채팅방 검색 중...")
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.8)
        paste_text(CHAT_NAME)
        time.sleep(1.2)
        pyautogui.press('enter')
        time.sleep(1.5)
        chat_hwnd = find_window(CHAT_NAME)

    if not chat_hwnd:
        log(f"ERROR: '{CHAT_NAME}' 채팅방 창을 찾을 수 없음")
        return False

    log(f"'{CHAT_NAME}' 채팅방 활성화")
    activate(chat_hwnd)
    time.sleep(0.5)

    # 3. Ctrl+S → 대화 내보내기
    log("Ctrl+S (대화 내보내기) 실행...")
    pyautogui.hotkey('ctrl', 's')

    # 4. 저장 대화상자 대기 및 처리
    log("저장 대화상자 대기 중...")
    save_hwnd = wait_window("다른 이름으로 저장", timeout=10)

    if not save_hwnd:
        log("ERROR: 저장 대화상자가 나타나지 않음")
        return False

    log("저장 경로·파일명 입력 중...")
    activate(save_hwnd)
    time.sleep(0.5)

    # 파일 이름 필드에 전체 경로 입력 → Windows가 폴더 이동 + 파일명 동시 처리
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    paste_text(save_path)
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(1.5)

    log(f"✅ 저장 완료: {save_path}")

    # 5. 카카오톡 정리 (원래 꺼져 있었으면 종료, 켜져 있었으면 트레이로)
    if not was_running:
        log("카카오톡 종료 (원래 꺼져 있었음)")
        subprocess.run(['taskkill', '/IM', 'KakaoTalk.exe', '/F'],
                       capture_output=True)
    else:
        log("카카오톡 트레이로 숨김 (원래 실행 중이었음)")
        hwnd = find_window("카카오톡")
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    log("=== 완료 ===")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
