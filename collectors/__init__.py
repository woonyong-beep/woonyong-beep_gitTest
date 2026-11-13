"""가격 데이터 수집기 모음.

모든 수집기 모듈은 같은 인터페이스를 가진다.

    fetch(symbol, start=None, end=None) -> rows
    fetch_series(symbol, start=None, end=None) -> (rows, meta)

- start, end: datetime.date 또는 "YYYY-MM-DD" 문자열. None 이면 소스가 주는 가장 이른 날 / 가장 최근 날.
  end 는 그날을 포함한다.
- rows: 날짜 오름차순 dict 목록. 키는 COLUMNS 와 같고, 소스에 없는 필드는 None 이다.
  date 는 "YYYY-MM-DD" 문자열, 나머지는 float (volume 도 float) 또는 None.
- meta: {"currency": ..., "name": ..., "asset_class": ...} 소스가 알려주는 정보 (없으면 빈 문자열).

모듈 속성
- SOURCE: 저장 경로 data/prices/<SOURCE>/ 에 쓰이는 이름.
- FULL_HISTORY: start=None 으로 불렀을 때 전체 이력을 주는지. False 면 (CoinGecko 무료) 최근 일부만 준다.
- ADJUSTED: adj_close 가 나중에 바뀔 수 있는지 (배당/분할 재조정). 저장 시 병합 규칙에 쓰인다.

어떤 수집기도 값을 만들어 내거나 보간하지 않는다. 소스가 값을 주지 않은 날은 행이 없거나 칸이 비어 있다.
"""

import datetime as dt
from importlib import import_module

COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]
SOURCES = ("yahoo", "coingecko", "fred")


def get(source):
    """소스 이름으로 수집기 모듈을 돌려준다."""
    if source not in SOURCES:
        raise ValueError(f"알 수 없는 소스: {source} (가능: {', '.join(SOURCES)})")
    return import_module(f"collectors.{source}")


def as_date(x):
    """None, datetime.date, "YYYY-MM-DD" 를 datetime.date (또는 None) 로."""
    if x is None or isinstance(x, dt.date):
        return x.date() if isinstance(x, dt.datetime) else x
    return dt.date.fromisoformat(str(x))


def clip(rows, start=None, end=None):
    """start <= date <= end 인 행만 남긴다."""
    start, end = as_date(start), as_date(end)
    lo = start.isoformat() if start else ""
    hi = end.isoformat() if end else "9999"
    return [r for r in rows if lo <= r["date"] <= hi]


def empty_row(date):
    row = dict.fromkeys(COLUMNS)
    row["date"] = date
    return row
