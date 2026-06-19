"""
Naver Finance 검색으로 포트폴리오 국내 ETF/주식 종목코드 자동 매핑
→ ticker_map.json 생성 (최초 1회만 실행)
"""
import sys, json, time, requests
sys.stdout.reconfigure(encoding='utf-8')

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

sess = requests.Session()
sess.headers['User-Agent'] = 'Mozilla/5.0'

def search_code(name):
    for target in ['etf', 'stock,etf,corp']:
        try:
            r = sess.get('https://ac.finance.naver.com/ac',
                params={'q': name, 'q_enc': 'utf8', 'target': target,
                        'reorderFlag': 'N', 'limit': 10}, timeout=8)
            for group in r.json().get('items', []):
                for item in group:
                    if isinstance(item, list) and len(item) >= 2 and item[0] == name:
                        return str(item[1])
        except Exception as e:
            pass
    return None

ticker_map = {}
not_found = []

print(f"국내 종목 {len(KR_STOCKS)}개 코드 검색 중...")
for name in KR_STOCKS:
    code = search_code(name)
    if code:
        ticker_map[name] = code
        print(f"  ✅ {name} → {code}")
    else:
        not_found.append(name)
        print(f"  ❌ {name} → 미매칭")
    time.sleep(0.3)

with open('ticker_map.json', 'w', encoding='utf-8') as f:
    json.dump(ticker_map, f, ensure_ascii=False, indent=2)

print(f"\n✅ ticker_map.json 저장 완료 ({len(ticker_map)}/{len(KR_STOCKS)}개)")
if not_found:
    print(f"⚠️  미매칭: {not_found}")
    print("   → ticker_map.json 에 직접 코드를 추가하거나 종목명 확인 필요")
