"""파일럿 범위(dart_watchlist.csv)를 받아 raw 에 캐시하고 extracted 표를 만든다.

다시 돌려도 캐시가 있는 응답은 받지 않는다. extracted 표는 캐시된 raw 에서 매번 새로 만들고,
내용이 같으면 파일을 다시 쓰지 않는다.
"""

import csv
import hashlib
import io
import re

from . import api, extract, paths

ANNUAL_RE = re.compile(r"^(\[[^\]]+\])?\s*사업보고서\s*\((\d{4})\.(\d{2})\)")
FILING_COLUMNS = ["corp_code", "stock_code", "company", "bsns_year", "report_nm", "rcept_no", "rcept_dt", "rm",
                  "prefix", "used_by_fnltt", "list_file"]


def read_watchlist(path=paths.WATCHLIST):
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("corp_code") and not r["corp_code"].startswith("#")]


def write_csv_if_changed(path, columns, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def verify_corp(client, entry, log):
    """watchlist 의 corp_code 가 corpCode.xml 의 이름·종목코드와 맞는지 확인하고 기업개황을 받는다."""
    codes = {c["corp_code"]: c for c in api.corp_codes(client)}
    c = codes.get(entry["corp_code"])
    if c is None:
        raise ValueError(f"{entry['name']}: corp_code {entry['corp_code']} 가 corpCode.xml 에 없음")
    if c["stock_code"] != entry["stock_code"]:
        raise ValueError(f"{entry['name']}: 종목코드 {entry['stock_code']} != corpCode.xml {c['stock_code']}")
    if c["corp_name"] != entry["name"]:
        log(f"  참고: watchlist 이름 {entry['name']!r}, corpCode.xml 이름 {c['corp_name']!r}")
    api.company(client, entry["corp_code"])
    return c


def annual_filings(rows, corp, list_files):
    """공시목록에서 사업보고서(원본·정정·첨부) 만 골라 bsns_year 를 붙인다."""
    out = []
    for r in rows:
        m = ANNUAL_RE.match(r.get("report_nm", "").strip())
        if not m:
            continue
        out.append({"corp_code": r["corp_code"], "stock_code": corp["stock_code"], "company": corp["name"],
                    "bsns_year": m.group(2), "report_nm": r["report_nm"].strip(), "rcept_no": r["rcept_no"],
                    "rcept_dt": r["rcept_dt"], "rm": r.get("rm", ""), "prefix": (m.group(1) or "").strip("[]"),
                    "used_by_fnltt": "", "list_file": ";".join(paths.rel(p) for p in list_files)})
    return out


def collect(client, entries, years, reprt_codes=("11011",), fs_divs=("CFS", "OFS"), log=print):
    """받기 + extracted 표 만들기. 반환: dict(rows, filings, notes, missing)."""
    all_rows, all_filings, notes, missing = [], [], [], []
    for e in entries:
        log(f"[{e['name']} {e['stock_code']} {e['corp_code']}]")
        verify_corp(client, e, log)
        corp = {"corp_code": e["corp_code"], "stock_code": e["stock_code"], "company": e["name"]}
        bgn, end = f"{min(years)}0101", f"{max(years) + 1}1231"
        lst, files = api.filings(client, e["corp_code"], bgn, end, "A")
        dates = {r["rcept_no"]: r["rcept_dt"] for r in lst}
        fil = annual_filings(lst, e, files)
        used = set()
        for y in years:
            for rc in reprt_codes:
                for fs in fs_divs:
                    obj, path = api.fnltt_all(client, e["corp_code"], y, rc, fs)
                    rows, n = extract.rows_from_fnltt(obj, fs, corp, paths.rel(path), dates)
                    notes.extend(n)
                    if not rows:
                        missing.append((e["name"], y, rc, fs, obj.get("status"), obj.get("message")))
                        log(f"  {y} {rc} {fs}: 데이터 없음 (status {obj.get('status')} {obj.get('message')})")
                        continue
                    rnos = sorted({r["rcept_no"] for r in rows})
                    used.update(rnos)
                    cnt = {}
                    for r in rows:
                        cnt[r["sj_div"]] = cnt.get(r["sj_div"], 0) + 1
                    log(f"  {y} {rc} {fs}: rcept_no {','.join(rnos)} ({rows[0]['rcept_dt']}) "
                        + " ".join(f"{k}={v}" for k, v in cnt.items()))
                    all_rows.extend(rows)
        for f in fil:
            f["used_by_fnltt"] = "Y" if f["rcept_no"] in used else ""
        all_filings.extend(f for f in fil if int(f["bsns_year"]) in set(years) or f["used_by_fnltt"])
    return {"rows": all_rows, "filings": all_filings, "notes": notes, "missing": missing}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_large_manifest():
    """raw/_large 아래 파일 목록 (커밋하지 않는 큰 파일)."""
    rows = []
    for p in sorted(paths.LARGE.rglob("*")):
        if p.is_file() and not p.name.endswith(".tmp"):
            kind = p.parent.name if p.parent != paths.LARGE else p.stem
            rows.append({"path": paths.rel(p), "kind": kind,
                         "rcept_no": p.stem if p.stem.isdigit() else "",
                         "bytes": p.stat().st_size, "sha256": sha256(p)})
    return write_csv_if_changed(paths.LARGE_MANIFEST, ["path", "kind", "rcept_no", "bytes", "sha256"], rows)
