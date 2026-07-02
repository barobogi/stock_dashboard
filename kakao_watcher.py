#!/usr/bin/env python3
# kakao_watcher.py — 카카오톡 파일 자동 감지 → 파싱 → GitHub push → GitHub Pages 배포

import os, re, json, time, sys, subprocess, requests, threading, logging
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

_processing_lock = threading.Lock()

# ── 로거 설정 (파일 + 콘솔 동시 출력) ──────────────────────────
def _setup_logger():
    log_path = Path(r"D:\AI\260619_2_Daily_for_stock_TEMP\watcher.log")
    logger = logging.getLogger("watcher")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

log = _setup_logger()

# ═══════════════════════════════════════════════════════════
#  설정 — 본인 환경에 맞게 수정
# ═══════════════════════════════════════════════════════════
GDRIVE_FOLDER  = r"C:\Users\82102\Downloads"                 # 카카오톡 PC 내보내기 기본 저장 폴더
REPO_PATH      = r"D:\AI\260619_2_Daily_for_stock_TEMP"     # Git 저장소 경로
DASHBOARD_HTML = os.path.join(REPO_PATH, "stock-dashboard.html")
TICKER_MAP_FILE= os.path.join(REPO_PATH, "ticker_map.json")
KAKAO_KEYWORD  = "KakaoTalk"   # 감지할 파일명 키워드 (대소문자 무시)
EXCHANGE_RATE  = 1375.0        # USD → KRW 기본 환율 (API 실패 시 폴백, 주기적 업데이트 필요)
FIRE_TARGET    = 1_000_000_000 # FIRE 목표 금액 (웹 UI에서 변경 시 localStorage 우선)

# ── 한국 공휴일 (주말과 동일하게 6시간 주기 적용) ────────────────
# lunar 기반 공휴일(설날·부처님오신날·추석)은 매년 수동 업데이트 필요
KR_HOLIDAYS = {
    # 2026
    '2026-01-01', '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-03-01', '2026-05-05', '2026-05-25', '2026-06-06',
    '2026-08-15', '2026-09-24', '2026-09-25', '2026-09-26',
    '2026-10-03', '2026-10-09', '2026-12-25',
    # 2027 (고정 공휴일만, lunar 계열 추후 추가)
    '2027-01-01', '2027-03-01', '2027-05-05', '2027-06-06',
    '2027-08-15', '2027-10-03', '2027-10-09', '2027-12-25',
}

def _is_holiday(dt: datetime) -> bool:
    return dt.strftime('%Y-%m-%d') in KR_HOLIDAYS

# ── 포트폴리오 국내 종목 (IRP 제외 — 가격체계 다름) ──────────────
KR_STOCKS = [
    'SOL 팔란티어미국채커버드콜혼합', 'SOL 팔란티어커버드콜OTM채권혼합',
    '삼성전자', 'ACE 미국AI테크핵심산업액티브', 'SOL 200타겟위클리커버드콜',
    'KODEX 미국우주항공', 'TIGER 현대차그룹플러스', 'KODEX 코스닥150레버리지',
    'KODEX 테슬라커버드콜채권혼합액티브', 'KODEX 200타겟위클리커버드콜',
    'PLUS 자사주매입고배당주', 'KODEX 미국나스닥100',
    'TIGER 미국테크TOP10타겟커버드콜', 'RISE 200위클리커버드콜',
    'ACE 미국빅테크7+데일리타겟커버드콜(합성)', 'TIGER 미국S&P500타겟데일리커버드콜',
    'KODEX 금융고배당TOP10타겟위클리커버드콜', 'KODEX 금융고배당TOP10타겟커버드콜',
    'KODEX 미국나스닥100데일리커버드콜OTM', 'KODEX 미국배당커버드콜액티브',
    'ACE KRX금현물', 'KODEX 미국S&P500', 'RISE 글로벌자산배분액티브',
]

# ── 포트폴리오 해외 종목 (이름 → yfinance 티커) ─────────────────
US_STOCKS = {
    '앰프리어스 테크놀로지스': 'AMPX',
    'AST 스페이스모바일':      'ASTS',
    'BTQ 테크놀로지스':        'BTQ',
    '셀레스티카':             'CLS',
    '아이렌':                 'IREN',
    '실스크':                 'LAES',
    '엔비디아':               'NVDA',
    '파가야 테크놀로지스':     'PGY',
    '퀀텀스케이프':           'QS',
    'Schwab 미국 배당주 ETF': 'SCHD',
    '서프 에어 모빌리티':     'SRFM',
    '팔란티어 테크놀로지스':  'PLTR',
    # 'Leverage Shares 2X Long CBRS Daily ETF': 'CBRS',  # Yahoo 'CBRS'는 다른 종목 → 잘못된 가격
}

