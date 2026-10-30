import { validateScene } from "./scene.js";

// Every hardware request uses one queue. Scene edits are coalesced, while mute
// and retune cancel unsent edits so an old update cannot re-enable a target.
export class SceneController {
  constructor(api, { delay = 80 } = {}) {
    this.api = api;
    this.delay = delay;
    this.state = null;
    this.targets = [];
    this.selected = -1;
    this.revision = 0;
    this.confirmedRevision = 0;
    this.dragging = false;
    this.operation = null;
    this.error = "";
    this.startup = null;
    this.listeners = new Set();
    this.queue = Promise.resolve();
    this.timer = null;
    this.sceneJob = null;
    this.refreshJob = null;
    this.pollTimer = null;
    this.running = false;
    this.motionUpperSamples = null;
    this.positionEdits = 0;
    this.phaseEdits = 0;
  }

  get dirty() {
    return this.revision !== this.confirmedRevision;
  }
  get canEdit() {
    return (
      !this.operation &&
      this.state?.connected &&
      Number.isFinite(this.state?.sample_rate_hz) &&
      this.state.sample_rate_hz > 0
    );
  }
  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  notify() {
    for (const listener of this.listeners) listener();
  }
  enqueue(task) {
    const result = this.queue.then(task);
    this.queue = result.catch(() => {});
    return result;
  }

  accept(snapshot, replaceScene = false) {
    this.state = snapshot;
    this.startup = null;
    if (
      replaceScene &&
      snapshot.targets?.every(
        (target) => Number.isFinite(target.delay_us) && Number.isFinite(target.doppler_hz),
      )
    ) {
      this.targets = snapshot.targets.map((target) => ({ ...target }));
      this.sceneTime = performance.now();
      this.selected = Math.min(this.selected, this.targets.length - 1);
    }
    if (snapshot.muted)
      this.targets.forEach((target) => {
        target.enabled = false;
      });
    this.error = snapshot.error || snapshot.warning || "";
    this.notify();
  }

  select(index) {
    this.selected = index;
    this.notify();
  }
  changed() {
    if (!this.canEdit) return;
    this.revision++;
    this.error = "";
    this.notify();
    this.schedule();
  }
  edit(change) {
    if (!this.canEdit) return;
    const before = this.targets.map((target) => ({ ...target }));
    change(this.targets);
    for (let i = 0; i < this.targets.length; i++) {
      const old = before[i],
        target = this.targets[i];
      if (!old || old.id !== target.id || old.delay_us !== target.delay_us)
        this.positionEdits |= 1 << i;
      if (!old || old.id !== target.id || old.doppler_hz !== target.doppler_hz)
        this.phaseEdits |= 1 << i;
    }
    this.changed();
  }
  replace(targets) {
    validateScene(targets, this.state);
    this.positionEdits = this.phaseEdits = 15;
    this.edit(() => {
      this.targets = targets.map((target) => ({ ...target }));
      this.selected = targets.length ? 0 : -1;
    });
  }
  schedule() {
    if (this.timer === null && !this.sceneJob && !this.operation && this.dirty) {
      this.timer = setTimeout(() => {
        this.timer = null;
        void this.flush();
      }, this.delay);
    }
  }
  cancelPending() {
    this.positionEdits = this.phaseEdits = 0;
    clearTimeout(this.timer);
    this.timer = null;
    this.revision++;
  }
  flush() {
    clearTimeout(this.timer);
    this.timer = null;
    if (this.operation || !this.dirty) return Promise.resolve();
    if (this.sceneJob) return this.sceneJob;
    this.sceneJob = this.enqueue(async () => {
      if (this.operation || !this.dirty) return;
      const revision = this.revision;
      const targets = this.targets.map((target) => ({ ...target }));
      try {
        const snapshot = await this.api.apply(targets, this.state, {
          positionEdits: this.positionEdits,
          phaseEdits: this.phaseEdits,
          upper: this.motionUpperSamples,
        });
        if (revision === this.revision) this.positionEdits = this.phaseEdits = 0;
        this.confirmedRevision = revision;
        this.accept(snapshot, revision === this.revision && !this.dragging && !this.operation);
      } catch (error) {
        this.error = error.message;
        this.notify();
        // Keep the edit visible, but don't automatically retry a failed write.
        this.failedRevision = this.revision;
      }
    }).finally(() => {
      this.sceneJob = null;
      if (this.failedRevision !== this.revision) this.schedule();
    });
    return this.sceneJob;
  }
  beginDrag() {
    if (this.canEdit) this.dragging = true;
  }
  endDrag() {
    if (!this.dragging) return;
    this.dragging = false;
    // Ask for final quantized readback even if the last move was already sent.
    if (!this.operation) {
      this.revision++;
      void this.flush();
    }
  }

  async exclusive(name, action) {
    if (this.operation) return;
    this.operation = name;
    this.dragging = false;
    this.cancelPending();
    this.notify();
    try {
      const snapshot = await this.enqueue(async () => {
        try {
          return await action();
        } catch (error) {
          try {
            this.accept(await this.api.state(), true);
          } catch {
            /* Keep the last known state. */
          }
          throw error;
        }
      });
      this.confirmedRevision = this.revision;
      this.accept(snapshot, true);
    } catch (error) {
      this.error = error.message;
      // Read back after an uncertain result instead of resending old targets.
      this.confirmedRevision = this.revision;
      this.notify();
    } finally {
      this.operation = null;
      this.notify();
    }
  }
  mute() {
    return this.exclusive("mute", () => this.api.mute());
  }
  carrier(hz) {
    return this.exclusive("carrier", () => this.api.carrier(hz));
  }
  gain(channel, db) {
    return this.enqueue(async () => {
      try {
        this.accept(await this.api.gain(channel, db));
      } catch (error) {
        this.error = error.message;
        this.notify();
      }
    });
  }
  refresh() {
    if (this.refreshJob) return this.refreshJob;
    const revision = this.revision;
    this.refreshJob = this.enqueue(async () => {
      try {
        const snapshot = await this.api.state();
        this.accept(
          snapshot,
          revision === this.revision && !this.dirty && !this.dragging && !this.operation,
        );
      } catch (error) {
        this.error = error.message;
        this.startup = error.startup || null;
        if (this.state) this.state = { ...this.state, connected: false };
        this.notify();
      }
    }).finally(() => {
      this.refreshJob = null;
    });
    return this.refreshJob;
  }
  start() {
    if (this.running) return;
    this.running = true;
    const poll = async () => {
      await this.refresh();
      if (this.running)
        this.pollTimer = setTimeout(
          poll,
          this.targets.some((t) => t.enabled && t.realistic_movement) ? 100 : 2500,
        );
    };
    void poll();
  }
  stop() {
    this.running = false;
    clearTimeout(this.pollTimer);
    clearTimeout(this.timer);
    this.timer = null;
  }
}
