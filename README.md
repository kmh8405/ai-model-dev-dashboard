# AI 모델 도메인별 강점 대시보드

개발자 페르소나를 위한 AI 모델 성능 비교 대시보드입니다. Overall / Coding / Math 세 카테고리에서 최신 AI 모델(Claude, GPT, Gemini 등)의 Arena Score를 비교하고, 모델별로 카테고리 간 순위 변화를 확인할 수 있습니다. 각 카테고리 상위 20개 모델을 기준으로 하며, 데이터가 매일 자동 갱신되기 때문에 카테고리 간 중복을 제외한 전체 모델 수는 시점마다 달라질 수 있습니다.

🔗 **[대시보드 바로가기](https://kmh8405.github.io/ai-model-dev-dashboard/)**

## 구성

- KPI 카드: 카테고리별 1위 모델 및 주요 지표
- 카테고리별(Overall/Coding/Math) 순위 막대 그래프
- 모델별 카테고리 간 순위를 비교하는 크로스 테이블

`index.html`은 Chart.js를 CDN이 아니라 파일에 직접 인라인으로 삽입해 오프라인에서도 동작합니다. 표시되는 순위 데이터(`data/data.json`)는 아래 자동화 파이프라인이 매일 갱신합니다.

## 데이터 소스 & 자동 갱신

- 원본: Hugging Face [`lmarena-ai/leaderboard-dataset`](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) (subset: `text`, split: `latest`)
- 사람들이 두 모델의 익명 답변을 비교 투표한 결과를 Bradley–Terry 모델(Elo와 유사)로 환산한 "Arena Score" 기반. 이 값은 데이터셋에 이미 계산되어 있어 별도로 재계산하지 않습니다.
- 카테고리: `overall`, `coding`, `math` (각 상위 20개 모델)

가격/비용 데이터는 조사했으나 신뢰할 수 있는 최신 소스가 없어 이번 버전에는 포함하지 않았습니다.

원본 데이터는 CSV가 아니라 **Supabase(Postgres)** 테이블(`ai_model_leaderboard`)에 저장됩니다. 매일 GitHub Actions(`.github/workflows/refresh-data.yml`)가 다음을 실행합니다:

1. `scripts/fetch_hf_to_supabase.py` — Hugging Face의 parquet export에서 최신 스냅샷 전체(29개 카테고리, ~9,700행)를 받아와 `overall`/`coding`/`math` 상위 20개만 걸러 Supabase에 upsert
2. `scripts/build_data.py` — Supabase에서 각 카테고리 최신 스냅샷을 조회해 `data/data.json` 재생성
3. `data/data.json`이 바뀌었으면 자동 커밋·푸시 → GitHub Pages에 반영

이 Supabase 프로젝트는 다른 대시보드(hcp-roi-dashboard)와 같은 프로젝트를 공유하며, 테이블만 분리되어 있습니다. Supabase 접속 정보는 이 저장소의 `Settings → Secrets and variables → Actions`에 `DATABASE_URL`로 등록되어 있습니다.

즉시 갱신이 필요하면 저장소 `Actions` 탭 → `Refresh dashboard data` → `Run workflow`로 수동 실행할 수 있습니다.

### 갱신 지연에 대해

원본 데이터셋(`lmarena-ai/leaderboard-dataset`)은 대략 하루 한 번, UTC 03:01(한국시간 12:01)경에 갱신됩니다. 반면 이 저장소의 크론은 UTC 21:00(한국시간 06:00)에 실행되므로, 두 시각이 어긋나 있어 최악의 경우 원본이 갱신된 후 최대 하루 가까이 지연되어 반영될 수 있습니다.

Hugging Face 웹훅으로 원본이 갱신되는 즉시 반영하는 것도 가능하지만, 이를 위해서는 웹훅을 받아 GitHub에 전달할 별도의 중계 서버(예: Cloudflare Worker)를 새로 호스팅·관리해야 합니다. 비용/관리 포인트를 최소화하는 것이 이 파이프라인의 설계 원칙이라, 현재는 폴링(하루 1회 크론) 방식을 유지하고 있습니다. 최신 데이터가 바로 필요하면 위의 수동 `Run workflow` 실행으로 대신합니다.

## 로컬 실행

```bash
python3 -m http.server 8000
# http://localhost:8000 접속
```

데이터 파이프라인을 로컬에서 돌리려면 `.env`에 `DATABASE_URL`을 넣고:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
set -a && source .env && set +a
python scripts/fetch_hf_to_supabase.py
python scripts/build_data.py
```
