"""재무상태표(BS) 표준화 층: as-reported 줄 -> 표준 계정과목(트리) -> 상위 노드 합계(roll-up) -> 대사 점검.

입력
- data/dart/standard/accounts_bs.csv  표준 계정과목 트리 (std_id, parent, ...). 연구 책임이 설계한다.
- data/dart/standard/mapping_bs.csv   as-reported 줄 하나 = 한 행. 키는 (corp_code, fs_div, account_id, account_nm,
  occurrence). occurrence 는 한 재무제표 안에서 같은 (account_id, account_nm) 이 여러 번 나올 때 ord 순서로 매긴
  번호(1, 2, ...)다. 대부분 1 이다 (현대자동차 연결 "금융업채권" 만 1, 2).
- data/dart/extracted/statements.csv  as-reported 긴 표

출력 (data/dart/standardized/)
- bs.csv         긴 표. 재무제표 하나 × 기간(당기·전기·전전기) × 노드 마다, 보고값(source=reported)과
                 하위 노드 합계(source=rollup)를 따로 적는다. 둘 다 있으면 두 행. 둘 다 없으면 행이 없다
                 (값을 지어내지 않는다). raw_file + raw_index 로 원본 줄을 가리킨다.
- bs_checks.csv  대사 점검. 보고값과 합계가 둘 다 있는 모든 노드, 그리고 BS.L + BS.E = BS.T, BS.A = BS.T.
- bs_checks.md   점검 요약 (실패는 모두 차이와 관련 줄을 적는다)
- bs_coverage.csv 노드별로 30개 재무제표 중 값이 있는 수, 연결 5개사 공통 여부

합계 규칙: 노드의 값 = 보고값이 있으면 보고값, 없으면 합계. 합계 = 자식 노드 값의 합 (값이 있는 자식만).
자식 중 하나도 값이 없으면 합계도 없다. 같은 노드에 여러 줄이 대응하면 보고값은 그 줄들의 합이다.
금액이 빈칸인 줄은 그 기간에 값이 없는 것으로 본다 (0 으로 채우지 않는다).
"""

import calendar
import csv
import json
from collections import Counter, OrderedDict, defaultdict

from . import collect, extract, paths

STANDARD = paths.DATA / "standard"
CHART_CSV = STANDARD / "accounts_bs.csv"
MAPPING_CSV = STANDARD / "mapping_bs.csv"
OUT = paths.DATA / "standardized"
BS_CSV = OUT / "bs.csv"
CHECKS_CSV = OUT / "bs_checks.csv"
CHECKS_MD = OUT / "bs_checks.md"
COVERAGE_CSV = OUT / "bs_coverage.csv"

PERIODS = [("current", "thstrm", 0), ("prior", "frmtrm", 1), ("prior2", "bfefrmtrm", 2)]
KEY_FIELDS = ["corp_code", "fs_div", "account_id", "account_nm", "occurrence"]
MAPPING_COLUMNS = ["corp_code", "company", "fs_div", "account_id", "account_nm", "occurrence", "std_id", "method",
                   "confidence", "review", "note", "years", "n_rows"]
BS_COLUMNS = ["corp_code", "stock_code", "company", "rcept_no", "rcept_dt", "bsns_year", "reprt_code", "fs_div",
              "period", "period_nm", "period_end", "std_id", "name_ko", "depth", "amount", "source", "n_lines",
              "raw_file", "raw_index"]
CHECK_COLUMNS = ["corp_code", "company", "bsns_year", "fs_div", "period", "period_end", "check", "std_id",
                 "reported", "computed", "diff", "status", "parts", "raw_index"]


# ---------------------------------------------------------------- 표준 계정 트리

