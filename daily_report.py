"""
매일 오후 7시 주식 일일 보고서 생성·발송 + 일간 스냅샷 저장
Windows 작업 스케줄러로 실행: python daily_report.py
Gmail 앱 비밀번호 필요 (환경변수 GMAIL_APP_PWD)
"""
import sys, os, re, json, smtplib, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text   import MIMEText
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# ── 설정 ─────────────────────────────────────────────────────
REPO_PATH      = r"D:\AI\260619_2_Daily_for_stock_TEMP"
DASHBOARD_HTML = os.path.join(REPO_PATH, "stock-dashboard.html")
SNAPSHOT_FILE  = os.path.join(REPO_PATH, "daily_snapshot.json")
TO_EMAIL       = "barobogi79@gmail.com"
FROM_EMAIL     = "barobogi79@gmail.com"
# Google 계정 > 보안 > 앱 비밀번호에서 생성 후 환경변수 설정
#   PowerShell: [System.Environment]::SetEnvironmentVariable("GMAIL_APP_PWD","xxxx xxxx xxxx xxxx","User")
GMAIL_APP_PWD  = os.environ.get("GMAIL_APP_PWD", "")

ACCOUNTS = [
    {"id":1,"name":"일반계좌1"}, {"id":2,"name":"일반계좌2"},
    {"id":3,"name":"ISA"},      {"id":4,"name":"IRP"},
    {"id":5,"name":"연금저축1"},{"id":6,"name":"연금저축2"},
    {"id":7,"name":"연금저축3"},
]

def acc_name(acc_id):
    return next((a["name"] for a in ACCOUNTS if a["id"] == acc_id), f"계좌{acc_id}")

# ── HTML 파싱 ─────────────────────────────────────────────────
def parse_html():
    html = Path(DASHBOARD_HTML).read_text(encoding='utf-8')

    # 1. KAKAO_PARSED_DATA (가격·거래·배당)
    kakao_data = {}
    m = re.search(r'<!-- KAKAO_AUTO:START -->(.*?)<!-- KAKAO_AUTO:END -->', html, re.DOTALL)
    if m:
        dm = re.search(r'window\.KAKAO_PARSED_DATA\s*=\s*(\{.*?\})\s*;', m.group(1), re.DOTALL)
        if dm:
            kakao_data = json.loads(dm.group(1))

    # 2. DEFAULT_STOCKS (기본 포지션)
    stocks = []
    sm = re.search(r'const DEFAULT_STOCKS\s*=\s*\[(.*?)\];', html, re.DOTALL)
    if sm:
        for obj in re.finditer(r'\{([^{}]+)\}', sm.group(1)):
            s = {}
            for kv in re.finditer(r"(\w+)\s*:\s*'?([^,'}]+)'?", obj.group(1)):
                k, v = kv.group(1), kv.group(2).strip().strip("'\"")
                try:    s[k] = int(v)
                except: s[k] = v
            if 'name' in s and 'qty' in s:
                stocks.append(s)

    # 3. 가격 적용 (curPrice / evalAmount 갱신)
    prices = kakao_data.get('prices', {})
    for s in stocks:
        p = prices.get(s['name'])
        if p and s.get('qty', 0) > 0:
            s['curPrice']   = p
            s['evalAmount'] = s['qty'] * p

    # 4. 포트폴리오 적용 거래 반영 (applyToPortfolio:true)
    today = datetime.date.today().strftime('%Y-%m-%d')
    for t in kakao_data.get('trades', []):
        if not t.get('applyToPortfolio', False):
            continue
        name, acc_id = t.get('stockName',''), t.get('accountId', 0)
        qty, price   = t.get('qty', 0), t.get('price', 0)
        ttype        = t.get('type','')
        existing = next((s for s in stocks if s['name'] == name and s['accountId'] == acc_id), None)
        if ttype == '매수':
            if existing:
                new_qty  = existing['qty'] + qty
                new_buy  = existing.get('buyAmount', 0) + qty * price
                existing.update({'qty': new_qty, 'buyAmount': new_buy,
                                 'evalAmount': new_qty * existing.get('curPrice', price)})
            else:
                stocks.append({'accountId': acc_id, 'name': name, 'qty': qty,
                               'curPrice': price, 'evalAmount': qty*price,
                               'buyAmount': qty*price, 'type':'주식'})
        elif ttype == '매도' and existing:
            new_qty = max(0, existing['qty'] - qty)
            existing['qty'] = new_qty
            existing['evalAmount'] = new_qty * existing.get('curPrice', 0)

    return stocks, kakao_data

