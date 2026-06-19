#!/usr/bin/env python3
# kakao_watcher.py — 카카오톡 파일 자동 감지 → 파싱 → GitHub push → Netlify 배포

import os, re, json, time, sys, subprocess
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ═══════════════════════════════════════════════════════════
#  설정 — 본인 환경에 맞게 수정
# ═══════════════════════════════════════════════════════════
MYBOX_FOLDER   = r"G:\내 드라이브\KakaoTalk"                  # Google Drive 가상 드라이브
REPO_PATH      = r"D:\AI\260619_2_Daily_for_stock_TEMP"     # Git 저장소 경로
DASHBOARD_HTML = os.path.join(REPO_PATH, "stock-dashboard.html")
KAKAO_KEYWORD  = "KakaoTalk"   # 감지할 파일명 키워드 (대소문자 무시)
EXCHANGE_RATE  = 1512.8        # USD → KRW 기본 환율

# 파싱 기준
DIV_CUTOFF        = "2025-01-01"
TRADE_DATE_CUT    = "2026-06-19"
TRADE_TIME_CUT    = "12:50"

# ═══════════════════════════════════════════════════════════
#  계좌 정의
# ═══════════════════════════════════════════════════════════
ACCOUNTS = [
    {"id": 1, "num": "70714", "type": "general"},
    {"id": 2, "num": "70871", "type": "general"},
    {"id": 3, "num": "71297", "type": "isa"},
    {"id": 4, "num": "70714", "type": "irp"},    # 70714이지만 IRP/퇴직연금 키워드로 구분
    {"id": 5, "num": "71462", "type": "pension"},
    {"id": 6, "num": "71615", "type": "pension"},
    {"id": 7, "num": "70868", "type": "pension"},
]

def find_account(num, ctx_lines):
    """계좌번호 앞5자리 + 주변 라인으로 계좌 특정"""
    if num == "70714":
        for l in ctx_lines:
            if "IRP" in l or "퇴직연금" in l:
                return next((a for a in ACCOUNTS if a["id"] == 4), None)
        return next((a for a in ACCOUNTS if a["id"] == 1), None)
    return next((a for a in ACCOUNTS if a["num"] == num and a["type"] != "irp"), None)

# ═══════════════════════════════════════════════════════════
#  파싱 유틸
# ═══════════════════════════════════════════════════════════
def to_int(s):
    return int(re.sub(r'[,\s]', '', s))

def parse_date(line):
    m = re.search(r'(\d{4})년\s*(\d+)월\s*(\d+)일', line)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None

def parse_datetime(line):
    m = re.search(r'(\d{4})년\s+(\d+)월\s+(\d+)일\s+(오전|오후)\s+(\d+):(\d+)', line)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ap, h, mi = m.group(4), int(m.group(5)), int(m.group(6))
        if ap == '오후' and h != 12: h += 12
        elif ap == '오전' and h == 12: h = 0
        return f"{y}-{mo:02d}-{d:02d}", f"{h:02d}:{mi:02d}"
    return parse_date(line), None

