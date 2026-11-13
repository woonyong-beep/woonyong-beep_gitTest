"""as-reported 표 점검. 실패를 고치지 않고 그대로 보고한다.

점검 항목 (회사·연도·보고서·연결/별도 단위)
- statements: BS, IS 또는 CIS, CF, SCE 가 있는지. 같은 (재무제표, account_id, 계정명, account_detail) 이 두 번 이상 나오는지.
- bs_identity: 자산총계 = 부채총계 + 자본총계 (당기, 전기, 전전기 각각, 원 단위 정확히)
- cf_cash: 현금흐름표 기말현금 = 재무상태표 현금및현금성자산 (당기, 전기)
- prior_year: N년 보고서의 전기 금액 = N-1년 보고서의 당기 금액. 다르면 재작성(restatement) 후보로 행마다 남긴다.

계정 찾기는 표준 account_id 를 먼저 쓰고, 없으면 계정명으로 찾는다. 어떻게 찾았는지 detail 에 적는다.
"""

from collections import defaultdict

from .extract import NON_STANDARD, amount

COLUMNS = ["check", "corp_code", "company", "bsns_year", "reprt_code", "fs_div", "period", "status",
           "lhs", "rhs", "diff", "detail"]
REQUIRED = ["BS", "CF", "SCE"]

ASSETS = (["ifrs-full_Assets"], ["자산총계"])
LIABS = (["ifrs-full_Liabilities"], ["부채총계"])
EQUITY = (["ifrs-full_Equity"], ["자본총계"])
CASH_BS = (["ifrs-full_CashAndCashEquivalents"], ["현금및현금성자산"])
CASH_END_CF = (["dart_CashAndCashEquivalentsAtEndOfPeriodCf"], ["기말현금및현금성자산", "기말의현금및현금성자산",
                                                               "기말현금", "현금및현금성자산의기말잔액"])
PERIODS = [("당기", "thstrm_amount"), ("전기", "frmtrm_amount"), ("전전기", "bfefrmtrm_amount")]


def _norm(s):
    return "".join(str(s).split())


def group(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["corp_code"], r["company"], str(r["bsns_year"]), r["reprt_code"], r["fs_div"])].append(r)
    return g


def find(rows, sj, spec):
    """(row 또는 None, 찾은 방법). 같은 id 가 여러 개면 account_detail 이 비었거나 '-' 인 것을 고른다."""
    ids, names = spec
    for how, pred in (("id", lambda r: r["account_id"] in ids),
                      ("이름", lambda r: _norm(r["account_nm"]) in {_norm(n) for n in names})):
        hits = [r for r in rows if r["sj_div"] == sj and pred(r)]
        if hits:
            plain = [r for r in hits if r.get("account_detail", "-") in ("", "-")] or hits
            return plain[0], how + (f" ({len(hits)}개 중 첫째)" if len(plain) > 1 else "")
    return None, "없음"


def _res(key, check, period, status, lhs="", rhs="", detail=""):
    corp, company, year, rc, fs = key
    diff = lhs - rhs if isinstance(lhs, int) and isinstance(rhs, int) else ""
    return {"check": check, "corp_code": corp, "company": company, "bsns_year": year, "reprt_code": rc,
            "fs_div": fs, "period": period, "status": status, "lhs": lhs, "rhs": rhs, "diff": diff,
            "detail": detail}


def check_statements(key, rows):
    out = []
    present = sorted({r["sj_div"] for r in rows})
    missing = [s for s in REQUIRED if s not in present]
    if "IS" not in present and "CIS" not in present:
        missing.append("IS/CIS")
    out.append(_res(key, "statements", "", "실패" if missing else "통과",
                    detail=f"있음 {','.join(present)}" + (f"; 없음 {','.join(missing)}" if missing else "")))
    rnos = sorted({r["rcept_no"] for r in rows})
    if len(rnos) > 1:
        out.append(_res(key, "statements", "", "실패", detail=f"접수번호가 여러 개 {','.join(rnos)}"))
    seen = defaultdict(list)
    for r in rows:
        seen[(r["sj_div"], r["account_id"], r["account_nm"], r.get("account_detail", ""))].append(r)
    for k, rs in seen.items():
        if len(rs) > 1:
            same = len({tuple(r[f] for _, f in PERIODS) for r in rs}) == 1
            out.append(_res(key, "duplicate_row", "", "참고" if same else "실패",
                            detail=f"{k[0]} {k[1]} {k[2]} {k[3]} {len(rs)}번 (금액 {'같음' if same else '다름'}, "
                                   f"ord {','.join(str(r['ord']) for r in rs)})"))
    return out