class Chart:
    """표준 계정 트리. nodes: {std_id: 행 dict} (파일 순서), children: {std_id: [std_id]}, roots: [std_id]."""

    def __init__(self, nodes):
        self.nodes = OrderedDict((n["std_id"], n) for n in nodes)
        self.children = defaultdict(list)
        self.roots = []
        for sid, n in self.nodes.items():
            p = n.get("parent", "") or ""
            if p:
                if p not in self.nodes:
                    raise ValueError(f"{sid}: 부모 {p} 가 차트에 없음")
                self.children[p].append(sid)
            else:
                self.roots.append(sid)
        for sid in self.nodes:          # 순환 확인
            self.depth(sid)

    def depth(self, sid):
        d, seen = 0, set()
        while self.nodes[sid].get("parent"):
            if sid in seen:
                raise ValueError(f"차트에 순환: {sid}")
            seen.add(sid)
            sid = self.nodes[sid]["parent"]
            d += 1
        return d

    def ancestors(self, sid):
        out = []
        while self.nodes[sid].get("parent"):
            sid = self.nodes[sid]["parent"]
            out.append(sid)
        return out


def load_chart(path=CHART_CSV):
    return Chart(collect.read_csv(path))


# ---------------------------------------------------------------- 매핑

def with_occurrence(stmt_rows):
    """한 재무제표의 행들 -> [(행, occurrence)]. 같은 (account_id, account_nm) 은 ord 순서로 1, 2, ..."""
    seen = Counter()
    out = []
    for r in sorted(stmt_rows, key=lambda r: (int(r["ord"]), int(r["raw_index"]))):
        k = (r["account_id"], r["account_nm"])
        seen[k] += 1
        out.append((r, seen[k]))
    return out


def mapping_key(row, occurrence):
    return (row["corp_code"], row["fs_div"], row["account_id"], row["account_nm"], str(occurrence))


def load_mapping(path=MAPPING_CSV):
    """{키: 매핑 행}. 같은 키가 두 번 있으면 오류."""
    out = {}
    for m in collect.read_csv(path):
        k = tuple(m[f] for f in KEY_FIELDS)
        if k in out:
            raise ValueError(f"매핑 키 중복: {k}")
        out[k] = m
    return out


def check_mapping(chart, mapping):
    """매핑의 std_id 가 차트에 있는지. 문제 목록."""
    return [f"{k}: std_id {m['std_id']} 가 차트에 없음" for k, m in mapping.items()
            if m["std_id"] and m["std_id"] not in chart.nodes]


# ---------------------------------------------------------------- 합계

def rollup(chart, lines):
    """lines: [(std_id, amount, ref)] -> {std_id: {"reported": (금액, [ref]) | None, "rollup": (금액, [ref]) | None}}.

    값이 하나도 없는 노드는 결과에 없다. 노드 값 = 보고값 우선, 없으면 합계. 합계 = 값이 있는 자식 값의 합.
    """
    reported = {}
    for sid, amt, ref in lines:
        if sid not in chart.nodes:
            raise KeyError(f"차트에 없는 노드 {sid}")
        a, refs = reported.get(sid, (0, []))
        reported[sid] = (a + amt, refs + [ref])
    out = {}

    def visit(sid):
        kids = [(k, visit(k)) for k in chart.children.get(sid, [])]
        kids = [(k, v) for k, v in kids if v is not None]
        roll = None
        if kids:
            roll = (sum(v[0] for _, v in kids), [r for _, v in kids for r in v[1]])
        rep = reported.get(sid)
        if rep is None and roll is None:
            return None
        out[sid] = {"reported": rep, "rollup": roll}
        return rep if rep is not None else roll

    for root in chart.roots:
        visit(root)
    return out


def value(node_result):
    """rollup() 결과의 한 노드 -> 노드 값 (보고값 우선)."""
    if node_result is None:
        return None
    v = node_result["reported"] or node_result["rollup"]
    return v[0] if v else None


# ---------------------------------------------------------------- 재무제표 단위 처리

def period_end(bsns_year, acc_mt, back):
    """사업연도·결산월 -> 기말일 (YYYY-MM-DD). back: 0 당기, 1 전기, 2 전전기."""
    y, m = int(bsns_year) - back, int(acc_mt)
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def read_acc_mt(corp_code):
    p = paths.company_json(corp_code)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("acc_mt") or None


def statements(rows):
    """BS 행 -> OrderedDict {(corp_code, bsns_year, reprt_code, fs_div): [행]}."""
    out = OrderedDict()
    for r in rows:
        if r["sj_div"] == "BS":
            out.setdefault((r["corp_code"], r["bsns_year"], r["reprt_code"], r["fs_div"]), []).append(r)
    return out


