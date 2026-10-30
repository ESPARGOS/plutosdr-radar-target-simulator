import { encodeScene } from "./scene.js";

export class RadarAPI {
  constructor({
    device = false,
    fetcher = globalThis.fetch.bind(globalThis),
    timeout = 10000,
  } = {}) {
    this.prefix = device ? "/cgi-bin/radar.cgi" : "/api";
    this.fetcher = fetcher;
    this.timeout = timeout;
  }

  async request(endpoint, body) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), this.timeout);
    try {
      const options = { signal: abort.signal };
      if (body !== undefined)
        Object.assign(options, {
          method: "POST",
          headers: { "Content-Type": "text/plain" },
          body,
        });
      const response = await this.fetcher(this.prefix + endpoint, options);
      const data = await response.json();
      if (!response.ok) {
        const error = new Error(data.error || `HTTP ${response.status}`);
        error.startup = data.startup || null;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Controller request timed out");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  state() {
    return this.request("/state");
  }
  apply(targets, state, edits = {}) {
    let payload = encodeScene(targets, state);
    if (state.motion_available) {
      const mask = targets.reduce(
        (mask, target, index) => mask | (target.realistic_movement ? 1 << index : 0),
        0,
      );
      const upper = Math.max(1, Math.min(2047, Math.floor(edits.upper ?? 2047)));
      payload = `motion ${mask} ${edits.positionEdits ?? 15} ${edits.phaseEdits ?? 15} ${upper}\n${payload}`;
    } else if (targets.some((t) => t.realistic_movement)) {
      throw new Error("Movement service unavailable");
    }
    return this.request("/apply", payload);
  }
  mute() {
    return this.request("/mute", "");
  }
  carrier(hz) {
    return this.request("/radio", String(hz));
  }
  gain(channel, db) {
    return this.request("/gain", `${channel} ${db}`);
  }
}