def check_bs_identity(key, rows):
    out = []
    a, ha = find(rows, "BS", ASSETS)
    l, hl = find(rows, "BS", LIABS)
    e, he = find(rows, "BS", EQUITY)
    if not (a and l and e):
        return [_res(key, "bs_identity", "", "판정불가", detail=f"자산 {ha}, 부채 {hl}, 자본 {he}")]
    for pname, f in PERIODS:
        va, vl, ve = amount(a, f), amount(l, f), amount(e, f)
        if va is None and vl is None and ve is None:
            continue
        if None in (va, vl, ve):
            out.append(_res(key, "bs_identity", pname, "판정불가", detail="금액 일부 없음"))
            continue
        out.append(_res(key, "bs_identity", pname, "통과" if va == vl + ve else "실패", va, vl + ve,
                        f"자산({ha}) = 부채({hl}) {vl} + 자본({he}) {ve}"))
    return out


def check_cf_cash(key, rows):
    out = []
    b, hb = find(rows, "BS", CASH_BS)
    c, hc = find(rows, "CF", CASH_END_CF)
    if not (b and c):
        return [_res(key, "cf_cash", "", "판정불가", detail=f"BS 현금 {hb}, CF 기말현금 {hc}")]
    for pname, f in PERIODS[:2]:
        vb, vc = amount(b, f), amount(c, f)
        if vb is None or vc is None:
            out.append(_res(key, "cf_cash", pname, "판정불가", detail="금액 없음"))
            continue
        out.append(_res(key, "cf_cash", pname, "통과" if vb == vc else "실패", vc, vb,
                        f"CF {c['account_nm']}({hc}) vs BS {b['account_nm']}({hb})"))
    return out


def row_key(r):
    return (r["sj_div"], r["account_id"], _norm(r["account_nm"]), _norm(r.get("account_detail", "")))


def id_key(r):
    return (r["sj_div"], r["account_id"], _norm(r.get("account_detail", "")))


def diff_kind(cur, old):
    """전기 금액(cur)과 전년 당기 금액(old)의 차이 종류."""
    if cur == old:
        return "같음"
    if cur is None or old is None:
        return "빈칸과0" if (cur or 0) == 0 and (old or 0) == 0 else "한쪽빈칸"
    if cur == -old:
        return "부호반대"
    return "금액다름"


def check_prior_year(groups):
    """N년 frmtrm 과 N-1년 thstrm 비교.

    짝 찾기 1단계: (재무제표, account_id, 계정명, account_detail) 이 같은 행 (공백 무시).
    2단계: 1단계에서 짝이 없고 account_id 가 표준(-표준계정코드 미사용- 이 아님)이면 (재무제표, id, detail) 이
    양쪽에서 하나뿐일 때 짝으로 본다 (계정명만 바뀐 경우). 짝이 여럿이면 판정하지 않는다.
    차이는 종류로 나눈다: 금액다름(재작성 후보), 부호반대(표시 부호가 바뀜), 빈칸과0, 한쪽빈칸.
    """
    out = []
    for key, rows in sorted(groups.items()):
        corp, company, year, rc, fs = key
        prev_key = (corp, company, str(int(year) - 1), rc, fs)
        if prev_key not in groups:
            continue
        prev, prev_id = defaultdict(list), defaultdict(list)
        for r in groups[prev_key]:
            prev[row_key(r)].append(r)
            prev_id[id_key(r)].append(r)
        cur_id = defaultdict(int)
        for r in rows:
            cur_id[id_key(r)] += 1
        counts = defaultdict(int)
        for r in rows:
            cur = amount(r, "frmtrm_amount")
            cands, how = prev.get(row_key(r), []), "id+이름"
            if not cands and r["account_id"] != NON_STANDARD and cur_id[id_key(r)] == 1 \
                    and len(prev_id.get(id_key(r), [])) == 1:
                cands, how = prev_id[id_key(r)], "id만(이름 바뀜)"
            if not cands:
                counts["짝없음"] += 1
                if cur not in (None, 0):
                    out.append(_res(key, "prior_year_unmatched", "전기", "참고", cur, "",
                                    f"{r['sj_div']} {r['account_id']} {r['account_nm']} {r.get('account_detail', '')}"
                                    " 의 짝이 전년 보고서에 없음"))
                continue
            if len(cands) > 1:
                counts["짝여럿"] += 1
                continue
            if how != "id+이름":
                counts["이름바뀜"] += 1
            old = amount(cands[0], "thstrm_amount")
            kind = diff_kind(cur, old)
            counts[kind] += 1
            if kind != "같음":
                out.append(_res(key, "prior_year_diff", "전기", kind, cur if cur is not None else "",
                                old if old is not None else "",
                                f"{r['sj_div']} {r['account_id']} {r['account_nm']} {r.get('account_detail', '')}"
                                f" | 짝: {how}, 전년 이름 {cands[0]['account_nm']} | {year}년 보고서 전기 vs "
                                f"{int(year) - 1}년 보고서 당기 ({cands[0]['rcept_no']})"))
        order = ["같음", "금액다름", "부호반대", "빈칸과0", "한쪽빈칸", "이름바뀜", "짝없음", "짝여럿"]
        status = "차이" if counts["금액다름"] or counts["한쪽빈칸"] else ("부호차이" if counts["부호반대"] else "통과")
        out.append(_res(key, "prior_year", "전기", status, detail=", ".join(f"{k} {counts[k]}" for k in order)))
    return out


