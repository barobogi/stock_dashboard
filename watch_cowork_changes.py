#!/usr/bin/env python3
# watch_cowork_changes.py — Cowork(Claude Desktop) / CLI 파일 변경 자동 감지 → git push

import os, time, subprocess, logging, threading
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_PATH    = Path(r"D:\AI\260619_2_Daily_for_stock_TEMP")
LOG_PATH     = REPO_PATH / "cowork_changes.log"
WATCH_EXTS   = {'.html', '.py', '.md', '.json', '.css', '.js', '.toml'}
IGNORE_FILES = {'watcher.log', 'cowork_changes.log'}
IGNORE_DIRS  = {'.git', '__pycache__'}
DEBOUNCE_SEC  = 12  # 연속 저장을 하나로 묶는 대기 시간
STARTUP_GRACE = 8   # 시작 직후 watchdog 초기 스캔 무시 (초)

# ── 로거 ──────────────────────────────────────────────────
logger = logging.getLogger("cowork_watcher")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(fh)
    logger.addHandler(ch)

_timer: threading.Timer | None = None
_timer_lock = threading.Lock()
_start_time  = time.time()

# ── git push ───────────────────────────────────────────────
def _git_push_changes():
    """변경사항 commit + push (kakao_watcher와 충돌 방지 포함)"""
    git_lock = REPO_PATH / ".git" / "index.lock"

    # kakao_watcher가 git 작업 중이면 최대 30초 대기
    for _ in range(6):
        if not git_lock.exists():
            break
        logger.warning("  ⏳ git index.lock 감지 — 5초 대기 (kakao_watcher 작업 중)")
        time.sleep(5)

    os.chdir(REPO_PATH)

    result = subprocess.run(['git', 'status', '--porcelain'],
                            capture_output=True, text=True)
    if not result.stdout.strip():
        logger.info("  변경사항 없음 — push 생략 (kakao_watcher가 이미 처리)")
        return

    changed = [ln[3:].strip() for ln in result.stdout.strip().splitlines()]
    logger.info(f"  📝 변경 파일: {', '.join(changed)}")

    # git add -u: 이미 추적 중인 파일만 스테이징 (미추적 신규파일 자동추가 방지)
    subprocess.run(['git', 'add', '-u'], check=True)
    msg = f"auto: Cowork/CLI 변경 자동 배포 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(['git', 'commit', '-m', msg], check=True)

    for attempt in range(1, 4):
        try:
            subprocess.run(['git', 'push'], check=True, timeout=30)
            logger.info("  ✅ push 완료 → GitHub Pages 배포 중 (2~3분)")
            return
        except Exception as e:
            logger.warning(f"  push 실패 ({attempt}/3): {e}")
            if attempt < 3:
                time.sleep(30)
    logger.error("  ❌ push 3회 실패 — 다음 변경 시 재시도")


def _schedule_push():
    global _timer
    with _timer_lock:
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE_SEC, _git_push_changes)
        _timer.start()


# ── watchdog 핸들러 ────────────────────────────────────────
class CoworkHandler(FileSystemEventHandler):
    def on_modified(self, event):
        self._handle(event.src_path)

    def on_created(self, event):
        self._handle(event.src_path)

    def _handle(self, path: str):
        p = Path(path)
        if p.is_dir():
            return
        if any(d in p.parts for d in IGNORE_DIRS):
            return
        if p.name in IGNORE_FILES:
            return
        if p.suffix not in WATCH_EXTS:
            return
        if time.time() - _start_time < STARTUP_GRACE:
            return  # 시작 직후 초기 스캔 이벤트 무시
        logger.info(f"  📂 변경 감지: {p.relative_to(REPO_PATH)} — {DEBOUNCE_SEC}초 후 push 예정")
        _schedule_push()


# ── 메인 루프 (observer 비정상 종료 시 자동 재시작) ─────────
def main():
    logger.info("=" * 52)
    logger.info("🤝 Cowork/CLI 변경사항 자동 배포 워처 시작")
    logger.info(f"   감시 폴더 : {REPO_PATH}")
    logger.info(f"   감시 확장 : {', '.join(sorted(WATCH_EXTS))}")
    logger.info(f"   debounce  : {DEBOUNCE_SEC}초")
    logger.info("=" * 52)

    while True:
        handler  = CoworkHandler()
        observer = Observer()
        observer.schedule(handler, str(REPO_PATH), recursive=True)
        observer.start()
        logger.info("  👀 파일 감시 시작")
        try:
            while observer.is_alive():
                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("\n워처 종료 (Ctrl+C)")
            observer.stop()
            observer.join()
            break
        except Exception as e:
            logger.error(f"  observer 오류: {e} — 10초 후 자동 재시작")
            observer.stop()
            observer.join()
            time.sleep(10)


if __name__ == '__main__':
    main()
