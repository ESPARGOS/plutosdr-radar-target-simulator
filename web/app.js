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
  $("visible").setAttribute("aria-pressed", String(target.enabled));
  $("movement").setAttribute("aria-pressed", String(Boolean(target.realistic_movement)));
  $("movement").disabled = !controller.canEdit || !state?.motion_available;
  $("movement").title = state?.motion_available
    ? "Move with radial velocity and bounce at the range limits"
    : "Requires the movement service on Pluto";
  for (const id of ["range", "doppler", "gain", "visible", "remove"]) {
    $(id).disabled = !controller.canEdit;
  }
}

function renderRadio() {
  const state = controller.state;
  $("carrier-form").hidden = !onDevice;
  $("radio-gains").hidden = !onDevice;
  $("carrier-input").disabled = !state?.connected || Boolean(controller.operation);
  if (!state) {
    $("rx-gain").disabled = $("tx-gain").disabled = true;
    return;
  }
  if (!carrierDirty && Number.isFinite(state.frequency_hz))
    setField("carrier-input", Number((state.frequency_hz / 1e6).toFixed(6)));
  for (const channel of ["rx", "tx"]) {
    const field = $(channel + "-gain");
    field.disabled =
      pendingGains.has(channel) ||
      !state.connected ||
      state.radio_available === false ||
      Boolean(controller.operation);
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
    ? `Sample rate ${format(state.sample_rate_hz / 1e6)} MSa/s${state.fallback ? " (fallback)" : ""}`
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
      ? `Analog bandwidth ${format(bandwidth / 1e6)} MHz\n≈ ${frequency(state.frequency_hz - bandwidth / 2)}–${frequency(state.frequency_hz + bandwidth / 2)} MHz`
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
  const amplitude = controller.targets
    .filter((t) => t.enabled)
    .reduce((sum, t) => sum + 10 ** (t.gain_db / 20), 0);
  const warning =
    controller.error ||
    (state?.clipped
      ? "Clipping detected. Reduce gain."
      : amplitude > 1
        ? "Combined gain may cause clipping. Reduce target gains."
        : "");
  $("connection").textContent =
    warning ||
    (controller.operation
      ? "Updating…"
      : controller.dirty
        ? "Applying…"
        : state?.mode === "demo"
          ? "Demo · no RF output"
          : state?.connected
            ? state.fallback
              ? "Running at 61.44 MHz (fallback)"
              : "Pluto connected"
            : "Controller unavailable");
  const startup = controller.startup;
  if (startup) {
    const detail = document.createElement("span");
    detail.className = "status-detail";
    const elapsed = Number.isFinite(startup.elapsed_seconds)
      ? `${startup.elapsed_seconds} s elapsed. `
      : "";
    detail.textContent = startup.failed
      ? `${elapsed}Targets muted. Check the startup log on Pluto.`
      : `${elapsed}${Number.isFinite(startup.stage_elapsed_seconds) ? `${startup.stage_elapsed_seconds} s in this step. ` : ""}${startup.fallback ? "160 MHz calibration failed." : "Usually about 30 s total."}`;
    $("connection").append(detail);
    $("connection").title = startup.failed
      ? "Logs: /tmp/radar-startup.log and /tmp/radar-motion.log"
      : "The FPGA loads during boot. Radio timing calibration and integrity checks take most of the startup time. Timing retries can take longer.";
  } else {
    $("connection").removeAttribute("title");
    if (state?.fallback && !warning) {
      const detail = document.createElement("span");
      detail.className = "status-detail";
      detail.textContent = `160 MHz calibration failed. Minimum range ${format(state.hardware_latency_us * METERS_PER_US, 1)} m.`;
      $("connection").append(detail);
    }
  }
  $("connection").className =
    "status " +
    (startup && !startup.failed
      ? "starting"
      : warning
        ? "error"
        : state?.fallback
          ? "fallback"
          : state?.mode === "demo"
            ? "demo"
            : state?.connected
              ? "online"
              : "");
  $("mute").disabled = Boolean(controller.operation);
  $("unmute").disabled = !controller.canEdit || !controller.targets.some((t) => !t.enabled);
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
      gain_db: -14,
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
$("visible").onclick = () =>
  editSelected((target) => {
    target.enabled = !target.enabled;
  });
$("movement").onclick = () =>
  editSelected((target) => {
    target.realistic_movement = !target.realistic_movement;
  });
$("remove").onclick = () =>
  controller.edit((targets) => {
    targets.splice(controller.selected, 1);
    controller.selected = Math.min(controller.selected, targets.length - 1);
  });
$("unmute").onclick = () =>
  controller.edit((targets) => {
    for (const target of targets) target.enabled = true;
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
  const targets = controller.targets.map(
    ({ enabled, delay_us, doppler_hz, gain_db, realistic_movement }) => ({
      enabled,
      delay_us,
      doppler_hz,
      gain_db,
      realistic_movement: Boolean(realistic_movement),
    }),
  );
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
