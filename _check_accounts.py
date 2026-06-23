import re
from pathlib import Path

TARGET = {"71417", "71661"}
f = Path(r"G:\내 드라이브\KakaoTalk\06231500.txt")
text = f.read_text(encoding="utf-8")
lines = text.splitlines()

for i, line in enumerate(lines):
    for num in TARGET:
        if num in line:
            chunk = lines[max(0,i-3):i+6]
            print(f"=== {num} (line {i}) ===")
            for c in chunk:
                print(" ", c.strip())
            print()
