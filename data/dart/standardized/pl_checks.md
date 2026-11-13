# 손익계산서·포괄손익계산서 표준화 점검 (`python dart_collect.py --standardize`)

`data/dart/standardized/pl_checks.csv` 의 요약이다. 매핑은 `data/dart/standard/mapping_pl.csv`, 차트는 `data/dart/standard/accounts_pl.csv`.

- 점검 1734건: 통과 1699, 실패 1, 값 없음 0, 한쪽만 있음(재작성 비교) 34
- 매핑 행 374개 (method: manual 3, name 14, position 3, xbrl_id 354; confidence: high 369, medium 5; review: ok 374); role: check_only 10, value 364; flip: -1 7, 1 367
- 문제 0건 (매핑 없는 줄, std_id 빈칸으로 뺀 줄)

## 점검 종류별

| 점검 | 노드 | 통과 | 실패 | 값 없음 |
|---|---|---|---|---|
| PL.CIO+PL.CIN=PL.CI | PL.CI | 44 | 1 | 0 |
| PL.NIO+PL.NIN=PL.NI | PL.NI | 45 | 0 | 0 |
| PL.NIO.CONT+PL.NIN.CONT=PL.CONT | PL.CONT | 6 | 0 | 0 |
| PL.NIO.DISC+PL.NIN.DISC=PL.DISC | PL.DISC | 4 | 0 | 0 |
| check_only=노드값 | PL.NI | 54 | 0 | 0 |
| 보고값=공식 | PL.CI | 90 | 0 | 0 |
| 보고값=공식 | PL.GP | 72 | 0 | 0 |
| 보고값=하위합계 | PL.CONT | 21 | 0 | 0 |
| 보고값=하위합계 | PL.NI | 90 | 0 | 0 |
| 보고값=하위합계 | PL.NIN | 6 | 0 | 0 |
| 보고값=하위합계 | PL.NIO | 6 | 0 | 0 |
| 보고값=하위합계 | PL.OCI | 90 | 0 | 0 |
| 보고값=하위합계 | PL.OCI.N | 78 | 0 | 0 |
| 보고값=하위합계 | PL.OCI.R | 63 | 0 | 0 |
| 보고값=하위합계 | PL.OP | 90 | 0 | 0 |
| 보고값=하위합계 | PL.PBT | 90 | 0 | 0 |
| 전기=전년보고서당기 | PL.CI | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.CIN | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.CIO | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.COGS | 16 | 0 | 0 |
| 전기=전년보고서당기 | PL.CONT | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.DISC | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.B | 19 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.B.CONT | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.B.DISC | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.D | 15 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.D.CONT | 0 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.PB | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.PB.CONT | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.PB.DISC | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.EPS.PD | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.EQM | 12 | 0 | 0 |
| 전기=전년보고서당기 | PL.FINCOST | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.FININC | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.FININC.INT | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.FININC.OTH | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.GP | 16 | 0 | 0 |
| 전기=전년보고서당기 | PL.NI | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIN | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIN.CONT | 0 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIN.DISC | 0 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIO | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIO.CONT | 0 | 0 | 0 |
| 전기=전년보고서당기 | PL.NIO.DISC | 0 | 0 | 0 |
| 전기=전년보고서당기 | PL.NONOP | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N.DB | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N.EQI | 16 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N.EQM | 6 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N.REV | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.N.TAX | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R | 18 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R.CFH | 14 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R.DEBT | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R.EQM | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R.FX | 10 | 0 | 0 |
| 전기=전년보고서당기 | PL.OCI.R.TAX | 4 | 0 | 0 |
| 전기=전년보고서당기 | PL.OOI | 2 | 0 | 0 |
| 전기=전년보고서당기 | PL.OP | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OPEX | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OTHEXP | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.OTHINC | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.PBT | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.REV | 20 | 0 | 0 |
| 전기=전년보고서당기 | PL.SGA | 16 | 0 | 0 |
| 전기=전년보고서당기 | PL.TAX | 20 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.CI | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.CIN | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.CIO | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.COGS | 8 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.CONT | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.DISC | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.B | 9 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.B.CONT | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.B.DISC | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.D | 7 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.D.CONT | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.PB | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.PB.CONT | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.PB.DISC | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EPS.PD | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.EQM | 6 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.FINCOST | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.FININC | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.FININC.INT | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.FININC.OTH | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.GP | 8 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NI | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIN | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIN.CONT | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIN.DISC | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIO | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIO.CONT | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NIO.DISC | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.NONOP | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N.DB | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N.EQI | 8 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N.EQM | 3 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N.REV | 0 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.N.TAX | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R | 9 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R.CFH | 7 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R.DEBT | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R.EQM | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R.FX | 5 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OCI.R.TAX | 2 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OOI | 1 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OP | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OPEX | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OTHEXP | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.OTHINC | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.PBT | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.REV | 10 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.SGA | 8 | 0 | 0 |
| 전전기=2년전보고서당기 | PL.TAX | 10 | 0 | 0 |

