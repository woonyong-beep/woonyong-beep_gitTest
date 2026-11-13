# 가격 데이터 수집과 백테스트

이 저장소는 두 가지 일을 한다.

1. 가격이나 값이 있는 것(주식, ETF, 지수, 환율, 암호화폐, 원자재, 금리)의 일별 데이터를 모아 한 가지 형식으로 저장한다.
2. 그 데이터로 백테스트 프로그램을 쓰고 시험한다.
3. (파일럿) 한국 상장사 재무제표를 DART(금융감독원 전자공시)에서 받아 as-reported 표로 저장한다. 아래 "DART 재무제표" 절.

값을 만들어 내거나 채우지 않는다. 소스가 주지 않은 날은 저장하지 않고, 받지 못한 시계열은 오류를 그대로 보고한다.

## 구성

```
collect.py                 수집 CLI
watchlist.csv              수집 대상 목록 (source, symbol, name, asset_class)
collectors/                소스별 수집기. 모두 fetch(symbol, start=None, end=None) -> rows
  yahoo.py                 Yahoo Finance chart API
  coingecko.py             CoinGecko 공개 API
  fred.py                  FRED (fredgraph.csv)
  http.py                  공통 HTTP 요청 (urllib, 재시도)
  store.py                 CSV 읽기/쓰기, 다시 받을 때의 병합 규칙, catalog
  checks.py                저장된 시계열 점검 (행 수, 공백, 0 이하 값, 급변)
data/
  prices/<source>/<symbol>.csv   시계열 하나 = 파일 하나
  catalog.csv              저장된 시계열 목록
  tqqq_daily_tiingo.csv    예전 교차검증용 Tiingo 조정 종가 (research/backtest_tqqq.py 가 교차검증에만 쓴다)
backtest/
  data.py                  시계열 불러오기, 점검, 여러 자산 날짜 맞추기
  engine.py                일별 루프 백테스터 (미래 정보 차단)
  metrics.py               최종자산, CAGR, 변동성, 샤프, 최대낙폭, 롤링 시작일 분포
  strategies/              매수후보유, N일 분할매수, 무한매수법, 일정비중 리밸런싱
research/                  예전 단발성 분석 스크립트와 그래프
tools/make_web_data.py     docs/tqqq-data.js 를 data/prices/yahoo/TQQQ.csv 에서 만든다
dart_collect.py            DART 재무제표 수집 CLI (파일럿)
dart_watchlist.csv         DART 수집 대상 (corp_code, stock_code, name)
dart/                      OpenDART 클라이언트·추출·점검·계정 목록·원문 시험 추출기
data/dart/                 DART 데이터 (raw, extracted, 점검 결과, 계정 목록). 아래 "DART 재무제표" 절
tests/                     pytest (네트워크 없이 돈다)
docs/                      브라우저용 시뮬레이터 페이지 (자기 파일만 쓴다. TQQQ 가격은 tqqq-data.js)
knowledge/                 작업 규칙 문서
```

### 저장 형식

`data/prices/<source>/<symbol>.csv`

```
date,open,high,low,close,adj_close,volume
2010-02-11,0.20343799889087677,0.21744799613952637,0.20278599858283997,0.21627600491046906,0.2051851898431778,6912000
```

- 날짜는 ISO (`YYYY-MM-DD`), 소스에 없는 칸은 비워 둔다 (CoinGecko·FRED 는 close 만 있다).
- Yahoo 의 open/high/low/close 는 분할만 반영된 가격, adj_close 는 분할과 배당을 모두 반영한 조정 종가다.
- 파일 이름은 심볼 그대로다 (`^GSPC.csv`, `KRW=X.csv`). 셸에서는 따옴표로 감싼다.

`data/catalog.csv`: `symbol, source, name, asset_class, currency, first_date, last_date, rows, fetched_at`
(`fetched_at` 은 마지막으로 받은 시각, UTC).

## 데이터 모으기

```
pip install -r requirements.txt
python collect.py                 # watchlist.csv 전체 갱신
python collect.py yahoo SPY       # 하나만 받기 (watchlist.csv 에 없으면 덧붙인다, --no-watchlist 로 끔)
python collect.py yahoo 069500.KS --name "KODEX 200" --asset-class etf
python collect.py fred DGS10 --name "미국 10년 국채 금리" --asset-class rate
python collect.py --check         # 받지 않고 저장된 파일만 점검
```

