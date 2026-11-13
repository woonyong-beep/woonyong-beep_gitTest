"""표준화 층: as-reported 줄 -> 표준 계정과목(트리) -> 상위 노드 합계(roll-up) -> 대사 점검.

재무상태표(BS)와 손익·포괄손익(PL) 두 가지를 같은 엔진으로 처리한다. 둘의 차이는 `Spec` 에 모았다.

입력
- data/dart/standard/accounts_bs.csv, accounts_pl.csv  표준 계정과목 트리. 연구 책임이 설계한다.
  열 `sign`(PL 만)은 노드가 부모에 더해지는 부호(+1/-1)다. 없거나 빈칸이면 +1 (BS 는 모두 +1).
  열 `kind`: total/subtotal/group/item 은 합산 나무, `formula` 는 나무 밖에서 열 `formula`(예: PL.REV-PL.COGS)로
  정의하는 항목, `attribution` 은 합계를 지배·비지배로 나누는 항목(나무 밖 루트, 자식은 합산), `per_share` 는 주당 금액
  (원/주)이라 부모도 자식도 없고 어떤 합산·공식에도 쓰지 않는다.
- data/dart/standard/mapping_bs.csv, mapping_pl.csv   as-reported 줄 하나 = 한 행.
  BS 키: (corp_code, fs_div, account_id, account_nm, occurrence).
  PL 키: (corp_code, fs_div, sj_div, bsns_year, account_id, account_nm, occurrence). bsns_year 가 빈칸이면 모든 연도에,
  값이 있으면 그 연도 보고서에만 쓴다 (같은 줄의 공시 부호가 연도마다 다를 때). 같은 키에 빈칸 행과 연도 행이
  함께 있으면 오류 (줄마다 정확히 한 행).
  occurrence 는 한 재무제표(sj_div) 안에서 같은 (account_id, account_nm) 이 여러 번 나올 때 ord 순서로 매긴 번호다.
  PL 만 있는 열: `role` = value(그 줄이 노드 값을 나른다) / check_only(다른 곳에 이미 있는 값을 다시 적은 줄. 노드 값과
  같아야 하지만 더하지 않는다), `flip` = 1 / -1 (차트 방향과 반대로 공시한 줄. 표준 금액 = 공시 금액 × flip).
- data/dart/extracted/statements.csv  as-reported 긴 표

출력 (data/dart/standardized/)
- bs.csv / pl.csv     긴 표. 재무제표 하나 × 기간(당기·전기·전전기) × 노드 마다, 보고값(source=reported)과
                      하위 노드 부호 합계(source=rollup), 공식 값(source=formula, PL.GP·PL.CI)을 따로 적는다. 값이 없으면
                      행이 없다 (값을 지어내지 않는다). raw_file + raw_index 로 원본 줄을 가리킨다.
                      PL 은 손익계산서(IS)와 포괄손익계산서(CIS)를 한 재무제표로 합친다 (raw_file 은 같은 JSON 하나).
                      PL 은 흐름이라 period_start 도 적는다. 사업보고서(11011)의 thstrm/frmtrm/bfefrmtrm 금액은 회계연도
                      전체(12개월) 금액이다.
- *_checks.csv / .md  대사 점검
- *_coverage.csv      노드별로 재무제표 중 값이 있는 수, 연결 5개사 공통 여부

합계 규칙: 노드의 값 = 보고값이 있으면 보고값, 없으면 합계. 합계 = Σ(자식 sign × 자식 값) (값이 있는 자식만).
자식 중 하나도 값이 없으면 합계도 없다. 같은 노드에 여러 줄이 대응하면 보고값은 그 줄들의 합이다.
금액이 빈칸인 줄은 그 기간에 값이 없는 것으로 본다 (0 으로 채우지 않는다).
공식 노드의 값 = 피연산자 값이 모두 있을 때의 공식 값. 보고값이 있으면 둘이 같은지 점검한다.
"""

import calendar
import csv
import datetime
import json
import re
from collections import Counter, OrderedDict, defaultdict

from . import collect, extract, paths

STANDARD = paths.DATA / "standard"
OUT = paths.DATA / "standardized"

# 재무상태표 (예전 이름 그대로 둔다)
CHART_CSV = STANDARD / "accounts_bs.csv"
MAPPING_CSV = STANDARD / "mapping_bs.csv"
BS_CSV = OUT / "bs.csv"
CHECKS_CSV = OUT / "bs_checks.csv"
CHECKS_MD = OUT / "bs_checks.md"
COVERAGE_CSV = OUT / "bs_coverage.csv"