def map_statement(stmt_rows, mapping):
    """-> (mapped [(행, 매핑 행)], unmapped [행], excluded [(행, 매핑 행)] (std_id 빈칸))."""
    mapped, unmapped, excluded = [], [], []
    for r, occ in with_occurrence(stmt_rows):
        m = mapping.get(mapping_key(r, occ))
        if m is None:
            unmapped.append(r)
        elif not m["std_id"]:
            excluded.append((r, m))
        else:
            mapped.append((r, m))
    return mapped, unmapped, excluded


def _fmt_parts(chart, res, sid):
    parts = []
    for k in chart.children.get(sid, []):
        if k in res:
            parts.append(f"{k}={value(res[k])}")
    return ";".join(parts)


def _refs(v):
    return ";".join(str(i) for i in sorted(v[1])) if v else ""


def standardize(rows, chart, mapping, acc_mt=None):
    """as-reported 행 -> (bs 행, 점검 행, 문제 목록). acc_mt: {corp_code: 결산월}, 없으면 company json 에서 읽는다."""
    acc_mt = dict(acc_mt or {})
    out, checks, problems = [], [], check_mapping(chart, mapping)
    for (corp, year, reprt, fs), srows in statements(rows).items():
        mapped, unmapped, excluded = map_statement(srows, mapping)
        for r in unmapped:
            problems.append(f"매핑 없음: {corp} {year} {fs} {r['account_id']} {r['account_nm']} (raw_index {r['raw_index']})")
        for r, m in excluded:
            problems.append(f"std_id 빈칸으로 제외: {corp} {year} {fs} {r['account_id']} {r['account_nm']}")
        first = srows[0]
        if corp not in acc_mt:
            acc_mt[corp] = read_acc_mt(corp)
        raw_files = sorted({r["raw_file"] for r in srows})
        if len(raw_files) != 1:
            problems.append(f"{corp} {year} {fs}: raw_file 이 여러 개 {raw_files}")
        for pname, prefix, back in PERIODS:
            lines = []
            for r, m in mapped:
                a = extract.amount(r, f"{prefix}_amount")
                if a is not None:
                    lines.append((m["std_id"], a, int(r["raw_index"])))
            if not lines:
                continue
            res = rollup(chart, lines)
            pend = period_end(year, acc_mt[corp], back) if acc_mt.get(corp) else ""
            base = {"corp_code": corp, "stock_code": first["stock_code"], "company": first["company"],
                    "rcept_no": first["rcept_no"], "rcept_dt": first["rcept_dt"], "bsns_year": year,
                    "reprt_code": reprt, "fs_div": fs, "period": pname, "period_nm": first[f"{prefix}_nm"],
                    "period_end": pend}
            for sid in chart.nodes:
                if sid not in res:
                    continue
                for source in ("reported", "rollup"):
                    v = res[sid][source]
                    if v is None:
                        continue
                    out.append({**base, "std_id": sid, "name_ko": chart.nodes[sid]["name_ko"],
                                "depth": chart.depth(sid), "amount": v[0], "source": source,
                                "n_lines": len(v[1]), "raw_file": raw_files[0], "raw_index": _refs(v)})
            cbase = {"corp_code": corp, "company": first["company"], "bsns_year": year, "fs_div": fs,
                     "period": pname, "period_end": pend}
            checks.extend(_checks(chart, res, cbase, fs))
    return out, checks, problems


REQUIRED = ["BS.A1", "BS.A2", "BS.A", "BS.L1", "BS.L2", "BS.L", "BS.E"]


def _check_row(cbase, check, sid, reported, computed, parts, refs):
    if reported is None or computed is None:
        status, diff = "missing", ""
    else:
        diff = reported - computed
        status = "pass" if diff == 0 else "fail"
    return {**cbase, "check": check, "std_id": sid, "reported": "" if reported is None else reported,
            "computed": "" if computed is None else computed, "diff": diff, "status": status, "parts": parts,
            "raw_index": refs}