# ═══════════════════════════════════════════════════════════
#  메인 파서 (JS parseContent 로직을 Python으로 포팅)
# ═══════════════════════════════════════════════════════════
def parse_kakao(filepath):
    try:
        text = Path(filepath).read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = Path(filepath).read_text(encoding='cp949')

    lines = text.splitlines()
    dividends, trades, deposits = [], [], []
    div_keys = set()
    cur_date = datetime.now().strftime('%Y-%m-%d')
    cur_time = '00:00'

    for i, raw in enumerate(lines):
        line = raw.strip()

        # 현재 날짜/시간 갱신
        dt, tm = parse_datetime(line)
        if dt:
            cur_date = dt
            if tm: cur_time = tm

        # ── 배당 (세후 분배금액만) ────────────────────────
        if (('세후 분배금액' in line or ('배당금' in line and '세전' not in line))
                and re.search(r':\s*[\d.,]+', line)):

            am = re.search(r':\s*([\d.,]+)\s*(?:USD|원)?', line)
            if not am: continue
            is_usd = 'USD' in line
            raw_val = float(am.group(1).replace(',', ''))
            amount  = round(raw_val * EXCHANGE_RATE) if is_usd else int(raw_val)
            if amount <= 0: continue

            tax = 0
            for j in range(max(0, i-3), i):
                tm2 = re.search(r'세금\s*:\s*([\d,]+)\s*원', lines[j].strip())
                if tm2: tax = to_int(tm2.group(1)); break

            stock_name = acc_num = ''
            div_date = cur_date

            for j in range(max(0, i-8), min(len(lines), i+2)):
                ck = lines[j].strip()
                if not stock_name and ('종목명' in ck or '상품명' in ck):
                    sm = re.search(r'[종목상품]명\s*:\s*(.+?)(?:\s*$|-)', ck)
                    if sm: stock_name = sm.group(1).strip()
                if not acc_num and '계좌번호' in ck:
                    am2 = re.search(r'(\d{5})\*+', ck)
                    if am2: acc_num = am2.group(1)
                d = parse_date(ck)
                if d: div_date = d

            if not stock_name or not acc_num or div_date < DIV_CUTOFF: continue
            account = find_account(acc_num, lines[max(0,i-8):min(len(lines),i+2)])
            if not account: continue

            key = f"{div_date}_{account['id']}_{stock_name}"
            if key in div_keys: continue
            div_keys.add(key)

            dividends.append({'accountId': account['id'], 'stock': stock_name,
                              'amount': amount, 'date': div_date, 'tax': tax})

        # ── 국내 매수/매도 ────────────────────────────────
        m_dom = re.search(r'(매수|매도)(\d+)주\s*([\d,]+)원', line)
        if m_dom:
            ctx = [lines[j].strip() for j in range(max(0,i-5), min(len(lines),i+3))]
            if any('주식체결안내' in c for c in ctx):
                t_type = m_dom.group(1)
                qty    = int(m_dom.group(2))
                price  = to_int(m_dom.group(3))
                sname  = acc_num2 = ''
                t_date = cur_date; t_time = cur_time

                for j in range(max(0,i-10), min(len(lines),i+5)):
                    ck = lines[j].strip()
                    if not sname and '종목명' in ck:
                        sm = re.search(r'종목명\s*:\s*(.+?)(?:\s*$|-)', ck)
                        if sm: sname = sm.group(1).strip()
                    if not acc_num2 and '계좌번호' in ck:
                        am2 = re.search(r'(\d{5})\*+', ck)
                        if am2: acc_num2 = am2.group(1)
                    d, t = parse_datetime(ck)
                    if d: t_date = d
                    if t: t_time = t

                if t_date < TRADE_DATE_CUT: continue
                if t_date == TRADE_DATE_CUT and t_time < TRADE_TIME_CUT: continue
                if not sname or not acc_num2: continue
                account = find_account(acc_num2, lines[max(0,i-5):min(len(lines),i+3)])
                if not account: continue

                trades.append({'accountId': account['id'], 'stockName': sname,
                               'type': t_type, 'qty': qty, 'price': price,
                               'date': t_date, 'total': qty*price})

        # ── 해외 매수/매도 ────────────────────────────────
        if '체결가격' in line and 'USD' in line:
            pm = re.search(r'체결가격\s*:\s*([\d.]+)\s*USD', line)
            if not pm: continue
            krw_price = round(float(pm.group(1)) * EXCHANGE_RATE)

            sname = acc_num3 = ''; qty2 = 0
            t_type2 = '매수'; t_date2 = cur_date; t_time2 = cur_time

            for j in range(max(0,i-20), min(len(lines),i+10)):
                ck = lines[j].strip()
                if not sname and '종목명' in ck:
                    sm = re.search(r'종목명\s*:\s*(.+?)(?:\s*$|-)', ck)
                    if sm: sname = sm.group(1).strip()
                if not qty2:
                    qm = re.search(r'체결수량\s*:\s*(\d+)', ck)
                    if qm: qty2 = int(qm.group(1))
                if not acc_num3 and '계좌번호' in ck:
                    am2 = re.search(r'(\d{5})\*+', ck)
                    if am2: acc_num3 = am2.group(1)
                if '매도' in ck: t_type2 = '매도'
                d, t = parse_datetime(ck)
                if d: t_date2 = d
                if t: t_time2 = t

            if t_date2 < TRADE_DATE_CUT: continue
            if t_date2 == TRADE_DATE_CUT and t_time2 < TRADE_TIME_CUT: continue
            if not sname or not qty2 or not acc_num3: continue
            account = find_account(acc_num3, lines[max(0,i-20):min(len(lines),i+10)])
            if not account: continue

            trades.append({'accountId': account['id'], 'stockName': sname,
                           'type': t_type2, 'qty': qty2, 'price': krw_price,
                           'date': t_date2, 'total': qty2*krw_price, 'isOverseas': True})

        # ── 입금 ──────────────────────────────────────────
        if '입금' in line and re.search(r'[\d,]+\s*원', line):
            am3 = re.search(r'([\d,]+)\s*원', line)
            if am3:
                amount3 = to_int(am3.group(1))
                if amount3 > 0:
                    acc_n = ''
                    for j in range(max(0,i-5), min(len(lines),i+3)):
                        ck = lines[j].strip()
                        if '계좌번호' in ck:
                            am4 = re.search(r'(\d{5})\*+', ck)
                            if am4: acc_n = am4.group(1); break
                    acc3 = find_account(acc_n, []) if acc_n else None
                    deposits.append({'accountId': acc3['id'] if acc3 else 0,
                                     'amount': amount3, 'date': cur_date})

    print(f"  파싱 결과: 거래 {len(trades)}건, 배당 {len(dividends)}건, 입금 {len(deposits)}건")
    return {
        'dividends': dividends,
        'trades': trades,
        'deposits': deposits,
        'exchangeRate': EXCHANGE_RATE,
        'pushedAt': datetime.now().isoformat(),
        'sourceFile': Path(filepath).name
    }

