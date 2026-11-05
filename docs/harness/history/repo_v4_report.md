# 명명 검증 결과

관점: developer

| 이름 | 통과 | 오독률 | 제외 | 충돌(참고) | 오독 근거 |
|---|---|---|---|---|---|
| sense-match | 0/9 | 0/9 |  | taken |  |
| name-mirror | 0/9 | 0/9 |  | free |  |
| intent-test | 2/9 | 0/9 |  | unverified |  |
| name-compass | 1/9 | 0/9 |  | unverified |  |
| name-decoder | 8/9 | 0/9 |  | unverified |  |
| name-clarity | 1/9 | 3/9 | 제외 | unverified | 이름이 얼마나 명확하고 이해하기 쉬운지를 뜻하는 말로, 변수나 함수, 파일 등의 이름이 그 역할을 분명히 드러내는지 평가하는 기준처럼 보입니다. |
| name-signal | 1/9 | 0/9 |  | unverified |  |
| meaning-check | 1/9 | 0/9 |  | unverified |  |

**선택: name-decoder** (Mandatory gates, then fixture pass rate; ties retain baseline)

판정 뒤 설명문을 직접 읽어 교차 확인할 것(규칙은 쉬운 말 표현을 놓칠 수 있다).

## 사전 검사
- C02 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C03 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C04 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C05 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C06 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C07 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
- C08 distinct_from "무작위 이름 생성기" → "random-name-generator": misread_as 분야·contrasts에 근거 없음
