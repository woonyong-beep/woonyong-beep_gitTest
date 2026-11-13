"""원문 문서 시험(probe): 삼성전자 사업보고서 원문에서 연결 재무상태표를 뽑아 API 값과 맞춰 본다.

`python dart_collect.py --doc-probe` 가 부른다. 원문 zip 은 data/dart/raw/_large/document/ 에 캐시된다
(커밋하지 않음). 결과: data/dart/doc_probe.md, data/dart/doc_probe_rows.csv
"""

import json

from . import api, document, paths
from .collect import write_csv_if_changed

CORP = "00126380"
# (접수번호, 사업연도, 비교할 API 응답 파일의 연도, API 열 이동) — 이동 0: 같은 보고서 / 1: 다음 해 보고서의 전기·전전기
TARGETS = [
    ("20260310002820", 2025, 2025, 0),
    ("20150331002915", 2014, 2015, 1),
    ("20140331002427", 2013, 2015, 2),
    ("20130401003031", 2012, None, None),
    ("20100331001680", 2009, None, None),
    ("20060331001832", 2005, None, None),
    ("20030331001534", 2002, None, None),
    ("20000330000796", 1999, None, None),
    ("19990403000009", 1998, None, None),
]
ROW_COLUMNS = ["rcept_no", "bsns_year", "row_no", "label", "doc_cur", "doc_prev", "doc_prev2", "result",
               "api_account_id", "api_account_nm", "api_cur", "api_prev", "api_prev2"]


def api_bs_rows(year, shift):
    """fnltt 응답의 CFS BS 행. shift 만큼 열을 당긴다 (1: 전기를 당기 자리로)."""
    obj = json.loads(paths.fnltt_json(CORP, year, "11011", "CFS").read_text(encoding="utf-8"))
    cols = ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"]
    out = []
    for r in obj.get("list", []):
        if r["sj_div"] != "BS":
            continue
        moved = dict(r)
        for i, c in enumerate(cols):
            src = i + shift
            moved[c] = r.get(cols[src], "") if src < len(cols) else ""
        out.append(moved)
    return out, obj["list"][0]["rcept_no"] if obj.get("list") else ""


def diagnose(text, files):
    """추출 실패 원인을 짐작할 사실들: 파일 수, 문서 끝 태그, 마지막 제목, 재무 관련 제목."""
    import re
    titles = [document.cell_text(m.group(1)) for m in re.finditer(r"<TITLE[^>]*>(.*?)</TITLE>", text, re.S)]
    fin = [t for t in titles if "재무" in t or "대차대조표" in t]
    ends = text.rstrip().endswith("</DOCUMENT>")
    return (f"zip 안 파일 {len(files)}개, 문서 끝 </DOCUMENT> {'있음' if ends else '없음(중간에 잘림)'}, "
            f"제목 {len(titles)}개, 마지막 제목 '{titles[-1] if titles else ''}', "
            f"재무 관련 제목 {', '.join(fin[:6]) if fin else '없음'}")


def totals_identity(rows):
    """원문 표 안에서 자산총계 = 부채총계 + 자본총계 인지 (첫 열)."""
    def get(*names):
        for r in rows:
            if r["name_norm"] in names and r["values"] and r["values"][0] is not None:
                return r["values"][0]
        return None
    a, l, e = get("자산총계"), get("부채총계"), get("자본총계")
    if None in (a, l, e):
        return f"판정불가 (자산 {a}, 부채 {l}, 자본 {e})"
    return "통과" if a == l + e else f"실패 (차이 {a - l - e:,})"


def run(client, log=print):
    md = ["# 원문 문서 시험: 삼성전자 연결 재무상태표", "",
          "`python dart_collect.py --doc-probe` 가 만든다. 추출기는 dart/document.py 하나이고 연도마다 고치지 않았다.", "",
          "| 사업연도 | 접수번호 | 본문 인코딩 | 본문 글자 수 | 추출 | 행 | 원문 내 자산=부채+자본 | API 비교 |",
          "|---|---|---|---|---|---|---|---|"]
    all_rows, details = [], []
    for rcept_no, year, api_year, shift in TARGETS:
        data, _ = api.document(client, rcept_no)
        files = document.read_zip(data)
        text, enc = document.main_text(files, rcept_no)
        res, err = document.extract_bs(text)
        if err:
            diag = diagnose(text, files)
            md.append(f"| {year} | {rcept_no} | {enc} | {len(text):,} | 실패: {err}. {diag} | — | — | — |")
            continue
        ident = totals_identity(res["rows"])
        cmp_txt = "API 없음 (fnlttSinglAcntAll 은 2015 사업연도부터)"
        if api_year is not None:
            arows, arno = api_bs_rows(api_year, shift)
            cmp, s = document.compare_with_api(res["rows"], arows, ncols=3 - shift)
            where = "같은 보고서" if shift == 0 else f"{api_year}년 보고서({arno})의 {'전기' if shift == 1 else '전전기'} 열"
            cmp_txt = (f"{where}: 숫자 있는 원문 행 {s['doc_rows_with_number']}, 이름 짝 {s['matched']}, "
                       f"비교 열 {3 - shift}개, 금액 일치 {s['equal']}, 금액 다름 {s['differ']}, 원문만 {s['doc_unmatched']}, "
                       f"API만 {len(s['api_unmatched'])}")
            for c in cmp:
                all_rows.append({"rcept_no": rcept_no, "bsns_year": year, **{k: c.get(k, "") for k in ROW_COLUMNS
                                                                             if k not in ("rcept_no", "bsns_year")}})
            bad = [c for c in cmp if c["result"] in ("금액다름", "짝없음")]
            details.append((year, rcept_no, bad, s["api_unmatched"]))
        else:
            for r in res["rows"]:
                v = r["values"] + [None] * 3
                all_rows.append({"rcept_no": rcept_no, "bsns_year": year, "row_no": r["row_no"], "label": r["label"],
                                 "doc_cur": v[0], "doc_prev": v[1], "doc_prev2": v[2], "result": "비교안함"})
        md.append(f"| {year} | {rcept_no} | {enc} | {len(text):,} | 단위 {res['unit_text']}, 머리글 "
                  f"{' / '.join(h for h in res['header'] if h)} | {len(res['rows'])} | {ident} | {cmp_txt} |")
        log(md[-1])
    for year, rno, bad, api_left in details:
        md += ["", f"## {year} ({rno}) 불일치", ""]
        if not bad and not api_left:
            md.append("없음")
        for c in bad:
            md.append(f"- {c['result']}: 원문 '{c['label']}' {c['doc_cur']} / {c['doc_prev']} / {c['doc_prev2']}"
                      f" vs API {c['api_account_nm']} ({c['api_account_id']}) {c['api_cur']} / {c['api_prev']} / "
                      f"{c['api_prev2']}")
        for aid, nm in api_left:
            md.append(f"- API에만 있음: {nm} ({aid})")
    for k in ("doc_cur", "doc_prev", "doc_prev2", "api_cur", "api_prev", "api_prev2"):
        for r in all_rows:
            if r.get(k) is None:
                r[k] = ""
    write_csv_if_changed(paths.DATA / "doc_probe_rows.csv", ROW_COLUMNS, all_rows)
    (paths.DATA / "doc_probe.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return "\n".join(md)
