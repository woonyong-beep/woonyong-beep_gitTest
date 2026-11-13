"""data/prices/<SOURCE>/<SYMBOL>.csv 와 data/catalog.csv 읽기·쓰기, 그리고 다시 받을 때의 병합 규칙.

파일 형식: date,open,high,low,close,adj_close,volume (ISO 날짜, 소스에 없는 값은 빈 칸).
숫자는 파이썬 float 의 repr (왕복해도 같은 값) 로 쓰고, 정수 값(거래량 등)은 소수점 없이 쓴다.

병합 규칙 (merge)
1. 같은 날짜가 저장본과 새로 받은 데이터에 모두 있으면 새로 받은 값으로 바꾼다.
   - Yahoo 의 adj_close 는 최근 날 기준의 거꾸로 조정이라, 새 배당/분할이 생기면 과거 전체가 바뀐다.
     수집기는 Yahoo 를 받을 때마다 전체 이력을 다시 받으므로, 파일의 adj_close 는 항상 마지막 수집 시점
     하나의 조정 기준으로 일관된다. 이 경우 바뀐 행 수는 '조정값만 바뀜' 으로 따로 보고한다.
   - close 등 원래 가격이 바뀐 경우(소스의 사후 정정)도 새 값으로 바꾸고 '가격 바뀜' 으로 보고한다.
2. 저장본에만 있는 날짜는 지우지 않고 남긴다 (CoinGecko 무료처럼 최근 365일만 주는 소스의 과거를 지키기 위해).
   전체 이력을 주는 소스에서 이런 날짜가 생기면 경고한다: 소스가 그 날을 없앤 것이고,
   남은 행의 adj_close 는 이전 조정 기준이다. 필요하면 파일을 지우고 다시 받는다.
   - 단, Yahoo 는 몇 분 간격으로 연달아 받아도 adj_close 가 매번 조금씩 다르게 온다 (2026-11 확인:
     상대 차이 중앙값 약 1.6e-7, 최대 약 1.6e-6. 서버 쪽 float32 반올림으로 보임). 그래서 원래 가격(OHLCV)이 같고
     adj_close 차이가 상대 ADJ_RTOL (1e-5) 이하이면 저장본 값을 그대로 둔다. 실제 배당 재조정은
     SPY/QQQ/TQQQ/005930.KS 전 기간에서 가장 작은 것도 약 1e-4 이므로 이 기준에 걸리지 않는다.
3. 결과가 저장본과 글자 하나까지 같으면 파일을 다시 쓰지 않는다. 따라서 같은 데이터로 두 번 돌려도
   가격 파일은 바뀌지 않는다 (catalog.csv 의 fetched_at 만 마지막 수집 시각으로 바뀐다).
"""

import csv
import datetime as dt
import io
import os
from pathlib import Path

from collectors import COLUMNS

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices"
CATALOG = ROOT / "data" / "catalog.csv"
WATCHLIST = ROOT / "watchlist.csv"
CATALOG_COLUMNS = ["symbol", "source", "name", "asset_class", "currency",
                   "first_date", "last_date", "rows", "fetched_at"]
WATCHLIST_COLUMNS = ["source", "symbol", "name", "asset_class"]
BAD_CHARS = '<>:"/\\|?*'
ADJ_RTOL = 1e-5


def fmt(x):
    if x is None or x == "":
        return ""
    x = float(x)
    if x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def path_for(source, symbol, root=None):
    root = PRICES if root is None else root
    name = "".join("_" if c in BAD_CHARS else c for c in symbol)
    return Path(root) / source / f"{name}.csv"


def to_text(rows):
    lines = [",".join(COLUMNS)]
    lines += [",".join([r["date"]] + [fmt(r[c]) for c in COLUMNS[1:]]) for r in rows]
    return "\n".join(lines) + "\n"


