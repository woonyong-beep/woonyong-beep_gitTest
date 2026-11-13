"""docs/dart-data.js (웹 페이지 3번 탭 "재무제표 탐색" 이 쓰는 데이터) 를 DART 표준화 CSV 에서 만든다.

입력 (모두 읽기만 한다)
  data/dart/standard/accounts_bs.csv, accounts_pl.csv   표준 계정과목 트리
  data/dart/standard/mapping_bs.csv, mapping_pl.csv     as-reported 줄 -> 표준 노드 매핑
  data/dart/standardized/bs.csv, pl.csv                 표준화 값 (period=current 만 쓴다)
  data/dart/standardized/bs_checks.csv, pl_checks.csv   대사 점검
  data/dart/extracted/statements.csv, filings.csv       as-reported 줄, 공시 목록

형식 (docs/dart.js 가 읽는다)
  window.DART = {
    "meta": {...},
    "companies": [[corp_code, 회사명, 종목코드], ...],
    "years": ["2023", "2024", "2025"],
    "charts": {"BS"|"PL": [[std_id, parent, sign, name_ko, name_en, kind, formula, note], ...]}  (파일 순서),
    "maps": {"BS"|"PL": [[std_id, role, flip, method, confidence, review, note, bsns_year, occurrence], ...]},
    "st": {"<corp_code>|<CFS|OFS>|<연도>": {
        "rcept_no", "rcept_dt", "report_nm", "raw_file",
        "lines": [[raw_index, sj_div, account_id ("" = 표준계정코드 미사용), account_nm, 당기 금액(공시 그대로), 재무제표("BS"|"PL"), maps 번호], ...],
        "BS"|"PL": {std_id: [보고값 | null, 합계·공식 값 | null]},
        "checks": [[재무제표, 점검, std_id, status, reported, computed, diff], ...]   (당기 열 점검)
    }},
    "summary": {"BS"|"PL": {"total", "status": {...}, "by_check": [[점검, 통과, 실패, 값 없음, 한쪽만]], "findings": [...]}}
  };
- 사업연도마다 그 해 보고서의 당기(thstrm) 열만 싣는다 (period=current).
- 금액은 원 단위 정수 그대로 JSON 정수로 쓴다 (최대 약 6e14 로 JS 배정밀도에서 정확하다). 반올림하지 않는다.
- 값이 없는 노드는 싣지 않는다 (0 으로 채우지 않는다).
- 만들면서 확인한다: 매핑으로 다시 고른 보고 줄의 합(× flip) 과 트리 합계가 bs.csv / pl.csv 의 amount·raw_index 와
  정확히 같아야 한다. 다르면 오류로 멈춘다 (웹 페이지가 출처 패널에 보여 주는 줄이 실제로 더한 줄과 같다는 보증).

실행 (저장소 루트에서): python tools/make_web_dart.py
          확인만:       python tools/make_web_dart.py --check   (파일이 지금 만든 것과 같은지)
"""

import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dart import standardize as S  # noqa: E402  (매핑 키·occurrence 규칙과 알려진 발견을 그대로 쓴다)

DART = ROOT / "data" / "dart"
OUT = ROOT / "docs" / "dart-data.js"
FETCHED = "2026-11-13"        # OpenDART 에서 받은 날
NO_ID = "-표준계정코드 미사용-"
SPECS = {"BS": S.BS, "PL": S.PL}
RESTATE = {c for _, _, c in S.RESTATEMENT_PAIRS}


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def chart_rows(spec):
    rows = read(spec.chart_csv)
    return [[r["std_id"], r.get("parent", ""), -1 if (r.get("sign") or "").strip() == "-1" else 1, r["name_ko"],
             r.get("name_en", ""), r.get("kind", ""), r.get("formula", ""), r.get("note", "")] for r in rows]


