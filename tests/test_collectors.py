"""수집기와 저장 규칙을 네트워크 없이 시험한다.

tests/fixtures 의 파일은 2026-11-13 에 각 소스에서 실제로 받은 작은 응답을 그대로 저장한 것이다.
"""

import json
import urllib.parse

import pytest

from collectors import COLUMNS, coingecko, fred, http, store, yahoo
from tests.conftest import FIXTURES


def fx(name):
    return (FIXTURES / name).read_bytes()


# ---------------------------------------------------------------- Yahoo

def test_yahoo_parse_split_window():
    rows, meta = yahoo.parse(fx("yahoo_TQQQ_2011-02.json"), now=2e9)
    assert [r["date"] for r in rows] == ["2011-02-22", "2011-02-23", "2011-02-24", "2011-02-25",
                                         "2011-02-28", "2011-03-01", "2011-03-02"]
    assert meta["currency"] == "USD" and meta["asset_class"] == "etf"
    assert all(set(r) == set(COLUMNS) for r in rows)
    r = rows[3]                                    # 2:1 분할일
    assert r["low"] <= r["close"] <= r["high"] and r["adj_close"] > 0 and r["volume"] > 0


def test_yahoo_dividend_adjustment_step():
    rows, _ = yahoo.parse(fx("yahoo_SPY_2024-03.json"), now=2e9)
    by = {r["date"]: r for r in rows}
    a, b = by["2024-03-14"], by["2024-03-15"]      # 2024-03-15 배당락 1.595
    fa, fb = a["adj_close"] / a["close"], b["adj_close"] / b["close"]
    assert fa / fb == pytest.approx(1 - 1.595 / a["close"], abs=1e-5)


def test_yahoo_drops_unfinished_bar_and_uses_exchange_date():
    payload = fx("yahoo_005930.KS_live.json")
    reg = json.loads(payload)["chart"]["result"][0]["meta"]["currentTradingPeriod"]["regular"]
    live, meta = yahoo.parse(payload, now=reg["start"] + 3600)     # 장중
    done, _ = yahoo.parse(payload, now=reg["end"] + 1)             # 장 마감 뒤
    assert meta["currency"] == "KRW" and meta["asset_class"] == "stock"
    assert done[-1]["date"] == "2026-11-13"        # 00:00 UTC 타임스탬프 = 서울 09:00 같은 날
    assert [r["date"] for r in live] == [r["date"] for r in done[:-1]]
    assert any("미확정" in n for n in meta["notes"])


def test_yahoo_error_payload():
    with pytest.raises(http.FetchError):
        yahoo.parse(fx("yahoo_error_notfound.json"))


def test_yahoo_fetch_builds_url_and_clips(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, **k):
        seen["url"], seen["headers"] = url, headers
        return fx("yahoo_TQQQ_2011-02.json")
    monkeypatch.setattr(http, "get", fake_get)
    rows = yahoo.fetch("TQQQ", "2011-02-23", "2011-02-28")
    assert [r["date"] for r in rows] == ["2011-02-23", "2011-02-24", "2011-02-25", "2011-02-28"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["url"]).query)
    assert q["interval"] == ["1d"] and q["events"] == ["div,splits"]
    assert "Mozilla" in seen["headers"]["User-Agent"]
    assert "%5EGSPC" in yahoo.url_for("^GSPC") and "KRW%3DX" in yahoo.url_for("KRW=X")


# ---------------------------------------------------------------- CoinGecko

def test_coingecko_parse():
    rows, meta = coingecko.parse(fx("coingecko_bitcoin_3d.json"))
    assert [r["date"] for r in rows] == ["2026-11-11", "2026-11-12", "2026-11-13"]   # 현재가 점은 제외
    assert rows[0]["close"] == pytest.approx(73721.18379734851)
    assert rows[0]["open"] is None and rows[0]["adj_close"] is None
    assert rows[0]["volume"] == pytest.approx(30562745994.870018)
    assert meta["currency"] == "USD"


def test_coingecko_history_limit_error():
    with pytest.raises(http.FetchError, match="365"):
        coingecko.parse(fx("coingecko_error_365.json"))


def test_coingecko_url_days_capped():
    import datetime as dt
    u = coingecko.url_for("bitcoin", start="2010-01-01", today=dt.date(2026, 11, 13))
    assert "days=365" in u
    u = coingecko.url_for("bitcoin", start="2026-11-01", today=dt.date(2026, 11, 13))
    assert "days=13" in u


# ---------------------------------------------------------------- FRED

def test_fred_parse_skips_missing():
    rows, meta = fred.parse(fx("fred_DTB3_2024-12.csv"), series="DTB3")
    dates = [r["date"] for r in rows]
    assert "2024-12-25" not in dates and "2025-01-01" not in dates
    assert len(rows) == 9 and rows[0]["close"] == 4.23 and rows[-1]["close"] == 4.20
    assert meta["asset_class"] == "rate" and any("2개" in n for n in meta["notes"])


def test_fred_wrong_series_or_html():
    with pytest.raises(http.FetchError):
        fred.parse(fx("fred_DTB3_2024-12.csv"), series="DGS10")
    with pytest.raises(http.FetchError):
        fred.parse(b"<html>blocked</html>")


