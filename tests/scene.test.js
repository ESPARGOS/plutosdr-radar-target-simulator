import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { encodeScene, parseSceneFile } from "../web/scene.js";
import { RadarAPI } from "../web/api.js";
const fixtures = JSON.parse(readFileSync(new URL("./scene-contract.json", import.meta.url)));
for (const fixture of fixtures)
  test(fixture.name, () => {
    assert.equal(encodeScene(fixture.targets, fixture), fixture.wire);
  });
test("scene import rejects malformed targets and unknown versions", () => {
  const state = { sample_rate_hz: 160e6 };
  for (const targets of [
    [{ enabled: "yes", delay_us: 0, doppler_hz: 0, gain_db: -18 }],
    [{ enabled: true, delay_us: -1, doppler_hz: 0, gain_db: -18 }],
    [{ enabled: true, delay_us: 0, doppler_hz: 80e6, gain_db: -18 }],
  ]) {
    assert.throws(() => encodeScene(targets, state));
  }
  assert.throws(() => parseSceneFile('{"version":2,"targets":[]}', state));
  assert.throws(() => encodeScene([], { sample_rate_hz: null }));
});
test("preview and device send identical register payloads", async () => {
  const requests = [];
  const fetcher = async (url, options) => {
    requests.push({ url, ...options });
    return { ok: true, json: async () => ({}) };
  };
  const fixture = fixtures[1];
  await new RadarAPI({ device: false, fetcher }).apply(fixture.targets, fixture);
  await new RadarAPI({ device: true, fetcher }).apply(fixture.targets, fixture);
  assert.equal(requests[0].body, requests[1].body);
  assert.equal(requests[0].headers["Content-Type"], "text/plain");
  assert.equal(requests[1].url, "/cgi-bin/radar.cgi/apply");
});
