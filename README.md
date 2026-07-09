# AI 모델 도메인별 강점 대시보드

개발자 페르소나를 위한 AI 모델 성능 비교 대시보드입니다. Overall / Coding / Math 세 카테고리에서 최신 AI 모델(Claude, GPT, Gemini 등)의 Arena Score를 비교하고, 모델별로 카테고리 간 순위 변화를 확인할 수 있습니다. 각 카테고리 상위 20개 모델을 기준으로 하며, 원본 데이터셋이 갱신될 때마다(웹훅) 자동으로 다시 반영되기 때문에 카테고리 간 중복을 제외한 전체 모델 수는 시점마다 달라질 수 있습니다.

🔗 **[대시보드 바로가기](https://kmh8405.github.io/ai-model-dev-dashboard/)**

## 구성

- KPI 카드: 카테고리별 1위 모델 및 주요 지표
- 카테고리별(Overall/Coding/Math) 순위 막대 그래프
- 모델별 카테고리 간 순위를 비교하는 크로스 테이블

`index.html`은 Chart.js를 CDN이 아니라 파일에 직접 인라인으로 삽입해 오프라인에서도 동작합니다. 표시되는 순위 데이터(`data/data.json`)는 아래 자동화 파이프라인이 원본 갱신 시점에 맞춰(웹훅) 또는 늦어도 하루 안에(크론 안전망) 갱신합니다.

## 데이터 소스 & 자동 갱신

- 원본: Hugging Face [`lmarena-ai/leaderboard-dataset`](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) (subset: `text`, split: `latest`)
- 사람들이 두 모델의 익명 답변을 비교 투표한 결과를 Bradley–Terry 모델(Elo와 유사)로 환산한 "Arena Score" 기반. 이 값은 데이터셋에 이미 계산되어 있어 별도로 재계산하지 않습니다.
- 카테고리: `overall`, `coding`, `math` (각 상위 20개 모델)

가격/비용 데이터는 조사했으나 신뢰할 수 있는 최신 소스가 없어 이번 버전에는 포함하지 않았습니다.

원본 데이터는 CSV가 아니라 **Supabase(Postgres)** 테이블(`ai_model_leaderboard`)에 저장됩니다. GitHub Actions(`.github/workflows/refresh-data.yml`)가 트리거될 때마다(웹훅 또는 매일 크론) 다음을 실행합니다:

1. `scripts/fetch_hf_to_supabase.py` — Hugging Face의 parquet export에서 최신 스냅샷 전체(29개 카테고리, ~9,700행)를 받아와 `overall`/`coding`/`math` 상위 20개만 걸러 Supabase에 upsert
2. `scripts/build_data.py` — Supabase에서 각 카테고리 최신 스냅샷을 조회해 `data/data.json` 재생성
3. `data/data.json`이 바뀌었으면 자동 커밋·푸시 → GitHub Pages에 반영

이 Supabase 프로젝트는 다른 대시보드(hcp-roi-dashboard)와 같은 프로젝트를 공유하며, 테이블만 분리되어 있습니다. Supabase 접속 정보는 이 저장소의 `Settings → Secrets and variables → Actions`에 `DATABASE_URL`로 등록되어 있습니다.

### 실시간 갱신 (Hugging Face 웹훅)

원본 데이터셋(`lmarena-ai/leaderboard-dataset`)은 고정된 주기가 아니라 하루~최대 열흘 이상 간격으로 불규칙하게 갱신됩니다(과거 커밋 이력 기준 간격 중앙값 약 2일). 하루 1회 크론만으로는 실제 갱신 시점과 어긋나 최대 하루 가까이 지연될 수 있어서, `webhook-relay/`에 Cloudflare Workers 기반 중계 서버를 추가해 원본이 바뀌는 즉시 반영되도록 했습니다.

흐름: **Hugging Face가 데이터셋을 갱신 → 웹훅 발송 → Cloudflare Worker(`webhook-relay/src/index.js`)가 시크릿 검증 후 GitHub Actions `workflow_dispatch` 호출 → `refresh-data.yml` 즉시 실행**. 원본이 바뀌면 보통 몇 초~몇 분 안에 이 대시보드도 갱신됩니다. 매일 크론(`0 21 * * *`)은 웹훅이 실패하거나 유실되는 경우를 대비한 안전망으로 그대로 남겨뒀습니다.

- 배포: `cd webhook-relay && npx wrangler deploy` (Cloudflare API 토큰은 `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` 환경변수로 주입)
- Worker 시크릿: `HF_WEBHOOK_SECRET`(HF 웹훅 헤더 검증용), `GH_DISPATCH_PAT`(이 저장소에 `Actions: Read and write`만 부여된 fine-grained PAT) — 둘 다 `wrangler secret put`으로 등록, 저장소에는 커밋되지 않습니다.
- Hugging Face 쪽 설정: `huggingface.co/settings/webhooks` → watched repo `datasets/lmarena-ai/leaderboard-dataset` → 대상 URL을 배포된 Worker 주소로, secret을 위 `HF_WEBHOOK_SECRET`과 동일하게, trigger는 `Repo update`로 등록
- 즉시 갱신이 필요하면 저장소 `Actions` 탭 → `Refresh dashboard data` → `Run workflow`로 수동 실행도 가능합니다

## 라이선스 / 데이터 출처

원본 데이터셋은 [`lmarena-ai/leaderboard-dataset`](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)(**CC BY 4.0**)이며, 이 라이선스는 출처만 명시하면 가공·재배포를 허용합니다. 이 저장소는 대시보드 본문과 이 README 양쪽에 출처를 명시해 그 조건을 충족하고 있습니다. Chart.js는 MIT 라이선스로 인라인 삽입되어 있습니다.

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
