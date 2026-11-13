"""DART 재무제표 수집 CLI (파일럿).

사용법 (저장소 루트에서, 환경 변수 DART_API_KEY 필요)
    python dart_collect.py                     # dart_watchlist.csv 전체, 2023~2025 사업보고서, 연결·별도
    python dart_collect.py --years 2021-2025   # 연도 범위 바꾸기
    python dart_collect.py --check             # 받지 않고 저장된 표만 점검 -> data/dart/checks.csv, checks.md
    python dart_collect.py --inventory         # 받지 않고 계정 목록 -> data/dart/account_inventory.csv
    python dart_collect.py --doc-probe         # 삼성전자 원문 문서에서 연결 재무상태표 시험 추출 -> data/dart/doc_probe.md
    python dart_collect.py --standardize       # 받지 않고 재무상태표 표준화·대사 -> data/dart/standardized/

받은 응답은 data/dart/raw/ 에 캐시하고, 캐시가 있으면 다시 받지 않는다. 공시목록을 새로 받으려면
data/dart/raw/list/ 의 해당 파일을 지운다. 값을 지어내거나 채우지 않는다. 없는 재무제표는 없다고 출력한다.
"""

import argparse
import sys

from dart import checks, client as dclient, collect, doc_probe, extract, inventory, paths, standardize


def parse_years(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def run_fetch(args):
    entries = collect.read_watchlist()
    if args.only:
        entries = [e for e in entries if e["name"] in args.only or e["stock_code"] in args.only]
    c = dclient.Client()
    try:
        res = collect.collect(c, entries, parse_years(args.years), tuple(args.reprt.split(",")),
                              tuple(args.fs.split(",")))
    except dclient.DartFatal as e:
        print(f"중단: {e}  (요청 {c.calls}회)")
        return 2
    w1 = collect.write_csv_if_changed(paths.STATEMENTS_CSV, extract.COLUMNS, res["rows"])
    w2 = collect.write_csv_if_changed(paths.FILINGS_CSV, collect.FILING_COLUMNS, res["filings"])
    w3 = collect.write_large_manifest()
    print(f"\n{paths.rel(paths.STATEMENTS_CSV)}: {len(res['rows'])}행 ({'갱신' if w1 else '변경 없음'})")
    print(f"{paths.rel(paths.FILINGS_CSV)}: {len(res['filings'])}행 ({'갱신' if w2 else '변경 없음'})")
    print(f"{paths.rel(paths.LARGE_MANIFEST)}: {'갱신' if w3 else '변경 없음'}")
    for n in res["notes"][:50]:
        print(f"  메모: {n}")
    if len(res["notes"]) > 50:
        print(f"  메모 {len(res['notes']) - 50}건 더 있음")
    for m in res["missing"]:
        print(f"  없음: {m}")
    print(f"API 요청 {c.calls}회, 캐시 사용 {c.cache_hits}회")
    return 0


def run_check():
    rows = collect.read_csv(paths.STATEMENTS_CSV)
    results = checks.run_all(rows)
    collect.write_csv_if_changed(paths.CHECKS_CSV, checks.COLUMNS, results)
    md = checks.to_markdown(results)
    paths.CHECKS_MD.write_text(md, encoding="utf-8")
    print(md)
    return 0


def run_inventory():
    rows = collect.read_csv(paths.STATEMENTS_CSV)
    inv = inventory.build(rows)
    collect.write_csv_if_changed(paths.INVENTORY_CSV, inventory.COLUMNS, inv)
    print(inventory.summary_text(rows, inv))
    return 0


def run_standardize():
    res = standardize.run()
    st = {s: sum(1 for c in res["checks"] if c["status"] == s) for s in ("pass", "fail", "missing")}
    print(f"{paths.rel(standardize.BS_CSV)}: {len(res['bs'])}행")
    print(f"{paths.rel(standardize.CHECKS_CSV)}: 점검 {len(res['checks'])}건 (통과 {st['pass']}, 실패 {st['fail']}, "
          f"값 없음 {st['missing']})")
    print(f"{paths.rel(standardize.COVERAGE_CSV)}, {paths.rel(standardize.CHECKS_MD)}")
    for p in res["problems"]:
        print(f"  문제: {p}")
    for c in res["checks"]:
        if c["status"] != "pass":
            print(f"  {c['status']}: {c['company']} {c['bsns_year']} {c['fs_div']} {c['period']} {c['check']} "
                  f"{c['std_id']} 보고 {c['reported']} 계산 {c['computed']} 차이 {c['diff']}")
    return 0 if st["fail"] == 0 and st["missing"] == 0 and not res["problems"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description="OpenDART 재무제표 수집 (파일럿)")
    p.add_argument("--years", default="2023-2025", help="사업연도 (예: 2023-2025 또는 2021,2023)")
    p.add_argument("--reprt", default="11011", help="보고서 코드 (11011 사업, 11012 반기, 11013 1분기, 11014 3분기)")
    p.add_argument("--fs", default="CFS,OFS", help="CFS 연결, OFS 별도")
    p.add_argument("--only", nargs="*", help="이 회사들만 (이름 또는 종목코드)")
    p.add_argument("--check", action="store_true", help="받지 않고 저장된 표 점검")
    p.add_argument("--inventory", action="store_true", help="받지 않고 계정 목록 만들기")
    p.add_argument("--doc-probe", action="store_true", help="삼성전자 원문 문서 시험 추출 (원문 zip 이 없으면 받는다)")
    p.add_argument("--standardize", action="store_true", help="받지 않고 재무상태표 표준화·대사 (data/dart/standardized/)")
    args = p.parse_args(argv)
    if args.doc_probe:
        c = dclient.Client(timeout=600)
        print(doc_probe.run(c, log=lambda s: None))
        print(f"API 요청 {c.calls}회, 캐시 사용 {c.cache_hits}회")
        return 0
    if args.check or args.inventory or args.standardize:
        rc = 0
        if args.check:
            rc |= run_check()
        if args.inventory:
            rc |= run_inventory()
        if args.standardize:
            rc |= run_standardize()
        return rc
    return run_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