# ── 리포트 계산 ───────────────────────────────────────────────
def build_report(stocks, kakao_data):
    today = datetime.date.today().strftime('%Y-%m-%d')
    total_eval = sum(s.get('evalAmount', 0) for s in stocks)
    total_buy  = sum(s.get('buyAmount',  0) for s in stocks if s.get('buyAmount',0) > 0)

    # 전일 스냅샷 비교
    prev = {}
    if Path(SNAPSHOT_FILE).exists():
        prev = json.loads(Path(SNAPSHOT_FILE).read_text(encoding='utf-8'))
    prev_eval   = prev.get('totalEval', total_eval)
    daily_chg   = total_eval - prev_eval
    daily_pct   = (daily_chg / prev_eval * 100) if prev_eval > 0 else 0.0

    # 오늘 거래 / 배당
    today_trades = [t for t in kakao_data.get('trades', [])     if t.get('date') == today]
    today_divs   = [d for d in kakao_data.get('dividends', [])  if d.get('date') == today]
    today_div_total = sum(d['amount'] for d in today_divs)

    # 종목별 손익률 (수량 > 0, buyAmount > 0)
    pnl_list = []
    seen = set()
    for s in stocks:
        key = (s['name'], s.get('accountId', 0))
        if key in seen: continue
        seen.add(key)
        buy = s.get('buyAmount', 0); ev = s.get('evalAmount', 0)
        qty = s.get('qty', 0)
        if buy > 0 and qty > 0:
            pnl = ev - buy
            pnl_list.append({'name': s['name'], 'pnl': pnl, 'pct': pnl/buy*100,
                             'accId': s.get('accountId', 0)})
    pnl_list.sort(key=lambda x: x['pct'], reverse=True)

    return {
        'today': today,
        'total_eval': total_eval, 'total_buy': total_buy,
        'daily_chg': daily_chg,  'daily_pct': daily_pct,
        'today_trades': today_trades,
        'today_divs': today_divs, 'today_div_total': today_div_total,
        'top3': pnl_list[:3],
        'bot3': list(reversed(pnl_list[-3:])),
    }

# ── HTML 이메일 생성 ──────────────────────────────────────────
def build_html(r):
    chg_color = '#10B981' if r['daily_chg'] >= 0 else '#EF4444'
    chg_sign  = '+' if r['daily_chg'] >= 0 else ''

    # 거래 테이블
    if r['today_trades']:
        tr_rows = ''.join(
            f'<tr><td style="padding:5px 8px;">{acc_name(t.get("accountId",0))}</td>'
            f'<td style="padding:5px 8px;">{t.get("stockName","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:{"#EF4444" if t.get("type")=="매도" else "#3B82F6"};font-weight:bold;">{t.get("type","")}</td>'
            f'<td style="padding:5px 8px;text-align:right;">{t.get("qty",0)}주</td>'
            f'<td style="padding:5px 8px;text-align:right;">₩{t.get("price",0):,}</td></tr>'
            for t in r['today_trades']
        )
        trades_html = f'<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f3f4f6;"><th style="padding:6px 8px;text-align:left;">계좌</th><th style="padding:6px 8px;text-align:left;">종목</th><th style="padding:6px 8px;text-align:center;">유형</th><th style="padding:6px 8px;text-align:right;">수량</th><th style="padding:6px 8px;text-align:right;">단가</th></tr></thead><tbody>{tr_rows}</tbody></table>'
    else:
        trades_html = '<p style="color:#9CA3AF;margin:0;">오늘 거래 없음</p>'

    # 상위/하위 3종목
    def pnl_rows(lst, bg):
        medals = ['🥇','🥈','🥉']
        rows = ''
        for i, s in enumerate(lst):
            c = '#10B981' if s['pnl'] >= 0 else '#EF4444'
            rows += (f'<tr><td style="padding:5px 8px;">{medals[i] if i<3 else "▼"}</td>'
                     f'<td style="padding:5px 8px;font-size:12px;">{s["name"][:20]}</td>'
                     f'<td style="padding:5px 8px;text-align:right;color:{c};font-weight:bold;">{s["pct"]:+.1f}%</td>'
                     f'<td style="padding:5px 8px;text-align:right;color:{c};">₩{s["pnl"]:+,.0f}</td></tr>')
        return f'<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:{bg};"><th style="padding:6px 8px;">순위</th><th style="padding:6px 8px;">종목명</th><th style="padding:6px 8px;text-align:right;">수익률</th><th style="padding:6px 8px;text-align:right;">손익액</th></tr></thead><tbody>{rows}</tbody></table>'

    top3_html = pnl_rows(r['top3'], '#f0fdf4')
    bot3_html = pnl_rows(r['bot3'], '#fef2f2')

    # 배당 테이블
    if r['today_divs']:
        div_rows = ''.join(
            f'<tr><td style="padding:5px 8px;">{d.get("stock","")}</td>'
            f'<td style="padding:5px 8px;text-align:right;color:#10B981;">₩{d["amount"]:,}</td></tr>'
            for d in sorted(r['today_divs'], key=lambda x: -x['amount'])
        )
        div_rows += f'<tr style="background:#ecfdf5;font-weight:bold;"><td style="padding:5px 8px;">합계</td><td style="padding:5px 8px;text-align:right;color:#10B981;">₩{r["today_div_total"]:,}</td></tr>'
        divs_html = f'<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f0fdf4;"><th style="padding:6px 8px;text-align:left;">종목</th><th style="padding:6px 8px;text-align:right;">배당금</th></tr></thead><tbody>{div_rows}</tbody></table>'
    else:
        divs_html = '<p style="color:#9CA3AF;margin:0;">금일 배당 없음</p>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Apple SD Gothic Neo',Arial,sans-serif;max-width:680px;margin:0 auto;padding:20px;background:#f9fafb;color:#111827;">

