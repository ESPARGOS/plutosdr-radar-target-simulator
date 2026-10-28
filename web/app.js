import { RadarAPI } from "./api.js";
import { SceneController } from "./controller.js";
import { TargetPlot } from "./plot.js";
import { $, format } from "./dom.js";
import { MAX_TARGETS, METERS_PER_US, latency, totalRange, parseSceneFile } from "./scene.js";

const onDevice = Boolean(window.RADAR_DEVICE);
export const controller = new SceneController(new RadarAPI({ device: onDevice }));
export const plot = new TargetPlot(controller);
let carrierDirty = false;
const pendingGains = new Set();
let lastSelected = -1;

function setField(id, value, force = false) {
  if (force || document.activeElement !== $(id)) $(id).value = value;
}

export function renderEditor() {
  const target = controller.targets[controller.selected];
  $("editor").hidden = !target;
  $("no-selection").hidden = Boolean(target);
  $("selected-tag").textContent = target ? `Target ${controller.selected + 1}` : "Target";
  if (!target) return;
  const force = controller.dragging || lastSelected !== controller.selected;
  lastSelected = controller.selected;
  const state = controller.state;
  $("range").min = Math.floor(latency(state) * METERS_PER_US * 1000) / 1000;
  $("range").max =
    Math.ceil(((state?.max_delay_us || 102.35) + latency(state)) * METERS_PER_US * 1000) / 1000;
  setField("range", Number(totalRange(target, state).toFixed(3)), force);
  setField("doppler", Number(target.doppler_hz.toFixed(3)), force);
  setField("gain", target.gain_db, force);
  $("delay-display").textContent = `${format(target.delay_us + latency(state), 5)} µs`;
  $("gain-label").textContent = `${format(target.gain_db, 1)} dB`;
  for (const [id, enabled] of [
    ["enabled", true],
    ["disabled", false],
  ]) {
    $(id).setAttribute("aria-pressed", String(target.enabled === enabled));
    $(id).setAttribute(
      "aria-label",
      `Turn target ${controller.selected + 1} ${enabled ? "on" : "off"}`,
    );
  }
  for (const id of ["range", "doppler", "gain", "enabled", "disabled", "remove"]) {
    $(id).disabled = !controller.canEdit;
  }
}

function renderRadio() {
  const state = controller.state;
  $("carrier-form").hidden = !onDevice;
  $("radio-gains").hidden = !onDevice;
  $("carrier-input").disabled = Boolean(controller.operation);
  if (!state) return;
  if (!carrierDirty && Number.isFinite(state.frequency_hz))
    setField("carrier-input", Number((state.frequency_hz / 1e6).toFixed(6)));
  for (const channel of ["rx", "tx"]) {
    const field = $(channel + "-gain");
    field.disabled =
      pendingGains.has(channel) || state.radio_available === false || Boolean(controller.operation);
    if (!pendingGains.has(channel) && Number.isFinite(state[channel + "_gain_db"])) {
      setField(channel + "-gain", state[channel + "_gain_db"]);
    }
    if (Number.isFinite(state[channel + "_gain_min_db"])) {
      field.min = state[channel + "_gain_min_db"];
      field.max = state[channel + "_gain_max_db"];
      field.step = state[channel + "_gain_step_db"];
    }
  }
  $("sample-rate").textContent = Number.isFinite(state.sample_rate_hz)
    ? `Sample rate ${format(state.sample_rate_hz / 1e6)} MSa/s`
    : "Sample clock unavailable";
  $("sample-rate").title = "Digital processing rate, not RF bandwidth";
  const bandwidth =
    Number.isFinite(state.rx_bandwidth_hz) && Number.isFinite(state.tx_bandwidth_hz)
      ? Math.min(state.rx_bandwidth_hz, state.tx_bandwidth_hz)
      : NaN;
  const frequency = (hz) =>
    Number(hz / 1e6).toLocaleString(undefined, { maximumFractionDigits: 2, useGrouping: false });
  $("bandwidth").textContent =
    Number.isFinite(state.frequency_hz) && Number.isFinite(bandwidth)
      ? `RF bandwidth ${format(bandwidth / 1e6)} MHz · ≈ ${frequency(state.frequency_hz - bandwidth / 2)}–${frequency(state.frequency_hz + bandwidth / 2)} MHz`
      : "Radio settings unavailable";
  $("bandwidth").title = "Nominal analog passband; filter edges roll off gradually";
  const knownLatency = Number.isFinite(state.hardware_latency_us);
  $("delay-caption").textContent = knownLatency ? "Total delay" : "Added delay";
  $("range-axis-title").textContent = knownLatency ? "Total range (m)" : "Range offset (m)";
}

