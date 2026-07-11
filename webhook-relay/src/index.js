// Relays Hugging Face dataset webhooks into a GitHub Actions workflow_dispatch.
//
// Hugging Face sends a POST with header `X-Webhook-Secret` matching whatever
// secret was configured on huggingface.co/settings/webhooks.
//
// The webhook is repo-wide — HF doesn't support subscribing to a single
// config/category within a dataset repo — but leaderboard-dataset bundles
// ~29 unrelated categories that each get their own commit on their own
// schedule (titled "Update <config> for <date>"). Only the "text" config
// feeds this dashboard's overall/coding/math data, so before dispatching we
// look up the triggering commit's title and skip anything that isn't a
// "text" update. Without this, every unrelated category refresh (webdev,
// text_to_image, agent_*, ...) burns a GitHub Actions run for nothing —
// which is exactly what caused a burst of ~30 runs (and failure
// notifications) on 2026-07-10 when none of them were actually "text".
//
// The webhook also fires for ref updates that have nothing to do with
// content commits at all — e.g. `refs/convert/parquet`, HF's internal
// parquet-conversion branch — where `updatedRefs` has no `refs/heads/main`
// entry. See mainBranchCommitSha() below for why those are ignored
// entirely rather than falling back to `repo.headSha`.

const GITHUB_OWNER = "kmh8405";
const GITHUB_REPO = "ai-model-dev-dashboard";
const WORKFLOW_FILE = "refresh-data.yml";

const HF_DATASET = "lmarena-ai/leaderboard-dataset";
const RELEVANT_CONFIG = "text";
// Matches "Update text for 2026-07-02" but not "Update text_style_control
// for ..." / "Update text_to_image for ..." (note the trailing space).
const RELEVANT_COMMIT_TITLE = new RegExp(`^Update ${RELEVANT_CONFIG} for `);

async function isRelevantCommit(sha) {
  const res = await fetch(
    `https://huggingface.co/api/datasets/${HF_DATASET}/commits/main?limit=20`,
    { headers: { "User-Agent": "ai-model-dashboard-hf-relay" } }
  );
  if (!res.ok) return true; // HF API hiccup — fail open
  const commits = await res.json();
  const commit = commits.find((c) => c.id === sha);
  if (!commit) return true; // sha fell outside the recent window — fail open
  return RELEVANT_COMMIT_TITLE.test(commit.title);
}

// Only a genuine content commit to `main` shows up as its own entry in
// updatedRefs — HF also fires this same webhook for unrelated ref updates
// (e.g. `refs/convert/parquet`, its internal parquet-conversion branch)
// where `updatedRefs` has no `refs/heads/main` entry at all. Those events
// still carry `repo.headSha` (whatever main's HEAD happens to be at that
// moment, unrelated to what actually changed), and using it as a fallback
// caused false-positive dispatches whenever HEAD coincidentally still
// pointed at a real "text" commit — this is what produced 7 dispatches for
// a single "text" update on 2026-07-11. So: no `refs/heads/main` entry
// means there's nothing relevant to check, full stop — no `repo.headSha`
// fallback.
function mainBranchCommitSha(payload) {
  return payload?.updatedRefs?.find((ref) => ref.ref === "refs/heads/main")?.newSha ?? null;
}

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      return new Response("ok", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const suppliedSecret = request.headers.get("x-webhook-secret");
    if (!suppliedSecret || suppliedSecret !== env.HF_WEBHOOK_SECRET) {
      return new Response("unauthorized", { status: 401 });
    }

    const payload = await request.json().catch(() => null);
    const sha = mainBranchCommitSha(payload);

    if (!sha) {
      return new Response("ignored: not a main-branch content update", { status: 202 });
    }

    if (!(await isRelevantCommit(sha))) {
      return new Response("ignored: not a text-config update", { status: 202 });
    }

    const dispatchUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
    const ghResponse = await fetch(dispatchUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_PAT}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "ai-model-dashboard-hf-relay",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    });

    if (!ghResponse.ok) {
      const errText = await ghResponse.text();
      return new Response(`github dispatch failed: ${ghResponse.status} ${errText}`, { status: 502 });
    }

    return new Response("dispatched", { status: 202 });
  },
};
