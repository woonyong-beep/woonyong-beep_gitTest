"""Yahoo Finance chart API 수집기.

https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>?period1=..&period2=..&interval=1d&events=div,splits

- 주식, ETF, 지수(^GSPC, ^KS11), 환율(KRW=X), 선물(GC=F, CL=F), 암호화폐(BTC-USD), 한국 주식(005930.KS) 등.
- 브라우저 비슷한 User-Agent 가 있어야 응답한다. 가끔 429 (Too Many Requests) 를 주므로 다시 시도한다.
- open/high/low/close 는 분할만 반영된 가격, adj_close 는 분할과 배당을 모두 반영한 조정 종가다.
  조정 종가는 가장 최근 날을 기준으로 과거를 거꾸로 조정하므로, 새 배당/분할이 생기면 과거 값이 모두 바뀐다.
- 날짜는 각 봉의 타임스탬프를 거래소 시간대(meta.exchangeTimezoneName)로 바꾼 날짜다.
- 아직 끝나지 않은 오늘 봉(장중 가격)은 저장하지 않는다. 종가(close)가 비어 있는 봉도 버린다.
- 지수와 환율은 거래량이 0 으로 온다. 받은 그대로 둔다.
"""

import datetime as dt
import json
import time
import urllib.parse
from zoneinfo import ZoneInfo

from collectors import as_date, clip, empty_row, http

SOURCE = "yahoo"
FULL_HISTORY = True
ADJUSTED = True
BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
EARLIEST = -2208988800        # 1900-01-01 UTC. period1=0 이면 1970년 이전 이력이 잘린다.

ASSET_CLASS = {"EQUITY": "stock", "ETF": "etf", "MUTUALFUND": "fund", "INDEX": "index",
               "CURRENCY": "fx", "FUTURE": "commodity", "CRYPTOCURRENCY": "crypto"}


def url_for(symbol, start=None, end=None):
    start, end = as_date(start), as_date(end)
    p1 = EARLIEST if start is None else int(dt.datetime(start.year, start.month, start.day,
                                                        tzinfo=dt.UTC).timestamp()) - 86400
    if end is None:
        p2 = int(time.time()) + 86400
    else:
        p2 = int(dt.datetime(end.year, end.month, end.day, tzinfo=dt.UTC).timestamp()) + 2 * 86400
    return http.build_url(BASE + urllib.parse.quote(symbol, safe=""),
                          {"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"})


def _num(x):
    return None if x is None else float(x)


def parse(payload, now=None):
    """chart API 응답(JSON bytes/str/dict)을 (rows, meta) 로 바꾼다. 네트워크를 쓰지 않는다.

    now: 현재 시각 (unix 초). 아직 끝나지 않은 봉을 가려내는 데 쓴다. None 이면 실제 현재 시각.
    """
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    chart = payload["chart"]
    if chart.get("error"):
        raise http.FetchError(f"Yahoo 오류: {chart['error']}")
    res = chart["result"][0]
    m = res["meta"]
    now = time.time() if now is None else now
    meta = {"currency": m.get("currency") or "", "name": m.get("longName") or m.get("shortName") or "",
            "asset_class": ASSET_CLASS.get(m.get("instrumentType", ""), ""), "notes": []}
    ts = res.get("timestamp") or []
    if not ts:
        return [], meta
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    tz = ZoneInfo(m.get("exchangeTimezoneName") or "UTC")

    # 아직 진행 중인 정규장: 그 세션이 시작한 뒤의 봉은 확정되지 않은 장중 가격이다
    reg = (m.get("currentTradingPeriod") or {}).get("regular") or {}
    open_from = reg["start"] if reg and now < reg.get("end", 0) else None

    by_date = {}
    for i, t in enumerate(ts):
        d = dt.datetime.fromtimestamp(t, tz).date().isoformat()
        close = q["close"][i]
        if t > now or (open_from is not None and t >= open_from):
            meta["notes"].append(f"{d} 미확정 봉 제외")
            continue
        if close is None:
            meta["notes"].append(f"{d} 종가 없음 제외")
            continue
        row = empty_row(d)
        row.update(open=_num(q["open"][i]), high=_num(q["high"][i]), low=_num(q["low"][i]),
                   close=float(close), adj_close=_num(adj[i]) if adj else None,
                   volume=_num(q["volume"][i]))
        if d in by_date:
            meta["notes"].append(f"{d} 같은 날짜 봉 중복, 나중 것 사용")
        by_date[d] = row
    return [by_date[d] for d in sorted(by_date)], meta


def fetch_series(symbol, start=None, end=None):
    rows, meta = parse(http.get(url_for(symbol, start, end), headers=HEADERS))
    return clip(rows, start, end), meta


def fetch(symbol, start=None, end=None):
    return fetch_series(symbol, start, end)[0]