def read_rows(path):
    """저장된 CSV 를 rows (dict 목록, 숫자는 float, 빈 칸은 None) 로."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"{path}: 열 이름이 {COLUMNS} 가 아님: {reader.fieldnames}")
        return [{c: (r[c] if c == "date" else (float(r[c]) if r[c] != "" else None)) for c in COLUMNS}
                for r in reader]


def write_text_if_changed(path, text):
    """내용이 다를 때만 쓴다 (임시 파일에 쓴 뒤 바꿔치기). 썼으면 True."""
    path = Path(path)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _key(r, cols):
    return tuple(fmt(r[c]) for c in cols)


def merge(stored, fetched, full_history=True):
    """병합 규칙(모듈 설명 참고)에 따라 (rows, report) 를 돌려준다."""
    old = {r["date"]: r for r in stored}
    new = {r["date"]: r for r in fetched}
    rep = {"added": 0, "price_changed": 0, "adj_changed": 0, "unchanged": 0, "adj_noise": 0,
           "kept_old_only": 0, "warnings": []}
    raw_cols = ["open", "high", "low", "close", "volume"]
    new = dict(new)
    for d, r in new.items():
        o = old.get(d)
        if o is None:
            rep["added"] += 1
        elif _key(o, raw_cols) != _key(r, raw_cols):
            rep["price_changed"] += 1
        elif fmt(o["adj_close"]) == fmt(r["adj_close"]):
            rep["unchanged"] += 1
        elif (o["adj_close"] is not None and r["adj_close"] is not None
              and abs(r["adj_close"] / o["adj_close"] - 1) <= ADJ_RTOL):
            new[d] = o                      # 소스 쪽 반올림 잡음: 저장본 유지
            rep["unchanged"] += 1
            rep["adj_noise"] += 1
        else:
            rep["adj_changed"] += 1
    only_old = sorted(set(old) - set(new))
    rep["kept_old_only"] = len(only_old)
    if only_old and fetched:
        first_new = min(new)
        inside = [d for d in only_old if d >= first_new]
        if inside:
            rep["warnings"].append(f"새로 받은 데이터에 없는 날짜 {len(inside)}개를 저장본에서 유지함 "
                                   f"(예: {', '.join(inside[:3])})")
        if full_history and len(inside) < len(only_old):
            rep["warnings"].append(f"전체 이력 소스인데 새 데이터가 {first_new} 부터 시작함. "
                                   f"그 전 {len(only_old) - len(inside)}행은 이전 조정 기준으로 남아 있음")
    rows = dict(old)
    rows.update(new)
    return [rows[d] for d in sorted(rows)], rep


# ---------------------------------------------------------------- watchlist / catalog

def _read_table(path, columns):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    missing = set(columns) - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"{path}: 열이 없음 {sorted(missing)}")
    return [{c: (r[c] or "").strip() for c in columns} for r in reader]


def _write_table(path, columns, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return write_text_if_changed(path, buf.getvalue())


def read_watchlist(path=None):
    return _read_table(WATCHLIST if path is None else path, WATCHLIST_COLUMNS)


def add_to_watchlist(entry, path=None):
    """watchlist.csv 끝에 한 줄 덧붙인다 (이미 있으면 아무것도 안 함). 주석 줄은 그대로 둔다."""
    path = Path(WATCHLIST if path is None else path)
    if any(e["source"] == entry["source"] and e["symbol"] == entry["symbol"] for e in read_watchlist(path)):
        return False
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow([entry.get(c, "") for c in WATCHLIST_COLUMNS])
    text = path.read_text(encoding="utf-8") if path.exists() else ",".join(WATCHLIST_COLUMNS) + "\n"
    if not text.endswith("\n"):
        text += "\n"
    write_text_if_changed(path, text + buf.getvalue())
    return True


def read_catalog(path=None):
    return _read_table(CATALOG if path is None else path, CATALOG_COLUMNS)


def update_catalog(entry, path=None):
    path = CATALOG if path is None else path
    rows = [r for r in read_catalog(path)
            if not (r["source"] == entry["source"] and r["symbol"] == entry["symbol"])]
    rows.append({c: str(entry.get(c, "")) for c in CATALOG_COLUMNS})
    rows.sort(key=lambda r: (r["source"], r["symbol"]))
    _write_table(path, CATALOG_COLUMNS, rows)


def now_utc():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