# 파싱 기준
DIV_CUTOFF        = f"{datetime.now().year - 1}-01-01"  # 전년도 1월1일 (매년 자동 갱신)
TRADE_DATE_CUT    = "2026-06-19"
TRADE_TIME_CUT    = "12:50"

# ═══════════════════════════════════════════════════════════
#  현재가 조회 (Naver Finance + yfinance)
# ═══════════════════════════════════════════════════════════
_sess = requests.Session()
_sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

def _naver_search_code(name):
    """Naver Finance 자동완성으로 종목코드 검색 (ac.stock.naver.com 사용)"""
    for target in ['etf', 'stock,etf,corp']:
        try:
            r = _sess.get('https://ac.stock.naver.com/ac',
                params={'q': name, 'q_enc': 'utf8', 'target': target,
                        'reorderFlag': 'N', 'limit': 10}, timeout=5)
            for group in r.json().get('items', []):
                for item in group:
                    if isinstance(item, list) and len(item) >= 2 and item[0] == name:
                        return str(item[1])
        except Exception:
            pass
    return None

def _naver_price(code):
    """Naver Finance 모바일 API로 종목 현재가(원) 조회"""
    try:
        r = _sess.get(f'https://m.stock.naver.com/api/stock/{code}/basic', timeout=5)
        info = r.json().get('stockItemTotal', {})
        return int(str(info.get('closePrice', '0')).replace(',', ''))
    except Exception:
        return 0

def fetch_exchange_rate():
    """USD/KRW 환율 조회 (Dunamu → Naver → Yahoo Finance → ExchangeRate-API 순 폴백)"""
    # 1. Dunamu
    try:
        r = _sess.get('https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD', timeout=5)
        rate = float(r.json()[0].get('basePrice', 0))
        if rate > 1000:
            log.info(f"  환율 조회(Dunamu): 1 USD = ₩{rate:,.1f}")
            return rate
    except Exception:
        pass
    # 2. Naver
    try:
        r = _sess.get('https://m.stock.naver.com/front-api/v1/index/info?indexCode=FRX.KRWUSD', timeout=5)
        rate = float(str(r.json().get('result', {}).get('closePrice', '0')).replace(',', ''))
        if rate > 1000:
            log.info(f"  환율 조회(Naver): 1 USD = ₩{rate:,.1f}")
            return rate
    except Exception:
        pass
    # 3. Yahoo Finance
    try:
        r = _sess.get('https://query1.finance.yahoo.com/v8/finance/chart/USDKRW=X?interval=1d&range=1d', timeout=5)
        rate = float(r.json()['chart']['result'][0]['meta']['regularMarketPrice'])
        if rate > 1000:
            log.info(f"  환율 조회(Yahoo): 1 USD = ₩{rate:,.1f}")
            return rate
    except Exception:
        pass
    # 4. ExchangeRate-API (무료, 인증 불필요)
    try:
        r = _sess.get('https://open.er-api.com/v6/latest/USD', timeout=5)
        rate = float(r.json()['rates']['KRW'])
        if rate > 1000:
            log.info(f"  환율 조회(ExchangeRate-API): 1 USD = ₩{rate:,.1f}")
            return rate
    except Exception:
        pass
    log.warning(f"  환율 조회 전체 실패 — 기존값 사용: ₩{EXCHANGE_RATE}")
    return None

