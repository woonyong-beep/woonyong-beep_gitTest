"""dart/standardize.py 시험 (손익·포괄손익 표준화, 엔진의 부호 나무·공식·귀속·check_only·flip·주당 노드). 네트워크 없이 돈다.

- 손으로 만든 작은 나무: 부호(sign), 공식 노드, 귀속 항등식, check_only, flip, 주당 노드 제외, 연도별 매핑 행
- 매핑 완전성: statements.csv 의 IS·CIS 줄마다 매핑 행이 정확히 하나 (쓰이지 않는 행 없음)
- 대사: 실제 30개 재무제표 × 3기간의 점검이 모두 통과하거나 알려진 발견으로 적혀 있다
- 회귀: as-reported 줄과 손으로 맞춰 본 표준화 값
- 디스크의 bs.csv·pl.csv 가 지금 코드로 다시 만든 것과 같다 (BS 출력이 바뀌지 않았음)
"""

import csv
import io

import pytest

from dart import collect, paths, standardize as S


# ---------------------------------------------------------------- 작은 나무

def signed_chart():
    # R = +A - B + C ;  B = B1 + B2 ;  F = A - B (공식) ;  P (주당) ;  O = O1 + O2 (귀속 루트)
    return S.Chart([
        {"std_id": "R", "parent": "", "sign": "", "kind": "total", "name_ko": "합계"},
        {"std_id": "A", "parent": "R", "sign": "1", "kind": "item", "name_ko": "수익"},
        {"std_id": "B", "parent": "R", "sign": "-1", "kind": "group", "name_ko": "비용"},
        {"std_id": "B1", "parent": "B", "sign": "1", "kind": "item", "name_ko": "비용1"},
        {"std_id": "B2", "parent": "B", "sign": "1", "kind": "item", "name_ko": "비용2"},
        {"std_id": "C", "parent": "R", "sign": "1", "kind": "item", "name_ko": "기타"},
        {"std_id": "F", "parent": "", "sign": "", "kind": "formula", "formula": "A-B", "name_ko": "공식"},
        {"std_id": "P", "parent": "", "sign": "", "kind": "per_share", "name_ko": "주당"},
        {"std_id": "O", "parent": "", "sign": "", "kind": "attribution", "name_ko": "지배"},
        {"std_id": "O1", "parent": "O", "sign": "1", "kind": "item", "name_ko": "지배1"},
        {"std_id": "O2", "parent": "O", "sign": "1", "kind": "item", "name_ko": "지배2"},
        {"std_id": "N", "parent": "", "sign": "", "kind": "attribution", "name_ko": "비지배"},
    ])


def test_signed_rollup():
    res = S.rollup(signed_chart(), [("A", 100, 1), ("B1", 30, 2), ("B2", 20, 3), ("C", -5, 4)])
    assert res["B"]["rollup"] == (50, [2, 3])          # 묶음 안에서는 더한다 (비용은 양수로 저장)
    assert res["R"]["rollup"] == (100 - 50 - 5, [1, 2, 3, 4])
    assert S._fmt_parts(signed_chart(), res, "R") == "A=100;-B=50;C=-5"


def test_signed_rollup_uses_reported_child_and_checks_parent():
    ch = signed_chart()
    res = S.rollup(ch, [("A", 100, 1), ("B", 50, 2), ("B1", 30, 3), ("B2", 20, 4), ("R", 50, 5)])
    assert res["R"]["rollup"] == (50, [1, 2])           # 자식 B 의 보고값을 쓴다 (B1, B2 를 다시 빼지 않는다)
    rows = S._checks(ch, res, {}, "OFS", S.PL)
    by = {c["std_id"]: c for c in rows if c["check"] == "보고값=하위합계"}
    assert by["R"]["status"] == "pass" and by["B"]["status"] == "pass"


