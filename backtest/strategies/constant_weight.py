"""일정비중 리밸런싱: every 거래일마다 (첫날 포함) 목표 비중으로 되돌린다. 나머지는 현금.

every=1 이면 매일 리밸런싱으로, research/infinite_buy.py 의 constant_mix 와 같다.
"""

from backtest.engine import Weights


class ConstantWeight:
    def __init__(self, weights, every=1):
        if isinstance(weights, str):
            weights = {weights: 1.0}
        self.weights, self.every = dict(weights), every

    def on_bar(self, ctx):
        if ctx.t % self.every == 0:
            return Weights(self.weights)
        return None