### 다시 받을 때 (병합 규칙)

자세한 규칙은 `collectors/store.py` 맨 위 설명에 있다.

- Yahoo 와 FRED 는 매번 **전체 이력**을 다시 받는다. Yahoo 조정 종가는 가장 최근 날을 기준으로 과거를 거꾸로
  조정하므로 새 배당·분할이 생기면 과거 값이 모두 바뀐다. 전체를 다시 받아 같은 날짜는 새 값으로 바꾸므로,
  파일의 adj_close 는 항상 마지막 수집 시점 하나의 조정 기준으로 맞는다. 이런 행은 "조정값만 바뀜" 으로 보고한다.
- Yahoo 는 몇 분 간격으로 받아도 adj_close 를 상대 1e-7 ~ 1.6e-6 정도 다르게 준다. 원래 가격이 같고 차이가
  1e-5 이하이면 저장본 값을 그대로 둔다 (실제 배당 재조정은 가장 작은 것도 약 1e-4).
- 저장본에만 있는 날짜는 지우지 않는다 (CoinGecko 무료는 최근 365일만 주므로 과거를 지키기 위해).
  전체 이력 소스에서 이런 날짜가 생기면 경고한다.
- 결과가 같으면 가격 파일을 다시 쓰지 않는다. 따라서 `python collect.py` 를 두 번 돌려도 가격 파일은 그대로이고
  `catalog.csv` 의 `fetched_at` 만 바뀐다.
- 아직 끝나지 않은 오늘 봉(장중 가격)과 종가가 빈 봉은 저장하지 않는다. 다음 수집 때 들어온다.

## 백테스트 쓰기

전략은 `on_bar(ctx)` 메서드가 있는 객체(또는 함수)다. 엔진은 매 거래일 종가 시점에 전략을 부르고,
전략이 돌려준 주문을 그날 종가에 체결한다 (`lag=1` 이면 다음 거래일 종가).

- `ctx.t`, `ctx.date`, `ctx.dates`: 오늘 번호와 날짜, 오늘까지의 날짜
- `ctx.prices[sym]`: 오늘까지의 가격 배열 (읽기 전용). 내일 이후 값은 들어 있지 않다
- `ctx.cash`, `ctx.shares[sym]`, `ctx.wealth`, `ctx.price(sym)`, `ctx.weight(sym)`
- 돌려주는 값: `None`, `Weights({sym: 비중})` (총자산 대비 목표 비중, 0 은 전량 매도),
  `Trades({sym: 금액})` (현금 금액 매수, 음수는 매도), 또는 이들의 list

**미래 정보 차단**: 전략은 엔진이 가진 원본 가격 배열에 닿지 않는다. `ctx.prices` 는 엔진이 매일 한 칸씩 채우는
별도 버퍼의 읽기 전용 뷰라서, 버퍼 전체(`.base`)를 꺼내도 내일 이후 칸은 비어(NaN) 있다. 체결과 평가는
원본으로 하므로 전략이 버퍼를 고쳐도 결과는 바뀌지 않는다. 금리 시계열도 전날까지 발표된 값만 쓴다.
`tests/test_lookahead.py` 가 미래 가격을 바꿔도 과거 결정이 그대로인지 확인한다.

**무위험 수익**: `rf=0.03` 처럼 숫자면 연율로 거래일마다 `exp(rf/252)` 씩 불어난다. `rf=data.load_rate("fred", "DTB3")`
처럼 금리 시계열(연 %)을 주면 전날 값으로 달력일 수 / 360 단리 이자를 준다 (DTB3 는 할인율 기준이라 근사).
**거래비용**: `cost_bps` (체결 금액 대비 bp, 기본 0).

### 예: 매수후보유, 월간 50:50 리밸런싱, 200일 추세

저장소 루트에 파일을 만들어 `python 파일이름.py` 로 돌린다 (다른 폴더에서는 `PYTHONPATH=.`).

