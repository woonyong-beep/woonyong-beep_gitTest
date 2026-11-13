"""dart/ 패키지 시험. 네트워크 없이 돈다 (conftest.py 가 urllib.request.urlopen 을 막는다).

- 클라이언트: 키 가리기, 캐시, 오류 처리 (가짜 _urlopen 을 끼운다)
- 응답 해석: 작은 실제 응답 조각 (tests/fixtures/dart, 키 없음)
- 점검 로직: 손으로 만든 작은 예
- 원문 추출기: 손으로 만든 작은 DART XML
- 회귀: 받아 둔 data/dart/extracted/statements.csv 의 잘 알려진 값
"""

import io
import json
import os
import re
import zipfile
from pathlib import Path

import pytest

from conftest import FIXTURES, ROOT
from dart import checks, client as dclient, collect, document, extract, inventory

FAKE_KEY = "0123456789abcdef0123456789abcdef01234567"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(payloads, seen):
    def _open(req, timeout):
        seen.append(req.full_url)
        return FakeResp(payloads.pop(0))
    return _open


# ---------------------------------------------------------------- 클라이언트

def test_redact_removes_key_and_param(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", FAKE_KEY)
    s = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={FAKE_KEY}&corp_code=1 실패 {FAKE_KEY}"
    out = dclient.redact(s)
    assert FAKE_KEY not in out
    assert "crtfc_key=***" in out
    assert dclient.redact("x?crtfc_key=abc&y=1") == "x?crtfc_key=***&y=1"
    assert "crtfc_key=***" in dclient.public_url("list.json", {"corp_code": "1"})


def test_missing_key_is_fatal(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(dclient.DartFatal):
        dclient.Client().key


def test_get_json_caches_and_never_stores_key(monkeypatch, tmp_path):
    seen = []
    body = json.dumps({"status": "000", "message": "정상", "list": [{"a": 1}]}).encode()
    monkeypatch.setattr(dclient, "_urlopen", fake_urlopen([body], seen))
    c = dclient.Client(key=FAKE_KEY, pause=0)
    path = tmp_path / "x.json"
    assert c.get_json("company.json", {"corp_code": "1"}, path)["list"] == [{"a": 1}]
    assert c.get_json("company.json", {"corp_code": "1"}, path)["list"] == [{"a": 1}]   # 두 번째는 캐시
    assert c.calls == 1 and c.cache_hits == 1 and len(seen) == 1
    assert FAKE_KEY in seen[0]                       # 요청에는 키가 들어가고
    assert FAKE_KEY not in path.read_text(encoding="utf-8")   # 저장본에는 없다


def test_quota_error_is_fatal_and_redacted(monkeypatch, tmp_path):
    body = json.dumps({"status": "020", "message": f"요청 제한 초과 {FAKE_KEY}"}).encode()
    monkeypatch.setattr(dclient, "_urlopen", fake_urlopen([body], []))
    c = dclient.Client(key=FAKE_KEY, pause=0)
    with pytest.raises(dclient.DartFatal) as e:
        c.get_json("list.json", {"corp_code": "1"}, tmp_path / "y.json")
    assert FAKE_KEY not in str(e.value)
    assert not (tmp_path / "y.json").exists()


def test_other_status_raises_and_no_data_is_cached(monkeypatch, tmp_path):
    bad = json.dumps({"status": "100", "message": "필드의 부적절한 값"}).encode()
    nodata = json.dumps({"status": "013", "message": "조회된 데이타가 없습니다."}).encode()
    monkeypatch.setattr(dclient, "_urlopen", fake_urlopen([bad, nodata], []))
    c = dclient.Client(key=FAKE_KEY, pause=0)
    with pytest.raises(dclient.DartError) as e:
        c.get_json("fnlttSinglAcntAll.json", {"bsns_year": "1"}, tmp_path / "a.json")
    assert FAKE_KEY not in str(e.value) and "crtfc_key=***" in str(e.value)
    assert c.get_json("fnlttSinglAcntAll.json", {"bsns_year": "2"}, tmp_path / "b.json")["status"] == "013"
    assert (tmp_path / "b.json").exists()


def test_zip_endpoint_error_body_not_cached(monkeypatch, tmp_path):
    xml = b'<?xml version="1.0" encoding="UTF-8"?><result><status>014</status><message>file not found</message></result>'
    monkeypatch.setattr(dclient, "_urlopen", fake_urlopen([xml], []))
    c = dclient.Client(key=FAKE_KEY, pause=0)
    with pytest.raises(dclient.DartError):
        c.get_bytes("document.xml", {"rcept_no": "1"}, tmp_path / "d.zip")
    assert not (tmp_path / "d.zip").exists()


# ---------------------------------------------------------------- 응답 해석

def load_fixture():
    return json.loads((FIXTURES / "dart" / "fnltt_samsung_2025_cfs_small.json").read_text(encoding="utf-8"))


def test_parse_amount():
    assert extract.parse_amount("1,234") == (1234, None)
    assert extract.parse_amount("-5") == (-5, None)
    assert extract.parse_amount("") == (None, None)
    assert extract.parse_amount("-") == (None, None)
    assert extract.parse_amount(None) == (None, None)
    v, note = extract.parse_amount("12.5")
    assert v is None and "정수가 아닌" in note


def test_rows_from_fixture():
    obj = load_fixture()
    corp = {"corp_code": "00126380", "stock_code": "005930", "company": "삼성전자"}
    rows, notes = extract.rows_from_fnltt(obj, "CFS", corp, "raw/x.json", {"20260310002820": "20260310"})
    assert len(rows) == len(obj["list"]) and not notes
    a = next(r for r in rows if r["account_id"] == "ifrs-full_Assets")
    assert a["thstrm_amount"] == 566942110000000 and a["frmtrm_amount"] == 514531948000000
    assert a["rcept_dt"] == "20260310" and a["raw_file"] == "raw/x.json"
    assert rows[a["raw_index"]] is a
    assert set(extract.COLUMNS) == set(a)
    assert any(r["account_id"] == extract.NON_STANDARD for r in rows)
    # 공시목록에 없는 접수번호면 날짜를 비우고 메모를 남긴다 (지어내지 않는다)
    rows2, notes2 = extract.rows_from_fnltt(obj, "CFS", corp, "raw/x.json", {})
    assert rows2[0]["rcept_dt"] == "" and notes2


def test_annual_filing_regex():
    rows = [{"corp_code": "1", "report_nm": "[기재정정]사업보고서 (2022.12)", "rcept_no": "20240314001531",
             "rcept_dt": "20240314", "rm": "연"},
            {"corp_code": "1", "report_nm": "사업보고서 (2022.12)", "rcept_no": "20230315001030",
             "rcept_dt": "20230315", "rm": "정연"},
            {"corp_code": "1", "report_nm": "반기보고서 (2022.06)", "rcept_no": "3", "rcept_dt": "3", "rm": ""}]
    out = collect.annual_filings(rows, {"stock_code": "005380", "name": "현대자동차"}, [])
    assert [(f["bsns_year"], f["prefix"]) for f in out] == [("2022", "기재정정"), ("2022", "")]


# ---------------------------------------------------------------- 점검 로직

def mk(sj, aid, nm, cur, prev="", prev2="", detail="-", year="2025", fs="CFS", ord_="1"):
    return {"corp_code": "1", "company": "가", "bsns_year": year, "reprt_code": "11011", "fs_div": fs,
            "rcept_no": f"r{year}", "sj_div": sj, "account_id": aid, "account_nm": nm, "account_detail": detail,
            "thstrm_amount": cur, "frmtrm_amount": prev, "bfefrmtrm_amount": prev2, "ord": ord_}


def base_rows(year="2025", assets=100, liabs=60, equity=40, cash=10, cf_cash=10):
    return [mk("BS", "ifrs-full_Assets", "자산총계", assets, assets, year=year),
            mk("BS", "ifrs-full_Liabilities", "부채총계", liabs, liabs, year=year),
            mk("BS", "ifrs-full_Equity", "자본총계", equity, equity, year=year),
            mk("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", cash, cash, year=year),
            mk("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "기말현금", cf_cash, cf_cash, year=year),
            mk("CIS", "ifrs-full_ProfitLoss", "당기순이익", 5, 4, year=year),
            mk("SCE", "ifrs-full_Equity", "기말자본", 40, 30, year=year)]


def by(results, check):
    return [r for r in results if r["check"] == check]


def test_checks_pass_and_fail():
    ok = checks.run_all(base_rows())
    assert {r["status"] for r in by(ok, "bs_identity")} == {"통과"}
    assert {r["status"] for r in by(ok, "cf_cash")} == {"통과"}
    assert by(ok, "statements")[0]["status"] == "통과"
    bad = checks.run_all(base_rows(assets=101, cf_cash=11))
    assert by(bad, "bs_identity")[0]["status"] == "실패" and by(bad, "bs_identity")[0]["diff"] == 1
    assert by(bad, "cf_cash")[0]["status"] == "실패"


def test_checks_missing_statement_and_name_fallback():
    rows = [r for r in base_rows() if r["sj_div"] not in ("CF", "SCE")]
    rows[0]["account_id"] = extract.NON_STANDARD     # 자산총계를 이름으로 찾아야 한다
    res = checks.run_all(rows)
    st = by(res, "statements")[0]
    assert st["status"] == "실패" and "CF" in st["detail"] and "SCE" in st["detail"]
    bi = by(res, "bs_identity")[0]
    assert bi["status"] == "통과" and "이름" in bi["detail"]
    assert by(res, "cf_cash")[0]["status"] == "판정불가"


def test_duplicate_rows():
    rows = base_rows() + [mk("BS", extract.NON_STANDARD, "금융업채권", 1), mk("BS", extract.NON_STANDARD, "금융업채권", 2)]
    d = by(checks.run_all(rows), "duplicate_row")
    assert len(d) == 1 and d[0]["status"] == "실패"


def test_prior_year_kinds():
    prev = base_rows("2024") + [mk("CF", "x_A", "가", 7, year="2024"), mk("CF", "x_B", "나", 8, year="2024"),
                                mk("CF", "x_C", "다", 0, year="2024"), mk("CF", "x_D", "옛이름", 9, year="2024")]
    cur = base_rows("2025") + [mk("CF", "x_A", "가", 1, prev=-7), mk("CF", "x_B", "나", 1, prev=80),
                               mk("CF", "x_C", "다", 1, prev=""), mk("CF", "x_D", "새이름", 1, prev=9)]
    for r in cur[:7]:
        r["frmtrm_amount"] = next(p["thstrm_amount"] for p in prev if p["account_id"] == r["account_id"]
                                  and p["sj_div"] == r["sj_div"])
    res = checks.run_all(prev + cur)
    diffs = {r["detail"].split()[1]: r["status"] for r in by(res, "prior_year_diff")}
    assert diffs == {"x_A": "부호반대", "x_B": "금액다름", "x_C": "빈칸과0"}
    summary = by(res, "prior_year")[0]
    assert summary["status"] == "차이" and "이름바뀜 1" in summary["detail"]


def test_inventory_counts():
    rows = base_rows()
    rows2 = [dict(r, company="나", corp_code="2") for r in base_rows()[:3]]
    inv = inventory.build(rows + rows2)
    a = next(i for i in inv if i["account_id"] == "ifrs-full_Assets")
    assert a["n_companies"] == 2 and a["companies"] == "가;나"
    s = inventory.summary(rows + rows2, inv)
    assert s["BS"]["all"] == 3 and s["BS"]["one"] == 1


# ---------------------------------------------------------------- 원문 추출기

SMALL_DOC = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY><SECTION-2><TITLE>1. 요약재무정보</TITLE><P>연결 재무상태표 는 아래와 같다</P></SECTION-2>
<SECTION-2><TITLE>2. 연결재무제표</TITLE>
<TABLE-GROUP><TITLE>2-1. 연결 재무상태표</TITLE>
<TABLE><TBODY><TR><TE>연결 재무상태표</TE></TR><TR><TE>(단위 : 백만원)</TE></TR></TBODY></TABLE>
<TABLE><THEAD><TR><TH>　</TH><TH>제 2 기</TH><TH>제 1 기</TH></TR></THEAD><TBODY>
<TR><TE>자산</TE><TE>　</TE><TE>　</TE></TR>
<TR><TE>　현금및현금성자산 (주4)</TE><TE>1,000</TE><TE>900</TE></TR>
<TR><TE>자 산 총 계</TE><TE>1,000</TE><TE>900</TE></TR>
<TR><TE>부채총계</TE><TE>(200)</TE><TE>-</TE></TR>
<TR><TE>자본총계</TE><TE>1,200</TE><TE>900</TE></TR>
</TBODY></TABLE></TABLE-GROUP></SECTION-2></BODY></DOCUMENT>"""


def test_document_extract_small():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("/123.xml", SMALL_DOC.encode("cp949"))      # 선언은 utf-8, 실제로는 cp949 (오래된 문서처럼)
    files = document.read_zip(data.getvalue())
    assert files[0][0] == "123.xml" and files[0][2] == "cp949"
    text, _ = document.main_text(files, "123")
    res, err = document.extract_bs(text)
    assert err is None and res["unit_text"] == "백만원"
    labels = [r["name_norm"] for r in res["rows"]]
    assert labels == ["자산", "현금및현금성자산", "자산총계", "부채총계", "자본총계"]
    debt = res["rows"][3]
    assert debt["values"] == [-200_000_000, None]
    api_rows = [{"account_id": "ifrs-full_CashAndCashEquivalents", "account_nm": "현금및현금성자산",
                 "thstrm_amount": "1000000000", "frmtrm_amount": "900000000", "bfefrmtrm_amount": ""},
                {"account_id": "ifrs-full_Assets", "account_nm": "자산총계", "thstrm_amount": "1000000000",
                 "frmtrm_amount": "1", "bfefrmtrm_amount": ""}]
    cmp, s = document.compare_with_api(res["rows"], api_rows)
    assert s["equal"] == 1 and s["differ"] == 1 and s["doc_unmatched"] == 2


def test_document_amounts_and_norm():
    assert document.parse_amount("△1,234") == -1234
    assert document.parse_amount(" 　") is None
    with pytest.raises(ValueError):
        document.parse_amount("abc")
    assert document.norm("Ⅰ. 유 동 자 산") == "유동자산"
    assert document.norm("　　매출채권 (주4,5,7,29)") == "매출채권"


# ---------------------------------------------------------------- 회귀

STATEMENTS = ROOT / "data" / "dart" / "extracted" / "statements.csv"
KNOWN = [  # (회사, 연도, 구분, 재무제표, account_id, 당기, 전기)
    ("삼성전자", "2025", "CFS", "BS", "ifrs-full_Assets", 566942110000000, 514531948000000),
    ("삼성전자", "2025", "CFS", "IS", "ifrs-full_Revenue", 333605938000000, 300870903000000),
    ("삼성전자", "2025", "CFS", "CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", 57856378000000, 53705579000000),
    ("SK하이닉스", "2025", "CFS", "CIS", "dart_OperatingIncomeLoss", 47206319000000, 23467319000000),
    ("현대자동차", "2024", "CFS", "BS", "ifrs-full_Equity", 120275933000000, 101809440000000),
    ("LG에너지솔루션", "2023", "OFS", "BS", "ifrs-full_Liabilities", 6944445000000, 6408238000000),
    ("NAVER", "2025", "CFS", "CIS", "ifrs-full_Revenue", 12035007218975, 10737719264647),
]


@pytest.fixture(scope="module")
def stored():
    if not STATEMENTS.exists():
        pytest.skip("data/dart/extracted/statements.csv 없음")
    return collect.read_csv(STATEMENTS)


@pytest.mark.parametrize("company,year,fs,sj,aid,cur,prev", KNOWN)
def test_regression_known_values(stored, company, year, fs, sj, aid, cur, prev):
    hits = [r for r in stored if (r["company"], r["bsns_year"], r["fs_div"], r["sj_div"], r["account_id"])
            == (company, year, fs, sj, aid)]
    assert len(hits) == 1
    assert extract.amount(hits[0], "thstrm_amount") == cur
    assert extract.amount(hits[0], "frmtrm_amount") == prev


def test_regression_shape_and_identity(stored):
    keys = {(r["company"], r["bsns_year"], r["fs_div"]) for r in stored}
    assert len(keys) == 30                              # 5개사 x 3년 x 연결·별도
    assert len(stored) == 5589
    res = checks.run_all(stored)
    assert {r["status"] for r in by(res, "bs_identity")} == {"통과"}
    assert {r["status"] for r in by(res, "cf_cash")} == {"통과"}
    for r in stored[:50]:                              # 모든 행은 raw 파일로 거슬러 올라간다
        raw = json.loads((ROOT / r["raw_file"]).read_text(encoding="utf-8"))
        src = raw["list"][int(r["raw_index"])]
        assert src["account_nm"] == r["account_nm"] and src["rcept_no"] == r["rcept_no"]


def test_no_key_in_committed_dart_files():
    pat = re.compile(r"crtfc_key=(?!\*\*\*)[0-9A-Za-z]{8,}")
    key = os.environ.get("DART_API_KEY", "").strip()
    for p in [*(ROOT / "data" / "dart").rglob("*.json"), *(ROOT / "data" / "dart").rglob("*.csv"),
              *(ROOT / "data" / "dart").rglob("*.md"), *(ROOT / "dart").rglob("*.py")]:
        if "_large" in p.parts:
            continue
        text = p.read_text(encoding="utf-8")
        assert not pat.search(text), p
        if key:
            assert key not in text, p