def test_fred_fetch_uses_default_user_agent(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, **k):
        seen["headers"] = headers
        return fx("fred_DTB3_2024-12.csv")
    monkeypatch.setattr(http, "get", fake_get)
    assert len(fred.fetch("DTB3", "2024-12-26")) == 6
    assert not seen["headers"]                     # 브라우저 User-Agent 를 넣으면 FRED 가 연결을 끊는다


# ---------------------------------------------------------------- 저장과 병합

def row(d, close, adj=None, vol=None):
    return {"date": d, "open": None, "high": None, "low": None, "close": close, "adj_close": adj,
            "volume": vol}


def test_fmt_roundtrip(tmp_path):
    rows = [row("2024-01-01", 0.1 + 0.2, 1 / 3, 65102220.0), row("2024-01-02", 1e-7, None, None)]
    p = tmp_path / "a.csv"
    p.write_text(store.to_text(rows))
    back = store.read_rows(p)
    assert back == rows
    assert p.read_text().splitlines()[1].endswith(",65102220")


def test_merge_rules():
    old = [row("2024-01-01", 10, 9.0), row("2024-01-02", 11, 9.9), row("2024-01-03", 12, 10.8)]
    new = [row("2024-01-02", 11, 10.0), row("2024-01-03", 12.5, 11.0), row("2024-01-04", 13, 12.0)]
    merged, rep = store.merge(old, new, full_history=True)
    assert [r["date"] for r in merged] == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
    assert merged[1]["adj_close"] == 10.0 and merged[2]["close"] == 12.5
    assert merged[0]["adj_close"] == 9.0                 # 저장본에만 있는 날은 남는다
    assert (rep["added"], rep["price_changed"], rep["adj_changed"], rep["kept_old_only"]) == (1, 1, 1, 1)
    assert any("이전 조정 기준" in w for w in rep["warnings"])
    _, rep2 = store.merge(old, new, full_history=False)
    assert not rep2["warnings"]                          # 최근 일부만 주는 소스에서는 정상


def test_merge_ignores_adj_close_noise():
    old = [row("2024-01-01", 10, 9.0), row("2024-01-02", 11, 9.9)]
    new = [row("2024-01-01", 10, 9.0 * (1 + 5e-6)), row("2024-01-02", 11, 9.9 * (1 + 1e-4))]
    merged, rep = store.merge(old, new)
    assert merged[0]["adj_close"] == 9.0                 # 1e-5 이하 차이: 저장본 유지
    assert merged[1]["adj_close"] == 9.9 * (1 + 1e-4)     # 실제 재조정: 새 값
    assert (rep["adj_noise"], rep["adj_changed"], rep["unchanged"]) == (1, 1, 1)


def test_merge_warns_on_missing_inside_range():
    old = [row("2024-01-01", 1), row("2024-01-02", 2), row("2024-01-03", 3)]
    new = [row("2024-01-01", 1), row("2024-01-03", 3)]
    merged, rep = store.merge(old, new)
    assert len(merged) == 3 and any("2024-01-02" in w for w in rep["warnings"])


def test_update_is_idempotent(tmp_path, monkeypatch):
    """같은 응답으로 두 번 갱신하면 가격 파일이 바뀌지 않는다."""
    import collect
    monkeypatch.setattr(store, "PRICES", tmp_path / "prices")
    monkeypatch.setattr(store, "CATALOG", tmp_path / "catalog.csv")
    monkeypatch.setattr(http, "get", lambda url, headers=None, **k: fx("yahoo_TQQQ_2011-02.json"))
    monkeypatch.setattr(yahoo, "parse", lambda p, now=None, _f=yahoo.parse: _f(p, now=2e9))
    e = {"source": "yahoo", "symbol": "TQQQ", "name": "", "asset_class": ""}
    r1 = collect.update_one(e, verbose=False)
    path = tmp_path / "prices" / "yahoo" / "TQQQ.csv"
    text, mtime = path.read_text(), path.stat().st_mtime_ns
    r2 = collect.update_one(e, verbose=False)
    assert r1["written"] and r1["added"] == 7
    assert not r2["written"] and r2["unchanged"] == 7 and r2["added"] == 0
    assert path.read_text() == text and path.stat().st_mtime_ns == mtime
    cat = store.read_catalog(tmp_path / "catalog.csv")
    assert len(cat) == 1 and cat[0]["rows"] == "7" and cat[0]["first_date"] == "2011-02-22"
    assert cat[0]["name"] == "ProShares UltraPro QQQ" and cat[0]["currency"] == "USD"


def test_watchlist_add_keeps_comments(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("# 주석\nsource,symbol,name,asset_class\nyahoo,SPY,S&P,etf\n")
    assert store.read_watchlist(p) == [{"source": "yahoo", "symbol": "SPY", "name": "S&P", "asset_class": "etf"}]
    assert store.add_to_watchlist({"source": "fred", "symbol": "DTB3", "name": "금리, 3개월", "asset_class": "rate"}, p)
    assert not store.add_to_watchlist({"source": "yahoo", "symbol": "SPY"}, p)
    assert p.read_text().startswith("# 주석\n")
    assert store.read_watchlist(p)[-1]["name"] == "금리, 3개월"


def test_path_for_sanitizes():
    assert store.path_for("yahoo", "^GSPC").name == "^GSPC.csv"
    assert store.path_for("x", "a/b:c").name == "a_b_c.csv"
