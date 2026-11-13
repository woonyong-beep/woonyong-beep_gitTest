"""dart/standardize.py 시험 (재무상태표 표준화). 네트워크 없이 돈다.

- 합계(roll-up): 손으로 만든 작은 트리 (보고값과 합계가 같은 경우, 다른 경우, 값이 없으면 노드가 없는 경우)
- 매핑 완전성: statements.csv 의 BS 줄마다 매핑 행이 정확히 하나
- 대사: 실제 30개 재무제표 × 3기간의 점검이 모두 원 단위로 통과
- 회귀: 잘 알려진 표준화 값
"""

import pytest

from dart import collect, paths, standardize as S


def tiny_chart():
    # R ── X ── X1
    #   │    └─ X2
    #   ├─ Y
    #   └─ Z ── Z1
    return S.Chart([
        {"std_id": "R", "parent": "", "name_ko": "합계"},
        {"std_id": "X", "parent": "R", "name_ko": "엑스"},
        {"std_id": "X1", "parent": "X", "name_ko": "엑스1"},
        {"std_id": "X2", "parent": "X", "name_ko": "엑스2"},
        {"std_id": "Y", "parent": "R", "name_ko": "와이"},
        {"std_id": "Z", "parent": "R", "name_ko": "제트"},
        {"std_id": "Z1", "parent": "Z", "name_ko": "제트1"},
    ])


# ---------------------------------------------------------------- 합계

def test_rollup_sums_children_and_records_provenance():
    res = S.rollup(tiny_chart(), [("X1", 3, 10), ("X2", 4, 11), ("Y", 5, 12)])
    assert res["X"] == {"reported": None, "rollup": (7, [10, 11])}
    assert res["R"]["rollup"] == (12, [10, 11, 12])
    assert res["R"]["reported"] is None
    assert res["X1"] == {"reported": (3, [10]), "rollup": None}


def test_rollup_absent_when_no_value():
    res = S.rollup(tiny_chart(), [("X1", 3, 1)])
    assert "Y" not in res and "Z" not in res and "Z1" not in res   # 보고값도 하위 값도 없으면 없다 (0 이 아님)
    assert "X2" not in res
    assert res["X"]["rollup"] == (3, [1])
    assert S.rollup(tiny_chart(), []) == {}


def test_rollup_zero_is_a_value():
    res = S.rollup(tiny_chart(), [("Z1", 0, 5)])
    assert res["Z"]["rollup"] == (0, [5])
    assert res["R"]["rollup"] == (0, [5])


def test_rollup_reported_and_children_agree():
    res = S.rollup(tiny_chart(), [("X", 7, 1), ("X1", 3, 2), ("X2", 4, 3), ("R", 7, 0)])
    assert res["X"]["reported"] == (7, [1]) and res["X"]["rollup"] == (7, [2, 3])
    # 부모 합계는 자식의 보고값을 쓴다 (보고값과 하위 합계를 둘 다 더하지 않는다)
    assert res["R"]["rollup"] == (7, [1])
    checks = S._checks(tiny_chart(), res, {}, "OFS")
    by = {c["std_id"]: c for c in checks if c["check"] == "보고값=하위합계" and c["std_id"] in ("X", "R")}
    assert by["X"]["status"] == "pass" and by["R"]["status"] == "pass"


def test_rollup_reported_and_children_disagree_is_reported():
    res = S.rollup(tiny_chart(), [("X", 8, 1), ("X1", 3, 2), ("X2", 4, 3)])
    checks = S._checks(tiny_chart(), res, {}, "OFS")
    x = [c for c in checks if c["std_id"] == "X"][0]
    assert x["status"] == "fail" and x["diff"] == 1 and x["raw_index"] == "2;3"
    assert S.value(res["X"]) == 8                               # 노드 값은 보고값


def test_rollup_several_lines_one_node():
    res = S.rollup(tiny_chart(), [("Y", 5, 1), ("Y", -2, 2)])
    assert res["Y"]["reported"] == (3, [1, 2])


def test_rollup_unknown_node_raises():
    with pytest.raises(KeyError):
        S.rollup(tiny_chart(), [("Q", 1, 0)])


def test_chart_rejects_missing_parent_and_cycle():
    with pytest.raises(ValueError):
        S.Chart([{"std_id": "A", "parent": "B", "name_ko": ""}])
    with pytest.raises(ValueError):
        S.Chart([{"std_id": "A", "parent": "B", "name_ko": ""}, {"std_id": "B", "parent": "A", "name_ko": ""}])


def test_occurrence_follows_ord():
    rows = [{"ord": "21", "raw_index": "5", "account_id": "x", "account_nm": "금융업채권"},
            {"ord": "9", "raw_index": "2", "account_id": "x", "account_nm": "금융업채권"},
            {"ord": "3", "raw_index": "0", "account_id": "y", "account_nm": "다른것"}]
    got = [(r["ord"], occ) for r, occ in S.with_occurrence(rows)]
    assert got == [("3", 1), ("9", 1), ("21", 2)]


def test_period_end():
    assert S.period_end("2025", "12", 0) == "2025-12-31"
    assert S.period_end("2025", "12", 2) == "2023-12-31"
    assert S.period_end("2024", "2", 0) == "2024-02-29"