def fetch_prices():
    """포트폴리오 전 종목 현재가 조회. {종목명: 현재가(원)} 반환"""
    ticker_map = {}
    if os.path.exists(TICKER_MAP_FILE):
        with open(TICKER_MAP_FILE, encoding='utf-8') as f:
            ticker_map = json.load(f)

    prices = {}
    map_updated = False

    try:
        import yfinance as yf

        # 국내 ETF / 주식: ticker_map 코드 → Yahoo {code}.KS
        # 코드 없으면 Naver 자동검색 → 캐시
        for name in KR_STOCKS:
            code = ticker_map.get(name)
            if not code:
                code = _naver_search_code(name)
                if code:
                    ticker_map[name] = code
                    map_updated = True
            if not code:
                continue
            try:
                ks = yf.Ticker(f"{code}.KS")
                krw = ks.fast_info.last_price or 0
                if krw > 0:
                    prices[name] = int(round(krw))
                else:
                    # 장 마감 후엔 regularMarketPreviousClose 사용
                    krw = ks.info.get('regularMarketPreviousClose', 0)
                    if krw > 0:
                        prices[name] = int(round(krw))
            except Exception:
                pass

        # 해외 주식 / ETF
        for name, ticker in US_STOCKS.items():
            if not ticker:
                continue
            try:
                usd = yf.Ticker(ticker).fast_info.last_price or 0
                if usd > 0:
                    prices[name] = int(round(usd * EXCHANGE_RATE))
            except Exception:
                pass

    except ImportError:
        # yfinance 없으면 Naver 가격 API 폴백
        for name in KR_STOCKS:
            code = ticker_map.get(name)
            if not code:
                code = _naver_search_code(name)
                if code:
                    ticker_map[name] = code
                    map_updated = True
            if code:
                p = _naver_price(code)
                if p > 0:
                    prices[name] = p

    if map_updated:
        with open(TICKER_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(ticker_map, f, ensure_ascii=False, indent=2)

    total = len(KR_STOCKS) + len(US_STOCKS)
    log.info(f"  현재가 조회: {len(prices)}/{total}개 성공")
    return prices

# ═══════════════════════════════════════════════════════════
#  계좌 정의
# ═══════════════════════════════════════════════════════════
ACCOUNTS_DEFAULT = [
    {"id": 1, "num": "70714", "type": "general", "name": "일반계좌1"},
    {"id": 2, "num": "70871", "type": "general", "name": "일반계좌2"},
    {"id": 3, "num": "71297", "type": "isa",     "name": "ISA"},
    {"id": 4, "num": "70714", "type": "irp",     "name": "IRP"},   # 70714이지만 IRP/퇴직연금 키워드로 구분
    {"id": 5, "num": "71462", "type": "pension", "name": "연금저축1"},
    {"id": 6, "num": "71615", "type": "pension", "name": "연금저축2"},
    {"id": 7, "num": "70868", "type": "pension", "name": "연금저축3"},
    {"id": 8, "num": "71417", "type": "general", "name": "일반계좌3"},  # 해외주식 계좌
    {"id": 9, "num": "71661", "type": "general", "name": "일반계좌4"},
]
# 카카오톡 단체방에 섞이는 타인 계좌 — 자동 등록 영구 제외
EXCLUDED_NUMS = {"71374"}
ACCOUNTS_FILE = Path(__file__).parent / 'accounts.json'

def _load_accounts():
    base = {(a['num'], a['type']): a for a in ACCOUNTS_DEFAULT}
    if ACCOUNTS_FILE.exists():
        try:
            for a in json.loads(ACCOUNTS_FILE.read_text(encoding='utf-8')):
                key = (a['num'], a['type'])
                if key not in base:
                    base[key] = a
        except Exception as e:
            log.warning(f"accounts.json 로드 실패: {e}")
    return list(base.values())

def _save_accounts(accounts):
    default_keys = {(a['num'], a['type']) for a in ACCOUNTS_DEFAULT}
    extra = [a for a in accounts if (a['num'], a['type']) not in default_keys]
    ACCOUNTS_FILE.write_text(json.dumps(extra, ensure_ascii=False, indent=2), encoding='utf-8')

def _next_account_name(accounts, type_):
    n = len([a for a in accounts if a['type'] == type_]) + 1
    return {'general': f'일반계좌{n}', 'isa': f'ISA{n}', 'irp': f'IRP{n}', 'pension': f'연금저축{n}'}.get(type_, f'{type_}{n}')

ACCOUNTS = _load_accounts()

def find_account(num, ctx_lines):
    """계좌번호 앞5자리 + 주변 라인으로 계좌 특정. 미등록 계좌는 일반계좌로 자동 등록."""
    global ACCOUNTS
    if num == "70714":
        for l in ctx_lines:
            if "IRP" in l or "퇴직연금" in l:
                return next((a for a in ACCOUNTS if a["num"] == "70714" and a["type"] == "irp"), None)
        return next((a for a in ACCOUNTS if a["num"] == "70714" and a["type"] == "general"), None)
    found = next((a for a in ACCOUNTS if a["num"] == num and a["type"] != "irp"), None)
    if found:
        return found
    if num in EXCLUDED_NUMS:
        return None  # 타인 계좌 — 조용히 무시
    # 미등록 계좌 → 일반계좌로 자동 등록
    new_id = max((a['id'] for a in ACCOUNTS), default=0) + 1
    new_acc = {"id": new_id, "num": num, "type": "general", "name": _next_account_name(ACCOUNTS, 'general')}
    ACCOUNTS.append(new_acc)
    _save_accounts(ACCOUNTS)
    log.warning(f"⚠️ 미등록 계좌 자동 등록: {num} → {new_acc['name']} (id:{new_id})")
    return new_acc

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
    # 카카오 메시지 포맷: 날짜는 별도 줄, 시간만 있는 줄 "[오후 2:30]" 처리
    tm = re.search(r'(오전|오후)\s+(\d+):(\d+)', line)
    if tm:
        ap, h, mi = tm.group(1), int(tm.group(2)), int(tm.group(3))
        if ap == '오후' and h != 12: h += 12
        elif ap == '오전' and h == 12: h = 0
        return parse_date(line), f"{h:02d}:{mi:02d}"
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

        # ── IRP 퇴직연금 배당 (입금액 형식) ─────────────────────
        if '퇴직연금 이자/배당/상환 안내' in line:
            sname_irpd = acc_irpd = ''; amount_irpd = 0
            div_date_irpd = cur_date
            for j in range(i+1, min(len(lines), i+12)):
                ck = lines[j].strip()
                if re.search(r'\d{4}년 \d+월 \d+일', ck) and '삼성증권' in ck:
                    break
                if not sname_irpd and '상품명' in ck:
                    sm = re.search(r'상품명\s*:\s*(.+?)$', ck)
                    if sm: sname_irpd = sm.group(1).strip()
                if not acc_irpd and '계좌번호' in ck:
                    am2 = re.search(r'(\d{5})\*+', ck)
                    if am2: acc_irpd = am2.group(1)
                if not amount_irpd and '입금액' in ck:
                    pm = re.search(r'입금액\s*:\s*([\d,]+)\s*원', ck)
                    if pm: amount_irpd = to_int(pm.group(1))
                if '입금일' in ck:
                    d = parse_date(ck)
                    if d: div_date_irpd = d
            if sname_irpd and acc_irpd and amount_irpd > 0 and div_date_irpd >= DIV_CUTOFF:
                ctx_irpd = [line] + [lines[j].strip() for j in range(i+1, min(len(lines),i+12))]
                account_irpd = find_account(acc_irpd, ctx_irpd)
                if account_irpd:
                    key_irpd = f"{div_date_irpd}_{account_irpd['id']}_{sname_irpd}"
                    if key_irpd not in div_keys:
                        div_keys.add(key_irpd)
                        dividends.append({'accountId': account_irpd['id'], 'stock': sname_irpd,
                                          'amount': amount_irpd, 'date': div_date_irpd, 'tax': 0})

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
                    # 구 포맷(2025): '종목명 :' 레이블
                    if not sname and '종목명' in ck and ':' in ck:
                        sm = re.search(r'종목명\s*:\s*(.+?)$', ck)
                        if sm: sname = sm.group(1).strip()
                    # 구 포맷(2025): '계좌번호 :' 레이블
                    if not acc_num2 and '계좌번호' in ck:
                        am2 = re.search(r'(\d{5})\*+', ck)
                        if am2: acc_num2 = am2.group(1)
                    # 구 포맷(2025): 주식체결안내 헤더에 계좌+종목명 내장
                    if '주식체결안내' in ck:
                        if not sname:
                            sm2 = re.search(r'\d{5}\*+\s*-\s*\d+\s+(.+?)$', ck)
                            if sm2: sname = sm2.group(1).strip()
                        if not acc_num2:
                            am3 = re.search(r'(\d{5})\*+', ck)
                            if am3: acc_num2 = am3.group(1)
                    d, t = parse_datetime(ck)
                    if d: t_date = d
                    if t: t_time = t

                # 신 포맷(2026): i-1=종목명, i-2=계좌번호 (별도 줄)
                if not sname and i >= 1:
                    prev1 = lines[i-1].strip()
                    if prev1 and not re.search(r'\*', prev1) and \
                       not re.search(r'주문|체결|안내', prev1) and '원' not in prev1:
                        sname = prev1
                if not acc_num2 and i >= 2:
                    am5 = re.search(r'(\d{5})\*+', lines[i-2].strip())
                    if am5: acc_num2 = am5.group(1)

                if t_date < TRADE_DATE_CUT: continue
                if not sname or not acc_num2: continue
                account = find_account(acc_num2, lines[max(0,i-5):min(len(lines),i+3)])
                if not account: continue

                apply = (t_date > TRADE_DATE_CUT) or \
                        (t_date == TRADE_DATE_CUT and t_time >= TRADE_TIME_CUT)
                trades.append({'accountId': account['id'], 'stockName': sname,
                               'type': t_type, 'qty': qty, 'price': price,
                               'date': t_date, 'time': t_time, 'total': qty*price,
                               'applyToPortfolio': apply})

        # ── 해외 매수/매도 (헤더 기반 전진 파싱) ──────────────────
        if '해외주식 매매 체결 안내' in line:
            d0, t0 = parse_datetime(line)
            t_date2 = d0 or cur_date; t_time2 = t0 or cur_time
            sname = acc_num3 = ''; qty2 = 0
            t_type2 = '매수'; krw_price = 0

            for j in range(i+1, min(len(lines), i+18)):
                ck = lines[j].strip()
                # 다음 메시지 헤더 감지 → 중단
                if re.search(r'\d{4}년 \d+월 \d+일', ck) and '삼성증권' in ck:
                    break
                if not sname and '종목명' in ck:
                    sm = re.search(r'종목명\s*:\s*(.+?)$', ck)
                    if sm: sname = sm.group(1).strip()
                if not qty2:
                    qm = re.search(r'체결수량\s*:\s*(\d+)', ck)
                    if qm: qty2 = int(qm.group(1))
                if not acc_num3 and '계좌번호' in ck:
                    am2 = re.search(r'(\d{5})\*+', ck)
                    if am2: acc_num3 = am2.group(1)
                if '해외주식 매도 주문' in ck: t_type2 = '매도'
                if not krw_price and '체결가격' in ck and 'USD' in ck:
                    pm = re.search(r'체결가격\s*:\s*([\d.]+)\s*USD', ck)
                    if pm: krw_price = round(float(pm.group(1)) * EXCHANGE_RATE)

            if t_date2 >= TRADE_DATE_CUT and sname and qty2 and krw_price and acc_num3:
                account = find_account(acc_num3, [line])
                if account:
                    apply2 = (t_date2 > TRADE_DATE_CUT) or \
                             (t_date2 == TRADE_DATE_CUT and t_time2 >= TRADE_TIME_CUT)
                    trades.append({'accountId': account['id'], 'stockName': sname,
                                   'type': t_type2, 'qty': qty2, 'price': krw_price,
                                   'date': t_date2, 'time': t_time2, 'total': qty2*krw_price, 'isOverseas': True,
                                   'applyToPortfolio': apply2})

        # ── IRP/퇴직연금 ETF 국내 체결 ───────────────────────────
        if '체결단가' in line:
            pm_irp = re.search(r'체결단가\s*:\s*([\d,]+)\s*원', line)
            if pm_irp:
                ctx_irp = [lines[j].strip() for j in range(max(0,i-15), min(len(lines),i+5))]
                if any('퇴직연금' in c for c in ctx_irp):
                    price_irp = to_int(pm_irp.group(1))
                    sname_irp = acc_irp = ''; qty_irp = 0
                    t_type_irp = '매수'; t_date_irp = cur_date; t_time_irp = cur_time
                    for j in range(max(0,i-15), min(len(lines),i+5)):
                        ck = lines[j].strip()
                        if not sname_irp and '종목명' in ck:
                            sm = re.search(r'종목명\s*:\s*(.+?)$', ck)
                            if sm: sname_irp = sm.group(1).strip()
                        if not qty_irp:
                            qm = re.search(r'체결수량\s*:\s*(\d+)', ck)
                            if qm: qty_irp = int(qm.group(1))
                        if not acc_irp and '계좌번호' in ck:
                            am2 = re.search(r'(\d{5})\*+', ck)
                            if am2: acc_irp = am2.group(1)
                        if '매도' in ck and '매매구분' in ck: t_type_irp = '매도'
                        d, t = parse_datetime(ck)
                        if d: t_date_irp = d
                        if t: t_time_irp = t
                    if t_date_irp >= TRADE_DATE_CUT and sname_irp and qty_irp and acc_irp:
                        account_irp = find_account(acc_irp, ctx_irp)
                        if account_irp:
                            apply_irp = (t_date_irp > TRADE_DATE_CUT) or \
                                        (t_date_irp == TRADE_DATE_CUT and t_time_irp >= TRADE_TIME_CUT)
                            trades.append({'accountId': account_irp['id'], 'stockName': sname_irp,
                                           'type': t_type_irp, 'qty': qty_irp, 'price': price_irp,
                                           'date': t_date_irp, 'time': t_time_irp, 'total': qty_irp * price_irp,
                                           'applyToPortfolio': apply_irp})

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

    log.info(f"  파싱 결과: 거래 {len(trades)}건, 배당 {len(dividends)}건, 입금 {len(deposits)}건")
    return {
        'dividends': dividends,
        'trades': trades,
        'deposits': deposits,
        'exchangeRate': EXCHANGE_RATE,
        'tradeDateCut': TRADE_DATE_CUT,
        'tradeTimeCut': TRADE_TIME_CUT,
        'pushedAt': datetime.now().isoformat(),
        'sourceFile': Path(filepath).name,
        'accounts': ACCOUNTS,
    }

# ═══════════════════════════════════════════════════════════
#  HTML 주입
# ═══════════════════════════════════════════════════════════
def _extract_existing_data():
    """현재 HTML에 주입된 기존 KAKAO_PARSED_DATA 추출"""
    try:
        html = Path(DASHBOARD_HTML).read_text(encoding='utf-8')
        m = re.search(r'window\.KAKAO_PARSED_DATA=(\{.*?\});</script>', html, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception:
        pass
    return None

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
    log.info("  HTML 주입 완료")

# ═══════════════════════════════════════════════════════════
#  GitHub push
# ═══════════════════════════════════════════════════════════
def git_push(data):
    os.chdir(REPO_PATH)
    subprocess.run(['git', 'add', 'stock-dashboard.html'], check=True)
    diff = subprocess.run(['git', 'diff', '--cached', '--stat'],
                          capture_output=True, text=True).stdout.strip()
    if not diff:
        log.info("  변경사항 없음 — push 생략")
        return False

    msg = (f"auto: KakaoTalk 업데이트 {data['pushedAt'][:16]} "
           f"거래:{len(data['trades'])}건 배당:{len(data['dividends'])}건 "
           f"현재가:{len(data.get('prices',{}))}개")
    subprocess.run(['git', 'commit', '-m', msg], check=True)

    for attempt in range(1, 4):
        try:
            subprocess.run(['git', 'push'], check=True, timeout=30)
            log.info("  GitHub push 완료")
            return True
        except Exception as e:
            log.warning(f"  push 실패 ({attempt}/3): {e}")
            if attempt < 3:
                time.sleep(30)
    log.error("  push 3회 실패 — 다음 갱신 시 재시도")
    return False

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
#  현재가만 갱신 (카카오톡 파일 없이 가격만 업데이트)
# ═══════════════════════════════════════════════════════════
def refresh_prices_only():
    """현재 KAKAO_PARSED_DATA에서 prices + pushedAt만 갱신하여 재주입"""
    with _processing_lock:
        log.info(f"\n[{datetime.now().strftime('%H:%M:%S')}] 정시 현재가 자동 갱신")
        html = Path(DASHBOARD_HTML).read_text(encoding='utf-8')
        m = re.search(
            r'<!-- KAKAO_AUTO:START -->\s*<script>window\.KAKAO_PARSED_DATA=(.+?);</script>\s*<!-- KAKAO_AUTO:END -->',
            html, re.DOTALL
        )
        if not m:
            log.warning("  KAKAO_PARSED_DATA 없음 — 갱신 건너뜀")
            return
        data = json.loads(m.group(1))
        new_rate = fetch_exchange_rate()
        if new_rate:
            global EXCHANGE_RATE
            EXCHANGE_RATE = new_rate
        data['exchangeRate'] = EXCHANGE_RATE  # 성공 시 갱신, 실패 시 이전 성공값 유지
        data.setdefault('fireTarget', FIRE_TARGET)  # 웹 UI 미변경 시 기본값 유지
        data['accounts'] = ACCOUNTS  # 신규 계좌 자동 등록 반영
        log.info("  현재가 조회 중...")
        data['prices']   = fetch_prices()
        data['pushedAt'] = datetime.now().isoformat()
        inject_to_html(data)

        os.chdir(REPO_PATH)
        subprocess.run(['git', 'add', 'stock-dashboard.html'], check=True)
        diff = subprocess.run(['git', 'diff', '--cached', '--stat'],
                              capture_output=True, text=True).stdout.strip()
        if not diff:
            log.info("  가격 변동 없음 — push 생략")
            return
        n = len(data.get('prices', {}))
        subprocess.run(['git', 'commit', '-m',
                        f"auto: 현재가 갱신 {data['pushedAt'][:16]} 현재가:{n}개"], check=True)
        for attempt in range(1, 4):
            try:
                subprocess.run(['git', 'push'], check=True, timeout=30)
                log.info(f"  ✅ 현재가 갱신 완료 ({n}개)")
                notify("📈 현재가 갱신", f"{n}개 종목 업데이트 · GitHub Pages 반영 중")
                break
            except Exception as e:
                log.warning(f"  push 실패 ({attempt}/3): {e}")
                if attempt < 3:
                    time.sleep(30)
        else:
            log.error("  push 3회 실패 — 다음 정시 갱신 시 재시도")

def _next_refresh_seconds():
    """현재 시각 기준 다음 갱신까지 대기 시간 계산
    평일 주간 (08:00~15:59) : 1시간 간격 (매 정시)
    평일 야간 (16:00~07:59) : 2시간 간격 (짝수 정시)
    토·일                   : 6시간 간격 (0/6/12/18시)
    """
    from datetime import timedelta
    now     = datetime.now()
    weekday = now.weekday()          # 0=월 … 4=금, 5=토, 6=일
    h, m, s = now.hour, now.minute, now.second

    if weekday >= 5 or _is_holiday(now):  # 주말 or 공휴일
        interval = 6
    elif 8 <= h < 16:                # 평일 주간
        interval = 1
    else:                            # 평일 야간
        interval = 2

    next_h = ((h // interval) + 1) * interval
    if next_h >= 24:
        base = datetime(now.year, now.month, now.day) + timedelta(days=1)
        next_dt = base.replace(hour=next_h % 24, minute=0, second=0, microsecond=0)
    else:
        next_dt = now.replace(hour=next_h, minute=0, second=0, microsecond=0)

    secs = max(60, (next_dt - now).total_seconds())
    return secs, next_dt.strftime('%H:%M'), interval

def _hourly_price_refresh_loop():
    """스마트 스케줄 현재가 갱신 (평일 주간 1h / 야간 2h / 주말 6h)"""
    while True:
        secs, next_time, interval = _next_refresh_seconds()
        log.info(f"  ⏰ 다음 갱신: {next_time} ({interval}시간 간격, {int(secs//60)}분 후)")
        time.sleep(secs)
        try:
            refresh_prices_only()
        except Exception as e:
            log.error(f"  ❌ 갱신 오류: {e}")

# ═══════════════════════════════════════════════════════════
#  파일 처리 파이프라인
# ═══════════════════════════════════════════════════════════
def process_file(filepath):
    log.info(f"\n{'='*55}")
    log.info(f"[{datetime.now().strftime('%H:%M:%S')}] 처리 시작: {Path(filepath).name}")
    try:
        with _processing_lock:
            new_rate = fetch_exchange_rate()
            if new_rate:
                global EXCHANGE_RATE
                EXCHANGE_RATE = new_rate
            data = parse_kakao(filepath)
            data['exchangeRate'] = EXCHANGE_RATE  # 성공 시 갱신, 실패 시 이전 성공값 유지
            data.setdefault('fireTarget', FIRE_TARGET)  # 웹 UI 미변경 시 기본값 유지

            # 방어 로직: 새 파일 배당이 기존보다 적으면 기존 배당·입금 보존
            existing = _extract_existing_data()
            if existing:
                ex_div = existing.get('dividends', [])
                ex_dep = existing.get('deposits', [])
                new_div = data.get('dividends', [])
                if len(new_div) < len(ex_div) * 0.8:  # 기존 80% 미만이면 보존
                    log.info(f"  🛡️ 배당 보존: 새 {len(new_div)}건 < 기존 {len(ex_div)}건 → 기존 유지")
                    data['dividends'] = ex_div
                if len(data.get('deposits', [])) == 0 and ex_dep:
                    data['deposits'] = ex_dep
            log.info("  현재가 조회 중...")
            data['prices'] = fetch_prices()
            inject_to_html(data)
            pushed = git_push(data)

        t, d = len(data['trades']), len(data['dividends'])
        if pushed:
            notify("📈 대시보드 자동 업데이트 완료",
                   f"거래 {t}건 · 배당 {d}건 → GitHub Pages 반영 중 (2~3분)")
            log.info(f"  ✅ 완료! GitHub Pages 배포 진행 중")
        else:
            notify("📈 파싱 완료 (변경 없음)", f"거래 {t}건 · 배당 {d}건")
            log.info(f"  ✅ 파싱 완료 (데이터 동일, push 생략)")
    except Exception as e:
        log.error(f"  ❌ 오류: {e}")
        notify("업데이트 오류", str(e)[:80])
        raise

# ═══════════════════════════════════════════════════════════
#  Watchdog 핸들러
# ═══════════════════════════════════════════════════════════
class GDriveHandler(FileSystemEventHandler):
    def __init__(self):
        self._done = set()

    def _check(self, path):
        name = Path(path).name
        # 카카오톡 파일 판별: 확장자/이름 불문하고 폴더 내 모든 신규 파일 시도
        # (카카오톡 내보내기 파일명이 매번 달라서 내용으로 판단)
        if path in self._done:
            return
        # 숨김파일·임시파일 제외
        if name.startswith('.') or name.startswith('~') or name.endswith('.tmp'):
            return
        self._done.add(path)
        time.sleep(3)   # 파일 쓰기 완료 대기
        # 카카오톡 대화 파일인지 첫 줄로 확인
        try:
            first = Path(path).read_text(encoding='utf-8', errors='ignore')[:100]
        except Exception:
            first = ''
        if '카카오톡' not in first and 'KakaoTalk' not in first:
            log.info(f"  ⏭️  카카오톡 파일 아님, 건너뜀: {name}")
            return
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
                log.warning(f"파일 없음: {arg}")
        return

    # 감시 모드
    folder = GDRIVE_FOLDER
    if not Path(folder).exists():
        log.error(f"❌ Google Drive 폴더를 찾을 수 없습니다: {folder}")
        log.error("   GDRIVE_FOLDER 경로를 스크립트 상단에서 수정하세요.")
        log.error("   Google Drive 앱 → 설정 → 동기화 폴더 에서 경로 확인")
        sys.exit(1)

    log.info("=" * 55)
    log.info("📂 카카오톡 자동 업데이트 워처 시작")
    log.info(f"   감시 폴더 : {folder}")
    log.info(f"   저장소    : {REPO_PATH}")
    log.info(f"   파일 키워드: *{KAKAO_KEYWORD}*.txt")
    log.info("=" * 55)
    log.info("카카오톡 → 내보내기 → Google Drive 저장 시 자동 처리됩니다.")
    log.info("종료: Ctrl+C\n")

    # 매 정시 현재가 자동 갱신 백그라운드 스레드
    t = threading.Thread(target=_hourly_price_refresh_loop, daemon=True)
    t.start()
    now = datetime.now()
    mins_left = 60 - now.minute
    log.info(f"  ⏰ 매 정시 현재가 자동 갱신 활성화 (다음 갱신: {mins_left}분 후)")

    while True:
        handler  = GDriveHandler()
        observer = Observer()
        observer.schedule(handler, folder, recursive=True)
        observer.start()
        log.info("  👀 파일 감시 시작")
        try:
            while observer.is_alive():
                time.sleep(5)
                if not observer.is_alive():
                    raise RuntimeError("observer 비정상 종료")
        except KeyboardInterrupt:
            log.info("\n워처 종료 (Ctrl+C)")
            observer.stop()
            observer.join()
            break
        except Exception as e:
            log.error(f"  observer 오류: {e} — 10초 후 자동 재시작")
            observer.stop()
            observer.join()
            time.sleep(10)

if __name__ == '__main__':
    main()
