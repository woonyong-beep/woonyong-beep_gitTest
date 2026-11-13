"""매수 후 보유: 첫날 종가에 목표 비중(기본 100%)만큼 사고 끝까지 둔다."""

from backtest.engine import Weights


class BuyAndHold:
    def __init__(self, symbol, weight=1.0):
        self.symbol, self.weight = symbol, weight

    def on_bar(self, ctx):
        if ctx.t == 0:
            return Weights({self.symbol: self.weight})
        return None
