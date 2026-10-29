// Scene values use microseconds, hertz and dB. The wire format uses FPGA words.
export const MAX_TARGETS = 4;
export const MAX_DELAY_SAMPLES = 2047;
export const METERS_PER_US = 149.896229;
export const PHASE_SCALE = 2 ** 32;

export function sampleRate(state) {
  const rate = state?.sample_rate_hz;
  if (!Number.isFinite(rate) || rate <= 0) throw new Error("Sample clock is unavailable");
  return rate;
}

export const latency = (state) =>
  Number.isFinite(state?.hardware_latency_us) ? state.hardware_latency_us : 0;
export const totalRange = (target, state) => (target.delay_us + latency(state)) * METERS_PER_US;
export const velocityPerHz = (state) => 299792458 / (2 * (state?.frequency_hz || 2380e6));

export function validateScene(targets, state) {
  const rate = sampleRate(state);
  if (!Array.isArray(targets) || targets.length > MAX_TARGETS) {
    throw new Error("Expected up to four targets");
  }
  for (const target of targets) {
    if (
      !target ||
      ![target.delay_us, target.doppler_hz, target.gain_db].every(Number.isFinite) ||
      typeof target.enabled !== "boolean" ||
      (target.realistic_movement !== undefined && typeof target.realistic_movement !== "boolean") ||
      target.delay_us < 0 ||
      target.delay_us > (MAX_DELAY_SAMPLES * 1e6) / rate ||
      Math.abs(target.doppler_hz) >= rate / 2 ||
      target.gain_db < -90 ||
      target.gain_db > 0
    ) {
      throw new Error("Target value out of range");
    }
  }
  return targets;
}

export function encodeScene(targets, state) {
  const rate = sampleRate(state);
  validateScene(targets, state);
  let mask = 0;
  const rows = targets.map((target, index) => {
    if (target.enabled) mask |= 1 << index;
    return [
      Math.round((target.delay_us * rate) / 1e6),
      Math.round((target.doppler_hz / rate) * PHASE_SCALE) >>> 0,
      Math.min(32767, Math.round(32768 * 10 ** (target.gain_db / 20))),
    ].join(" ");
  });
  while (rows.length < MAX_TARGETS) rows.push("0 0 0");
  return [mask, ...rows].join("\n");
}

export function parseSceneFile(text, state) {
  const scene = JSON.parse(text);
  if (scene.version !== undefined && scene.version !== 1)
    throw new Error("Unsupported scene version");
  return validateScene(scene.targets, state).map((target) => ({ ...target }));
}
