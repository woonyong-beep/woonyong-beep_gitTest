"""작은 일별 백테스트 엔진.

- data: data/prices 의 시계열 불러오기, 점검, 날짜 맞추기
- engine: 일별 루프 (미래 정보 차단), 주문 형식 Weights / Trades
- metrics: 최종자산, CAGR, 변동성, 샤프, 최대낙폭, 롤링 시작일 분포
- strategies: 매수후보유, N일 분할매수, 무한매수법, 일정비중 리밸런싱
"""
