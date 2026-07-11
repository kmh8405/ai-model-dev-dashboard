# AI 모델 도메인별 강점 대시보드

개발자 페르소나를 위한 AI 모델 성능 비교 대시보드입니다. Overall / Coding / Math 세 카테고리에서 최신 AI 모델(Claude, GPT, Gemini 등)의 Arena Score를 비교하고, 모델별로 카테고리 간 순위 변화를 확인할 수 있습니다. 각 카테고리 상위 20개 모델을 기준으로 하며, 원본 데이터셋이 갱신될 때마다(웹훅) 자동으로 다시 반영되기 때문에 카테고리 간 중복을 제외한 전체 모델 수는 시점마다 달라질 수 있습니다.

🔗 **[대시보드 바로가기](https://kmh8405.github.io/ai-model-dev-dashboard/)**

## 구성

- KPI 카드: 카테고리별 1위 모델 및 주요 지표
- 카테고리별(Overall/Coding/Math) 순위 막대 그래프
- 모델별 카테고리 간 순위를 비교하는 크로스 테이블
- 변경사항 배너: 원본 데이터셋이 갱신되면 이전 스냅샷과 비교해 카테고리별 순위 변동(상승/하락/신규 진입/이탈)을 헤드라인 한 줄 + 목록으로 보여줍니다. `scripts/build_data.py`가 Supabase에 이미 쌓여 있는 스냅샷 이력을 규칙 기반으로 비교해 계산하며(LLM·외부 API 호출 없음), 변동이 없거나 이전 스냅샷이 아직 없으면 배너 자체가 표시되지 않습니다.

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

Hugging Face 쪽이 데이터셋을 새로 커밋하는 동안(parquet 재변환 중)에는 export API가 잠깐 400을 반환할 수 있습니다. 변환이 정확히 얼마나 걸릴지 문서화된 상한이 없어서, `fetch_hf_to_supabase.py`는 이 실패를 최대 60초로 캡을 씌운 지수 백오프로 재시도합니다(`_get_with_retry`, 최대 34회 · 총 최대 약 30분). 이 저장소는 public repo라 GitHub Actions 실행 시간이 무료라, 사람이 나중에 수동으로 재실행하는 대신 자동으로 그만큼 버티도록 넉넉하게 잡았습니다.

또한 이 웹훅은 `refs/heads/main`에 대한 실제 콘텐츠 커밋이 아닌 이벤트(예: HF의 내부 parquet 변환 브랜치 `refs/convert/parquet` 갱신)에도 발동되는데, 그런 이벤트는 `updatedRefs`에 `refs/heads/main` 항목이 아예 없습니다. `webhook-relay/src/index.js`는 이 경우 `repo.headSha`로 대체(fallback)하지 않고 그냥 무시합니다 — 예전엔 이 fallback 때문에 마침 HEAD가 우연히 실제 `text` 커밋이었던 순간에 무관한 이벤트가 필터를 통과해버려, 커밋 하나에 중복 디스패치가 여러 번 발생한 적이 있습니다(2026-07-11). Worker의 `wrangler.toml`에는 `[observability]`를 켜둬서 다음에 비슷한 일이 생기면 Cloudflare 대시보드(Workers & Pages → 해당 Worker → Observability 탭)에서 바로 원인을 확인할 수 있습니다.

`refresh-data.yml`에는 `concurrency` 그룹도 걸려 있어서, 그래도 중복 실행이 오면 동시에 안 돌고 큐에 순서대로 처리되며, `git push` 전 `git pull --rebase`로 서로 충돌 없이 안전하게 넘어갑니다.

### 실시간 갱신 (Hugging Face 웹훅)

원본 데이터셋(`lmarena-ai/leaderboard-dataset`)은 고정된 주기가 아니라 하루~최대 열흘 이상 간격으로 불규칙하게 갱신됩니다(과거 커밋 이력 기준 간격 중앙값 약 2일). 하루 1회 크론만으로는 실제 갱신 시점과 어긋나 최대 하루 가까이 지연될 수 있어서, `webhook-relay/`에 Cloudflare Workers 기반 중계 서버를 추가해 원본이 바뀌는 즉시 반영되도록 했습니다.

흐름: **Hugging Face가 데이터셋을 갱신 → 웹훅 발송 → Cloudflare Worker(`webhook-relay/src/index.js`)가 시크릿 검증 후 GitHub Actions `workflow_dispatch` 호출 → `refresh-data.yml` 즉시 실행**. 원본이 바뀌면 보통 몇 초~몇 분 안에 이 대시보드도 갱신됩니다. 매일 크론(`0 21 * * *`)은 웹훅이 실패하거나 유실되는 경우를 대비한 안전망으로 그대로 남겨뒀습니다.

`lmarena-ai/leaderboard-dataset`은 이 대시보드가 쓰지 않는 카테고리(29개 중 `overall`/`coding`/`math`를 담고 있는 `text` config 하나만 씀)를 포함한 저장소 전체를 한 웹훅으로 묶어서 보내고, HF 웹훅은 config 단위로 필터링하는 기능이 없습니다. 그래서 Worker가 디스패치 전에 해당 웹훅을 유발한 커밋(`updatedRefs`의 sha)의 제목을 HF 커밋 API로 조회해 `"Update text for ..."` 형태인지 확인하고, 관련 없는 카테고리 갱신(`webdev`, `text_to_image`, `agent_*` 등)이면 그냥 무시합니다. 조회에 실패하거나 판단이 애매하면 안전하게 그대로 디스패치합니다(fail open).

- 배포: `cd webhook-relay && npx wrangler deploy`. 인증은 `npx wrangler login`으로 브라우저에서 로그인하는 걸 권장합니다(토큰을 어디에도 붙여넣을 필요 없음). CI 등 비대화형 환경에서만 `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` 환경변수를 씁니다.
- Worker 시크릿: `HF_WEBHOOK_SECRET`(HF 웹훅 헤더 검증용), `GH_DISPATCH_PAT`(이 저장소에 `Actions: Read and write`만 부여된 fine-grained PAT) — 둘 다 `wrangler secret put`으로 등록, 저장소에는 커밋되지 않습니다.
- Hugging Face 쪽 설정: `huggingface.co/settings/webhooks` → watched repo `datasets/lmarena-ai/leaderboard-dataset` → 대상 URL을 배포된 Worker 주소로, secret을 위 `HF_WEBHOOK_SECRET`과 동일하게, trigger는 `Repo update`로 등록
- 즉시 갱신이 필요하면 저장소 `Actions` 탭 → `Refresh dashboard data` → `Run workflow`로 수동 실행도 가능합니다

## 테스트 & CI

`tests/`에 `scripts/fetch_hf_to_supabase.py`(필터링, 재시도 로직)와 `scripts/build_data.py`(Supabase row → JSON 변환)에 대한 pytest 유닛 테스트가 있습니다. Supabase/Hugging Face 호출은 모킹되어 있어 네트워크나 `DATABASE_URL` 없이도 실행됩니다.

```bash
pip install -r requirements-dev.txt
pytest
```

`webhook-relay/test/`에는 Cloudflare Worker(`webhook-relay/src/index.js`)의 카테고리 필터링·시크릿 검증·fail-open 동작을 검증하는 테스트가 Node 내장 테스트 러너(`node --test`, 추가 패키지 설치 없음)로 있습니다.

```bash
cd webhook-relay
node --test
```

`requirements.txt`는 `refresh-data.yml`이 실제로 필요로 하는 런타임 의존성만 담고 있고, `requirements-dev.txt`는 여기에 `pytest`를 더한 로컬/CI용입니다. `.github/workflows/ci.yml`이 `main`에 대한 모든 push·PR에서 pytest와 `node --test` 둘 다 자동으로 돌립니다. 커밋·push 전에는 항상 로컬에서 먼저 이 테스트들을 통과시키는 것을 원칙으로 합니다.

## 트러블슈팅 히스토리

실제로 있었던 문제를 문제 → 원인 → 해결 순으로 남깁니다. 앞으로 이 파이프라인에 문제가 생기고 고치면 이 형식으로 계속 추가합니다.

### 2026-07-10 — 무관한 카테고리 갱신으로 CI 실패 33건

- **문제**: 하룻밤 사이 GitHub Actions 실패 알림 33개.
- **원인**: `lmarena-ai/leaderboard-dataset`은 29개 카테고리를 한 저장소에 묶어두는데, 이 대시보드가 안 쓰는 `webdev`/`text_to_image`/`image_edit` 카테고리가 갱신됐을 뿐인데도 HF 웹훅이 저장소 전체 단위라 매번 워크플로우가 트리거됨. 마침 그 시점에 전체 parquet 재변환이 진행 중이라 우리가 쓰는 `text` config API도 잠깐 400을 반환해서 33건 전부 실패.
- **해결**: `fetch_hf_to_supabase.py`에 지수 백오프 재시도를 추가하고, `webhook-relay/src/index.js`가 디스패치 전에 커밋 제목이 `"Update text for ..."`인지 확인해 무관한 카테고리는 걸러내도록 수정.

### 2026-07-11 — 재시도 예산 부족으로 실제 갱신 실패 7건

- **문제**: 실제 `text` config 갱신(`overall`/`coding`/`math`)이 있었는데도 워크플로우 7건이 전부 실패.
- **원인**: HF의 parquet 재변환이 기존 재시도 예산(5회, 최대 ~75초)보다 오래 걸림 — 몇 시간 뒤 같은 API를 직접 호출해보니 정상 200이었고 데이터도 이미 갱신돼 있었음. 즉 재시도 예산만 부족했던 것.
- **해결**: 재시도 횟수를 34회(60초 캡 · 총 최대 약 30분)로 확대. Public repo라 GitHub Actions 실행 시간이 무료라는 점을 감안해 넉넉하게 설정.

### 2026-07-11 — 웹훅 false positive로 커밋 1개에 디스패치 7번

- **문제**: 실제 `text` 커밋은 1개인데 9초 사이 GitHub Actions가 7번 실행됨.
- **원인**: 사용자가 HF 웹훅 Activity 로그에서 직접 가져온 실제 페이로드로 확인 — `refs/convert/parquet`(HF 내부 parquet 변환 브랜치) 갱신 이벤트였고 `updatedRefs`에 `refs/heads/main` 항목이 아예 없었음. 기존 코드는 이럴 때 `repo.headSha`(그 순간 main의 HEAD)로 대체했는데, 마침 HEAD가 아직 실제 `text` 커밋이었던 순간에 이 무관한 이벤트가 필터를 통과해 중복 디스패치가 발생.
- **해결**: `refs/heads/main` 항목이 없으면 `repo.headSha`로 대체하지 않고 그냥 무시하도록 수정. 실제 페이로드 형태 그대로 회귀 테스트 추가. 다음에 비슷한 일이 생기면 바로 진단할 수 있도록 Cloudflare Worker에 Observability(요청 로그)도 켜둠.

## 라이선스 / 데이터 출처

원본 데이터셋은 [`lmarena-ai/leaderboard-dataset`](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)(**CC BY 4.0**)이며, 이 라이선스는 출처만 명시하면 가공·재배포를 허용합니다. 이 저장소는 대시보드 본문과 이 README 양쪽에 출처를 명시해 그 조건을 충족하고 있습니다. Chart.js는 MIT 라이선스로 인라인 삽입되어 있습니다.

## 로컬 실행

```bash
python -m http.server 8000
# http://localhost:8000 접속
```

데이터 파이프라인을 로컬에서 돌리려면 `.env`에 `DATABASE_URL`을 넣고:

**macOS / Linux**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
set -a && source .env && set +a
python scripts/fetch_hf_to_supabase.py
python scripts/build_data.py
pytest
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Get-Content .env | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item "env:$($matches[1].Trim())" $matches[2] } }
python scripts/fetch_hf_to_supabase.py
python scripts/build_data.py
pytest
```
