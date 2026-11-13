"""일별 루프 백테스트 엔진: 자산 여러 개 + 무위험 수익을 받는 현금.

하루의 순서 (t = 0, 1, ..., n-1)
1. t > 0 이면 현금이 t-1 → t 무위험 수익만큼 불어난다 (현금이 음수면 같은 이율로 빌린 것).
2. 엔진이 t 일 가격(종가)을 전략에게 보여줄 기록 버퍼에 한 칸 덧붙인다.
3. t < n-1 이면 전략을 부른다. 전략은 Context 하나만 받는다: t 일까지의 날짜와 가격, 현재 현금과 보유 수량.
   전략이 돌려준 주문은 t 일 종가에 체결된다 (lag=1 이면 다음 거래일 종가에 체결).
   마지막 날(n-1)에는 주문을 받지 않는다. 그날 산 것을 평가할 다음 날이 없기 때문이다.
4. t 일 종가로 자산을 평가해 기록한다 (체결 뒤 값).

미래 정보를 볼 수 없게 만든 방법
- 전략은 엔진이 가진 전체 가격 배열에 손댈 수 없다. Context.prices[sym] 은 엔진이 매일 한 칸씩 채우는
  별도 버퍼의 [:t+1] 읽기 전용 뷰다. 버퍼의 t+1 이후 칸은 아직 NaN 이므로 .base 로 버퍼 전체를 꺼내도
  미래 값이 없다. 체결과 평가는 엔진이 따로 가진 원본 배열로 하므로 전략이 버퍼를 고쳐도 결과에 영향이 없다.
- 무위험 금리 시계열도 t-1 일까지 발표된 값만 t-1 → t 이자 계산에 쓴다.
- 단, 전략 객체를 만들 때 사용자가 미래 데이터를 직접 넣는 것까지 막을 수는 없다. 전략은 Context 만 쓴다.

주문 형식 (전략이 돌려주는 값)
- None: 아무것도 안 함.
- Weights({sym: w}): 체결 직전 총자산 대비 목표 비중. 적힌 자산만 맞추고 나머지는 그대로 둔다. w=0 은 전량 매도.
- Trades({sym: 금액}): 현금 금액만큼 매수(양수) / 매도(음수).
- 위 둘의 list 도 된다 (차례로 체결).
거래비용: 체결 금액의 cost_bps / 10000 을 현금에서 뺀다 (기본 0). 현금이 모자라도 막지 않는다 (음수 현금 = 차입).

무위험 수익 rf
- 숫자: 연율. 거래일마다 exp(rf / periods_per_year) 로 불어난다 (research/backtest_tqqq.py 와 같은 방식).
- Series (예: data.load_rate("fred", "DTB3"), 연 %): t-1 → t 사이 달력일 수 x (t-1 일 또는 그 전 마지막 발표값)
  / 100 / 360 의 단리 (ACT/360). DTB3 는 할인율 기준이라 실제 투자수익률과 조금 다르다 (근사).
  t-1 일 이전에 발표된 값이 하나도 없으면 오류.
"""

from dataclasses import dataclass, field

import numpy as np

from backtest.data import Series, align


class Weights(dict):
    """목표 비중 주문 {symbol: weight}."""


class Trades(dict):
    """금액 주문 {symbol: 현금 금액}. 양수 매수, 음수 매도."""


class Context:
    """전략이 t 일 종가 시점에 볼 수 있는 정보. t 일 이후 값은 들어 있지 않다."""

    __slots__ = ("t", "date", "dates", "prices", "cash", "shares", "initial")

    def __init__(self, t, dates, prices, cash, shares, initial):
        self.t = t
        self.dates = dates              # datetime64[D] 배열, 길이 t+1 (읽기 전용)
        self.date = dates[-1]
        self.prices = prices            # {symbol: 길이 t+1 가격 배열 (읽기 전용)}
        self.cash = cash
        self.shares = shares            # {symbol: 보유 수량} (복사본)
        self.initial = initial

    def price(self, sym):
        return self.prices[sym][-1]

    def position_value(self, sym):
        return self.shares[sym] * self.prices[sym][-1]

    @property
    def wealth(self):
        return self.cash + sum(self.shares[s] * self.prices[s][-1] for s in self.shares)

    def weight(self, sym):
        return self.position_value(sym) / self.wealth


@dataclass
class Result:
    dates: np.ndarray            # (n,) datetime64[D]
    symbols: list
    wealth: np.ndarray           # (n,) 각 날 체결 뒤 종가 평가 총자산
    cash: np.ndarray             # (n,)
    shares: np.ndarray           # (n, k) 각 날 체결 뒤 보유 수량
    weights: np.ndarray          # (n, k) 각 날 체결 뒤 비중
    rf_returns: np.ndarray       # (n-1,) t-1 → t 현금 수익률
    trades: list = field(default_factory=list)   # (t, date, symbol, shares, price, value, cost)
    initial: float = 1.0
    strategy: object = None

    @property
    def exposure(self):
        """주문을 받은 날(0..n-2) 체결 뒤 위험자산 비중 합의 평균. 다음 날까지 들고 간 비중의 평균이다."""
        return self.weights[:-1].sum(axis=1).mean()

    @property
    def total_cost(self):
        return sum(tr[6] for tr in self.trades)


