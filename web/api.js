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
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
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
  apply(targets, state) {
    return this.request("/apply", encodeScene(targets, state));
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