```python
from backtest import data, engine, metrics
from backtest.engine import Weights
from backtest.strategies import BuyAndHold, ConstantWeight

spy = data.load("yahoo", "SPY", start="2005-01-01")
qqq = data.load("yahoo", "QQQ", start="2005-01-01")
dtb3 = data.load_rate("fred", "DTB3")


class Trend:
    """SPY 종가가 200일 평균보다 높으면 SPY 100%, 아니면 현금."""

    def on_bar(self, ctx):
        h = ctx.prices["SPY"]                    # t 일까지의 가격만 들어 있다
        if len(h) < 200:
            return None
        return Weights({"SPY": 1.0 if h[-1] > h[-200:].mean() else 0.0})


for name, strat, d in [("SPY 매수후보유", BuyAndHold("SPY"), spy),
                       ("SPY/QQQ 50:50 월간", ConstantWeight({"SPY": 0.5, "QQQ": 0.5}, every=21), [spy, qqq]),
                       ("SPY 200일 추세", Trend(), spy)]:
    r = engine.run(strat, d, rf=dtb3, cost_bps=5)
    m = metrics.summary(r, budget=100)
    print(f"{name:<18} 최종 {m['final']:8.1f}  CAGR {m['cagr']:6.1%}  변동성 {m['vol']:5.1%}  "
          f"샤프 {m['sharpe']:5.2f}  최대낙폭 {m['mdd']:6.1%} ({m['mdd_date']})  거래비용 {100 * m['cost']:.2f}")
```

2026-11-13 에 받은 데이터 (2005-01-03 ~ 2026-11-11) 로 돌린 결과:

```
SPY 매수후보유          최종    938.3  CAGR  10.8%  변동성 18.9%  샤프  0.54  최대낙폭 -55.2% (2009-03-09)  거래비용 0.05
SPY/QQQ 50:50 월간   최종   1410.5  CAGR  12.9%  변동성 19.9%  샤프  0.62  최대낙폭 -53.7% (2009-03-09)  거래비용 0.50
SPY 200일 추세        최종    602.0  CAGR   8.6%  변동성 11.5%  샤프  0.62  최대낙폭 -20.9% (2010-09-10)  거래비용 12.92
```

여러 자산을 넘기면 `data.align` 으로 모두 값이 있는 날짜(교집합)만 쓴다. 롤링 시작일 연구는
`metrics.windows`, `metrics.distribution`, `metrics.win_rate` (벡터 계산용) 또는 `metrics.rolling_run` (엔진으로 창마다 실행, 느림)을 쓴다.

## 테스트

```
python -m pytest
```

- `test_metrics.py`: 지표를 손으로 계산한 작은 예와 비교
- `test_engine.py`: 엔진·주문·거래비용·금리·데이터 점검
- `test_lookahead.py`: 미래 가격을 바꿔도 과거 결정이 같은지, 전략이 미래 값에 닿을 수 없는지
- `test_collectors.py`: `tests/fixtures/` 에 저장한 실제 응답으로 수집기와 병합 규칙 시험 (네트워크를 막고 돈다)
- `test_regression_tqqq.py`: 새 엔진이 `research/backtest_tqqq.py` (a) 의 TQQQ 수치
  (`data/prices/yahoo/TQQQ.csv` 2010-02-11 ~ 2026-11-11, 최종자산 29,456 / 24,420 / 22,848 / 12,272,
  완료 사이클 72회, 평균 비중 70.1%, 최장 사이클 780거래일) 를 재현하는지.
  끝 날짜를 고정하고 가격 비율로만 비교하므로 collect.py 가 새 행을 덧붙이거나 새 배당으로 과거 adj_close 를
  상수배 재조정해도 깨지지 않는다. 그 이전 구간의 수익률이 바뀌면 (실제 데이터 정정) 실패한다

- `test_dart.py`: DART 클라이언트(키 가리기, 캐시, 오류), 응답 해석(`tests/fixtures/dart/`, 키 없음), 점검 로직(손으로 만든 예),
  원문 추출기(작은 DART XML), 받아 둔 표의 잘 알려진 값 (삼성전자 2025 연결 자산총계 566,942,110백만원 등)

## DART 재무제표 (파일럿)