def build():
    statements = read(DART / "extracted" / "statements.csv")
    filings = {f["rcept_no"]: f for f in read(DART / "extracted" / "filings.csv")}
    watch = read(ROOT / "dart_watchlist.csv")
    companies = [[w["corp_code"], w["name"], w["stock_code"]] for w in watch]
    years = sorted({r["bsns_year"] for r in statements})

    charts, maps, map_index = {}, {}, {}
    chart_obj = {}
    for name, spec in SPECS.items():
        charts[name] = chart_rows(spec)
        chart_obj[name] = S.load_chart(spec.chart_csv)
        maps[name] = []
        map_index[name] = {}

    st = OrderedDict()
    # ---------------------------------------------------------------- as-reported 줄 (당기 금액이 있는 BS·IS·CIS 줄)
    for name, spec in SPECS.items():
        mapping = S.load_mapping(spec.mapping_csv, spec.key_fields)
        for (corp, year, reprt, fs), srows in S.statements(statements, spec.sj_divs).items():
            key = f"{corp}|{fs}|{year}"
            first = srows[0]
            f = filings.get(first["rcept_no"], {})
            s = st.setdefault(key, {"rcept_no": first["rcept_no"], "rcept_dt": first["rcept_dt"],
                                    "report_nm": f.get("report_nm", ""), "raw_file": first["raw_file"],
                                    "lines": [], "BS": {}, "PL": {}, "checks": []})
            if s["raw_file"] != first["raw_file"] or s["rcept_no"] != first["rcept_no"]:
                raise SystemExit(f"{key}: BS 와 PL 의 원본 파일·접수번호가 다르다")
            for r, occ in S.with_occurrence(srows):
                amt = r["thstrm_amount"]
                if amt == "":
                    continue
                m = S.lookup(mapping, r, occ, spec.key_fields)
                if m is None or not m["std_id"]:
                    raise SystemExit(f"{key}: 매핑 없는 줄 {r['account_id']} {r['account_nm']}")
                mk = tuple(m[k] for k in spec.key_fields)
                if mk not in map_index[name]:
                    map_index[name][mk] = len(maps[name])
                    maps[name].append([m["std_id"], m.get("role") or "value", -1 if str(m.get("flip", "1")).strip() == "-1" else 1,
                                       m["method"], m["confidence"], m["review"], m["note"], m.get("bsns_year", ""),
                                       int(m["occurrence"])])
                s["lines"].append([int(r["raw_index"]), r["sj_div"], "" if r["account_id"] == NO_ID else r["account_id"],
                                   r["account_nm"], int(amt), name, map_index[name][mk]])
    for s in st.values():
        s["lines"].sort(key=lambda l: l[0])

    # ---------------------------------------------------------------- 표준화 값 (당기)
    for name, spec in SPECS.items():
        for r in read(spec.out_csv):
            if r["period"] != "current":
                continue
            key = f"{r['corp_code']}|{r['fs_div']}|{r['bsns_year']}"
            v = st[key][name].setdefault(r["std_id"], [None, None])
            slot = 0 if r["source"] == "reported" else 1
            if v[slot] is not None:
                raise SystemExit(f"{key} {r['std_id']} {r['source']}: 두 번 나온다")
            v[slot] = int(r["amount"])
            v.append((slot, r["raw_index"]))
    # 확인: 보고 줄과 합계가 CSV 와 정확히 같은지 (웹 페이지가 하는 계산과 같은 방법으로)
    for key, s in st.items():
        for name in SPECS:
            verify(key, s, name, chart_obj[name], maps[name])
            s[name] = OrderedDict((sid, v[:2]) for sid, v in sorted(s[name].items(),
                                                                       key=lambda kv: list(chart_obj[name].nodes).index(kv[0])))

    # ---------------------------------------------------------------- 점검
    summary = {}
    for name, spec in SPECS.items():
        rows = read(spec.checks_csv)
        st_count = Counter(r["status"] for r in rows)
        by = OrderedDict()
        for r in rows:
            c = by.setdefault(r["check"], Counter())
            c[r["status"]] += 1
            if r["period"] == "current" and r["check"] not in RESTATE:
                key = f"{r['corp_code']}|{r['fs_div']}|{r['bsns_year']}"
                st[key]["checks"].append([name, r["check"], r["std_id"], r["status"], num(r["reported"]),
                                          num(r["computed"]), num(r["diff"])])
        findings = []
        for r in rows:
            if r["status"] != "fail":
                continue
            k = (r["corp_code"], r["bsns_year"], r["fs_div"], r["period"], r["check"], r["std_id"])
            findings.append({"company": r["company"], "bsns_year": r["bsns_year"], "fs_div": r["fs_div"],
                             "period": r["period"], "period_end": r["period_end"], "check": r["check"],
                             "std_id": r["std_id"], "reported": num(r["reported"]), "computed": num(r["computed"]),
                             "diff": num(r["diff"]), "parts": r["parts"], "known": S.KNOWN_FINDINGS.get(k, "")})
        summary[name] = {"total": len(rows), "status": dict(sorted(st_count.items())),
                         "by_check": [[k, c["pass"], c["fail"], c["missing"], c["one_side"]] for k, c in by.items()],
                         "findings": findings, "file": rel(spec.checks_csv)}

    obj = OrderedDict([
        ("meta", {"fetched": FETCHED, "source": "금융감독원 OpenDART fnlttSinglAcntAll (사업보고서 11011)",
                  "period": "current",
                  "files": [rel(p) for p in (S.CHART_CSV, S.PL_CHART_CSV, S.MAPPING_CSV, S.PL_MAPPING_CSV, S.BS_CSV,
                                             S.PL_CSV, S.CHECKS_CSV, S.PL_CHECKS_CSV, DART / "extracted" / "statements.csv",
                                             DART / "extracted" / "filings.csv")]}),
        ("companies", companies), ("years", years), ("charts", charts), ("maps", maps), ("st", st),
        ("summary", summary),
    ])
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return "\n".join([
        "// 자동 생성 파일: tools/make_web_dart.py 가 data/dart/ 의 표준화 CSV 에서 만든 것. 손으로 고치지 않는다.",
        f"// 출처: 금융감독원 OpenDART 에서 {FETCHED} 에 받은 사업보고서 재무제표. 금액은 원 단위 정수 (당기 열).",
        "window.DART = " + body + ";",
    ]) + "\n"