## 실패·값 없음 전체 (재작성 비교 제외)

| 회사 | 연도 | 구분 | 기간 | 점검 | 노드 | 보고 | 계산 | 차이 | 구성 |
|---|---|---|---|---|---|---|---|---|---|
| LG에너지솔루션 | 2023 | CFS | prior2 | PL.CIO+PL.CIN=PL.CI | PL.CI | 1438374000000 | 1438373000000 | 1000000 | PL.CIO=1195531000000;PL.CIN=242842000000 |

## 알려진 발견 (KNOWN_FINDINGS, 고치지 않음)

- LG에너지솔루션 2023 CFS prior2 PL.CIO+PL.CIN=PL.CI: 차이 1000000. LG에너지솔루션 2023 보고서 전전기(2021) 열: 지배 1,195,531 + 비지배 242,842 = 1,438,373 백만원 ≠ 총포괄손익 1,438,374 백만원 (차이 1백만원). 총포괄손익 = 당기순이익 929,868 + 기타포괄손익 508,506 은 맞고, 당기순이익 귀속도 맞는다. 공시 금액이 백만원 단위라 반올림 차이로 보이지만 원문으로 확인하지 않았다

설명되지 않은 실패: 0건

## 재작성·재분류 (N 년 보고서 전기·전전기 열 vs 앞선 보고서 당기 열, 표준화 노드 값)

차이는 고치지 않고 적는다. status=one_side 는 한쪽 보고서에만 그 노드 값이 있는 경우 (표시 방식 차이).

금액 차이 없음.

한쪽에만 값이 있는 노드:

- NAVER CFS 2024 전기=전년보고서당기 PL.NIO.CONT: 2024보고서 prior= (없음); 2023보고서 current=1012321527624 (reported)
- NAVER CFS 2024 전기=전년보고서당기 PL.NIN.CONT: 2024보고서 prior= (없음); 2023보고서 current=-27303765131 (reported)
- NAVER CFS 2024 전기=전년보고서당기 PL.OCI.N.REV: 2024보고서 prior=0 (reported); 2023보고서 current= (없음)
- NAVER CFS 2024 전기=전년보고서당기 PL.EPS.B: 2024보고서 prior=6661 (reported); 2023보고서 current= (없음)
- NAVER CFS 2024 전기=전년보고서당기 PL.EPS.D: 2024보고서 prior=6576 (reported); 2023보고서 current= (없음)
- NAVER CFS 2024 전기=전년보고서당기 PL.EPS.B.CONT: 2024보고서 prior= (없음); 2023보고서 current=6661 (reported)
- NAVER CFS 2024 전기=전년보고서당기 PL.EPS.D.CONT: 2024보고서 prior= (없음); 2023보고서 current=6576 (reported)
- NAVER CFS 2025 전기=전년보고서당기 PL.OCI.R.CFH: 2025보고서 prior=0 (reported); 2024보고서 current= (없음)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.NIO.CONT: 2025보고서 prior2= (없음); 2023보고서 current=1012321527624 (reported)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.NIN.CONT: 2025보고서 prior2= (없음); 2023보고서 current=-27303765131 (reported)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.OCI.N.REV: 2025보고서 prior2=0 (reported); 2023보고서 current= (없음)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.OCI.R.CFH: 2025보고서 prior2=0 (reported); 2023보고서 current= (없음)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.EPS.B: 2025보고서 prior2=6661 (reported); 2023보고서 current= (없음)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.EPS.D: 2025보고서 prior2=6576 (reported); 2023보고서 current= (없음)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.EPS.B.CONT: 2025보고서 prior2= (없음); 2023보고서 current=6661 (reported)
- NAVER CFS 2025 전전기=2년전보고서당기 PL.EPS.D.CONT: 2025보고서 prior2= (없음); 2023보고서 current=6576 (reported)
- NAVER OFS 2024 전기=전년보고서당기 PL.OCI.N.REV: 2024보고서 prior=0 (reported); 2023보고서 current= (없음)
- NAVER OFS 2025 전기=전년보고서당기 PL.OCI.R: 2025보고서 prior=0 (reported); 2024보고서 current= (없음)
- NAVER OFS 2025 전기=전년보고서당기 PL.OCI.R.CFH: 2025보고서 prior=0 (reported); 2024보고서 current= (없음)
- NAVER OFS 2025 전전기=2년전보고서당기 PL.OCI.N.REV: 2025보고서 prior2=0 (reported); 2023보고서 current= (없음)
- NAVER OFS 2025 전전기=2년전보고서당기 PL.OCI.R: 2025보고서 prior2=0 (reported); 2023보고서 current= (없음)
- NAVER OFS 2025 전전기=2년전보고서당기 PL.OCI.R.CFH: 2025보고서 prior2=0 (reported); 2023보고서 current= (없음)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.DISC: 2024보고서 prior= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.NIO.CONT: 2024보고서 prior= (없음); 2023보고서 current=1237180000000 (reported)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.NIO.DISC: 2024보고서 prior= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.NIN.CONT: 2024보고서 prior= (없음); 2023보고서 current=400805000000 (reported)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.NIN.DISC: 2024보고서 prior= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2024 전기=전년보고서당기 PL.EPS.B.CONT: 2024보고서 prior= (없음); 2023보고서 current=5287 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.DISC: 2025보고서 prior2= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.NIO.CONT: 2025보고서 prior2= (없음); 2023보고서 current=1237180000000 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.NIO.DISC: 2025보고서 prior2= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.NIN.CONT: 2025보고서 prior2= (없음); 2023보고서 current=400805000000 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.NIN.DISC: 2025보고서 prior2= (없음); 2023보고서 current=0 (reported)
- LG에너지솔루션 CFS 2025 전전기=2년전보고서당기 PL.EPS.B.CONT: 2025보고서 prior2= (없음); 2023보고서 current=5287 (reported)

