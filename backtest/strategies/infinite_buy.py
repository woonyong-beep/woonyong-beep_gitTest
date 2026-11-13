"""무한매수법 (research/infinite_buy.py 와 같은 단순화 규칙).

- 사이클 시작 시 현금을 splits(40) 등분한 금액을 1회분으로 정하고, 매 거래일 종가에 1회분씩 산다.
  (현금이 1회분보다 적으면 남은 현금만큼)
- 종가 x 보유수량 >= (1 + take_profit) x 이번 사이클 투입 원금 이면 그날 종가에 전량 매도하고,
  다음 거래일부터 새 사이클 (그날은 사지 않는다).
- 40회분을 다 쓰면 익절 조건이 될 때까지 보유한다 (손절 없음).
- 실제 무한매수법의 LOC 주문, 절반 평단 매수, 쿼터 손절 등은 반영하지 않았다.
- 판단과 체결이 같은 종가에서 일어난다고 가정한다 (엔진 lag=0, LOC 주문에 해당). 투입 원금에 거래비용은 넣지 않는다.

실행 뒤 기록 (거래일 인덱스)
- cycles: 완료 사이클 (시작일, 매도일) 목록
- open_cycle: 마지막 날까지 끝나지 않은 사이클 (시작일, None) 또는 None
- full_spells: 40회분 소진 후 익절까지 기다린 구간 (소진일, 해소일 또는 None)
"""

from backtest.engine import Trades, Weights


class InfiniteBuy:
    def __init__(self, symbol, splits=40, take_profit=0.10):
        self.symbol, self.splits, self.take_profit = symbol, splits, take_profit
        self.reset()

    def reset(self):
        self.cost = 0.0           # 이번 사이클 투입 원금
        self.bought = 0           # 이번 사이클 매수 횟수
        self.unit = None          # 1회 매수 금액
        self.start = 0
        self.full_since = None
        self.cycles, self.full_spells = [], []
        self.open_cycle = None
        self.last_t = None

    def on_bar(self, ctx):
        s = ctx.price(self.symbol)
        sh = ctx.shares[self.symbol]
        self.last_t = ctx.t
        if self.unit is None:
            self.unit = ctx.cash / self.splits
        if sh > 0 and s * sh >= (1 + self.take_profit) * self.cost:
            self.unit = (ctx.cash + sh * s) / self.splits
            self.cost, self.bought = 0.0, 0
            self.cycles.append((self.start, ctx.t))
            if self.full_since is not None:
                self.full_spells.append((self.full_since, ctx.t))
                self.full_since = None
            self.start = ctx.t + 1
            self.open_cycle = None
            return Weights({self.symbol: 0.0})
        if self.bought < self.splits:
            amount = min(self.unit, ctx.cash)
            self.cost += amount
            self.bought += 1
            if self.bought == self.splits:
                self.full_since = ctx.t
            self.open_cycle = (self.start, None)
            return Trades({self.symbol: amount})
        return None

    def cycle_lengths(self, n_days):
        """완료 사이클과 진행 중 사이클의 길이(거래일, 양 끝 포함). n_days = 전체 거래일 수."""
        out = [(e - s + 1, s, e) for s, e in self.cycles]
        if self.open_cycle is not None:
            out.append((n_days - 1 - self.open_cycle[0] + 1, self.open_cycle[0], None))
        return out
