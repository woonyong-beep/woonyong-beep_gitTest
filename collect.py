"""가격 데이터 수집 CLI.

사용법 (저장소 루트에서)
    python collect.py                      # watchlist.csv 에 있는 모든 시계열을 받아 갱신
    python collect.py yahoo SPY            # 하나만 받아 갱신. watchlist.csv 에 없으면 덧붙인다
    python collect.py yahoo SPY --name "SPDR S&P 500 ETF" --asset-class etf
    python collect.py --check              # 받지 않고 저장된 파일만 점검 (행 수, 공백, 0 이하 값, 급변)

저장 위치: data/prices/<source>/<symbol>.csv, 목록: data/catalog.csv.
다시 받을 때의 병합 규칙은 collectors/store.py 설명에 있다. 요약하면
- 같은 날짜는 새로 받은 값으로 바꾼다 (Yahoo 조정 종가는 받을 때마다 전체 이력이 새 기준으로 바뀐다).
- 저장본에만 있는 날짜는 지우지 않는다.
- 내용이 같으면 파일을 다시 쓰지 않는다.
받지 못한 시계열은 건너뛰고 오류를 그대로 출력한다. 값을 지어내거나 채우지 않는다.
"""

import argparse
import sys
import time

import collectors
from collectors import checks, http, store

JUMP = {"fx": 0.10, "index": 0.15}      # 하루 급변으로 볼 기준. 그 외 자산은 25%
PAUSE = {"yahoo": 1.0, "coingecko": 3.0, "fred": 1.0}   # 같은 소스 연속 요청 사이 대기 (초)


def check_rows(rows, asset_class):
    if asset_class == "rate":
        return checks.check(rows, jump=float("inf"), allow_nonpositive=True)
    return checks.check(rows, jump=JUMP.get(asset_class, 0.25))


def group_notes(notes):
    """수집기 메모 "YYYY-MM-DD 내용" 을 내용별로 묶는다."""
    out = {}
    for n in notes:
        head, _, rest = n.partition(" ")
        if len(head) == 10 and head[4] == "-":
            out.setdefault(rest, []).append(head)
        else:
            out.setdefault(n, [])
    return out


def update_one(entry, verbose=True):
    """한 시계열을 받아 병합·저장하고 catalog 를 갱신한다. 성공하면 report dict."""
    source, symbol = entry["source"], entry["symbol"]
    mod = collectors.get(source)
    rows, meta = mod.fetch_series(symbol)
    if not rows:
        raise http.FetchError(f"{source} {symbol}: 받은 행이 없음")
    path = store.path_for(source, symbol)
    merged, rep = store.merge(store.read_rows(path), rows, full_history=mod.FULL_HISTORY)
    rep["written"] = store.write_text_if_changed(path, store.to_text(merged))
    name = entry.get("name") or meta.get("name", "")
    asset_class = entry.get("asset_class") or meta.get("asset_class", "")
    store.update_catalog({
        "symbol": symbol, "source": source, "name": name, "asset_class": asset_class,
        "currency": meta.get("currency", ""), "first_date": merged[0]["date"],
        "last_date": merged[-1]["date"], "rows": len(merged), "fetched_at": store.now_utc()})
    rep.update(rows=len(merged), notes=meta.get("notes", []), name=name, asset_class=asset_class,
               check=check_rows(merged, asset_class))
    if verbose:
        state = "파일 갱신" if rep["written"] else "변경 없음"
        print(f"[{source} {symbol}] {state}: 추가 {rep['added']}, 가격 바뀜 {rep['price_changed']}, "
              f"조정값만 바뀜 {rep['adj_changed']}, 같음 {rep['unchanged']}"
              f" (조정값 1e-5 이하 잡음 무시 {rep['adj_noise']}), 저장본에만 있음 {rep['kept_old_only']}")
        print(f"    {checks.summary_line(rep['check'])}")
        for kind, dates in group_notes(rep["notes"]).items():
            if dates:
                print(f"    참고: {kind} {len(dates)}건 (마지막: {', '.join(dates[-3:])})")
            else:
                print(f"    참고: {kind}")
        for w in rep["warnings"]:
            print(f"    경고: {w}")
    return rep


def run_check():
    cat = {(r["source"], r["symbol"]): r for r in store.read_catalog()}
    entries = store.read_watchlist()
    keys = [(e["source"], e["symbol"]) for e in entries]
    keys += [k for k in cat if k not in keys]
    for source, symbol in keys:
        path = store.path_for(source, symbol)
        if not path.exists():
            print(f"[{source} {symbol}] 파일 없음")
            continue
        ac = cat.get((source, symbol), {}).get("asset_class", "")
        print(f"[{source} {symbol}] {checks.summary_line(check_rows(store.read_rows(path), ac))}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="가격 데이터 수집")
    ap.add_argument("source", nargs="?", help=f"소스 ({', '.join(collectors.SOURCES)})")
    ap.add_argument("symbol", nargs="?", help="심볼 (예: SPY, ^GSPC, KRW=X, bitcoin, DTB3)")
    ap.add_argument("--name", default="", help="이름 (watchlist/catalog 에 기록)")
    ap.add_argument("--asset-class", default="", help="자산군 (stock, etf, index, fx, commodity, crypto, rate)")
    ap.add_argument("--no-watchlist", action="store_true", help="하나만 받을 때 watchlist.csv 에 덧붙이지 않음")
    ap.add_argument("--check", action="store_true", help="받지 않고 저장된 파일만 점검")
    a = ap.parse_args(argv)

    if a.check:
        run_check()
        return 0
    if a.source and not a.symbol:
        ap.error("소스와 심볼을 함께 주어야 한다")
    if a.source:
        entries = [{"source": a.source, "symbol": a.symbol, "name": a.name, "asset_class": a.asset_class}]
        for e in store.read_watchlist():
            if (e["source"], e["symbol"]) == (a.source, a.symbol):
                entries = [{**e, **{k: v for k, v in entries[0].items() if v}}]
    else:
        entries = store.read_watchlist()
        if not entries:
            print(f"{store.WATCHLIST} 가 비어 있거나 없다")
            return 1

    failed, last = [], {}
    for e in entries:
        src = e["source"]
        wait = PAUSE.get(src, 1.0) - (time.time() - last.get(src, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            rep = update_one(e)
            if a.source and not a.no_watchlist:
                if store.add_to_watchlist({**e, "name": rep["name"], "asset_class": rep["asset_class"]}):
                    print(f"    watchlist.csv 에 추가함")
        except Exception as ex:      # 하나가 실패해도 나머지는 계속 받는다
            failed.append((src, e["symbol"], f"{type(ex).__name__}: {ex}"))
            print(f"[{src} {e['symbol']}] 실패: {type(ex).__name__}: {ex}")
        last[src] = time.time()

    print(f"\n완료: {len(entries) - len(failed)}개 성공, {len(failed)}개 실패")
    for src, sym, err in failed:
        print(f"  실패 {src} {sym}: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
