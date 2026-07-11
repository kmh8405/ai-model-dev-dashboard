import { test, describe } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";

const FAKE_COMMITS = [
  { id: "sha-text-update", title: "Update text for 2026-07-09" },
  { id: "sha-text-style", title: "Update text_style_control for 2026-07-09" },
  { id: "sha-webdev", title: "Update webdev for 2026-07-09" },
  { id: "sha-t2i", title: "Update text_to_image for 2026-07-09" },
];

const ENV = { HF_WEBHOOK_SECRET: "test-secret", GH_DISPATCH_PAT: "unused" };

function makeRequest({ secret = "test-secret", sha, noHeader = false } = {}) {
  return new Request("https://example.com/webhook", {
    method: "POST",
    headers: noHeader ? {} : { "x-webhook-secret": secret },
    body: JSON.stringify(
      sha ? { updatedRefs: [{ ref: "refs/heads/main", newSha: sha }] } : {}
    ),
  });
}

// Stubs global.fetch for the duration of one test and reports whether the
// GitHub workflow_dispatch call happened.
function installFetch({ hfOk = true } = {}) {
  let dispatched = false;
  global.fetch = async (url) => {
    const href = String(url);
    if (href.includes("huggingface.co")) {
      return { ok: hfOk, json: async () => FAKE_COMMITS };
    }
    if (href.includes("api.github.com")) {
      dispatched = true;
      return { ok: true, text: async () => "" };
    }
    throw new Error(`unexpected fetch to ${href}`);
  };
  return () => dispatched;
}

describe("webhook relay", () => {
  test("responds ok to a GET health check", async () => {
    const res = await worker.fetch(new Request("https://example.com/webhook", { method: "GET" }), ENV);
    assert.equal(res.status, 200);
  });

  test("rejects methods other than GET/POST", async () => {
    const res = await worker.fetch(new Request("https://example.com/webhook", { method: "PUT" }), ENV);
    assert.equal(res.status, 405);
  });

  test("rejects a request with no secret header", async () => {
    const wasDispatched = installFetch();
    const res = await worker.fetch(makeRequest({ noHeader: true, sha: "sha-text-update" }), ENV);
    assert.equal(res.status, 401);
    assert.equal(wasDispatched(), false);
  });

  test("rejects a request with the wrong secret", async () => {
    const wasDispatched = installFetch();
    const res = await worker.fetch(makeRequest({ secret: "wrong", sha: "sha-text-update" }), ENV);
    assert.equal(res.status, 401);
    assert.equal(wasDispatched(), false);
  });

  test("dispatches on a relevant 'text' config commit", async () => {
    const wasDispatched = installFetch();
    const res = await worker.fetch(makeRequest({ sha: "sha-text-update" }), ENV);
    assert.equal(res.status, 202);
    assert.equal(wasDispatched(), true);
  });

  for (const sha of ["sha-text-style", "sha-webdev", "sha-t2i"]) {
    test(`ignores an irrelevant category commit (${sha})`, async () => {
      const wasDispatched = installFetch();
      const res = await worker.fetch(makeRequest({ sha }), ENV);
      assert.equal(res.status, 202);
      assert.equal(wasDispatched(), false);
    });
  }

  test("fails open (dispatches) when the sha isn't in the recent commit window", async () => {
    const wasDispatched = installFetch();
    const res = await worker.fetch(makeRequest({ sha: "sha-unknown" }), ENV);
    assert.equal(res.status, 202);
    assert.equal(wasDispatched(), true);
  });

  test("fails open (dispatches) when the HF commits lookup errors", async () => {
    const wasDispatched = installFetch({ hfOk: false });
    const res = await worker.fetch(makeRequest({ sha: "sha-text-update" }), ENV);
    assert.equal(res.status, 202);
    assert.equal(wasDispatched(), true);
  });

  test("ignores a payload with no refs/heads/main entry at all", async () => {
    const wasDispatched = installFetch();
    const res = await worker.fetch(makeRequest({ sha: undefined }), ENV);
    assert.equal(res.status, 202);
    assert.equal(wasDispatched(), false);
  });

  test("ignores a refs/convert/parquet update, even when repo.headSha matches a relevant commit", async () => {
    // Real payload shape from a 2026-07-11 incident: HF's internal parquet-
    // conversion branch updated (unrelated to any "text" content commit),
    // but repo.headSha happened to still equal the sha of an earlier
    // relevant "text" commit. Falling back to repo.headSha here is exactly
    // the bug that produced 7 dispatches for one real update.
    const wasDispatched = installFetch();
    const req = new Request("https://example.com/webhook", {
      method: "POST",
      headers: { "x-webhook-secret": "test-secret" },
      body: JSON.stringify({
        event: { action: "update", scope: "repo" },
        repo: { type: "dataset", name: "lmarena-ai/leaderboard-dataset", headSha: "sha-text-update" },
        updatedRefs: [
          { ref: "refs/convert/parquet", oldSha: "old-parquet-sha", newSha: "new-parquet-sha" },
        ],
      }),
    });
    const res = await worker.fetch(req, ENV);
    assert.equal(res.status, 202);
    assert.equal(wasDispatched(), false);
  });

  test("returns 502 when the GitHub dispatch call itself fails", async () => {
    global.fetch = async (url) => {
      const href = String(url);
      if (href.includes("huggingface.co")) {
        return { ok: true, json: async () => FAKE_COMMITS };
      }
      return { ok: false, status: 500, text: async () => "boom" };
    };
    const res = await worker.fetch(makeRequest({ sha: "sha-text-update" }), ENV);
    assert.equal(res.status, 502);
  });
});
