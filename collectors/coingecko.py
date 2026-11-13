"""CoinGecko 수집기 (무료 공개 API, 키 없음).

https://api.coingecko.com/api/v3/coins/<id>/market_chart?vs_currency=usd&days=365&interval=daily

- symbol 은 CoinGecko 코인 id 다 (예: bitcoin, ethereum). 기준 통화는 VS_CURRENCY (usd).
- 무료 공개 API 는 최근 365일까지만 준다. days=max 나 그보다 긴 기간을 요청하면
  error_code 10012 "Public API users are limited to querying historical data within the past 365 days" 를 돌려준다
  (2026-11 확인). 그래서 FULL_HISTORY = False 이고, 저장할 때는 예전 행을 지우지 않고 새 행을 덧붙인다.
- 일별 값은 매일 00:00 UTC 시점의 가격 하나뿐이다. close 칸에 넣고 open/high/low/adj_close 는 비워 둔다.
  date 는 그 타임스탬프의 UTC 날짜다. 즉 date=D 의 값은 D 일 00:00 UTC 가격으로,
  Yahoo BTC-USD 의 D-1 일 종가(23:59 UTC 무렵)와 거의 같은 시점이다.
- volume 은 CoinGecko 의 total_volumes (그 시점까지 24시간 거래대금, 기준 통화 단위) 이다. 주식 수가 아니다.
- 응답 끝에 붙는 '지금 이 순간' 가격(00:00 UTC 가 아닌 점)은 확정된 일별 값이 아니므로 버린다.
- 무료 API 는 분당 호출 수 제한이 있다 (429). http.get 이 기다렸다가 다시 시도한다.
"""

import datetime as dt
import json

from collectors import as_date, clip, empty_row, http

SOURCE = "coingecko"
FULL_HISTORY = False
ADJUSTED = False
MAX_DAYS = 365
VS_CURRENCY = "usd"
BASE = "https://api.coingecko.com/api/v3/coins/"
HEADERS = {"Accept": "application/json"}
DAY_MS = 86_400_000


def url_for(symbol, start=None, end=None, today=None):
    today = today or dt.datetime.now(dt.UTC).date()
    start = as_date(start)
    days = MAX_DAYS if start is None else max(1, min(MAX_DAYS, (today - start).days + 1))
    return http.build_url(f"{BASE}{symbol}/market_chart",
                          {"vs_currency": VS_CURRENCY, "days": days, "interval": "daily"})


def parse(payload):
    """market_chart 응답을 (rows, meta) 로. 네트워크를 쓰지 않는다."""
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    if "error" in payload or ("status" in payload and "prices" not in payload):
        raise http.FetchError(f"CoinGecko 오류: {payload}")
    meta = {"currency": VS_CURRENCY.upper(), "name": "", "asset_class": "crypto", "notes": []}
    vol = {int(t): v for t, v in payload.get("total_volumes", [])}
    by_date = {}
    for t, price in payload["prices"]:
        t = int(t)
        d = dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()
        if t % DAY_MS:
            meta["notes"].append(f"{d} 00:00 UTC 가 아닌 값(현재가) 제외")
            continue
        if price is None:
            continue
        row = empty_row(d)
        row["close"] = float(price)
        row["volume"] = None if vol.get(t) is None else float(vol[t])
        by_date[d] = row
    return [by_date[d] for d in sorted(by_date)], meta


def fetch_series(symbol, start=None, end=None):
    rows, meta = parse(http.get(url_for(symbol, start, end), headers=HEADERS))
    return clip(rows, start, end), meta


def fetch(symbol, start=None, end=None):
    return fetch_series(symbol, start, end)[0]