## 연구 책임 확인 필요 (review=needs_lead)

없음.

## 부호 반대로 공시한 줄 (flip=-1)

- NAVER CFS CIS 모든 연도 ifrs-full_ShareOfOtherComprehensiveIncomeOfAssociatesAndJointVenturesAccountedForUsingEquityMethodThatWillBeReclassifiedToProfitOrLossNetOfTax "지분법자본변동" -> PL.OCI.R.EQM: 부호 반대로 공시: R 소계 = 해외사업환산손익(+채무상품·현금흐름위험회피) - 이 줄 이 2023·2024·2025 보고서 모든 기간(9개 열)에서 원 단위로 맞고, 더하면 하나도 맞지 않는다. 독립 근거: 자본변동표(SCE) 지분법자본변동(연결재무제표 member) 2023 -515,729,167,155 = -(이 줄 545,588,292,957) + 재분류 안 되는 지분법자본변동 29,859,125,802, 2022 열도 같은 방식으로 맞는다. 원 데이터(XBRL)의 부호 오류로 보인다
- LG에너지솔루션 CFS CIS 2024 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillNotBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.N.TAX: 2024 보고서는 비용을 양수로 공시: 소계 = 세전 구성 항목 - 이 줄 (3개 열 일치). 같은 금액이 2023 보고서와 부호만 반대 (2024 전기 열 = -(2023 당기 열)). 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장
- LG에너지솔루션 CFS CIS 2025 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillNotBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.N.TAX: 2025 보고서는 비용을 양수로 공시: 소계 = 세전 구성 항목 - 이 줄 (3개 열 일치). 2025 전기 열 = 2024 당기 열. 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장
- LG에너지솔루션 CFS CIS 2024 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.R.TAX: 2024 보고서는 비용을 양수로 공시: 소계 = 세전 구성 항목 - 이 줄 (3개 열 일치). 같은 금액이 2023 보고서와 부호만 반대 (2024 전기 열 = -(2023 당기 열)). 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장
- LG에너지솔루션 CFS CIS 2025 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.R.TAX: 2025 보고서는 비용을 양수로 공시: 소계 = 세전 구성 항목 - 이 줄 (3개 열 일치). 2025 전기 열 = 2024 당기 열. 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장
- LG에너지솔루션 OFS CIS 모든 연도 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillNotBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.N.TAX: 비용을 양수로 공시: 2023·2024·2025 보고서 모두 소계 = 세전 구성 항목 - 이 줄 (보고서마다 3개 열 원 단위 일치). 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장
- LG에너지솔루션 OFS CIS 모든 연도 ifrs-full_IncomeTaxRelatingToComponentsOfOtherComprehensiveIncomeThatWillBeReclassifiedToProfitOrLoss "기타포괄손익 법인세효과" -> PL.OCI.R.TAX: 비용을 양수로 공시: 2023·2024·2025 보고서 모두 소계 = 세전 구성 항목 - 이 줄 (보고서마다 3개 열 원 단위 일치). 차트 노드는 OCI 에 더하는 방향(세금 혜택이 양수)으로 저장