function render() {
  renderRadio();
  renderEditor();
  plot.draw();
  const state = controller.state;
  $("connection").textContent =
    state?.mode === "demo"
      ? "Demo · no RF output"
      : state?.connected
        ? "Pluto connected"
        : "Controller unavailable";
  $("connection").className =
    "status " + (state?.mode === "demo" ? "demo" : state?.connected ? "online" : "");
  $("feedback").textContent =
    controller.error || (state?.clipped ? "Clipping detected. Reduce gain." : "");
  $("feedback").classList.toggle("error", Boolean(controller.error || state?.clipped));
  $("mute").disabled = Boolean(controller.operation);
  $("change-status").textContent = controller.operation
    ? "Updating…"
    : controller.error
      ? "Check settings"
      : controller.dirty
        ? "Applying…"
        : "Ready";
}

function showError(error) {
  controller.error = error.message;
  controller.notify();
}
function editSelected(change) {
  const index = controller.selected;
  if (index >= 0) controller.edit((targets) => change(targets[index]));
}

$("add").onclick = () =>
  controller.edit((targets) => {
    if (targets.length >= MAX_TARGETS) return;
    targets.push({
      delay_us: plot.rangeSpan() * (0.2 + 0.18 * targets.length),
      doppler_hz: plot.dopplerLimit() * [0.3, -0.3, 0.55, -0.55][targets.length],
      gain_db: -18,
      enabled: true,
    });
    controller.selected = targets.length - 1;
  });
$("range").onchange = () => {
  const value = Number($("range").value);
  if (!Number.isFinite(value) || !$("range").checkValidity())
    return showError(new Error("Range is outside the available window"));
  const state = controller.state;
  editSelected((target) => {
    const delay =
      Math.round((value / METERS_PER_US - latency(state)) / state.delay_step_us) *
      state.delay_step_us;
    target.delay_us = Math.max(0, Math.min(state.max_delay_us, delay));
  });
  plot.select(controller.selected);
};
$("doppler").onchange = () => {
  const value = Number($("doppler").value);
  if (!$("doppler").value || !Number.isFinite(value)) return;
  if (Math.abs(value) >= controller.state.sample_rate_hz / 2)
    return showError(new Error("Doppler exceeds the sample-rate limit"));
  editSelected((target) => {
    target.doppler_hz = value;
  });
  plot.select(controller.selected);
};
$("gain").oninput = () =>
  editSelected((target) => {
    target.gain_db = Number($("gain").value);
  });
for (const [id, enabled] of [
  ["enabled", true],
  ["disabled", false],
]) {
  $(id).onclick = () =>
    editSelected((target) => {
      target.enabled = enabled;
    });
}
$("remove").onclick = () =>
  controller.edit((targets) => {
    targets.splice(controller.selected, 1);
    controller.selected = Math.min(controller.selected, targets.length - 1);
  });
$("mute").onclick = () => {
  void controller.mute();
};
for (const channel of ["rx", "tx"]) {
  $(channel + "-gain").onchange = async () => {
    const field = $(channel + "-gain");
    if (!field.value || !field.checkValidity() || pendingGains.has(channel)) return;
    pendingGains.add(channel);
    renderRadio();
    await controller.gain(channel, Number(field.value));
    pendingGains.delete(channel);
    if (Number.isFinite(controller.state?.[channel + "_gain_db"]))
      field.value = controller.state[channel + "_gain_db"];
    renderRadio();
  };
}
$("carrier-input").oninput = () => {
  carrierDirty = true;
};
$("carrier-input").onchange = () => {
  if (carrierDirty) $("carrier-form").requestSubmit();
};
$("carrier-form").onsubmit = async (event) => {
  event.preventDefault();
  const hz = Math.round(Number($("carrier-input").value) * 1e6);
  if (!Number.isFinite(hz) || hz < 325e6 || hz > 3800e6)
    return showError(new Error("Carrier must be between 325 and 3800 MHz"));
  await controller.carrier(hz);
  carrierDirty = false;
  if (Number.isFinite(controller.state?.frequency_hz))
    $("carrier-input").value = controller.state.frequency_hz / 1e6;
};
$("export").onclick = () => {
  const targets = controller.targets.map(({ enabled, delay_us, doppler_hz, gain_db }) => ({
    enabled,
    delay_us,
    doppler_hz,
    gain_db,
  }));
  const url = URL.createObjectURL(
    new Blob([JSON.stringify({ version: 1, targets }, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "target-scene.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("import").onclick = () => $("file").click();
$("file").onchange = async (event) => {
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 16384) throw new Error("Scene file is too large");
    const revision = controller.revision;
    const text = await file.text();
    if (revision !== controller.revision || controller.operation) return;
    controller.replace(parseSceneFile(text, controller.state));
    plot.select(controller.selected);
  } catch (error) {
    showError(error);
  } finally {
    $("file").value = "";
  }
};
controller.subscribe(render);
render();
controller.start();
