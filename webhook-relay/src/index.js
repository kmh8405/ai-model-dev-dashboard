// Relays Hugging Face dataset webhooks into a GitHub Actions workflow_dispatch.
//
// Hugging Face sends a POST with header `X-Webhook-Secret` matching whatever
// secret was configured on huggingface.co/settings/webhooks. We only check
// that header; the payload body itself isn't inspected since this endpoint
// is dedicated to a single subscription (lmarena-ai/leaderboard-dataset).

const GITHUB_OWNER = "kmh8405";
const GITHUB_REPO = "ai-model-dev-dashboard";
const WORKFLOW_FILE = "refresh-data.yml";

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