def _as_frame(data):
    """Series / Series 목록 / (dates, {sym: values}) 를 (dates, {sym: values}) 로."""
    if isinstance(data, Series):
        return data.dates, {data.name: data.values}
    if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
        dates, px = data
        dates = np.asarray(dates, dtype="datetime64[D]")
        px = {k: np.asarray(v, dtype=float) for k, v in px.items()}
        for k, v in px.items():
            if v.shape != dates.shape:
                raise ValueError(f"{k}: 길이 {v.shape} 가 날짜 {dates.shape} 와 다름")
        return dates, px
    return align(*data)


def _rf_growth(rf, dates, periods_per_year):
    """t-1 → t 현금 성장률 (길이 n-1)."""
    n = len(dates)
    if isinstance(rf, Series):
        idx = np.searchsorted(rf.dates, dates[:-1], side="right") - 1    # t-1 일 또는 그 전 마지막 발표
        if (idx < 0).any():
            raise ValueError(f"금리 {rf.name} 가 {dates[0]} 이전 값이 없다")
        days = np.diff(dates.astype("int64"))
        return 1 + rf.values[idx] / 100 * days / 360
    return np.full(n - 1, np.exp(float(rf) / periods_per_year))


def run(strategy, data, rf=0.0, cost_bps=0.0, initial=1.0, lag=0, periods_per_year=252):
    """백테스트를 돌려 Result 를 돌려준다.

    strategy: on_bar(ctx) 메서드가 있는 객체, 또는 ctx 를 받는 함수. reset() 이 있으면 시작 전에 부른다.
    data: Series, Series 목록 (공통 날짜로 맞춤), 또는 (dates, {symbol: prices}).
    rf: 연 무위험수익률(숫자) 또는 금리 Series (연 %). 모듈 설명 참고.
    cost_bps: 체결 금액 대비 거래비용 (bp).
    lag: 0 이면 결정한 날 종가에 체결, 1 이면 다음 거래일 종가에 체결.
    """
    if lag not in (0, 1):
        raise ValueError("lag 는 0 또는 1")
    dates, px = _as_frame(data)
    syms = list(px)
    n, k = len(dates), len(syms)
    if n < 2:
        raise ValueError("최소 2거래일이 필요하다")
    P = np.column_stack([px[s] for s in syms])          # 엔진만 쓰는 원본
    if not np.isfinite(P).all() or (P <= 0).any():
        raise ValueError("가격에 결측 또는 0 이하 값이 있다")
    growth = _rf_growth(rf, dates, periods_per_year)
    fee = cost_bps / 10_000

    # 전략에게 보여줄 버퍼: 매일 한 칸씩 채운다
    buf_px = {s: np.full(n, np.nan) for s in syms}
    buf_dates = np.full(n, np.datetime64("NaT", "D"), dtype="datetime64[D]")

    on_bar = strategy.on_bar if hasattr(strategy, "on_bar") else strategy
    if hasattr(strategy, "reset"):
        strategy.reset()

    cash = float(initial)
    shares = np.zeros(k)
    wealth = np.empty(n)
    cash_rec = np.empty(n)
    sh_rec = np.empty((n, k))
    w_rec = np.empty((n, k))
    trades = []
    pending = None

    def execute(orders, t):
        nonlocal cash
        p = P[t]
        for order in orders if isinstance(orders, list) else [orders]:
            if order is None:
                continue
            if isinstance(order, Weights):
                W = cash + shares @ p
                items = [(s, (0.0 if w == 0 else w * W / p[syms.index(s)]) - shares[syms.index(s)])
                         for s, w in order.items()]
            elif isinstance(order, Trades):
                items = [(s, a / p[syms.index(s)]) for s, a in order.items()]
            else:
                raise TypeError(f"알 수 없는 주문 형식: {type(order).__name__} (Weights, Trades, None, list)")
            for s, dsh in items:
                j = syms.index(s)
                if dsh == 0:
                    continue
                if isinstance(order, Weights) and order[s] == 0:
                    dsh = -shares[j]
                    value = -(shares[j] * p[j])
                    shares[j] = 0.0
                elif isinstance(order, Trades):
                    value = order[s]
                    shares[j] += dsh
                else:
                    value = dsh * p[j]
                    shares[j] += dsh
                c = abs(value) * fee
                cash -= value
                cash -= c
                trades.append((t, dates[t], s, dsh, p[j], value, c))

    for t in range(n):
        if t:
            cash *= growth[t - 1]
        for j, s in enumerate(syms):
            buf_px[s][t] = P[t, j]
        buf_dates[t] = dates[t]
        if pending is not None:
            execute(pending, t)
            pending = None
        if t < n - 1:
            views = {}
            for s in syms:
                v = buf_px[s][: t + 1]
                v.flags.writeable = False
                views[s] = v
            dv = buf_dates[: t + 1]
            dv.flags.writeable = False
            ctx = Context(t, dv, views, cash, dict(zip(syms, shares.tolist())), initial)
            orders = on_bar(ctx)
            if lag == 0:
                execute(orders, t)
            else:
                pending = orders
        value = shares * P[t]
        wealth[t] = cash + value.sum()
        cash_rec[t] = cash
        sh_rec[t] = shares
        w_rec[t] = value / wealth[t]
    return Result(dates=dates, symbols=syms, wealth=wealth, cash=cash_rec, shares=sh_rec,
                  weights=w_rec, rf_returns=growth - 1, trades=trades, initial=float(initial),
                  strategy=strategy)