def test_formula_node():
    ch = signed_chart()
    res = S.rollup(ch, [("A", 100, 1), ("B1", 30, 2), ("B2", 20, 3), ("F", 51, 9)])
    assert res["F"]["rollup"] == (50, [1, 2, 3])
    assert res["F"]["reported"] == (51, [9])
    assert "F" not in res["R"]["rollup"][1] and res["R"]["rollup"][0] == 50   # 공식 노드는 합산 나무 밖
    rows = [c for c in S._checks(ch, res, {}, "OFS", S.PL) if c["check"] == "보고값=공식"]
    assert len(rows) == 1 and rows[0]["status"] == "fail" and rows[0]["diff"] == 1
    assert rows[0]["parts"] == "A=100;-B=50"
    # 피연산자가 하나라도 없으면 공식 값도 없다
    res2 = S.rollup(ch, [("A", 100, 1)])
    assert "F" not in res2
    res3 = S.rollup(ch, [("A", 100, 1), ("F", 7, 2)])
    assert res3["F"] == {"reported": (7, [2]), "rollup": None}
    assert [c["status"] for c in S._checks(ch, res3, {}, "OFS", S.PL) if c["check"] == "보고값=공식"] == ["missing"]


def test_parse_formula():
    assert S.parse_formula("PL.REV-PL.COGS") == [("PL.REV", 1), ("PL.COGS", -1)]
    assert S.parse_formula("PL.NI+PL.OCI") == [("PL.NI", 1), ("PL.OCI", 1)]
    with pytest.raises(ValueError):
        S.parse_formula("")


def test_chart_rejects_bad_formula_per_share_and_sign():
    base = [{"std_id": "A", "parent": "", "kind": "item", "name_ko": ""}]
    with pytest.raises(ValueError):       # 공식에 주당 노드
        S.Chart(base + [{"std_id": "P", "parent": "", "kind": "per_share", "name_ko": ""},
                        {"std_id": "F", "parent": "", "kind": "formula", "formula": "A+P", "name_ko": ""}])
    with pytest.raises(ValueError):       # 공식에 없는 노드
        S.Chart(base + [{"std_id": "F", "parent": "", "kind": "formula", "formula": "A-Q", "name_ko": ""}])
    with pytest.raises(ValueError):       # 주당 노드에 부모
        S.Chart(base + [{"std_id": "P", "parent": "A", "kind": "per_share", "name_ko": ""}])
    with pytest.raises(ValueError):       # 공식 노드에 자식
        S.Chart(base + [{"std_id": "F", "parent": "", "kind": "formula", "formula": "A", "name_ko": ""},
                        {"std_id": "G", "parent": "F", "kind": "item", "name_ko": ""}])
    with pytest.raises(ValueError):
        S.Chart([{"std_id": "A", "parent": "", "sign": "2", "name_ko": ""}])


def test_per_share_carried_not_summed():
    ch = signed_chart()
    res = S.rollup(ch, [("A", 100, 1), ("P", 1234, 7)])
    assert res["P"] == {"reported": (1234, [7]), "rollup": None}
    assert res["R"]["rollup"] == (100, [1])
    assert S._per_share_leaks(ch, res, "c", "y", "f", "p") == []


def tiny_spec(**kw):
    d = dict(name="T", title="시험", sj_divs=("IS", "CIS"), key_fields=S.PL_KEY_FIELDS, columns=S.PL_COLUMNS, flow=True,
             required=[], required_cfs=[],
             identities=[("O+N=R", "R", [("O", 1), ("N", 1)], "value", "cfs")], restatement=False)
    d.update(kw)
    return S.Spec(**d)


def test_attribution_identity():
    ch = signed_chart()
    res = S.rollup(ch, [("A", 100, 1), ("O1", 60, 2), ("O2", 10, 3), ("N", 30, 4)])
    rows = {c["check"]: c for c in S._checks(ch, res, {}, "CFS", tiny_spec())}
    assert rows["O+N=R"]["status"] == "pass" and rows["O+N=R"]["computed"] == 100
    res = S.rollup(ch, [("A", 100, 1), ("O1", 60, 2), ("N", 30, 4)])
    rows = {c["check"]: c for c in S._checks(ch, res, {}, "CFS", tiny_spec())}
    assert rows["O+N=R"]["status"] == "fail" and rows["O+N=R"]["diff"] == 10
    # 연결은 필수: 귀속 값이 없으면 missing, 별도는 점검 행이 없다
    res = S.rollup(ch, [("A", 100, 1)])
    assert [c["status"] for c in S._checks(ch, res, {}, "CFS", tiny_spec()) if c["check"] == "O+N=R"] == ["missing"]
    assert [c for c in S._checks(ch, res, {}, "OFS", tiny_spec()) if c["check"] == "O+N=R"] == []


