import sys
sys.stdout.reconfigure(encoding='utf-8')

# kakao_watcher 함수들만 임포트 (main() 실행 방지)
import importlib.util, types

spec = importlib.util.spec_from_file_location("kw", "kakao_watcher.py")
mod  = importlib.util.module_from_spec(spec)
mod.__name__ = "kw"   # __main__ 방지
spec.loader.exec_module(mod)

filepath = r"G:\내 드라이브\KakaoTalk\KakaoTalkChats_260619_1700.txt"

print(f"파일 파싱 시작: {filepath}")
try:
    data = mod.parse_kakao(filepath)
    print(f"거래: {len(data['trades'])}건")
    print(f"배당: {len(data['dividends'])}건")
    print(f"입금: {len(data['deposits'])}건")
    print(f"시각: {data['pushedAt']}")

    print("\n현재가 조회 중...")
    data['prices'] = mod.fetch_prices()
    print(f"현재가: {len(data['prices'])}개 조회됨")
    for name, price in list(data['prices'].items())[:5]:
        print(f"  {name}: {price:,}원")

    print("\nHTML 주입 중...")
    mod.inject_to_html(data)
    print("HTML 주입 완료")

    print("\nGitHub push 중...")
    pushed = mod.git_push(data)
    if pushed:
        print("push 완료!")
    else:
        print("변경 없음 (push 생략)")

except Exception as e:
    import traceback
    traceback.print_exc()
