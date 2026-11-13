"""fnlttSinglAcntAll 응답 -> as-reported 긴 표 행.

값은 받은 그대로 옮긴다. 금액 문자열은 정수로 바꾸되, 빈칸·"-" 같은 값은 빈칸으로 두고 parse_notes 에 남긴다.
소수점이 있거나 숫자가 아닌 금액은 지어내지 않고 빈칸 + 메모로 남긴다.
"""

import re

COLUMNS = ["corp_code", "stock_code", "company", "rcept_no", "rcept_dt", "bsns_year", "reprt_code", "fs_div",
           "sj_div", "sj_nm", "ord", "account_id", "account_nm", "account_detail",
           "thstrm_nm", "thstrm_amount", "thstrm_add_amount", "frmtrm_nm", "frmtrm_amount", "frmtrm_add_amount",
           "bfefrmtrm_nm", "bfefrmtrm_amount", "currency", "raw_file", "raw_index"]
AMOUNT_FIELDS = ["thstrm_amount", "thstrm_add_amount", "frmtrm_amount", "frmtrm_add_amount", "bfefrmtrm_amount"]
NON_STANDARD = "-표준계정코드 미사용-"
_INT = re.compile(r"^-?\d+$")


def parse_amount(s):
    """'1,234' / '-5' / '' -> (int 또는 None, 메모 또는 None)."""
    if s is None:
        return None, None
    t = str(s).strip().replace(",", "")
    if t in ("", "-"):
        return None, None
    if _INT.match(t):
        return int(t), None
    return None, f"정수가 아닌 금액 {s!r}"


def rows_from_fnltt(obj, fs_div, corp, raw_file, rcept_dates):
    """응답 dict 하나를 행 list 로. corp: {corp_code, stock_code, company}. rcept_dates: {rcept_no: rcept_dt}.

    반환 (rows, notes). 응답이 데이터 없음(013)이면 빈 list.
    """
    rows, notes = [], []
    for i, r in enumerate(obj.get("list", []) or []):
        row = {"corp_code": r.get("corp_code", ""), "stock_code": corp.get("stock_code", ""),
               "company": corp.get("company", ""), "rcept_no": r.get("rcept_no", ""),
               "bsns_year": r.get("bsns_year", ""), "reprt_code": r.get("reprt_code", ""), "fs_div": fs_div,
               "sj_div": r.get("sj_div", ""), "sj_nm": r.get("sj_nm", ""), "ord": r.get("ord", ""),
               "account_id": r.get("account_id", ""), "account_nm": r.get("account_nm", ""),
               "account_detail": r.get("account_detail", ""), "thstrm_nm": r.get("thstrm_nm", ""),
               "frmtrm_nm": r.get("frmtrm_nm", ""), "bfefrmtrm_nm": r.get("bfefrmtrm_nm", ""),
               "currency": r.get("currency", ""), "raw_file": raw_file, "raw_index": i}
        if r.get("corp_code") and corp.get("corp_code") and r["corp_code"] != corp["corp_code"]:
            notes.append(f"{raw_file}#{i}: 응답 corp_code {r['corp_code']} != {corp['corp_code']}")
        row["rcept_dt"] = rcept_dates.get(row["rcept_no"], "")
        if not row["rcept_dt"]:
            notes.append(f"{raw_file}#{i}: rcept_no {row['rcept_no']} 가 공시목록에 없어 rcept_dt 비움")
        for f in AMOUNT_FIELDS:
            v, note = parse_amount(r.get(f))
            row[f] = "" if v is None else v
            if note:
                notes.append(f"{raw_file}#{i} {f}: {note}")
        rows.append(row)
    return rows, notes


def amount(row, field):
    """행의 금액 (int 또는 None). CSV 에서 읽은 문자열 행에도 쓴다."""
    v = row.get(field, "")
    if v == "" or v is None:
        return None
    return int(v)