def num(v):
    return None if v == "" else int(v)


def verify(key, s, name, chart, maps):
    """s[name] 의 각 노드: 보고값 = 그 노드에 매핑된 value 줄의 합(× flip), 합계 = 자식 값의 부호 합. raw_index 도 같아야 한다."""
    vals = s[name]
    lines = [l for l in s["lines"] if l[5] == name]
    rep_lines = defaultdict(list)
    for l in lines:
        m = maps[l[6]]
        if m[1] == "value":
            rep_lines[m[0]].append(l)

    def node_val(sid):
        v = vals.get(sid)
        if v is None:
            return None
        return v[0] if v[0] is not None else v[1]

    def leaf_refs(sid):
        v = vals.get(sid)
        if v is None:
            return []
        if v[0] is not None:
            return [l[0] for l in rep_lines[sid]]
        if chart.kind(sid) == "formula":
            return [i for t, _ in chart.formulas[sid] for i in leaf_refs(t)]
        return [i for k in chart.children.get(sid, []) for i in leaf_refs(k)]

    for sid, v in vals.items():
        refs = dict(v[2:])
        if v[0] is not None:
            got = sum(l[4] * maps[l[6]][2] for l in rep_lines[sid])
            if got != v[0] or sorted(l[0] for l in rep_lines[sid]) != idx(refs[0]):
                raise SystemExit(f"{key} {sid}: 보고 줄 재구성 불일치 {got} != {v[0]}")
        if v[1] is not None:
            if chart.kind(sid) == "formula":
                got = sum(sg * node_val(t) for t, sg in chart.formulas[sid])
            else:
                kids = [k for k in chart.children.get(sid, []) if node_val(k) is not None]
                got = sum(chart.sign(k) * node_val(k) for k in kids)
            if got != v[1]:
                raise SystemExit(f"{key} {sid}: 합계 재구성 불일치 {got} != {v[1]}")
            terms = [t for t, _ in chart.formulas[sid]] if chart.kind(sid) == "formula" else chart.children.get(sid, [])
            if sorted(i for t in terms for i in leaf_refs(t)) != idx(refs[1]):
                raise SystemExit(f"{key} {sid}: 합계 원본 줄 재구성 불일치")
    for sid in rep_lines:
        if sid not in vals:
            raise SystemExit(f"{key} {sid}: 매핑된 줄이 있는데 값이 없다")


def idx(s):
    return sorted(int(x) for x in s.split(";")) if s else []


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="쓰지 않고 지금 파일과 같은지만 확인")
    a = ap.parse_args()
    text = build()
    if a.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{OUT.relative_to(ROOT)}: {'같음' if same else '다름'}")
        sys.exit(0 if same else 1)
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text.splitlines()[-1][len("window.DART = "):-1])
    nv = sum(len(s["BS"]) + len(s["PL"]) for s in d["st"].values())
    nl = sum(len(s["lines"]) for s in d["st"].values())
    print(f"{OUT.relative_to(ROOT)} 저장: 재무제표 {len(d['st'])}개, 노드 값 {nv}개, as-reported 줄 {nl}개, "
          f"{OUT.stat().st_size:,} 바이트")


if __name__ == "__main__":
    main()