OpenDART API 로 사업보고서 재무제표(재무상태표 BS, 손익계산서 IS, 포괄손익계산서 CIS, 현금흐름표 CF, 자본변동표 SCE)를
받아 **받은 그대로(as-reported)** 저장하고, 재무상태표는 표준 계정과목(트리)으로 옮긴 층도 만든다 (아래 "표준화 층").
값을 지어내거나 채우지 않는다.

```
export DART_API_KEY=...            # OpenDART 인증키. 코드는 환경 변수에서만 읽고 어디에도 남기지 않는다
python dart_collect.py             # dart_watchlist.csv 5개사, 2023~2025 사업보고서, 연결(CFS)·별도(OFS)
python dart_collect.py --years 2021-2025 --only 삼성전자
python dart_collect.py --check     # 받지 않고 점검 -> data/dart/checks.csv, checks.md
python dart_collect.py --inventory # 받지 않고 계정 목록 -> data/dart/account_inventory.csv
python dart_collect.py --doc-probe # 삼성전자 원문 문서에서 연결 재무상태표 시험 추출 -> data/dart/doc_probe.md
python dart_collect.py --standardize # 받지 않고 재무상태표 표준화·대사 -> data/dart/standardized/
```

받은 응답은 모두 디스크에 캐시하고, 캐시가 있으면 다시 받지 않는다 (OpenDART 는 하루 호출 한도가 있다).
그래서 두 번째 실행은 API 요청 0회다. 공시목록을 새로 받으려면 `data/dart/raw/list/` 의 해당 파일을 지운다.
요청 URL 을 기록할 때는 키 자리를 `crtfc_key=***` 로 둔다.

### 저장 층

1. **raw** `data/dart/raw/` — API 응답 그대로 (JSON). 커밋한다.
   - `company/<corp_code>.json` 기업개황, `list/<corp_code>_<공시유형>_<시작>_<끝>_p<쪽>.json` 공시검색,
     `fnltt/<corp_code>/<연도>_<보고서코드>_<CFS|OFS>.json` 단일회사 전체 재무제표, `taxonomy/<양식>.json` XBRL 택사노미
   - `raw/_large/` 의 원문 zip(`document/`), XBRL zip(`xbrl/`), 고유번호 zip(`corpCode.zip`) 은 크기 때문에 커밋하지 않는다.
     `data/dart/large_manifest.csv` 에 경로, 접수번호, 바이트 수, sha256 을 남긴다.
2. **extracted (as-reported)** `data/dart/extracted/statements.csv` — 긴 표 하나. 한 행 = 응답의 한 줄.
   `corp_code, stock_code, company, rcept_no, rcept_dt(접수일), bsns_year, reprt_code, fs_div, sj_div, sj_nm, ord,
   account_id(XBRL 요소 id 또는 "-표준계정코드 미사용-"), account_nm, account_detail(자본변동표의 자본 구성요소 열),
   thstrm/frmtrm/bfefrmtrm _nm·_amount(당기·전기·전전기, 원 단위 정수), thstrm_add_amount·frmtrm_add_amount(분기·반기 누적),
   currency, raw_file, raw_index`. `raw_file` 의 `list[raw_index]` 가 그 행의 원본이다.
   금액이 빈칸이거나 "-" 이면 빈칸으로 둔다. `rcept_dt` 는 공시목록(list.json)에서 그 접수번호의 접수일을 가져온다.
   `filings.csv` 는 사업보고서 공시 목록(원본·정정 포함)과 재무제표 API 가 실제로 쓴 접수번호(`used_by_fnltt`).
3. **표준화 층** `data/dart/standardized/` — 지금은 재무상태표(BS)만. 아래 "표준화 층 (재무상태표)" 절.
   설계 근거 자료로 `data/dart/account_inventory.csv` 가 있다: 서로 다른 (재무제표, account_id, 계정명) 마다 쓰는 회사, 연도,
   연결/별도, 행 수, ord 범위, 같은 이름의 id 수, 같은 id 의 이름 수.

### 표준화 층 (재무상태표, `--standardize`)