# 손익
PL_CHART_CSV = STANDARD / "accounts_pl.csv"
PL_MAPPING_CSV = STANDARD / "mapping_pl.csv"
PL_CSV = OUT / "pl.csv"
PL_CHECKS_CSV = OUT / "pl_checks.csv"
PL_CHECKS_MD = OUT / "pl_checks.md"
PL_COVERAGE_CSV = OUT / "pl_coverage.csv"

PERIODS = [("current", "thstrm", 0), ("prior", "frmtrm", 1), ("prior2", "bfefrmtrm", 2)]
KEY_FIELDS = ["corp_code", "fs_div", "account_id", "account_nm", "occurrence"]
PL_KEY_FIELDS = ["corp_code", "fs_div", "sj_div", "bsns_year", "account_id", "account_nm", "occurrence"]
MAPPING_COLUMNS = ["corp_code", "company", "fs_div", "account_id", "account_nm", "occurrence", "std_id", "method",
                   "confidence", "review", "note", "years", "n_rows"]
PL_MAPPING_COLUMNS = ["corp_code", "company", "fs_div", "sj_div", "bsns_year", "account_id", "account_nm", "occurrence",
                      "std_id", "role", "flip", "method", "confidence", "review", "note", "years", "n_rows"]
BS_COLUMNS = ["corp_code", "stock_code", "company", "rcept_no", "rcept_dt", "bsns_year", "reprt_code", "fs_div",
              "period", "period_nm", "period_end", "std_id", "name_ko", "depth", "amount", "source", "n_lines",
              "raw_file", "raw_index"]
PL_COLUMNS = ["corp_code", "stock_code", "company", "rcept_no", "rcept_dt", "bsns_year", "reprt_code", "fs_div",
              "period", "period_nm", "period_start", "period_end", "std_id", "name_ko", "depth", "kind", "amount", "unit",
              "source", "n_lines", "raw_file", "raw_index"]
CHECK_COLUMNS = ["corp_code", "company", "bsns_year", "fs_div", "period", "period_end", "check", "std_id",
                 "reported", "computed", "diff", "status", "parts", "raw_index"]

SUM_KINDS = ("total", "subtotal", "group", "item", "attribution", "")


# ---------------------------------------------------------------- 표준 계정 트리

class Chart:
    """표준 계정 트리. nodes: {std_id: 행 dict} (파일 순서), children: {std_id: [std_id]}, roots: [std_id].

    formulas: {std_id: [(피연산자 std_id, 부호)]} (kind=formula 노드).
    """

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
            s = (n.get("sign") or "").strip()
            if s not in ("", "1", "+1", "-1"):
                raise ValueError(f"{sid}: sign {s!r} 는 1 또는 -1 이어야 함")
        for sid in self.nodes:          # 순환 확인
            self.depth(sid)
        self.formulas = {}
        for sid, n in self.nodes.items():
            k = self.kind(sid)
            if k in ("formula", "per_share"):
                if n.get("parent") or self.children.get(sid):
                    raise ValueError(f"{sid}: {k} 노드는 부모도 자식도 없어야 함")
            if k == "formula":
                self.formulas[sid] = parse_formula(n.get("formula", ""))
        for sid, terms in self.formulas.items():
            for t, _ in terms:
                if t not in self.nodes:
                    raise ValueError(f"{sid}: 공식의 {t} 가 차트에 없음")
                if self.kind(t) in ("per_share", "formula"):
                    raise ValueError(f"{sid}: 공식에 {self.kind(t)} 노드 {t} 를 쓸 수 없음")

    def kind(self, sid):
        return self.nodes[sid].get("kind", "") or ""

    def sign(self, sid):
        """노드가 부모에 더해지는 부호."""
        return -1 if (self.nodes[sid].get("sign") or "").strip() == "-1" else 1

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


def parse_formula(text):
    """'PL.REV-PL.COGS' -> [('PL.REV', 1), ('PL.COGS', -1)]."""
    text = (text or "").replace(" ", "")
    if not text:
        raise ValueError("공식이 비어 있음")
    terms = re.findall(r"([+-]?)([^+-]+)", text)
    if "".join(s + t for s, t in terms) != text:
        raise ValueError(f"공식을 읽을 수 없음: {text}")
    return [(t, -1 if s == "-" else 1) for s, t in terms]


def load_chart(path=CHART_CSV):
    return Chart(collect.read_csv(path))


# ---------------------------------------------------------------- 명세 (BS / PL 차이)

