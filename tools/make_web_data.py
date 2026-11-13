"""docs/tqqq-data.js (웹 시뮬레이터가 쓰는 TQQQ 가격) 를 data/prices/yahoo/TQQQ.csv 에서 만든다.

형식 (docs/calc.js 의 decodePrices 가 푼다)
  window.TQQQ = {"start": 첫 거래일, "end": 마지막 거래일, "n": 행 수,
                 "gaps": 이전 거래일과의 달력일 차이를 한 자리 숫자로 이어 붙인 문자열 (길이 n-1),
                 "p": 조정 종가 (유효숫자 10자리) 배열};
- 기간은 research/backtest_tqqq.py 와 같은 START ~ END 로 고정한다. collect.py 가 새 행을 덧붙여도
  웹 페이지 수치가 Python 출력과 같게 하려는 것이다. 기간을 늘리려면 두 파일의 END 를 같이 고친다.
- 값을 고치거나 채우지 않는다. 달력일 차이가 10일 이상이면 한 자리로 쓸 수 없으므로 오류를 낸다.

실행 (저장소 루트에서): python tools/make_web_data.py
          확인만:       python tools/make_web_data.py --check   (파일이 지금 만든 것과 같은지)
"""

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "prices" / "yahoo" / "TQQQ.csv"
OUT = ROOT / "docs" / "tqqq-data.js"
START, END = "2010-02-11", "2026-11-11"
FETCHED = "2026-11-13"       # SRC 를 받은 날 (data/catalog.csv 의 fetched_at)


def build():
    with open(SRC, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if START <= r["date"] <= END]
    if not rows or rows[0]["date"] != START or rows[-1]["date"] != END:
        raise SystemExit(f"{SRC}: {START} ~ {END} 구간이 온전하지 않다")
    days = [dt.date.fromisoformat(r["date"]) for r in rows]
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if min(gaps) < 1 or max(gaps) > 9:
        raise SystemExit(f"달력일 차이 {min(gaps)} ~ {max(gaps)}: 한 자리 숫자로 쓸 수 없다")
    p = [float(format(float(r["adj_close"]), ".10g")) for r in rows]
    if min(p) <= 0:
        raise SystemExit("0 이하 가격이 있다")
    obj = {"start": START, "end": END, "n": len(rows), "gaps": "".join(map(str, gaps)), "p": p}
    return "\n".join([
        f"// 자동 생성 파일: tools/make_web_data.py 가 {SRC.relative_to(ROOT).as_posix()} 의 adj_close "
        f"({START} ~ {END}) 를 웹용으로 줄인 것.",
        "// start = 첫 거래일, gaps = 이전 거래일과의 달력일 차이(한 자리 숫자), p = 조정 종가 (유효숫자 10자리).",
        f"// 출처: Yahoo Finance chart API 에서 {FETCHED} 에 직접 받은 분할·배당 조정 종가 (collect.py).",
        "window.TQQQ = " + json.dumps(obj, separators=(",", ":")) + ";",
    ]) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="쓰지 않고 지금 파일과 같은지만 확인")
    a = ap.parse_args()
    text = build()
    if a.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{OUT.relative_to(ROOT)}: {'같음' if same else '다름'}")
        sys.exit(0 if same else 1)
    OUT.write_text(text, encoding="utf-8")
    n = json.loads(text.splitlines()[-1][len("window.TQQQ = "):-1])["n"]
    print(f"{OUT.relative_to(ROOT)} 저장: {START} ~ {END}, {n}행")


if __name__ == "__main__":
    main()