def _row(sj, ord_, aid, nm, cur, prior="", year="2025", idx=0, fs="CFS"):
    return {"corp_code": "X", "stock_code": "000000", "company": "가상", "rcept_no": "1", "rcept_dt": "20260301",
            "bsns_year": year, "reprt_code": "11011", "fs_div": fs, "sj_div": sj, "sj_nm": "", "ord": str(ord_),
            "account_id": aid, "account_nm": nm, "account_detail": "-", "thstrm_nm": "당기", "thstrm_amount": str(cur),
            "thstrm_add_amount": "", "frmtrm_nm": "전기", "frmtrm_amount": str(prior), "frmtrm_add_amount": "",
            "bfefrmtrm_nm": "", "bfefrmtrm_amount": "", "currency": "KRW", "raw_file": f"raw/{year}.json",
            "raw_index": str(idx)}


def _m(sj, aid, nm, sid, role="value", flip="1", year=""):
    return {"corp_code": "X", "fs_div": "CFS", "sj_div": sj, "bsns_year": year, "account_id": aid, "account_nm": nm,
            "occurrence": "1", "std_id": sid, "role": role, "flip": flip}


def _mapping(ms):
    return {tuple(m[f] for f in S.PL_KEY_FIELDS): m for m in ms}


def test_is_cis_merge_check_only_and_flip():
    ch = signed_chart()
    rows = [_row("IS", 1, "a", "수익", 100, idx=0), _row("IS", 2, "b1", "비용1", 30, idx=1),
            _row("IS", 3, "b2", "비용2", -20, idx=2),                  # 비용을 음수로 공시 -> flip -1
            _row("IS", 4, "r", "합계", 50, idx=3),
            _row("CIS", 1, "r", "합계", 50, idx=4),                    # CIS 맨 위에 다시 적은 합계 -> check_only
            _row("CIS", 2, "p", "주당", 777, idx=5)]
    mapping = _mapping([_m("IS", "a", "수익", "A"), _m("IS", "b1", "비용1", "B1"),
                        _m("IS", "b2", "비용2", "B2", flip="-1"), _m("IS", "r", "합계", "R"),
                        _m("CIS", "r", "합계", "R", role="check_only"), _m("CIS", "p", "주당", "P")])
    out, checks, problems = S.standardize(rows, ch, mapping, acc_mt={"X": "12"}, spec=tiny_spec())
    assert problems == []
    cur = {(r["std_id"], r["source"]): r for r in out if r["period"] == "current"}
    assert cur[("B2", "reported")]["amount"] == 20
    assert cur[("R", "reported")]["amount"] == 50 and cur[("R", "reported")]["raw_index"] == "3"   # CIS 줄은 더하지 않음
    assert cur[("R", "rollup")]["amount"] == 50
    assert cur[("P", "reported")]["unit"] == "KRW/주" and cur[("R", "reported")]["unit"] == "KRW"
    assert cur[("R", "reported")]["period_start"] == "2025-01-01" and cur[("R", "reported")]["period_end"] == "2025-12-31"
    assert len({r["raw_file"] for r in out}) == 1                     # IS 와 CIS 가 한 재무제표
    co = [c for c in checks if c["check"] == "check_only=노드값" and c["period"] == "current"]
    assert len(co) == 1 and co[0]["status"] == "pass" and co[0]["raw_index"] == "4"
    sub = {c["std_id"]: c["status"] for c in checks if c["check"] == "보고값=하위합계" and c["period"] == "current"}
    assert sub == {"R": "pass"}
    # flip 이 없으면 대사가 깨진다 (flip 은 산술 근거가 있을 때만 쓴다)
    mapping2 = dict(mapping)
    mapping2[("X", "CFS", "IS", "", "b2", "비용2", "1")] = _m("IS", "b2", "비용2", "B2")
    _, checks2, _ = S.standardize(rows, ch, mapping2, acc_mt={"X": "12"}, spec=tiny_spec())
    assert [c["diff"] for c in checks2 if c["check"] == "보고값=하위합계" and c["period"] == "current"] == [-40]
    assert [c["status"] for c in checks2 if c["check"] == "check_only=노드값" and c["period"] == "current"] == ["pass"]


