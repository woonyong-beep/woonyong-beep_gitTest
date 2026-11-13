"""N일 분할매수 후 보유 (익절 없음).

0..N-1 번째 거래일 종가에 남은 현금의 1/(N-k) 씩 산다 (k = 날 번호). 현금이 무위험 수익으로 불어나므로
k 번째 매수 금액은 '처음 예산의 1/N 을 k 일 동안 무위험으로 불린 값' 이 되고, N 번째 날에 현금을 다 쓴다.
research/infinite_buy.py 의 dca_hold, research/backtest_tqqq.py 의 path_dca 와 같은 규칙이다.
"""

from backtest.engine import Trades


class SplitBuy:
    def __init__(self, symbol, splits=40):
        self.symbol, self.splits = symbol, splits

    def on_bar(self, ctx):
        if ctx.t < self.splits:
            return Trades({self.symbol: ctx.cash / (self.splits - ctx.t)})
        return None