<div style="background:linear-gradient(135deg,#1e3a8a,#2563eb);color:white;padding:24px;border-radius:12px;margin-bottom:20px;">
  <h1 style="margin:0;font-size:22px;letter-spacing:-0.5px;">📊 Barobogi 주식 일일 보고서</h1>
  <p style="margin:6px 0 0;opacity:0.85;font-size:14px;">{r['today']} · 자동 발송</p>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
  <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;">
    <p style="margin:0;font-size:11px;color:#6b7280;">📈 총 평가금액</p>
    <p style="margin:6px 0 0;font-size:20px;font-weight:bold;">₩{r['total_eval']:,}</p>
  </div>
  <div style="background:white;border:2px solid {chg_color};border-radius:10px;padding:18px;">
    <p style="margin:0;font-size:11px;color:#6b7280;">📅 일간 변동 (전일 대비)</p>
    <p style="margin:6px 0 0;font-size:20px;font-weight:bold;color:{chg_color};">{chg_sign}₩{abs(r['daily_chg']):,}</p>
    <p style="margin:2px 0 0;font-size:13px;color:{chg_color};">{chg_sign}{r['daily_pct']:.2f}%</p>
  </div>
</div>

<div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin-bottom:16px;">
  <h3 style="margin:0 0 12px;font-size:14px;color:#374151;">📋 오늘의 매수/매도 거래</h3>
  {trades_html}
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
  <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;">
    <h3 style="margin:0 0 12px;font-size:14px;color:#374151;">🏆 수익 상위 3종목</h3>
    {top3_html}
  </div>
  <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;">
    <h3 style="margin:0 0 12px;font-size:14px;color:#374151;">📉 손실 하위 3종목</h3>
    {bot3_html}
  </div>
</div>

<div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin-bottom:16px;">
  <h3 style="margin:0 0 12px;font-size:14px;color:#374151;">💰 금일 배당금 내역</h3>
  {divs_html}
</div>

<p style="text-align:center;color:#9ca3af;font-size:11px;margin-top:20px;">
  Barobogi Stock Dashboard · 매일 오후 7시 자동 발송<br>
  <a href="https://barobogi.netlify.app" style="color:#3b82f6;">대시보드 바로가기</a>
</p>
</body></html>"""

# ── 이메일 발송 ───────────────────────────────────────────────
def send_email(subject, html_body, app_pwd):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = FROM_EMAIL
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(FROM_EMAIL, app_pwd)
        s.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())

# ── 메인 ─────────────────────────────────────────────────────
def main():
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] 일일 보고서 생성 시작")

    stocks, kakao_data = parse_html()
    r = build_report(stocks, kakao_data)

    print(f"  총 평가금액: ₩{r['total_eval']:,}")
    print(f"  일간 변동:  {'+' if r['daily_chg']>=0 else ''}₩{r['daily_chg']:,} ({r['daily_pct']:+.2f}%)")
    print(f"  오늘 거래:  {len(r['today_trades'])}건")
    print(f"  오늘 배당:  {len(r['today_divs'])}건 ₩{r['today_div_total']:,}")

    # 앱 비밀번호 확인
    app_pwd = GMAIL_APP_PWD
    if not app_pwd:
        print("\n⚠️  Gmail 앱 비밀번호 미설정. 이메일 발송 생략.")
        print("  설정: Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호 생성")
        print("  PowerShell 환경변수 등록:")
        print('  [System.Environment]::SetEnvironmentVariable("GMAIL_APP_PWD","앱비밀번호","User")')
    else:
        subject = (f"[Barobogi] 주식 일일 보고서 {r['today']} "
                   f"₩{r['total_eval']:,} ({'+' if r['daily_pct']>=0 else ''}{r['daily_pct']:.2f}%)")
        html_body = build_html(r)
        try:
            send_email(subject, html_body, app_pwd)
            print(f"  ✅ 메일 발송 완료 → {TO_EMAIL}")
        except Exception as e:
            print(f"  ❌ 메일 발송 실패: {e}")

    # 일간 스냅샷 저장 (내일 비교용)
    Path(SNAPSHOT_FILE).write_text(
        json.dumps({'date': r['today'], 'totalEval': r['total_eval'],
                    'totalBuy': r['total_buy']}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(f"  ✅ 스냅샷 저장: {r['today']} ₩{r['total_eval']:,}")

if __name__ == '__main__':
    main()