def _checks(chart, res, cbase, fs):
    rows = []
    required = REQUIRED + (["BS.E1"] if fs == "CFS" else [])
    for sid in chart.nodes:
        r = res.get(sid)
        has_both = r is not None and r["reported"] is not None and r["rollup"] is not None
        if not has_both and sid not in required:
            continue
        rep = r["reported"][0] if r and r["reported"] else None
        roll = r["rollup"][0] if r and r["rollup"] else None
        refs = _refs(r["rollup"]) if r else ""
        rows.append(_check_row(cbase, "보고값=하위합계", sid, rep, roll, _fmt_parts(chart, res, sid), refs))
    # 부채와자본총계
    t = res.get("BS.T")
    t_rep = t["reported"][0] if t and t["reported"] else None
    lv, ev, av = value(res.get("BS.L")), value(res.get("BS.E")), value(res.get("BS.A"))
    le = lv + ev if lv is not None and ev is not None else None
    rows.append(_check_row(cbase, "BS.L+BS.E=BS.T", "BS.T", t_rep, le, f"BS.L={lv};BS.E={ev}", ""))
    rows.append(_check_row(cbase, "BS.A=BS.T", "BS.T", t_rep, av, f"BS.A={av}", ""))
    return rows


# ---------------------------------------------------------------- 커버리지

COVERAGE_COLUMNS = ["std_id", "parent", "depth", "kind", "name_ko", "n_mapping_rows", "n_statements", "n_reported",
                    "n_rollup_only", "n_cfs", "n_ofs", "cfs_companies_all_years", "cfs_missing", "all5_cfs",
                    "frontier_cfs"]


def coverage(chart, bs_rows, mapping, statement_keys):
    """노드별 값이 있는 재무제표 수 (당기 열 기준). statement_keys: [(corp_code, company, bsns_year, fs_div)]."""
    have = defaultdict(lambda: defaultdict(set))       # sid -> statement key -> {sources}
    for r in bs_rows:
        if r["period"] == "current":
            have[r["std_id"]][(r["corp_code"], r["bsns_year"], r["fs_div"])].add(r["source"])
    used = Counter(m["std_id"] for m in mapping.values() if m["std_id"])
    cfs_keys = [k for k in statement_keys if k[3] == "CFS"]
    companies = OrderedDict((k[0], k[1]) for k in statement_keys)
    all5 = {}
    rows = []
    for sid, n in chart.nodes.items():
        h = have.get(sid, {})
        missing = []
        for corp, name in companies.items():
            years = [k[2] for k in cfs_keys if k[0] == corp and (k[0], k[2], k[3]) not in h]
            if years:
                missing.append(f"{name}:{','.join(years)}")
        all5[sid] = not missing and len(companies) > 0
        rows.append({"std_id": sid, "parent": n.get("parent", ""), "depth": chart.depth(sid), "kind": n.get("kind", ""),
                     "name_ko": n["name_ko"], "n_mapping_rows": used.get(sid, 0), "n_statements": len(h),
                     "n_reported": sum(1 for s in h.values() if "reported" in s),
                     "n_rollup_only": sum(1 for s in h.values() if s == {"rollup"}),
                     "n_cfs": sum(1 for k in h if k[2] == "CFS"), "n_ofs": sum(1 for k in h if k[2] == "OFS"),
                     "cfs_companies_all_years": sum(1 for corp in companies
                                                    if all((corp, k[2], "CFS") in h for k in cfs_keys if k[0] == corp)),
                     "cfs_missing": " / ".join(missing), "all5_cfs": "yes" if all5[sid] else "no"})
    for r in rows:
        kids = chart.children.get(r["std_id"], [])
        r["frontier_cfs"] = "yes" if all5[r["std_id"]] and (not kids or not all(all5[k] for k in kids)) else "no"
    return rows


def deepest_common_level(chart, cov_rows):
    """depth 별 (노드 수, 연결 5개사 공통 노드 수). 그리고 모든 노드가 공통인 가장 깊은 depth."""
    by = defaultdict(lambda: [0, 0])
    for r in cov_rows:
        by[r["depth"]][0] += 1
        by[r["depth"]][1] += r["all5_cfs"] == "yes"
    full = [d for d, (n, k) in sorted(by.items()) if n == k]
    deepest_full = -1
    for d in sorted(by):
        if by[d][0] == by[d][1]:
            deepest_full = d
        else:
            break
    return dict(by), deepest_full, full


# ---------------------------------------------------------------- 요약

