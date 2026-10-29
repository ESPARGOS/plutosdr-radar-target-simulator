import test from "node:test";
import assert from "node:assert/strict";
import { SceneController } from "../web/controller.js";

const target = { enabled: true, delay_us: 1, doppler_hz: 10, gain_db: -18 };
const snapshot = () => ({ connected: true, sample_rate_hz: 160e6, targets: [{ ...target }] });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
function setup(t, api = {}) {
  const controller = new SceneController(
    { state: async () => snapshot(), ...api },
    { delay: 1000 },
  );
  controller.accept(snapshot(), true);
  t.after(() => controller.stop());
  return controller;
}

test("scene edits coalesce into one latest-value request", async (t) => {
  const requests = [];
  const controller = setup(t, {
    apply: async (targets) => {
      requests.push(structuredClone(targets));
      return { ...snapshot(), targets };
    },
  });
  controller.edit((targets) => {
    targets[0].delay_us = 2;
  });
  controller.edit((targets) => {
    targets[0].delay_us = 3;
  });
  await controller.flush();
  assert.equal(requests.length, 1);
  assert.equal(requests[0][0].delay_us, 3);
  assert.equal(controller.dirty, false);
});

test("an old apply response cannot replace newer drag edits", async (t) => {
  const pending = deferred();
  const controller = setup(t, { apply: () => pending.promise });
  controller.beginDrag();
  controller.edit((targets) => {
    targets[0].delay_us = 2;
  });
  const job = controller.flush();
  await tick();
  controller.edit((targets) => {
    targets[0].delay_us = 3;
  });
  pending.resolve({ ...snapshot(), targets: [{ ...target, delay_us: 2 }] });
  await job;
  assert.equal(controller.targets[0].delay_us, 3);
  assert.equal(controller.dirty, true);
});

test("mute waits for an in-flight write and cancels unsent edits", async (t) => {
  const pending = deferred(),
    calls = [];
  const controller = setup(t, {
    apply: () => {
      calls.push("apply");
      return pending.promise;
    },
    mute: async () => {
      calls.push("mute");
      return { ...snapshot(), muted: true, targets: [{ ...target, enabled: false }] };
    },
  });
  controller.edit((targets) => {
    targets[0].delay_us = 2;
  });
  const apply = controller.flush();
  await tick();
  controller.edit((targets) => {
    targets[0].delay_us = 3;
  });
  const mute = controller.mute();
  assert.equal(controller.canEdit, false);
  assert.deepEqual(calls, ["apply"]);
  pending.resolve(snapshot());
  await Promise.all([apply, mute]);
  await tick();
  assert.deepEqual(calls, ["apply", "mute"]);
  assert.equal(controller.targets[0].enabled, false);
  assert.equal(controller.dirty, false);
});

test("mute still confirms disabled targets when the radio clock cannot be read", async (t) => {
  const controller = setup(t, {
    mute: async () => ({
      ...snapshot(),
      muted: true,
      sample_rate_hz: null,
      radio_available: false,
      targets: [{ ...target, delay_us: null, doppler_hz: null, enabled: false }],
    }),
  });
  await controller.mute();
  assert.equal(controller.targets[0].enabled, false);
  assert.equal(controller.canEdit, false);
});

test("a poll started before an edit does not overwrite that edit", async (t) => {
  const pending = deferred();
  const controller = setup(t, { state: () => pending.promise });
  const poll = controller.refresh();
  await tick();
  controller.edit((targets) => {
    targets[0].delay_us = 4;
  });
  pending.resolve(snapshot());
  await poll;
  assert.equal(controller.targets[0].delay_us, 4);
});

test("gain writes and polls share the same queue", async (t) => {
  const pending = deferred(),
    calls = [];
  const controller = setup(t, {
    gain: () => {
      calls.push("gain");
      return pending.promise;
    },
    state: async () => {
      calls.push("state");
      return snapshot();
    },
  });
  const gain = controller.gain("rx", 30),
    poll = controller.refresh();
  await tick();
  assert.deepEqual(calls, ["gain"]);
  pending.resolve(snapshot());
  await Promise.all([gain, poll]);
  assert.deepEqual(calls, ["gain", "state"]);
});

test("failed writes stay visible without an automatic retry loop", async (t) => {
  let calls = 0;
  const controller = setup(t, {
    apply: async () => {
      calls++;
      throw Error("write failed");
    },
  });
  controller.edit((targets) => {
    targets[0].delay_us = 2;
  });
  await controller.flush();
  assert.equal(controller.error, "write failed");
  assert.equal(controller.targets[0].delay_us, 2);
  assert.equal(controller.timer, null);
  assert.equal(calls, 1);
});

test("failed retune reads hardware back without resending an enabled scene", async (t) => {
  let applied = false;
  const controller = setup(t, {
    carrier: async () => {
      throw Error("retune failed");
    },
    state: async () => ({ ...snapshot(), targets: [{ ...target, enabled: false }] }),
    apply: async () => {
      applied = true;
      return snapshot();
    },
  });
  controller.edit((targets) => {
    targets[0].delay_us = 2;
  });
  await controller.carrier(2400e6);
  assert.equal(controller.targets[0].enabled, false);
  assert.equal(controller.error, "retune failed");
  assert.equal(controller.dirty, false);
  assert.equal(applied, false);
});

test("an edit to one target does not overwrite another moving trajectory", async (t) => {
  const calls = [];
  const controller = setup(t, {
    apply: async (targets, state, edits) => {
      calls.push(edits);
      return { ...snapshot(), targets };
    },
  });
  controller.targets.push({ ...target, realistic_movement: true });
  controller.edit((targets) => {
    targets[0].gain_db = -12;
  });
  await controller.flush();
  assert.equal(calls[0].positionEdits, 0);
  assert.equal(calls[0].phaseEdits, 0);
  controller.edit((targets) => {
    targets[0].delay_us = 2;
    targets[0].doppler_hz = 20;
  });
  await controller.flush();
  assert.equal(calls[1].positionEdits, 1);
  assert.equal(calls[1].phaseEdits, 1);
  controller.edit((targets) => {
    targets[1].gain_db = -9;
  });
  await controller.flush();
  assert.equal(calls[2].positionEdits, 0);
  assert.equal(calls[2].phaseEdits, 0);
});