class Spec:
    def __init__(self, **kw):
        self.__dict__.update(kw)


BS = Spec(name="BS", title="재무상태표", sj_divs=("BS",), chart_csv=CHART_CSV, mapping_csv=MAPPING_CSV,
          key_fields=KEY_FIELDS, out_csv=BS_CSV, checks_csv=CHECKS_CSV, checks_md=CHECKS_MD, coverage_csv=COVERAGE_CSV,
          columns=BS_COLUMNS, flow=False, required=["BS.A1", "BS.A2", "BS.A", "BS.L1", "BS.L2", "BS.L", "BS.E"],
          required_cfs=["BS.E1"],
          # (점검 이름, 대상, [(노드, 부호)], 대상 값 출처, 필수 여부: "all"/"cfs"/"")
          identities=[("BS.L+BS.E=BS.T", "BS.T", [("BS.L", 1), ("BS.E", 1)], "reported", "all"),
                      ("BS.A=BS.T", "BS.T", [("BS.A", 1)], "reported", "all")],
          restatement=False)

PL = Spec(name="PL", title="손익계산서·포괄손익계산서", sj_divs=("IS", "CIS"), chart_csv=PL_CHART_CSV,
          mapping_csv=PL_MAPPING_CSV, key_fields=PL_KEY_FIELDS, out_csv=PL_CSV, checks_csv=PL_CHECKS_CSV,
          checks_md=PL_CHECKS_MD, coverage_csv=PL_COVERAGE_CSV, columns=PL_COLUMNS, flow=True,
          required=["PL.OP", "PL.PBT", "PL.NI", "PL.OCI"], required_cfs=[],
          identities=[("PL.NIO+PL.NIN=PL.NI", "PL.NI", [("PL.NIO", 1), ("PL.NIN", 1)], "value", "cfs"),
                      ("PL.CIO+PL.CIN=PL.CI", "PL.CI", [("PL.CIO", 1), ("PL.CIN", 1)], "value", "cfs"),
                      ("PL.NIO.CONT+PL.NIN.CONT=PL.CONT", "PL.CONT", [("PL.NIO.CONT", 1), ("PL.NIN.CONT", 1)], "value", ""),
                      ("PL.NIO.DISC+PL.NIN.DISC=PL.DISC", "PL.DISC", [("PL.NIO.DISC", 1), ("PL.NIN.DISC", 1)], "value", "")],
          restatement=True)


# ---------------------------------------------------------------- 매핑

def with_occurrence(stmt_rows):
    """한 재무제표의 행들 -> [(행, occurrence)]. 같은 (sj_div, account_id, account_nm) 은 ord 순서로 1, 2, ..."""
    seen = Counter()
    out = []
    for r in sorted(stmt_rows, key=lambda r: (int(r["ord"]), int(r["raw_index"]))):
        k = (r.get("sj_div", ""), r["account_id"], r["account_nm"])
        seen[k] += 1
        out.append((r, seen[k]))
    return out


def mapping_key(row, occurrence, fields=KEY_FIELDS, year=None):
    """as-reported 행 -> 매핑 키. year: bsns_year 칸에 넣을 값 (None 이면 행의 연도)."""
    out = []
    for f in fields:
        if f == "occurrence":
            out.append(str(occurrence))
        elif f == "bsns_year":
            out.append(row["bsns_year"] if year is None else year)
        else:
            out.append(row[f])
    return tuple(out)


def load_mapping(path=MAPPING_CSV, fields=KEY_FIELDS):
    """{키: 매핑 행}. 같은 키가 두 번 있거나, 연도 빈칸 행과 연도 행이 같은 줄을 함께 가리키면 오류."""
    out = {}
    for m in collect.read_csv(path):
        k = tuple(m[f] for f in fields)
        if k in out:
            raise ValueError(f"매핑 키 중복: {k}")
        out[k] = m
    if "bsns_year" in fields:
        i = fields.index("bsns_year")
        generic = {k[:i] + k[i + 1:] for k in out if k[i] == ""}
        for k in out:
            if k[i] != "" and k[:i] + k[i + 1:] in generic:
                raise ValueError(f"매핑 키가 연도 빈칸 행과 연도 {k[i]} 행에 함께 있음: {k}")
    return out


def lookup(mapping, row, occurrence, fields=KEY_FIELDS):
    """행에 맞는 매핑 행 (연도 행 우선, 없으면 연도 빈칸 행). 없으면 None."""
    if "bsns_year" in fields:
        return mapping.get(mapping_key(row, occurrence, fields)) or mapping.get(mapping_key(row, occurrence, fields, ""))
    return mapping.get(mapping_key(row, occurrence, fields))


