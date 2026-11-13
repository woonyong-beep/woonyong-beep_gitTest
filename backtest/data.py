"""백테스트용 데이터 불러오기: data/prices/<source>/<symbol>.csv 한 개 = Series 하나.

- 가격 열: 기본은 adj_close (모두 채워져 있을 때), 아니면 close. field 로 직접 고를 수도 있다.
- 기본 점검: 날짜가 엄격히 오름차순(중복 없음), 값이 모두 있음, 가격은 모두 0 보다 큼.
  점검에 걸리면 ValueError. 값을 고치거나 채우지 않는다.
  (예: Yahoo CL=F 는 2020-04-20 종가가 -37.63 이라 가격 점검에 걸린다. 실제 있었던 값이다.)
- 금리 시계열(FRED DTB3 등)은 load_rate 로 읽는다. 0 이하 값도 허용한다.
- align: 여러 시계열을 모두 값이 있는 날짜(교집합)에만 맞춘다. 빠진 날을 채우지 않는다.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Series:
    """날짜(datetime64[D])와 값(float) 배열 한 쌍."""
    name: str
    dates: np.ndarray
    values: np.ndarray

    def __len__(self):
        return len(self.dates)

    def between(self, start=None, end=None):
        """start <= date <= end 부분 (문자열 "YYYY-MM-DD" 가능)."""
        m = np.ones(len(self.dates), bool)
        if start is not None:
            m &= self.dates >= np.datetime64(start, "D")
        if end is not None:
            m &= self.dates <= np.datetime64(end, "D")
        return Series(self.name, self.dates[m], self.values[m])


def validate(s, positive=True):
    if len(s) == 0:
        raise ValueError(f"{s.name}: 행이 없음")
    d = np.diff(s.dates.astype("int64"))
    if (d <= 0).any():
        i = int(np.argmax(d <= 0)) + 1
        raise ValueError(f"{s.name}: 날짜 정렬/중복 문제 ({s.dates[i]})")
    if not np.isfinite(s.values).all():
        i = int(np.argmax(~np.isfinite(s.values)))
        raise ValueError(f"{s.name}: 값 없음 ({s.dates[i]})")
    if positive and (s.values <= 0).any():
        i = int(np.argmax(s.values <= 0))
        raise ValueError(f"{s.name}: 0 이하 가격 ({s.dates[i]} {s.values[i]})")
    return s


def load_csv(path, column=None, name=None, positive=True):
    """날짜 열(date 또는 observation_date)과 값 열 하나를 읽는다.

    column=None 이면 adj_close 가 모두 채워져 있을 때 adj_close, 아니면 close.
    data/tqqq_daily.csv (date,adj_close) 같은 예전 파일도 이것으로 읽는다.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path}: 행이 없음")
    date_col = "date" if "date" in rows[0] else "observation_date"
    if column is None:
        if "adj_close" in rows[0] and all(r["adj_close"] != "" for r in rows):
            column = "adj_close"
        elif "close" in rows[0]:
            column = "close"
        elif "adj_close" in rows[0]:
            column = "adj_close"
        else:
            raise ValueError(f"{path}: adj_close/close 열이 없음. column 을 지정하라")
    vals = [r[column] for r in rows]
    if any(v == "" for v in vals):
        i = next(i for i, v in enumerate(vals) if v == "")
        raise ValueError(f"{path}: {column} 값이 빈 행 ({rows[i][date_col]})")
    s = Series(name or path.stem, np.array([r[date_col] for r in rows], dtype="datetime64[D]"),
               np.array(vals, dtype=float))
    return validate(s, positive=positive)


def load(source, symbol, field=None, start=None, end=None, root=None):
    """data/prices/<source>/<symbol>.csv 를 Series 로. 이름은 symbol."""
    from collectors.store import path_for
    path = path_for(source, symbol, root)
    if not path.exists():
        raise FileNotFoundError(f"{path} 가 없다. 먼저 python collect.py {source} {symbol}")
    s = load_csv(path, column=field, name=symbol)
    return s.between(start, end) if (start or end) else s


def load_rate(source="fred", symbol="DTB3", start=None, end=None, root=None):
    """금리 시계열 (연 %, 값은 close 열). 0 이하 값을 허용한다."""
    from collectors.store import path_for
    s = load_csv(path_for(source, symbol, root), column="close", name=symbol, positive=False)
    return s.between(start, end) if (start or end) else s


def align(*series):
    """모든 시계열에 값이 있는 날짜(교집합)만 남긴다. (dates, {name: values}) 를 돌려준다."""
    if not series:
        raise ValueError("시계열이 없다")
    names = [s.name for s in series]
    if len(set(names)) != len(names):
        raise ValueError(f"이름이 겹친다: {names}")
    common = series[0].dates
    for s in series[1:]:
        common = np.intersect1d(common, s.dates)
    if len(common) == 0:
        raise ValueError("겹치는 날짜가 없다")
    out = {}
    for s in series:
        idx = np.searchsorted(s.dates, common)
        out[s.name] = s.values[idx]
    return common, out
