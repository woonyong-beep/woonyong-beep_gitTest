"""FRED (세인트루이스 연준) 수집기.

https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=YYYY-MM-DD&coed=YYYY-MM-DD

- 금리 등 경제 시계열. 값은 close 칸에 넣고 나머지 칸은 비워 둔다.
  예: DTB3 = 미국 3개월 T-bill 유통시장 금리, 할인율 기준 연 % (5.22 는 연 5.22%).
- 값이 '.' 이거나 빈 날(휴일 등)은 행을 만들지 않는다 (채우거나 보간하지 않는다).
- 2026-11 확인: User-Agent 가 "Mozilla/5.0 ..." 로 시작하면 서버가 응답 없이 연결을 끊는다
  (urllib: RemoteDisconnected, curl: "HTTP/2 stream not closed cleanly" 류).
  그래서 브라우저 흉내를 내지 않고 urllib 기본 User-Agent 를 그대로 쓴다.
"""

import csv
import io

from collectors import as_date, clip, empty_row, http

SOURCE = "fred"
FULL_HISTORY = True
ADJUSTED = False
BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def url_for(series, start=None, end=None):
    params = {"id": series}
    if start is not None:
        params["cosd"] = as_date(start).isoformat()
    if end is not None:
        params["coed"] = as_date(end).isoformat()
    return http.build_url(BASE, params)


def parse(payload, series=None):
    """fredgraph.csv 응답을 (rows, meta) 로. 네트워크를 쓰지 않는다."""
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    if len(header) < 2 or header[0].strip().lower() not in ("observation_date", "date"):
        raise http.FetchError(f"FRED 응답 형식이 예상과 다름: {text[:200]!r}")
    if series is not None and header[1].strip() != series:
        raise http.FetchError(f"FRED 응답의 시계열 이름 {header[1]!r} != 요청 {series!r}")
    meta = {"currency": "", "name": "", "asset_class": "rate", "notes": []}
    rows, skipped = [], 0
    for rec in reader:
        if not rec:
            continue
        d, v = rec[0].strip(), rec[1].strip()
        if v in ("", "."):
            skipped += 1
            continue
        row = empty_row(as_date(d).isoformat())
        row["close"] = float(v)
        rows.append(row)
    if skipped:
        meta["notes"].append(f"값('.' 또는 빈 칸) 없는 날 {skipped}개 제외")
    rows.sort(key=lambda r: r["date"])
    return rows, meta


def fetch_series(symbol, start=None, end=None):
    rows, meta = parse(http.get(url_for(symbol, start, end)), series=symbol)
    return clip(rows, start, end), meta


def fetch(symbol, start=None, end=None):
    return fetch_series(symbol, start, end)[0]
