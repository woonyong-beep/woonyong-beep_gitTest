"""저장된 시계열의 기본 점검: 연도별 행 수, 날짜 공백, 0 이하 값, 하루 급변.

값을 고치지 않는다. 이상해 보이는 곳을 보고만 한다.
"""

import datetime as dt
from collections import Counter


def price_of(r):
    return r["adj_close"] if r["adj_close"] is not None else r["close"]


def check(rows, jump=0.25, allow_nonpositive=False):
    """rows 를 점검해 dict 로 돌려준다.

    jump: |하루 변화율| 이 이보다 크면 '급변' 으로 적는다 (조정 종가가 있으면 그것, 없으면 종가 기준).
    allow_nonpositive: 금리처럼 0 이하가 정상인 시계열이면 True.
    """
    out = {"rows": len(rows), "first": None, "last": None, "per_year": {}, "max_gap_days": 0,
           "max_gap_end": None, "gaps_ge_5": 0, "nonpositive": [], "missing_close": 0,
           "unsorted_or_dup": 0, "jumps": [], "ohlc_inconsistent": 0, "flat_zero_volume": []}
    if not rows:
        return out
    out["first"], out["last"] = rows[0]["date"], rows[-1]["date"]
    out["per_year"] = dict(sorted(Counter(r["date"][:4] for r in rows).items()))
    dates = [dt.date.fromisoformat(r["date"]) for r in rows]
    for a, b, r in zip(dates, dates[1:], rows[1:]):
        g = (b - a).days
        if g <= 0:
            out["unsorted_or_dup"] += 1
        if g > out["max_gap_days"]:
            out["max_gap_days"], out["max_gap_end"] = g, r["date"]
        if g >= 5:
            out["gaps_ge_5"] += 1
    # 거래량이 있는 시계열에서 거래량 0, 시가=고가=저가=종가=전일 종가 인 행: 휴장일을 소스가 전일 가격으로
    # 채운 것으로 보인다 (Yahoo 의 한국 종목 2000년대 휴일 등). 고치지 않고 개수만 센다.
    vols = sorted(r["volume"] for r in rows if r["volume"] is not None)
    if vols and vols[len(vols) // 2] > 0:
        for a, r in zip(rows, rows[1:]):
            if (r["volume"] == 0 and r["close"] is not None and a["close"] is not None
                    and r["open"] == r["high"] == r["low"] == r["close"] == a["close"]):
                out["flat_zero_volume"].append(r["date"])
    prev = None
    for r in rows:
        if r["close"] is None:
            out["missing_close"] += 1
            continue
        p = price_of(r)
        if not allow_nonpositive and any(r[c] is not None and r[c] <= 0
                                         for c in ("open", "high", "low", "close", "adj_close")):
            out["nonpositive"].append(r["date"])
        h, lo = r["high"], r["low"]
        if h is not None and lo is not None and (h < lo or not (lo <= r["close"] <= h)):
            out["ohlc_inconsistent"] += 1
        if prev is not None and prev > 0 and p is not None:
            chg = p / prev - 1
            if abs(chg) > jump:
                out["jumps"].append((r["date"], chg))
        prev = p
    return out


def summary_line(c):
    years = list(c["per_year"].values())
    inner = years[1:-1] or years
    s = (f"{c['rows']}행 {c['first']} ~ {c['last']}, 연간 행 수(첫해/마지막해 제외) "
         f"{min(inner) if inner else 0}~{max(inner) if inner else 0}, "
         f"최대 공백 {c['max_gap_days']}일({c['max_gap_end']} 직전), 5일 이상 공백 {c['gaps_ge_5']}회")
    if c["nonpositive"]:
        s += f", 0 이하 값 {len(c['nonpositive'])}일(예: {c['nonpositive'][0]})"
    if c["unsorted_or_dup"]:
        s += f", 정렬/중복 문제 {c['unsorted_or_dup']}곳"
    if c["ohlc_inconsistent"]:
        s += f", 고가<저가 또는 종가가 고저 범위 밖 {c['ohlc_inconsistent']}일"
    if c["flat_zero_volume"]:
        f = c["flat_zero_volume"]
        s += f", 거래량 0·가격 변화 없는 행(휴장일 채움 의심) {len(f)}일({f[0]} ~ {f[-1]})"
    if c["jumps"]:
        top = sorted(c["jumps"], key=lambda x: -abs(x[1]))[:3]
        s += f", 하루 급변 {len(c['jumps'])}회(" + ", ".join(f"{d} {v:+.0%}" for d, v in top) + ")"
    return s
