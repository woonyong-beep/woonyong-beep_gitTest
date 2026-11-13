# 가격 데이터 수집과 백테스트

이 저장소는 두 가지 일을 한다.

1. 가격이나 값이 있는 것(주식, ETF, 지수, 환율, 암호화폐, 원자재, 금리)의 일별 데이터를 모아 한 가지 형식으로 저장한다.
2. 그 데이터로 백테스트 프로그램을 쓰고 시험한다.

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
  tqqq_daily.csv           예전 TQQQ 조정 종가 (research/ 스크립트와 docs/ 가 쓴다. 손대지 않는다)
  tqqq_daily_tiingo.csv    예전 교차검증용 Tiingo 조정 종가
backtest/
  data.py                  시계열 불러오기, 점검, 여러 자산 날짜 맞추기
  engine.py                일별 루프 백테스터 (미래 정보 차단)
  metrics.py               최종자산, CAGR, 변동성, 샤프, 최대낙폭, 롤링 시작일 분포
  strategies/              매수후보유, N일 분할매수, 무한매수법, 일정비중 리밸런싱
research/                  예전 단발성 분석 스크립트와 그래프
tests/                     pytest (네트워크 없이 돈다)
docs/                      브라우저용 시뮬레이터 페이지 (자기 파일만 쓴다)
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
  (최종자산 29,238 / 24,239 / 23,480 / 12,212, 완료 사이클 72회, 평균 비중 70.1%, 최장 사이클 780거래일) 를 재현하는지

## 예전 분석 스크립트 (research/)

저장소 루트에서 돌린다. 출력은 옮기기 전과 같다.

```
python research/buy_duration.py      # 매수듀레이션 몬테카를로, research/buy_duration_frontier.png
python research/infinite_buy.py      # 무한매수법 몬테카를로 (몇 분 걸림)
python research/backtest_tqqq.py     # TQQQ 실데이터 백테스트, data/tqqq_daily.csv, research/backtest_tqqq.png
```

`backtest_tqqq.py` 만 pandas 를 쓴다.

## 데이터 소스와 한계 (2026-11 확인)

| 소스 | 대상 | 이력 | 한계와 주의 |
|---|---|---|---|
| Yahoo Finance chart API (`query1.finance.yahoo.com`) | 주식, ETF, 지수, 환율, 선물, 암호화폐, 한국 종목 | 상장/산출 시작부터 (^GSPC 1927년~) | 공식 API 가 아니다. 브라우저 비슷한 User-Agent 가 필요하고 가끔 429 를 준다 (재시도). adj_close 에 1e-6 수준 잡음. 지수·환율 거래량은 0. KRW=X·GC=F 는 고가/저가가 종가를 감싸지 않는 날이 많다. 005930.KS 는 2000년대 휴장일 일부가 거래량 0·전일 가격으로 들어 있다 (`--check` 가 '휴장일 채움 의심' 으로 센다). 선물(GC=F, CL=F)은 근월물 연결 가격이라 월물 교체 효과가 섞여 있고, CL=F 는 2020-04-20 에 음수 가격(-37.63)이 있다 (backtest.data.load 의 양수 점검에 걸린다) |
| CoinGecko 공개 API (`api.coingecko.com`) | 암호화폐 | **최근 365일만** | 더 긴 기간은 `error_code 10012` (HTTP 401) 로 거절된다. 하루 한 값 (00:00 UTC 가격) 이고, date=D 값은 Yahoo BTC-USD 의 D-1 일 종가와 거의 같다 (중앙값 차이 0.03%). volume 은 24시간 거래대금. 분당 호출 제한이 있다 |
| FRED (`fred.stlouisfed.org/graph/fredgraph.csv`) | 금리, 경제지표 | 시계열 시작부터 (DTB3 1954년~) | User-Agent 가 `Mozilla/5.0...` 이면 서버가 응답 없이 연결을 끊는다. 그래서 기본 User-Agent 를 쓴다. 값이 없는 날('.' 또는 빈 칸)은 행을 만들지 않는다 |

stooq.com 은 자바스크립트 봇 확인 페이지를 주므로 쓰지 않는다. 그 밖의 사이트는 이 환경의 네트워크 정책상 막혀 있다.