def test_check_only_mismatch_is_reported():
    ch = signed_chart()
    rows = [_row("IS", 1, "a", "수익", 100, idx=0), _row("CIS", 1, "r", "합계", 99, idx=1)]
    mapping = _mapping([_m("IS", "a", "수익", "A"), _m("CIS", "r", "합계", "R", role="check_only")])
    _, checks, _ = S.standardize(rows, ch, mapping, acc_mt={"X": "12"}, spec=tiny_spec())
    co = [c for c in checks if c["check"] == "check_only=노드값" and c["period"] == "current"][0]
    assert co["status"] == "fail" and co["diff"] == -1 and co["computed"] == 100     # 노드 값은 합계(rollup) 100


def test_year_specific_mapping_rows(tmp_path):
    ch = signed_chart()
    rows = [_row("IS", 1, "a", "수익", 100, year="2024", idx=0), _row("IS", 1, "a", "수익", -100, year="2025", idx=0)]
    mapping = _mapping([_m("IS", "a", "수익", "A", year="2024"), _m("IS", "a", "수익", "A", flip="-1", year="2025")])
    out, _, problems = S.standardize(rows, ch, mapping, acc_mt={"X": "12"}, spec=tiny_spec())
    assert problems == []
    got = {r["bsns_year"]: r["amount"] for r in out if r["std_id"] == "A" and r["period"] == "current"}
    assert got == {"2024": 100, "2025": 100}
    # 연도 빈칸 행과 연도 행이 같은 줄을 함께 가리키면 오류
    p = tmp_path / "m.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=S.PL_MAPPING_COLUMNS, lineterminator="\n")
        w.writeheader()
        for y in ("", "2025"):
            w.writerow({**{c: "" for c in S.PL_MAPPING_COLUMNS}, **_m("IS", "a", "수익", "A", year=y)})
    with pytest.raises(ValueError):
        S.load_mapping(p, S.PL_KEY_FIELDS)


def test_period_start():
    assert S.period_start("2025", "12", 0) == "2025-01-01"
    assert S.period_start("2025", "12", 2) == "2023-01-01"
    assert S.period_start("2025", "3", 0) == "2024-04-01"


# ---------------------------------------------------------------- 실제 데이터

@pytest.fixture(scope="module")
def real():
    rows = collect.read_csv(paths.STATEMENTS_CSV)
    chart = S.load_chart(S.PL_CHART_CSV)
    mapping = S.load_mapping(S.PL_MAPPING_CSV, S.PL_KEY_FIELDS)
    pl, checks, problems = S.standardize(rows, chart, mapping, spec=S.PL)
    return {"rows": rows, "chart": chart, "mapping": mapping, "pl": pl, "checks": checks, "problems": problems}


def test_every_is_cis_line_has_exactly_one_mapping_row(real):
    counts = {k: 0 for k in real["mapping"]}
    n_lines = 0
    for _, srows in S.statements(real["rows"], ("IS", "CIS")).items():
        for r, occ in S.with_occurrence(srows):
            n_lines += 1
            hits = [k for k in (S.mapping_key(r, occ, S.PL_KEY_FIELDS), S.mapping_key(r, occ, S.PL_KEY_FIELDS, ""))
                    if k in real["mapping"]]
            assert len(hits) == 1, f"매핑 행 {len(hits)}개: {r['company']} {r['bsns_year']} {r['account_nm']}"
            counts[hits[0]] += 1
    assert n_lines == 809 == sum(1 for r in real["rows"] if r["sj_div"] in ("IS", "CIS"))
    assert [k for k, n in counts.items() if n == 0] == []
    ms = real["mapping"].values()
    assert all(m["std_id"] for m in ms)
    assert S.check_mapping(real["chart"], real["mapping"]) == []
    assert all(m["method"] in ("xbrl_id", "name", "position", "manual") for m in ms)
    assert all(m["confidence"] in ("high", "medium", "low") for m in ms)
    assert all(m["review"] in ("ok", "needs_lead") for m in ms)
    assert all(m["role"] in ("value", "check_only") for m in ms)
    assert all(m["flip"] in ("1", "-1") for m in ms)
    assert all(m["note"] for m in ms if m["flip"] == "-1")             # flip 에는 근거를 적는다
    # check_only 는 두 재무제표 회사의 CIS 당기순이익뿐
    co = {(m["company"], m["sj_div"], m["account_id"]) for m in ms if m["role"] == "check_only"}
    assert co == {(c, "CIS", "ifrs-full_ProfitLoss") for c in ("삼성전자", "현대자동차", "LG에너지솔루션")}


