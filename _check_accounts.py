import re
from pathlib import Path

KNOWN_NUMS = {"70714", "70871", "71297", "71462", "71615", "70868"}
files = [
    r"G:\내 드라이브\KakaoTalk\06231500.txt",
    r"G:\내 드라이브\KakaoTalk\06231300.txt",
    r"G:\내 드라이브\KakaoTalk\06231200.txt",
]

for f in files:
    p = Path(f)
    if not p.exists():
        print(f"{p.name}: 파일 없음")
        continue
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    unknown = {}
    for i, line in enumerate(lines):
        if "계좌번호" in line or "주식체결안내" in line:
            chunk = lines[max(0, i-2):i+5]
            chunk_str = "\n".join(chunk)
            for m in re.finditer(r"(\d{5})\*+", chunk_str):
                num = m.group(1)
                if num not in KNOWN_NUMS:
                    ctx = " | ".join(c.strip() for c in chunk if c.strip())[:200]
                    unknown.setdefault(num, []).append(ctx)
    if unknown:
        for num, ctxs in unknown.items():
            print(f"[{p.name}] 미등록 계좌: {num}")
            for c in ctxs[:3]:
                print(f"  >> {c}")
            print()
    else:
        print(f"[{p.name}] 미등록 계좌 없음")