def check_mapping(chart, mapping):
    """매핑의 std_id 가 차트에 있는지, role·flip 값이 맞는지. 문제 목록."""
    out = [f"{k}: std_id {m['std_id']} 가 차트에 없음" for k, m in mapping.items()
           if m["std_id"] and m["std_id"] not in chart.nodes]
    for k, m in mapping.items():
        if m.get("role", "value") not in ("value", "check_only"):
            out.append(f"{k}: role {m['role']!r}")
        if str(m.get("flip", "1")) not in ("1", "-1"):
            out.append(f"{k}: flip {m['flip']!r}")
    return out


def _role(m):
    return m.get("role") or "value"


def _flip(m):
    return -1 if str(m.get("flip", "1")).strip() == "-1" else 1


# ---------------------------------------------------------------- 합계

def rollup(chart, lines):
    """lines: [(std_id, amount, ref)] -> {std_id: {"reported": (금액, [ref]) | None, "rollup": (금액, [ref]) | None}}.

    값이 하나도 없는 노드는 결과에 없다. 노드 값 = 보고값 우선, 없으면 합계. 합계 = Σ(sign × 값이 있는 자식 값).
    공식 노드는 "rollup" 칸에 공식 값을 둔다 (피연산자 값이 모두 있을 때만). 주당 노드는 보고값만 있다.
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
            roll = (sum(chart.sign(k) * v[0] for k, v in kids), [r for _, v in kids for r in v[1]])
        rep = reported.get(sid)
        if rep is None and roll is None:
            return None
        out[sid] = {"reported": rep, "rollup": roll}
        return rep if rep is not None else roll

    for root in chart.roots:
        if chart.kind(root) != "formula":
            visit(root)
    for sid, terms in chart.formulas.items():
        vals = [(out.get(t), s) for t, s in terms]
        roll = None
        if all(v is not None for v, _ in vals):
            picked = [(v["reported"] or v["rollup"], s) for v, s in vals]
            roll = (sum(s * p[0] for p, s in picked), [r for p, _ in picked for r in p[1]])
        rep = reported.get(sid)
        if rep is not None or roll is not None:
            out[sid] = {"reported": rep, "rollup": roll}
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


def period_start(bsns_year, acc_mt, back):
    """사업보고서 기간의 시작일 = 한 해 전 기말일 다음 날. 결산월 12 이면 그해 1월 1일."""
    prev = datetime.date.fromisoformat(period_end(bsns_year, acc_mt, back + 1))
    return (prev + datetime.timedelta(days=1)).isoformat()


def read_acc_mt(corp_code):
    p = paths.company_json(corp_code)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("acc_mt") or None


def statements(rows, sj_divs=("BS",)):
    """sj_divs 행 -> OrderedDict {(corp_code, bsns_year, reprt_code, fs_div): [행]}. PL 은 IS 와 CIS 를 한 묶음으로."""
    out = OrderedDict()
    for r in rows:
        if r["sj_div"] in sj_divs:
            out.setdefault((r["corp_code"], r["bsns_year"], r["reprt_code"], r["fs_div"]), []).append(r)
    return out


def map_statement(stmt_rows, mapping, fields=KEY_FIELDS):
    """-> (mapped [(행, 매핑 행)], unmapped [행], excluded [(행, 매핑 행)] (std_id 빈칸))."""
    mapped, unmapped, excluded = [], [], []
    for r, occ in with_occurrence(stmt_rows):
        m = lookup(mapping, r, occ, fields)
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
            pre = "-" if chart.sign(k) < 0 else ""
            parts.append(f"{pre}{k}={value(res[k])}")
    return ";".join(parts)


def _refs(v):
    return ";".join(str(i) for i in sorted(v[1])) if v else ""


def standardize(rows, chart, mapping, acc_mt=None, spec=BS):
    """as-reported 행 -> (표준화 행, 점검 행, 문제 목록). acc_mt: {corp_code: 결산월}, 없으면 company json 에서 읽는다."""
    acc_mt = dict(acc_mt or {})
    out, checks, problems = [], [], check_mapping(chart, mapping)
    by_stmt = {}            # (corp, fs, year) -> {period: res}
    cbases = {}
    for (corp, year, reprt, fs), srows in statements(rows, spec.sj_divs).items():
        mapped, unmapped, excluded = map_statement(srows, mapping, spec.key_fields)
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
        currency = Counter(r.get("currency", "") for r in srows).most_common(1)[0][0]
        for pname, prefix, back in PERIODS:
            lines, check_lines = [], []
            for r, m in mapped:
                a = extract.amount(r, f"{prefix}_amount")
                if a is not None:
                    item = (m["std_id"], a * _flip(m), int(r["raw_index"]))
                    (check_lines if _role(m) == "check_only" else lines).append(item)
            if not lines and not check_lines:
                continue
            res = rollup(chart, lines)
            problems.extend(_per_share_leaks(chart, res, corp, year, fs, pname))
            pend = period_end(year, acc_mt[corp], back) if acc_mt.get(corp) else ""
            base = {"corp_code": corp, "stock_code": first["stock_code"], "company": first["company"],
                    "rcept_no": first["rcept_no"], "rcept_dt": first["rcept_dt"], "bsns_year": year,
                    "reprt_code": reprt, "fs_div": fs, "period": pname, "period_nm": first[f"{prefix}_nm"],
                    "period_start": period_start(year, acc_mt[corp], back) if acc_mt.get(corp) else "",
                    "period_end": pend}
            for sid in chart.nodes:
                if sid not in res:
                    continue
                kind = chart.kind(sid)
                for source in ("reported", "rollup"):
                    v = res[sid][source]
                    if v is None:
                        continue
                    row = {**base, "std_id": sid, "name_ko": chart.nodes[sid]["name_ko"],
                           "depth": chart.depth(sid), "kind": kind, "amount": v[0],
                           "unit": f"{currency}/주" if kind == "per_share" else currency,
                           "source": "formula" if (source == "rollup" and kind == "formula") else source,
                           "n_lines": len(v[1]), "raw_file": raw_files[0], "raw_index": _refs(v)}
                    out.append({c: row[c] for c in spec.columns})
            cbase = {"corp_code": corp, "company": first["company"], "bsns_year": year, "fs_div": fs,
                     "period": pname, "period_end": pend}
            checks.extend(_checks(chart, res, cbase, fs, spec))
            checks.extend(_check_only_checks(chart, res, cbase, check_lines))
            by_stmt.setdefault((corp, fs, year), {})[pname] = res
            cbases[(corp, fs, year, pname)] = cbase
    if spec.restatement:
        checks.extend(_restatement_checks(chart, by_stmt, cbases))
    return out, checks, problems


def _per_share_leaks(chart, res, corp, year, fs, pname):
    """주당 노드의 값이 다른 노드의 합계·공식에 들어갔는지 (차트 검사로 막지만 결과에서도 확인)."""
    ps = {sid for sid in chart.nodes if chart.kind(sid) == "per_share"}
    if not ps:
        return []
    out = []
    for sid, r in res.items():
        if chart.kind(sid) == "per_share" and r["rollup"] is not None:
            out.append(f"{corp} {year} {fs} {pname}: 주당 노드 {sid} 에 합계가 생김")
        if r["rollup"] is not None and chart.kind(sid) != "per_share":
            leaked = set(r["rollup"][1]) & {i for p in ps if p in res for i in res[p]["reported"][1]}
            if leaked:
                out.append(f"{corp} {year} {fs} {pname}: {sid} 합계에 주당 줄 {sorted(leaked)} 이 들어감")
    return out


def _check_row(cbase, check, sid, reported, computed, parts, refs):
    if reported is None or computed is None:
        status, diff = "missing", ""
    else:
        diff = reported - computed
        status = "pass" if diff == 0 else "fail"
    return {**cbase, "check": check, "std_id": sid, "reported": "" if reported is None else reported,
            "computed": "" if computed is None else computed, "diff": diff, "status": status, "parts": parts,
            "raw_index": refs}


def _checks(chart, res, cbase, fs, spec=BS):
    rows = []
    required = spec.required + (spec.required_cfs if fs == "CFS" else [])
    for sid in chart.nodes:
        if chart.kind(sid) == "formula":
            continue
        r = res.get(sid)
        has_both = r is not None and r["reported"] is not None and r["rollup"] is not None
        if not has_both and sid not in required:
            continue
        rep = r["reported"][0] if r and r["reported"] else None
        roll = r["rollup"][0] if r and r["rollup"] else None
        refs = _refs(r["rollup"]) if r else ""
        rows.append(_check_row(cbase, "보고값=하위합계", sid, rep, roll, _fmt_parts(chart, res, sid), refs))
    for sid, terms in chart.formulas.items():
        r = res.get(sid)
        if r is None or r["reported"] is None:
            continue
        roll = r["rollup"][0] if r["rollup"] else None
        parts = ";".join(f"{'-' if s < 0 else ''}{t}={value(res.get(t))}" for t, s in terms)
        rows.append(_check_row(cbase, "보고값=공식", sid, r["reported"][0], roll, parts, _refs(r["rollup"])))
    for name, target, terms, tsource, req in spec.identities:
        t = res.get(target)
        tv = (t["reported"][0] if t and t["reported"] else None) if tsource == "reported" else value(t)
        pv = [(k, s, value(res.get(k))) for k, s in terms]
        must = req == "all" or (req == "cfs" and fs == "CFS")
        if not must and (tv is None or any(v is None for _, _, v in pv)):
            continue
        comp = sum(s * v for _, s, v in pv) if all(v is not None for _, _, v in pv) else None
        rows.append(_check_row(cbase, name, target, tv, comp, ";".join(f"{k}={v}" for k, _, v in pv), ""))
    return rows


def _check_only_checks(chart, res, cbase, check_lines):
    """check_only 줄 = 노드 값 (그 줄은 더하지 않는다)."""
    rows = []
    for sid, amt, ref in check_lines:
        r = res.get(sid)
        src = ("reported" if r["reported"] else "rollup") if r else ""
        rows.append(_check_row(cbase, "check_only=노드값", sid, amt, value(r), f"{sid}({src})={value(r)}", str(ref)))
    return rows


RESTATEMENT_PAIRS = [("prior", 1, "전기=전년보고서당기"), ("prior2", 2, "전전기=2년전보고서당기")]


def _restatement_checks(chart, by_stmt, cbases):
    """N 년 보고서의 전기(전전기) 열 = N-1 (N-2) 년 보고서의 당기 열, 표준화 노드 값 단위. 차이는 재작성·재분류 (고치지 않음)."""
    rows = []
    for (corp, fs, year), periods in sorted(by_stmt.items()):
        for pname, back, check in RESTATEMENT_PAIRS:
            old = by_stmt.get((corp, fs, str(int(year) - back)), {}).get("current")
            new = periods.get(pname)
            if old is None or new is None:
                continue
            cbase = cbases[(corp, fs, year, pname)]
            for sid in chart.nodes:
                a, b = value(new.get(sid)), value(old.get(sid))
                if a is None and b is None:
                    continue
                parts = (f"{year}보고서 {pname}={'' if a is None else a} ({_src(new.get(sid))}); "
                         f"{int(year) - back}보고서 current={'' if b is None else b} ({_src(old.get(sid))})")
                row = _check_row(cbase, check, sid, a, b, parts, "")
                if a is None or b is None:
                    row["status"] = "one_side"        # 한쪽 보고서에만 값: 표시 방식 차이, 금액 차이가 아님
                rows.append(row)
    return rows


# 알려진 발견 (고치지 않는다). (corp_code, bsns_year, fs_div, period, check, std_id) -> 설명
KNOWN_FINDINGS = {
    ("01515323", "2023", "CFS", "prior2", "PL.CIO+PL.CIN=PL.CI", "PL.CI"):
        "LG에너지솔루션 2023 보고서 전전기(2021) 열: 지배 1,195,531 + 비지배 242,842 = 1,438,373 백만원 ≠ 총포괄손익 "
        "1,438,374 백만원 (차이 1백만원). 총포괄손익 = 당기순이익 929,868 + 기타포괄손익 508,506 은 맞고, 당기순이익 귀속도 맞는다. "
        "공시 금액이 백만원 단위라 반올림 차이로 보이지만 원문으로 확인하지 않았다",
}


def unexplained_failures(checks):
    """status=fail 이면서 KNOWN_FINDINGS 에 없는 점검."""
    return [c for c in checks if c["status"] == "fail"
            and (c["corp_code"], c["bsns_year"], c["fs_div"], c["period"], c["check"], c["std_id"]) not in KNOWN_FINDINGS]


def _src(r):
    if r is None:
        return "없음"
    return "reported" if r["reported"] else "rollup"


# ---------------------------------------------------------------- 커버리지

COVERAGE_COLUMNS = ["std_id", "parent", "depth", "kind", "name_ko", "n_mapping_rows", "n_statements", "n_reported",
                    "n_rollup_only", "n_cfs", "n_ofs", "cfs_companies_all_years", "cfs_missing", "all5_cfs",
                    "frontier_cfs"]


def coverage(chart, bs_rows, mapping, statement_keys):
    """노드별 값이 있는 재무제표 수 (당기 열 기준). statement_keys: [(corp_code, company, bsns_year, fs_div)].

    n_rollup_only 는 보고값 없이 합계(또는 공식 값)로만 있는 재무제표 수.
    """
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
                     "n_rollup_only": sum(1 for s in h.values() if "reported" not in s),
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

def _counts(mapping, field):
    return ", ".join(f"{k} {v}" for k, v in sorted(Counter(m.get(field, "") for m in mapping.values()).items()))


def to_markdown(checks, problems, cov_rows, levels, mapping, spec=BS):
    st = Counter(c["status"] for c in checks)
    cmd = "python dart_collect.py --standardize"
    lines = [f"# {spec.title} 표준화 점검 (`{cmd}`)", "",
             f"`{paths.rel(spec.checks_csv)}` 의 요약이다. 매핑은 `{paths.rel(spec.mapping_csv)}`, "
             f"차트는 `{paths.rel(spec.chart_csv)}`.", "",
             f"- 점검 {len(checks)}건: 통과 {st['pass']}, 실패 {st['fail']}, 값 없음 {st['missing']}"
             + (f", 한쪽만 있음(재작성 비교) {st['one_side']}" if spec.restatement else ""),
             f"- 매핑 행 {len(mapping)}개 "
             f"(method: {_counts(mapping, 'method')}; "
             f"confidence: {_counts(mapping, 'confidence')}; "
             f"review: {_counts(mapping, 'review')})"
             + (f"; role: {_counts(mapping, 'role')}; flip: {_counts(mapping, 'flip')}" if spec.name == "PL" else ""),
             f"- 문제 {len(problems)}건 (매핑 없는 줄, std_id 빈칸으로 뺀 줄)", ""]
    by_check = defaultdict(Counter)
    for c in checks:
        by_check[(c["check"], c["std_id"])][c["status"]] += 1
    lines += ["## 점검 종류별", "", "| 점검 | 노드 | 통과 | 실패 | 값 없음 |", "|---|---|---|---|---|"]
    for (ck, sid), cnt in sorted(by_check.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines.append(f"| {ck} | {sid} | {cnt['pass']} | {cnt['fail']} | {cnt['missing']} |")
    restate = {c for _, _, c in RESTATEMENT_PAIRS}
    bad = [c for c in checks if c["status"] != "pass" and c["check"] not in restate]
    lines += ["", "## 실패·값 없음 전체" + (" (재작성 비교 제외)" if spec.restatement else ""), ""]
    if not bad:
        lines.append("없음.")
    else:
        lines += ["| 회사 | 연도 | 구분 | 기간 | 점검 | 노드 | 보고 | 계산 | 차이 | 구성 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for c in bad:
            lines.append(f"| {c['company']} | {c['bsns_year']} | {c['fs_div']} | {c['period']} | {c['check']} | "
                         f"{c['std_id']} | {c['reported']} | {c['computed']} | {c['diff']} | {c['parts']} |")
    if spec.restatement:
        rfail = [c for c in checks if c["check"] in restate and c["status"] == "fail"]
        rmiss = [c for c in checks if c["check"] in restate and c["status"] == "one_side"]
        known = [c for c in checks if c["status"] == "fail" and c not in unexplained_failures(checks)]
        lines += ["", "## 알려진 발견 (KNOWN_FINDINGS, 고치지 않음)", ""]
        lines += [f"- {c['company']} {c['bsns_year']} {c['fs_div']} {c['period']} {c['check']}: 차이 {c['diff']}. "
                  f"{KNOWN_FINDINGS[(c['corp_code'], c['bsns_year'], c['fs_div'], c['period'], c['check'], c['std_id'])]}"
                  for c in known] or ["없음."]
        lines += ["", f"설명되지 않은 실패: {len(unexplained_failures(checks))}건"]
        lines += ["", "## 재작성·재분류 (N 년 보고서 전기·전전기 열 vs 앞선 보고서 당기 열, 표준화 노드 값)", "",
                  "차이는 고치지 않고 적는다. status=one_side 는 한쪽 보고서에만 그 노드 값이 있는 경우 (표시 방식 차이).", ""]
        if not rfail:
            lines.append("금액 차이 없음.")
        else:
            lines += ["| 회사 | 구분 | 비교 | 노드 | N년 보고서 값 | 앞선 보고서 값 | 차이 | 구성 |", "|---|---|---|---|---|---|---|---|"]
            for c in rfail:
                lines.append(f"| {c['company']} | {c['fs_div']} | {c['bsns_year']} {c['check']} | {c['std_id']} | "
                             f"{c['reported']} | {c['computed']} | {c['diff']} | {c['parts']} |")
        if rmiss:
            lines += ["", "한쪽에만 값이 있는 노드:", ""]
            for c in rmiss:
                lines.append(f"- {c['company']} {c['fs_div']} {c['bsns_year']} {c['check']} {c['std_id']}: {c['parts']}")
    if spec.name == "PL":
        needs = [m for m in mapping.values() if m.get("review") == "needs_lead"]
        flips = [m for m in mapping.values() if _flip(m) < 0]
        lines += ["", "## 연구 책임 확인 필요 (review=needs_lead)", ""]
        lines += [f"- {m['company']} {m['fs_div']} {m['sj_div']} {m['account_id']} \"{m['account_nm']}\" -> {m['std_id']}: "
                  f"{m['note']}" for m in needs] or ["없음."]
        lines += ["", "## 부호 반대로 공시한 줄 (flip=-1)", ""]
        lines += [f"- {m['company']} {m['fs_div']} {m['sj_div']} {m['bsns_year'] or '모든 연도'} {m['account_id']} "
                  f"\"{m['account_nm']}\" -> {m['std_id']}: {m['note']}" for m in flips] or ["없음."]
        lines += ["", "주당이익(kind=per_share) 노드는 부모·자식이 없고 공식에도 쓰지 않으며 (차트 검사), 결과에서도 어떤 "
                  "합계에 주당 줄이 들어가지 않았음을 확인한다. pl.csv 의 unit 이 KRW/주 다.", ""]
    if problems:
        lines += ["", "## 문제", ""] + [f"- {p}" for p in problems]
    by, deepest_full, _ = levels
    lines += ["", "## 비교 가능성 (연결, 당기 열, 5개사 × 3년 모두 값이 있는 노드)", "",
              "| depth | 노드 수 | 5개사 공통 |", "|---|---|---|"]
    for d in sorted(by):
        lines.append(f"| {d} | {by[d][0]} | {by[d][1]} |")
    if spec.name == "PL":
        common = [r["std_id"] for r in cov_rows if r["all5_cfs"] == "yes"]
        lines += ["", f"5개사 공통 노드 (보고값 또는 합계·공식): {', '.join(common)}", "",
                  "PL 의 depth 0 에는 합산 나무 밖 노드(공식·귀속·주당)도 있어 'depth 별 공통' 은 BS 만큼 뜻이 없다. "
                  "위 공통 노드 목록을 본다."]
    lines += ["", f"모든 노드가 5개사 공통인 가장 깊은 depth: {deepest_full}", "",
              "5개사 공통이 아닌 노드 (빠진 회사:연도):", ""]
    for r in cov_rows:
        if r["all5_cfs"] != "yes":
            lines.append(f"- {r['std_id']} {r['name_ko']} (depth {r['depth']}): {r['cfs_missing']}")
    return "\n".join(lines) + "\n"


def run_spec(spec, rows):
    chart = load_chart(spec.chart_csv)
    mapping = load_mapping(spec.mapping_csv, spec.key_fields)
    out_rows, check_rows, problems = standardize(rows, chart, mapping, spec=spec)
    keys = []
    for (corp, year, reprt, fs), srows in statements(rows, spec.sj_divs).items():
        keys.append((corp, srows[0]["company"], year, fs))
    cov = coverage(chart, out_rows, mapping, keys)
    levels = deepest_common_level(chart, cov)
    collect.write_csv_if_changed(spec.out_csv, spec.columns, out_rows)
    collect.write_csv_if_changed(spec.checks_csv, CHECK_COLUMNS, check_rows)
    collect.write_csv_if_changed(spec.coverage_csv, COVERAGE_COLUMNS, cov)
    md = to_markdown(check_rows, problems, cov, levels, mapping, spec)
    OUT.mkdir(parents=True, exist_ok=True)
    spec.checks_md.write_text(md, encoding="utf-8")
    return {"rows": out_rows, "checks": check_rows, "problems": problems, "coverage": cov, "levels": levels, "md": md,
            "spec": spec}


def run(statements_csv=paths.STATEMENTS_CSV):
    """BS 결과 dict (예전 키 bs 포함). PL 결과는 키 "pl" 아래에 같은 모양으로."""
    rows = collect.read_csv(statements_csv)
    bs = run_spec(BS, rows)
    bs["bs"] = bs["rows"]
    bs["pl"] = run_spec(PL, rows)
    return bs