def test_all_reconciliation_checks_pass_or_are_known(real):
    assert real["problems"] == []
    assert S.unexplained_failures(real["checks"]) == []
    fails = [(c["corp_code"], c["bsns_year"], c["fs_div"], c["period"], c["check"], c["std_id"])
             for c in real["checks"] if c["status"] == "fail"]
    assert set(fails) == set(S.KNOWN_FINDINGS)
    assert [c for c in real["checks"] if c["status"] == "missing"] == []
    restate = {c for _, _, c in S.RESTATEMENT_PAIRS}
    assert {c["status"] for c in real["checks"] if c["status"] == "one_side"} <= {"one_side"}
    assert all(c["check"] in restate for c in real["checks"] if c["status"] == "one_side")

    def n(check, sid=None):
        return sum(1 for c in real["checks"] if c["check"] == check and (sid is None or c["std_id"] == sid))
    for sid in ("PL.OP", "PL.PBT", "PL.NI", "PL.OCI"):      # 30개 재무제표 × 3기간
        assert n("보고값=하위합계", sid) == 90
    assert n("보고값=공식", "PL.CI") == 90 and n("보고값=공식", "PL.GP") == 72    # NAVER 는 매출총이익 없음
    assert n("PL.NIO+PL.NIN=PL.NI") == 45 and n("PL.CIO+PL.CIN=PL.CI") == 45      # 연결만
    assert n("check_only=노드값") == 54                                            # 3개사 × 연결·별도 × 3년 × 3기간
    # 재작성 비교: 금액 차이는 하나도 없다
    assert [c for c in real["checks"] if c["check"] in restate and c["status"] == "fail"] == []


def test_per_share_lines_never_summed(real):
    eps_refs = {(r["raw_file"], i) for r in real["pl"] if r["kind"] == "per_share" for i in r["raw_index"].split(";")}
    assert eps_refs and all(r["unit"] == "KRW/주" for r in real["pl"] if r["kind"] == "per_share")
    assert all(r["source"] == "reported" for r in real["pl"] if r["kind"] == "per_share")
    for r in real["pl"]:
        if r["kind"] != "per_share":
            assert not ({(r["raw_file"], i) for i in r["raw_index"].split(";")} & eps_refs), r


def _get(real, corp, year, fs, period, sid, source):
    hits = [r for r in real["pl"] if r["corp_code"] == corp and r["bsns_year"] == year and r["fs_div"] == fs
            and r["period"] == period and r["std_id"] == sid and r["source"] == source]
    assert len(hits) <= 1
    return hits[0]["amount"] if hits else None


SAM, HMC, SKH, NAVER, LGES = "00126380", "00164742", "00164779", "00266961", "01515323"


