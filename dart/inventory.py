"""계정 목록: 서로 다른 (재무제표, account_id, 계정명) 마다 어느 회사가, 어느 해, 연결/별도 중 어디서 쓰는지.

표준화 계정과목 설계(연구 책임의 일)의 근거 자료다. 여기서는 묶거나 고치지 않고 받은 그대로 센다.
계정명은 받은 그대로 두고, 공백만 다른 이름도 따로 센다 (name_norm 열로 묶어 볼 수 있다).
"""

from collections import defaultdict
from statistics import median

from .extract import NON_STANDARD

COLUMNS = ["sj_div", "account_id", "account_nm", "name_norm", "standard_id", "n_companies", "companies",
           "years", "fs_divs", "n_rows", "n_details", "ord_min", "ord_median", "ord_max",
           "ids_for_same_name", "names_for_same_id"]


def _norm(s):
    return "".join(str(s).split())


def build(rows):
    acc = defaultdict(lambda: {"companies": set(), "years": set(), "fs": set(), "n": 0, "details": set(),
                               "ords": []})
    for r in rows:
        k = (r["sj_div"], r["account_id"], r["account_nm"])
        a = acc[k]
        a["companies"].add(r["company"])
        a["years"].add(str(r["bsns_year"]))
        a["fs"].add(r["fs_div"])
        a["n"] += 1
        a["details"].add(r.get("account_detail", ""))
        try:
            a["ords"].append(int(r["ord"]))
        except (TypeError, ValueError):
            pass
    ids_by_name, names_by_id = defaultdict(set), defaultdict(set)
    for sj, aid, nm in acc:
        ids_by_name[(sj, _norm(nm))].add(aid)
        if aid != NON_STANDARD:
            names_by_id[(sj, aid)].add(nm)
    out = []
    for (sj, aid, nm), a in sorted(acc.items(), key=lambda kv: (kv[0][0], -len(kv[1]["companies"]),
                                                                 median(kv[1]["ords"]) if kv[1]["ords"] else 0,
                                                                 kv[0][1], kv[0][2])):
        ords = a["ords"]
        out.append({"sj_div": sj, "account_id": aid, "account_nm": nm, "name_norm": _norm(nm),
                    "standard_id": "N" if aid == NON_STANDARD else ("dart" if aid.startswith("dart_") else
                                                                   ("ifrs" if aid.startswith("ifrs") else "기타")),
                    "n_companies": len(a["companies"]), "companies": ";".join(sorted(a["companies"])),
                    "years": ";".join(sorted(a["years"])), "fs_divs": ";".join(sorted(a["fs"])),
                    "n_rows": a["n"], "n_details": len(a["details"]),
                    "ord_min": min(ords) if ords else "", "ord_median": median(ords) if ords else "",
                    "ord_max": max(ords) if ords else "",
                    "ids_for_same_name": len(ids_by_name[(sj, _norm(nm))]),
                    "names_for_same_id": len(names_by_id[(sj, aid)]) if aid != NON_STANDARD else ""})
    return out


def summary(rows, inv):
    """재무제표별 요약 숫자 dict."""
    companies = sorted({r["company"] for r in rows})
    n_comp = len(companies)
    s = {}
    for sj in sorted({i["sj_div"] for i in inv}):
        items = [i for i in inv if i["sj_div"] == sj]
        rs = [r for r in rows if r["sj_div"] == sj]
        by_id = defaultdict(set)
        for r in rs:
            if r["account_id"] != NON_STANDARD:
                by_id[r["account_id"]].add(r["company"])
        s[sj] = {"accounts": len(items),
                 "all": sum(1 for i in items if i["n_companies"] == n_comp),
                 "one": sum(1 for i in items if i["n_companies"] == 1),
                 "std_ids": len(by_id),
                 "std_ids_all": sum(1 for v in by_id.values() if len(v) == n_comp),
                 "std_ids_one": sum(1 for v in by_id.values() if len(v) == 1),
                 "rows": len(rs),
                 "rows_nonstd": sum(1 for r in rs if r["account_id"] == NON_STANDARD),
                 "rows_dart": sum(1 for r in rs if r["account_id"].startswith("dart_")),
                 "rows_ifrs": sum(1 for r in rs if r["account_id"].startswith("ifrs")),
                 "companies": {c: sum(1 for i in items if c in i["companies"].split(";")) for c in companies}}
    return s


def summary_text(rows, inv):
    s = summary(rows, inv)
    companies = sorted({r["company"] for r in rows})
    lines = [f"계정 목록 {len(inv)}개 (재무제표, account_id, 계정명 조합), 회사 {len(companies)}곳", "",
             "| 재무제표 | 조합 수 | 5곳 모두 | 1곳만 | 표준 id 수 | 표준 id 5곳 모두 | 표준 id 1곳만 | 행 수 | 미사용 표시 행 | dart_ 행 | ifrs 행 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sj, v in s.items():
        lines.append(f"| {sj} | {v['accounts']} | {v['all']} | {v['one']} | {v['std_ids']} | {v['std_ids_all']} | "
                     f"{v['std_ids_one']} | {v['rows']} | {v['rows_nonstd']} | {v['rows_dart']} | {v['rows_ifrs']} |")
    lines += ["", "회사별 조합 수: " + "; ".join(
        f"{sj} " + ", ".join(f"{c} {n}" for c, n in v["companies"].items()) for sj, v in s.items())]
    return "\n".join(lines)