def to_markdown(checks, problems, cov_rows, levels, mapping):
    st = Counter(c["status"] for c in checks)
    lines = ["# 재무상태표 표준화 점검 (`python dart_collect.py --standardize`)", "",
             "`data/dart/standardized/bs_checks.csv` 의 요약이다. 매핑은 `data/dart/standard/mapping_bs.csv`, "
             "차트는 `data/dart/standard/accounts_bs.csv`.", "",
             f"- 점검 {len(checks)}건: 통과 {st['pass']}, 실패 {st['fail']}, 값 없음 {st['missing']}",
             f"- 매핑 행 {len(mapping)}개 "
             f"(method: {', '.join(f'{k} {v}' for k, v in sorted(Counter(m['method'] for m in mapping.values()).items()))}; "
             f"confidence: {', '.join(f'{k} {v}' for k, v in sorted(Counter(m['confidence'] for m in mapping.values()).items()))}; "
             f"review: {', '.join(f'{k} {v}' for k, v in sorted(Counter(m['review'] for m in mapping.values()).items()))})",
             f"- 문제 {len(problems)}건 (매핑 없는 줄, std_id 빈칸으로 뺀 줄)", ""]
    by_check = defaultdict(Counter)
    for c in checks:
        by_check[(c["check"], c["std_id"])][c["status"]] += 1
    lines += ["## 점검 종류별", "", "| 점검 | 노드 | 통과 | 실패 | 값 없음 |", "|---|---|---|---|---|"]
    for (ck, sid), cnt in sorted(by_check.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines.append(f"| {ck} | {sid} | {cnt['pass']} | {cnt['fail']} | {cnt['missing']} |")
    bad = [c for c in checks if c["status"] != "pass"]
    lines += ["", "## 실패·값 없음 전체", ""]
    if not bad:
        lines.append("없음.")
    else:
        lines += ["| 회사 | 연도 | 구분 | 기간 | 점검 | 노드 | 보고 | 계산 | 차이 | 구성 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for c in bad:
            lines.append(f"| {c['company']} | {c['bsns_year']} | {c['fs_div']} | {c['period']} | {c['check']} | "
                         f"{c['std_id']} | {c['reported']} | {c['computed']} | {c['diff']} | {c['parts']} |")
    if problems:
        lines += ["", "## 문제", ""] + [f"- {p}" for p in problems]
    by, deepest_full, _ = levels
    lines += ["", "## 비교 가능성 (연결, 당기 열, 5개사 × 3년 모두 값이 있는 노드)", "",
              "| depth | 노드 수 | 5개사 공통 |", "|---|---|---|"]
    for d in sorted(by):
        lines.append(f"| {d} | {by[d][0]} | {by[d][1]} |")
    lines += ["", f"모든 노드가 5개사 공통인 가장 깊은 depth: {deepest_full}", "",
              "5개사 공통이 아닌 노드 (빠진 회사:연도):", ""]
    for r in cov_rows:
        if r["all5_cfs"] != "yes":
            lines.append(f"- {r['std_id']} {r['name_ko']} (depth {r['depth']}): {r['cfs_missing']}")
    return "\n".join(lines) + "\n"


def run(statements_csv=paths.STATEMENTS_CSV):
    rows = collect.read_csv(statements_csv)
    chart = load_chart()
    mapping = load_mapping()
    bs_rows, check_rows, problems = standardize(rows, chart, mapping)
    keys = []
    for (corp, year, reprt, fs), srows in statements(rows).items():
        keys.append((corp, srows[0]["company"], year, fs))
    cov = coverage(chart, bs_rows, mapping, keys)
    levels = deepest_common_level(chart, cov)
    collect.write_csv_if_changed(BS_CSV, BS_COLUMNS, bs_rows)
    collect.write_csv_if_changed(CHECKS_CSV, CHECK_COLUMNS, check_rows)
    collect.write_csv_if_changed(COVERAGE_CSV, COVERAGE_COLUMNS, cov)
    md = to_markdown(check_rows, problems, cov, levels, mapping)
    OUT.mkdir(parents=True, exist_ok=True)
    CHECKS_MD.write_text(md, encoding="utf-8")
    return {"bs": bs_rows, "checks": check_rows, "problems": problems, "coverage": cov, "levels": levels, "md": md}