def test_regression_values(real):
    # 삼성 2025 연결: 매출 333,605,938 백만, 매출원가 202,235,513 + 판관비 87,769,374 = 영업비용(합계) 290,004,887
    assert _get(real, SAM, "2025", "CFS", "current", "PL.REV", "reported") == 333_605_938_000_000
    assert _get(real, SAM, "2025", "CFS", "current", "PL.OPEX", "reported") is None
    assert _get(real, SAM, "2025", "CFS", "current", "PL.OPEX", "rollup") == 290_004_887_000_000
    assert _get(real, SAM, "2025", "CFS", "current", "PL.OP", "rollup") == 43_601_051_000_000
    assert _get(real, SAM, "2025", "CFS", "current", "PL.GP", "formula") == 131_370_425_000_000
    # 삼성 2024: 계속영업이익 줄 없음 -> PBT 37,529,734 - 법인세 3,078,383 합계로만
    assert _get(real, SAM, "2024", "CFS", "current", "PL.CONT", "reported") is None
    assert _get(real, SAM, "2024", "CFS", "current", "PL.CONT", "rollup") == 34_451_351_000_000
    # 법인세수익(음수) 은 그대로: 삼성 2023 연결 -4,480,835
    assert _get(real, SAM, "2023", "CFS", "current", "PL.TAX", "reported") == -4_480_835_000_000
    # NAVER 2025 연결: 영업비용 한 줄이 PL.OPEX 보고값, 금융수익 = 금융수익 584,121,145,195 + 이자수익 222,501,659,173
    assert _get(real, NAVER, "2025", "CFS", "current", "PL.OPEX", "reported") == 9_826_868_830_255
    assert _get(real, NAVER, "2025", "CFS", "current", "PL.FININC", "rollup") == 806_622_804_368
    assert _get(real, NAVER, "2025", "CFS", "current", "PL.GP", "formula") is None
    # NAVER 재분류되는 지분법자본변동: 공시 533,355,458,319 를 flip
    assert _get(real, NAVER, "2025", "CFS", "current", "PL.OCI.R.EQM", "reported") == -533_355_458_319
    # LG 연결 법인세효과(재분류됨): 2023 은 공시 그대로 12,686, 2024 는 공시 -12,512 를 flip
    assert _get(real, LGES, "2023", "CFS", "current", "PL.OCI.R.TAX", "reported") == 12_686_000_000
    assert _get(real, LGES, "2024", "CFS", "current", "PL.OCI.R.TAX", "reported") == 12_512_000_000
    assert _get(real, LGES, "2024", "CFS", "prior", "PL.OCI.R.TAX", "reported") == 12_686_000_000
    assert _get(real, LGES, "2023", "CFS", "current", "PL.OOI", "reported") == 676_874_000_000
    # 현대 2025 연결 재분류 안 되는 지분법: 지분법자본변동(코드 없음) -126,680 + 지분법이익잉여금 -311,608
    assert _get(real, HMC, "2025", "CFS", "current", "PL.OCI.N.EQM", "reported") == -438_288_000_000
    assert _get(real, HMC, "2023", "CFS", "current", "PL.EQM", "reported") == 2_470_933_000_000
    assert _get(real, HMC, "2023", "CFS", "current", "PL.DISC", "reported") == -719_721_000_000
    assert _get(real, HMC, "2023", "CFS", "current", "PL.EPS.B", "reported") == 45_703
    # SK하이닉스 2023: OCI 소계 줄 없이 구성 항목만 -> OCI.R 은 합계로만: -22,414 + 132,561 + 7,848 = 117,995
    # (2025 보고서는 R 소계 줄이 있고 전전기 열이 117,995 로 같다)
    assert _get(real, SKH, "2023", "CFS", "current", "PL.OCI.R", "reported") is None
    assert _get(real, SKH, "2023", "CFS", "current", "PL.OCI.R", "rollup") == 117_995_000_000
    assert _get(real, SKH, "2025", "CFS", "prior2", "PL.OCI.R", "reported") == 117_995_000_000
    # 영업외손익은 보고 줄이 없고 합계로만: 2,261,801 - 6,093,167 + 623,867 - 735,065 + 15,061 = -3,927,503 (= PBT - OP)
    assert _get(real, SKH, "2023", "CFS", "current", "PL.NONOP", "reported") is None
    assert _get(real, SKH, "2023", "CFS", "current", "PL.NONOP", "rollup") == -3_927_503_000_000


def test_provenance_points_to_raw_rows(real):
    rows_by = {(r["raw_file"], r["raw_index"]): r for r in real["rows"]}
    hits = [r for r in real["pl"] if r["corp_code"] == NAVER and r["bsns_year"] == "2025" and r["fs_div"] == "CFS"
            and r["period"] == "current" and r["std_id"] == "PL.FININC"]
    src = [rows_by[(hits[0]["raw_file"], i)] for i in hits[0]["raw_index"].split(";")]
    assert sorted(s["account_nm"] for s in src) == ["금융수익", "이자수익"]
    assert sum(int(s["thstrm_amount"]) for s in src) == hits[0]["amount"]


def _as_csv(columns, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


@pytest.mark.parametrize("spec", [S.BS, S.PL], ids=["BS", "PL"])
def test_outputs_on_disk_are_current(spec):
    rows = collect.read_csv(paths.STATEMENTS_CSV)
    chart = S.load_chart(spec.chart_csv)
    mapping = S.load_mapping(spec.mapping_csv, spec.key_fields)
    out, checks, _ = S.standardize(rows, chart, mapping, spec=spec)
    assert spec.out_csv.read_text(encoding="utf-8") == _as_csv(spec.columns, out)
    assert spec.checks_csv.read_text(encoding="utf-8") == _as_csv(S.CHECK_COLUMNS, checks)