# ═══════════════════════════════════════════════════════════
#  HTML 주입
# ═══════════════════════════════════════════════════════════
def inject_to_html(data):
    html = Path(DASHBOARD_HTML).read_text(encoding='utf-8')

    # 기존 주입 블록 제거
    html = re.sub(
        r'\n\s*<!-- KAKAO_AUTO:START -->.*?<!-- KAKAO_AUTO:END -->',
        '', html, flags=re.DOTALL
    )

    data_js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    block = (
        f'\n  <!-- KAKAO_AUTO:START -->'
        f'\n  <script>window.KAKAO_PARSED_DATA={data_js};</script>'
        f'\n  <!-- KAKAO_AUTO:END -->'
    )
    html = html.replace('</head>', block + '\n</head>', 1)

    Path(DASHBOARD_HTML).write_text(html, encoding='utf-8')
    print("  HTML 주입 완료")

# ═══════════════════════════════════════════════════════════
#  GitHub push
# ═══════════════════════════════════════════════════════════
def git_push(data):
    os.chdir(REPO_PATH)
    subprocess.run(['git', 'add', 'stock-dashboard.html'], check=True)
    diff = subprocess.run(['git', 'diff', '--cached', '--stat'],
                          capture_output=True, text=True).stdout.strip()
    if not diff:
        print("  변경사항 없음 — push 생략")
        return False

    msg = (f"auto: KakaoTalk 업데이트 {data['pushedAt'][:16]} "
           f"거래:{len(data['trades'])}건 배당:{len(data['dividends'])}건")
    subprocess.run(['git', 'commit', '-m', msg], check=True)
    subprocess.run(['git', 'push'], check=True)
    print(f"  GitHub push 완료")
    return True

# ═══════════════════════════════════════════════════════════
#  Windows 알림
# ═══════════════════════════════════════════════════════════
def notify(title, body):
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.BalloonTipTitle = '{title}'
$n.BalloonTipText  = '{body}'
$n.ShowBalloonTip(8000)
Start-Sleep 9
$n.Dispose()
"""
    subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', ps])

# ═══════════════════════════════════════════════════════════
#  파일 처리 파이프라인
# ═══════════════════════════════════════════════════════════
def process_file(filepath):
    print(f"\n{'='*55}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 처리 시작: {Path(filepath).name}")
    try:
        data   = parse_kakao(filepath)
        inject_to_html(data)
        pushed = git_push(data)

        t, d = len(data['trades']), len(data['dividends'])
        if pushed:
            notify("📈 대시보드 자동 업데이트 완료",
                   f"거래 {t}건 · 배당 {d}건 → Netlify 배포 중 (1~2분)")
            print(f"  ✅ 완료! Netlify 자동 배포 진행 중")
        else:
            notify("📈 파싱 완료 (변경 없음)", f"거래 {t}건 · 배당 {d}건")
            print(f"  ✅ 파싱 완료 (데이터 동일, push 생략)")
    except Exception as e:
        print(f"  ❌ 오류: {e}")
        notify("업데이트 오류", str(e)[:80])
        raise

# ═══════════════════════════════════════════════════════════
#  Watchdog 핸들러
# ═══════════════════════════════════════════════════════════
class MYBOXHandler(FileSystemEventHandler):
    def __init__(self):
        self._done = set()

    def _check(self, path):
        name = Path(path).name
        if (path not in self._done
                and name.lower().endswith('.txt')
                and KAKAO_KEYWORD.lower() in name.lower()):
            self._done.add(path)
            time.sleep(3)   # 파일 쓰기 완료 대기
            process_file(path)

    def on_created(self, event):
        if not event.is_directory: self._check(event.src_path)

    def on_moved(self, event):
        if not event.is_directory: self._check(event.dest_path)

# ═══════════════════════════════════════════════════════════
#  진입점
# ═══════════════════════════════════════════════════════════
def main():
    # 명령줄에서 파일 직접 지정 시 즉시 처리
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if Path(arg).exists():
                process_file(arg)
            else:
                print(f"파일 없음: {arg}")
        return

    # 감시 모드
    folder = MYBOX_FOLDER
    if not Path(folder).exists():
        print(f"❌ MYBOX 폴더를 찾을 수 없습니다: {folder}")
        print("   MYBOX_FOLDER 경로를 스크립트 상단에서 수정하세요.")
        print("   네이버 MYBOX 앱 → 설정 → PC 동기화 폴더 에서 경로 확인")
        sys.exit(1)

    print("=" * 55)
    print("📂 카카오톡 자동 업데이트 워처 시작")
    print(f"   감시 폴더 : {folder}")
    print(f"   저장소    : {REPO_PATH}")
    print(f"   파일 키워드: *{KAKAO_KEYWORD}*.txt")
    print("=" * 55)
    print("카카오톡 → 내보내기 → MYBOX 저장 시 자동 처리됩니다.")
    print("종료: Ctrl+C\n")

    handler  = MYBOXHandler()
    observer = Observer()
    observer.schedule(handler, folder, recursive=True)
    observer.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n워처 종료")
    finally:
        observer.stop(); observer.join()

if __name__ == '__main__':
    main()