- **표준 계정과목** `data/dart/standard/accounts_bs.csv` (`std_id, parent, name_ko, name_en, kind, note`): 트리다.
  루트는 `BS.A` 자산총계, `BS.L` 부채총계, `BS.E` 자본총계, `BS.T` 부채와자본총계. 그 아래 유동·비유동 소계(`BS.A1` …),
  항목, 묶음(group, 예: `BS.A13` 매출채권및기타채권 아래 `BS.A131` 매출채권, `BS.A132` 미수금및기타채권). 회사마다 표시
  단위가 달라서(NAVER 는 "매출채권및기타채권" 한 줄, 삼성전자는 매출채권·미수금을 따로) 각 줄을 **맞는 가장 깊은 노드**에
  붙이고, 회사끼리 비교할 때는 자식을 공통 조상까지 더한다. 차트는 연구 책임이 정한다.
- **매핑표** `data/dart/standard/mapping_bs.csv`: as-reported BS 줄 하나 = 한 행. 키는
  `corp_code, fs_div, account_id, account_nm, occurrence` (occurrence 는 한 재무제표 안에 같은 (id, 이름) 이 여러 번 있을 때
  ord 순서로 매긴 1, 2, … — 현대자동차 연결 "금융업채권" 두 줄만 2 까지 있다). 열 `std_id`, `method`(`xbrl_id` id 만으로,
  `name` 계정명으로, `position` 표 안의 위치로(유동/비유동을 산술 대사·원문으로 확인), `manual` 그 밖), `confidence`
  (high/medium/low), `review`(`ok` / `needs_lead`), `note`, 참고용 `years, n_rows`.
- **표준화 표** `bs.csv`: 재무제표 × 기간(`period` = current/prior/prior2, `period_end` 는 사업연도와 기업개황 결산월로 계산) ×
  노드의 긴 표. `source=reported` 는 그 노드에 바로 대응한 줄(여러 줄이면 합), `source=rollup` 은 값이 있는 자식 노드 값의 합
  (자식 값은 보고값 우선, 없으면 그 자식의 합계). 둘 다 있으면 두 행. 둘 다 없으면 행이 없다 (0 으로 채우지 않는다).
  `raw_file` + `raw_index`(세미콜론 목록)가 실제로 더한 as-reported 줄을 가리킨다.
- **대사** `bs_checks.csv`, 요약 `bs_checks.md`: 보고값과 하위 합계가 둘 다 있는 모든 노드(유동자산, 비유동자산, 자산총계,
  유동·비유동부채, 부채총계, 지배기업소유주지분(연결), 자본총계, 자본금 …), 그리고 BS.L + BS.E = BS.T, BS.A = BS.T.
  원 단위로 정확히 같아야 통과다. 실패는 고치지 않고 차이와 관련 줄을 적는다.
- **비교 가능성** `bs_coverage.csv`: 노드마다 30개 재무제표(5개사 × 3년 × 연결/별도, 당기 열) 중 값이 있는 수, 매핑 행 수,
  연결에서 5개사 × 3년 모두 값이 있는지(`all5_cfs`), 그 노드가 공통으로 비교되는 가장 깊은 노드인지(`frontier_cfs`).

`python dart_collect.py --standardize` 는 받지 않고 `statements.csv` 에서 다시 만든다. 점검 실패나 매핑 없는 줄이 있으면
종료 코드 1. 매핑표에 없는 줄(새 회사·새 연도)은 "매핑 없음" 으로 보고하고 값에 넣지 않는다.

### 점검 (`--check`)

회사·연도·연결/별도마다 재무제표가 다 있는지와 중복 행, 자산총계 = 부채총계 + 자본총계 (원 단위 정확히),
현금흐름표 기말현금 = 재무상태표 현금및현금성자산, N년 보고서의 전기 = N-1년 보고서의 당기 (다르면 종류별로: 금액다름,
부호반대, 빈칸과0, 한쪽빈칸). 실패를 고치지 않고 그대로 적는다.

### 알아 둘 것 (2026-11 확인)

- `fnlttSinglAcntAll` 은 2015 사업연도(사업보고서)와 2016 1분기부터 데이터가 있다. 그 이전은 원문 문서에서 뽑아야 한다.
- 정정공시가 있으면 `fnlttSinglAcntAll` 은 마지막 정정본의 접수번호와 값만 준다 (원래 공시의 값은 이 API 로는 못 받는다).
- `ord` 는 화면에 보이는 행 순서가 아니다 (같은 묶음 안에서 대체로 account_id 순). 행의 위·아래 관계(계층)도 주지 않는다.
- 단일 포괄손익계산서를 쓰는 회사(SK하이닉스, NAVER)는 IS 가 없고 손익 항목이 CIS 에 있다.