def run_all(rows):
    g = group(rows)
    out = []
    for key in sorted(g):
        out += check_statements(key, g[key])
        out += check_bs_identity(key, g[key])
        out += check_cf_cash(key, g[key])
    out += check_prior_year(g)
    return out


def _fmt(v):
    return f"{v:,}" if isinstance(v, int) else str(v)


def to_markdown(results):
    """사람이 읽는 요약. 회사·연도·연결별 표 하나 + 실패·차이 목록."""
    lines = ["# DART as-reported 점검 결과", "",
             "`python dart_collect.py --check` 가 만든다. 실패를 고치지 않고 그대로 적는다. 금액 단위는 원.", "",
             "| 회사 | 연도 | 구분 | 재무제표 | 자산=부채+자본 | CF기말현금=BS현금 | 전기=전년당기 (행 수) |",
             "|---|---|---|---|---|---|---|"]
    by = defaultdict(list)
    for r in results:
        by[(r["company"], r["bsns_year"], r["reprt_code"], r["fs_div"])].append(r)
    for k in sorted(by):
        rs = by[k]

        def cell(check):
            xs = [r for r in rs if r["check"] == check]
            if not xs:
                return "—"
            return " ".join(f"{r['period']}{r['status']}" for r in xs)
        stm = [r for r in rs if r["check"] == "statements"]
        dup = sum(1 for r in rs if r["check"] == "duplicate_row")
        st = stm[0]["status"] + (f" (중복 {dup})" if dup else "") if stm else "—"
        py = [r for r in rs if r["check"] == "prior_year"]
        pyc = f"{py[0]['status']}: {py[0]['detail']}" if py else "—"
        lines.append(f"| {k[0]} | {k[1]} | {k[3]} | {st} | {cell('bs_identity')} | {cell('cf_cash')} | {pyc} |")
    bad = [r for r in results if r["status"] in ("실패", "판정불가", "금액다름", "한쪽빈칸", "부호반대")]
    lines += ["", f"## 실패·판정불가·차이 ({len(bad)}건)", ""]
    if bad:
        lines += ["| 점검 | 회사 | 연도 | 구분 | 기간 | 상태 | 좌변 | 우변 | 차이 | 내용 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in bad:
            lines.append(f"| {r['check']} | {r['company']} | {r['bsns_year']} | {r['fs_div']} | {r['period']} | "
                         f"{r['status']} | {_fmt(r['lhs'])} | {_fmt(r['rhs'])} | {_fmt(r['diff'])} | "
                         f"{r['detail'].replace('|', '/')} |")
    else:
        lines.append("없음")
    notes = [r for r in results if r["status"] in ("참고", "빈칸과0")]
    lines += ["", f"## 참고 ({len(notes)}건: 중복이지만 금액이 같은 행, 빈칸과 0 의 차이, 전년 보고서에 짝이 없는 0 아닌 전기 금액)", "",
              "목록은 data/dart/checks.csv 에 있다.", ""]
    return "\n".join(lines)
