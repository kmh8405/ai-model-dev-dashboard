# AI 모델 도메인별 강점 대시보드

개발자 페르소나를 위한 AI 모델 성능 비교 대시보드입니다. Overall / Coding / Math 세 카테고리에서 최신 AI 모델(Claude, GPT, Gemini 등 32개)의 Arena Score를 비교하고, 모델별로 카테고리 간 순위 변화를 확인할 수 있습니다.

🔗 **[대시보드 바로가기](https://kmh8405.github.io/ai-model-dev-dashboard/)**

## 구성

- KPI 카드: 카테고리별 1위 모델 및 주요 지표
- 카테고리별(Overall/Coding/Math) 순위 막대 그래프
- 모델별 카테고리 간 순위를 비교하는 크로스 테이블

정적 단일 HTML 파일로, Chart.js를 CDN이 아니라 파일에 직접 인라인으로 삽입해 오프라인에서도 동작합니다. 별도의 빌드 과정이나 서버가 필요 없습니다.

## 데이터 소스

- Hugging Face [`lmarena-ai/leaderboard-dataset`](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) (subset: `text`, split: `latest`)
- 사람들이 두 모델의 익명 답변을 비교 투표한 결과를 Bradley–Terry 모델(Elo와 유사)로 환산한 "Arena Score" 기반
- 카테고리: `overall`, `coding`, `math` (각 상위 20개 모델)
- 스냅샷 발표일: 2026-07-02

가격/비용 데이터는 조사했으나 신뢰할 수 있는 최신 소스가 없어 이번 버전에는 포함하지 않았습니다.

## 로컬 실행

이 저장소를 클론한 뒤 `index.html`을 브라우저로 바로 열면 됩니다. 별도의 서버나 의존성 설치가 필요 없습니다.