## 예전 분석 스크립트 (research/)

저장소 루트에서 돌린다. 출력은 옮기기 전과 같다.

```
python research/buy_duration.py      # 매수듀레이션 몬테카를로, research/buy_duration_frontier.png
python research/infinite_buy.py      # 무한매수법 몬테카를로 (몇 분 걸림)
python research/backtest_tqqq.py     # TQQQ 실데이터 백테스트, data/prices/yahoo/TQQQ.csv (2010-02-11 ~ 2026-11-11), research/backtest_tqqq.png
```

`backtest_tqqq.py` 만 pandas 를 쓴다. 예전에는 `data/tqqq_daily.csv` (공개 GitHub 저장소의 Yahoo 사본) 를 썼는데,
2025-12 ~ 2026-09 의 배당 조정 네 번이 날짜가 어긋나 있어 2026-11 에 collect.py 가 직접 받은
`data/prices/yahoo/TQQQ.csv` 로 바꾸고 지웠다. 수치는 그때 다시 계산했다.

## 웹 페이지 데이터 (docs/tqqq-data.js)

```
python tools/make_web_data.py            # data/prices/yahoo/TQQQ.csv 2010-02-11 ~ 2026-11-11 → docs/tqqq-data.js
python tools/make_web_data.py --check    # 지금 파일이 다시 만든 것과 같은지만 확인
```

기간은 `research/backtest_tqqq.py` 와 같은 끝 날짜로 고정되어 있어, 웹 페이지 2번 탭의 기본값 결과가 그 스크립트 (a) 와 같다.
기간을 늘리려면 두 파일의 `END` 와 `docs/index.html` 의 데이터 설명을 함께 고친다.

## 데이터 소스와 한계 (2026-11 확인)

| 소스 | 대상 | 이력 | 한계와 주의 |
|---|---|---|---|
| Yahoo Finance chart API (`query1.finance.yahoo.com`) | 주식, ETF, 지수, 환율, 선물, 암호화폐, 한국 종목 | 상장/산출 시작부터 (^GSPC 1927년~) | 공식 API 가 아니다. 브라우저 비슷한 User-Agent 가 필요하고 가끔 429 를 준다 (재시도). adj_close 에 1e-6 수준 잡음. 지수·환율 거래량은 0. KRW=X·GC=F 는 고가/저가가 종가를 감싸지 않는 날이 많다. 005930.KS 는 2000년대 휴장일 일부가 거래량 0·전일 가격으로 들어 있다 (`--check` 가 '휴장일 채움 의심' 으로 센다). 선물(GC=F, CL=F)은 근월물 연결 가격이라 월물 교체 효과가 섞여 있고, CL=F 는 2020-04-20 에 음수 가격(-37.63)이 있다 (backtest.data.load 의 양수 점검에 걸린다) |
| CoinGecko 공개 API (`api.coingecko.com`) | 암호화폐 | **최근 365일만** | 더 긴 기간은 `error_code 10012` (HTTP 401) 로 거절된다. 하루 한 값 (00:00 UTC 가격) 이고, date=D 값은 Yahoo BTC-USD 의 D-1 일 종가와 거의 같다 (중앙값 차이 0.03%). volume 은 24시간 거래대금. 분당 호출 제한이 있다 |
| FRED (`fred.stlouisfed.org/graph/fredgraph.csv`) | 금리, 경제지표 | 시계열 시작부터 (DTB3 1954년~) | User-Agent 가 `Mozilla/5.0...` 이면 서버가 응답 없이 연결을 끊는다. 그래서 기본 User-Agent 를 쓴다. 값이 없는 날('.' 또는 빈 칸)은 행을 만들지 않는다 |

stooq.com 은 자바스크립트 봇 확인 페이지를 주므로 쓰지 않는다. 그 밖의 사이트는 이 환경의 네트워크 정책상 막혀 있다.
