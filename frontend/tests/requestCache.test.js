import test from "node:test";
import assert from "node:assert/strict";

const { api, cachedGet, bumpSessionEpoch } =
  await import("../src/api/requestCache.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("in-flight response cannot cross a session boundary into the new cache", async () => {
  const first = deferred();
  const second = deferred();
  let calls = 0;

  api.defaults.adapter = async (config) => {
    calls += 1;
    const current = calls === 1 ? first : second;
    const data = calls === 1 ? { owner: "old-user" } : { owner: "new-user" };
    await current.promise;
    return {
      data,
      status: 200,
      statusText: "OK",
      headers: {},
      config,
      request: {},
    };
  };

  const oldRequest = cachedGet("/dashboard/", { force: true });
  bumpSessionEpoch();

  const newRequest = cachedGet("/dashboard/", { force: true });
  second.resolve();

  assert.deepEqual(await newRequest, { owner: "new-user" });

  first.resolve();
  await assert.rejects(oldRequest, /Stale cached request discarded/);

  assert.deepEqual(
    await cachedGet("/dashboard/"),
    { owner: "new-user" },
  );
  assert.equal(calls, 2);
});