주당이익(kind=per_share) 노드는 부모·자식이 없고 공식에도 쓰지 않으며 (차트 검사), 결과에서도 어떤 합계에 주당 줄이 들어가지 않았음을 확인한다. pl.csv 의 unit 이 KRW/주 다.


## 비교 가능성 (연결, 당기 열, 5개사 × 3년 모두 값이 있는 노드)

| depth | 노드 수 | 5개사 공통 |
|---|---|---|
| 0 | 18 | 7 |
| 1 | 8 | 3 |
| 2 | 12 | 5 |
| 3 | 2 | 2 |
| 4 | 8 | 7 |
| 5 | 4 | 0 |

5개사 공통 노드 (보고값 또는 합계·공식): PL.NI, PL.CONT, PL.PBT, PL.OP, PL.REV, PL.OPEX, PL.NONOP, PL.FININC, PL.FINCOST, PL.OTHINC, PL.OTHEXP, PL.EQM, PL.TAX, PL.NIO, PL.NIN, PL.OCI, PL.OCI.N, PL.OCI.N.DB, PL.OCI.R, PL.OCI.R.FX, PL.OCI.R.EQM, PL.CI, PL.CIO, PL.CIN

PL 의 depth 0 에는 합산 나무 밖 노드(공식·귀속·주당)도 있어 'depth 별 공통' 은 BS 만큼 뜻이 없다. 위 공통 노드 목록을 본다.

모든 노드가 5개사 공통인 가장 깊은 depth: -1

5개사 공통이 아닌 노드 (빠진 회사:연도):

- PL.COGS 매출원가 (depth 5): NAVER:2023,2024,2025
- PL.SGA 판매비와관리비 (depth 5): NAVER:2023,2024,2025
- PL.OOI 기타영업수익 (depth 4): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / NAVER:2023,2024,2025
- PL.GP 매출총이익 (depth 0): NAVER:2023,2024,2025
- PL.FININC.INT 이자수익(별도 표시) (depth 5): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2023,2024,2025
- PL.FININC.OTH 이자수익 외 금융수익 (depth 5): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2023,2024,2025
- PL.DISC 중단영업이익 (depth 1): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2023,2024,2025
- PL.NIO.CONT 지배기업소유주지분 계속영업이익 (depth 1): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2024,2025
- PL.NIO.DISC 지배기업소유주지분 중단영업이익 (depth 1): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2023,2024,2025
- PL.NIN.CONT 비지배지분 계속영업이익 (depth 1): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2024,2025
- PL.NIN.DISC 비지배지분 중단영업이익 (depth 1): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2023,2024,2025
- PL.OCI.N.EQI 기타포괄손익-공정가치 지분상품 손익 (depth 2): SK하이닉스:2023,2024,2025
- PL.OCI.N.EQM 지분법 기타포괄손익(재분류 안 됨) (depth 2): SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025
- PL.OCI.N.REV 재평가손익 (depth 2): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023
- PL.OCI.N.TAX 법인세효과(재분류 안 됨) (depth 2): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / NAVER:2023,2024,2025
- PL.OCI.R.CFH 현금흐름위험회피 손익 (depth 2): NAVER:2023,2024
- PL.OCI.R.DEBT 기타포괄손익-공정가치 채무상품 손익 (depth 2): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.OCI.R.TAX 법인세효과(재분류됨) (depth 2): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.B 기본주당이익(보통주) (depth 0): NAVER:2023
- PL.EPS.D 희석주당이익(보통주) (depth 0): LG에너지솔루션:2023,2024,2025 / NAVER:2023
- PL.EPS.B.CONT 계속영업 기본주당이익(보통주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2024,2025 / NAVER:2024,2025
- PL.EPS.B.DISC 중단영업 기본주당이익(보통주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.D.CONT 계속영업 희석주당이익(보통주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2024,2025
- PL.EPS.D.DISC 중단영업 희석주당이익(보통주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / 현대자동차:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.PB 기본주당이익(우선주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.PD 희석주당이익(우선주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.PB.CONT 계속영업 기본주당이익(우선주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
- PL.EPS.PB.DISC 중단영업 기본주당이익(우선주) (depth 0): 삼성전자:2023,2024,2025 / SK하이닉스:2023,2024,2025 / LG에너지솔루션:2023,2024,2025 / NAVER:2023,2024,2025