# ---------------------------------------------------------------- 실제 데이터

@pytest.fixture(scope="module")
def real():
    rows = collect.read_csv(paths.STATEMENTS_CSV)
    chart = S.load_chart()
    mapping = S.load_mapping()
    bs, checks, problems = S.standardize(rows, chart, mapping)
    return {"rows": rows, "chart": chart, "mapping": mapping, "bs": bs, "checks": checks, "problems": problems}


def test_every_bs_line_has_exactly_one_mapping_row(real):
    counts = {k: 0 for k in real["mapping"]}
    n_lines = 0
    for _, srows in S.statements(real["rows"]).items():
        for r, occ in S.with_occurrence(srows):
            n_lines += 1
            k = S.mapping_key(r, occ)
            assert k in real["mapping"], f"매핑 없음: {k}"
            counts[k] += 1
    assert n_lines == 1455
    # 키가 유일하므로 줄마다 정확히 한 행. 쓰이지 않는 매핑 행도 없어야 한다
    assert [k for k, n in counts.items() if n == 0] == []
    assert all(m["std_id"] for m in real["mapping"].values())
    assert S.check_mapping(real["chart"], real["mapping"]) == []
    assert all(m["method"] in ("xbrl_id", "name", "position", "manual") for m in real["mapping"].values())
    assert all(m["confidence"] in ("high", "medium", "low") for m in real["mapping"].values())
    assert all(m["review"] in ("ok", "needs_lead") for m in real["mapping"].values())


def test_all_reconciliation_checks_pass(real):
    assert real["problems"] == []
    bad = [c for c in real["checks"] if c["status"] != "pass"]
    assert bad == []
    # 30개 재무제표 × 3기간 모두 핵심 대사가 있다
    for sid in ("BS.A1", "BS.A2", "BS.A", "BS.L1", "BS.L2", "BS.L", "BS.E"):
        assert sum(1 for c in real["checks"] if c["std_id"] == sid and c["check"] == "보고값=하위합계") == 90
    assert sum(1 for c in real["checks"] if c["check"] == "BS.L+BS.E=BS.T") == 90
    assert sum(1 for c in real["checks"] if c["std_id"] == "BS.E1") == 45     # 연결만


def _get(real, corp, year, fs, period, sid, source):
    hits = [r for r in real["bs"] if r["corp_code"] == corp and r["bsns_year"] == year and r["fs_div"] == fs
            and r["period"] == period and r["std_id"] == sid and r["source"] == source]
    assert len(hits) <= 1
    return hits[0] if hits else None


def test_regression_values(real):
    sam, hmc, naver = "00126380", "00164742", "00266961"
    a25 = _get(real, sam, "2025", "CFS", "current", "BS.A", "reported")
    assert a25["amount"] == 566_942_110_000_000 and a25["period_end"] == "2025-12-31"
    assert _get(real, sam, "2025", "CFS", "current", "BS.A", "rollup")["amount"] == 566_942_110_000_000
    assert _get(real, sam, "2023", "CFS", "current", "BS.A", "reported")["amount"] == 455_905_980_000_000
    assert _get(real, sam, "2025", "CFS", "prior2", "BS.A", "reported")["amount"] == 455_905_980_000_000
    # 삼성 기타유동자산 묶음은 보고 줄이 없고 선급비용 + 그밖의기타유동자산 합계로만 있다
    assert _get(real, sam, "2025", "CFS", "current", "BS.A16", "reported") is None
    assert _get(real, sam, "2025", "CFS", "current", "BS.A16", "rollup")["amount"] == 10_591_701_000_000
    # 자본금: 보고값과 보통주+우선주 합계 둘 다
    assert _get(real, sam, "2025", "CFS", "current", "BS.E11", "reported")["amount"] == 897_514_000_000
    assert _get(real, sam, "2025", "CFS", "current", "BS.E11", "rollup")["amount"] == 897_514_000_000
    # 현대 금융업채권 두 줄: 유동 / 비유동
    assert _get(real, hmc, "2025", "CFS", "current", "BS.A18", "reported")["amount"] == 55_808_152_000_000
    assert _get(real, hmc, "2025", "CFS", "current", "BS.A2B", "reported")["amount"] == 78_542_440_000_000
    # 별도: 지배기업소유주지분은 합계로만, 자본총계와 같다
    e1 = _get(real, naver, "2025", "OFS", "current", "BS.E1", "rollup")
    assert e1["amount"] == 15_729_782_986_276
    assert _get(real, naver, "2025", "OFS", "current", "BS.E1", "reported") is None
    # 값이 없는 노드는 행이 없다: 삼성은 사용권자산 줄이 없다
    assert _get(real, sam, "2025", "CFS", "current", "BS.A22", "reported") is None
    assert _get(real, sam, "2025", "CFS", "current", "BS.A22", "rollup") is None


def test_provenance_points_to_raw_rows(real):
    rows_by = {(r["raw_file"], r["raw_index"]): r for r in real["rows"]}
    r = _get(real, "00164742", "2025", "CFS", "current", "BS.A18", "reported")
    src = rows_by[(r["raw_file"], r["raw_index"])]
    assert src["account_nm"] == "금융업채권" and int(src["thstrm_amount"]) == r["amount"]
