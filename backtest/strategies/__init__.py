"""기본 전략 모음. 전략은 on_bar(ctx) 로 주문(Weights / Trades / None)을 돌려주는 객체다.

상태가 있는 전략은 reset() 에서 상태를 초기화한다 (엔진이 시작할 때 부른다).
"""

from backtest.strategies.buy_hold import BuyAndHold
from backtest.strategies.constant_weight import ConstantWeight
from backtest.strategies.infinite_buy import InfiniteBuy
from backtest.strategies.split_buy import SplitBuy

__all__ = ["BuyAndHold", "ConstantWeight", "InfiniteBuy", "SplitBuy"]
