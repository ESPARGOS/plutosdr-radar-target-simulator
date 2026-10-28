import { $, format, colors, svg, svgText } from "./dom.js";
import { METERS_PER_US, MAX_TARGETS, latency, totalRange, velocityPerHz } from "./scene.js";

export class TargetPlot {
  constructor(controller) {
    this.controller = controller;
    this.drag = null;
    this.wheelAxes = { range: true, velocity: true };
    this.rangeMaximum = 1500;
    this.velocityMaximum = 10;
    for (const axis of ["range", "velocity"]) {
      const input = $(axis === "range" ? "delay-window" : "doppler-window");
      input.oninput = () => {
        const [low, high] = this.limits(axis);
        this.setWindow(axis, low * (high / low) ** Number(input.value));
        this.draw();
      };
      $(axis + "-zoom").onclick = (event) => {
        if (event.target.tagName === "INPUT") return;
        this.wheelAxes[axis] = !this.wheelAxes[axis];
        $(axis + "-wheel").setAttribute("aria-pressed", String(this.wheelAxes[axis]));
        $(axis + "-zoom").classList.toggle("selected", this.wheelAxes[axis]);
      };
    }
    $("plot").addEventListener("wheel", (event) => this.zoom(event), { passive: false });
    $("plot").addEventListener("pointermove", (event) => this.move(event));
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) {
      $("plot").addEventListener(event, (event) => this.endDrag(event));
    }
    $("fit").onclick = () => this.fit();
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe($("plot-wrap"));
  }
  get state() {
    return this.controller.state;
  }
  limits(axis) {
    if (axis === "velocity") return [0.05, 1000];
    return [
      Math.max(3, Math.ceil((latency(this.state) * METERS_PER_US + 3) / 10) * 10),
      ((this.state?.max_delay_us || 102.35) + latency(this.state)) * METERS_PER_US,
    ];
  }
  windowValue(axis) {
    return axis === "range" ? this.rangeMaximum : this.velocityMaximum;
  }
  setWindow(axis, value) {
    const [low, high] = this.limits(axis);
    value = Math.max(low, Math.min(high, value));
    if (axis === "range") this.rangeMaximum = value;
    else this.velocityMaximum = value;
    $(axis === "range" ? "delay-window" : "doppler-window").value =
      Math.log(value / low) / Math.log(high / low);
  }
  rangeCeiling() {
    return this.rangeMaximum / METERS_PER_US;
  }
  rangeSpan() {
    return Math.max(0, this.rangeCeiling() - latency(this.state));
  }
  dopplerLimit() {
    return this.velocityMaximum / velocityPerHz(this.state);
  }
  geometry() {
    const w = $("plot-wrap").clientWidth,
      h = $("plot-wrap").clientHeight;
    return {
      w,
      h,
      left: 88,
      right: w - 24,
      top: 24,
      bottom: h - 60,
      width: w - 112,
      height: h - 84,
      centerX: (88 + w - 24) / 2,
    };
  }
  point(target) {
    const p = this.geometry();
    return {
      x: p.centerX - ((p.width / 2) * target.doppler_hz) / this.dopplerLimit(),
      y: p.bottom - (p.height * (target.delay_us + latency(this.state))) / this.rangeCeiling(),
    };
  }
  inView(target) {
    return (
      target.delay_us >= -1e-8 &&
      target.delay_us <= this.rangeSpan() + 1e-8 &&
      Math.abs(target.doppler_hz) <= this.dopplerLimit() + 1e-8
    );
  }
  showRange(delay) {
    this.setWindow("range", (delay + latency(this.state)) * METERS_PER_US * 1.05);
  }
  showVelocity(hz) {
    this.setWindow("velocity", Math.abs(hz) * velocityPerHz(this.state) * 1.05);
  }
  select(index) {
    const target = this.controller.targets[index];
    if (target) {
      if (target.delay_us > this.rangeSpan()) this.showRange(target.delay_us);
      if (Math.abs(target.doppler_hz) > this.dopplerLimit()) this.showVelocity(target.doppler_hz);
    }
    this.controller.select(index);
  }
  fit() {
    this.showRange(Math.max(0, ...this.controller.targets.map((target) => target.delay_us)));
    this.showVelocity(
      Math.max(0, ...this.controller.targets.map((target) => Math.abs(target.doppler_hz))),
    );
    this.draw();
  }
  plotPoint(event) {
    return new DOMPoint(event.clientX, event.clientY).matrixTransform(
      $("plot").getScreenCTM().inverse(),
    );
  }
  position(event, offset = { dx: 0, dy: 0 }) {
    const p = this.plotPoint(event),
      g = this.geometry();
    const x = p.x - offset.dx,
      y = p.y - offset.dy;
    return {
      delay_us: Math.max(
        0,
        Math.min(
          this.rangeSpan(),
          ((g.bottom - y) / g.height) * this.rangeCeiling() - latency(this.state),
        ),
      ),
      doppler_hz: Math.max(
        -this.dopplerLimit(),
        Math.min(this.dopplerLimit(), ((g.centerX - x) / (g.width / 2)) * this.dopplerLimit()),
      ),
      inside:
        p.x >= g.left &&
        p.x <= g.right &&
        p.y >= g.top &&
        p.y <= g.bottom - (g.height * latency(this.state)) / this.rangeCeiling(),
    };
  }
  beginDrag(event, index) {
    event.stopPropagation();
    if (event.button !== 0 || !this.controller.canEdit) return;
    const position = this.plotPoint(event),
      target = this.point(this.controller.targets[index]);
    this.drag = {
      index,
      id: event.pointerId,
      dx: position.x - target.x,
      dy: position.y - target.y,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    this.controller.beginDrag();
    this.controller.select(index);
    $("plot").setPointerCapture(event.pointerId);
    $("plot").classList.add("dragging");
  }
  move(event) {
    if (!this.drag || event.pointerId !== this.drag.id || !this.controller.canEdit) return;
    if (
      !this.drag.moved &&
      Math.hypot(event.clientX - this.drag.startX, event.clientY - this.drag.startY) < 3
    )
      return;
    this.drag.moved = true;
    const position = this.position(event, this.drag),
      step = this.state.delay_step_us;
    this.controller.edit((targets) =>
      Object.assign(targets[this.drag.index], {
        delay_us: Math.max(
          0,
          Math.min(this.state.max_delay_us, Math.round(position.delay_us / step) * step),
        ),
        doppler_hz: position.doppler_hz,
      }),
    );
  }
  endDrag(event) {
    if (!this.drag || event.pointerId !== this.drag.id) return;
    this.drag = null;
    $("plot").classList.remove("dragging");
    if ($("plot").hasPointerCapture(event.pointerId))
      $("plot").releasePointerCapture(event.pointerId);
    this.controller.endDrag();
  }
  zoom(event) {
    if ((!this.wheelAxes.range && !this.wheelAxes.velocity) || this.drag) return;
    event.preventDefault();
    const delta =
      event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.geometry().h : 1);
    const factor = Math.exp(Math.max(-0.5, Math.min(0.5, delta * 0.002)));
    for (const axis of ["range", "velocity"])
      if (this.wheelAxes[axis]) this.setWindow(axis, this.windowValue(axis) * factor);
    this.draw();
  }
  draw() {
    this.setWindow("range", this.rangeMaximum);
    this.setWindow("velocity", this.velocityMaximum);
    $("range-window-value").textContent = `0–${format(this.rangeMaximum, 1)} m`;
    $("velocity-window-value").textContent = `±${format(this.velocityMaximum, 2)} m/s`;
    const p = this.geometry();
    if (p.width <= 0 || p.height <= 0) return;
    $("plot").setAttribute("viewBox", `0 0 ${p.w} ${p.h}`);
    for (const [key, value] of Object.entries({
      x: p.left,
      y: p.top,
      width: p.width,
      height: p.height,
    })) {
      $("plot-background").setAttribute(key, value);
    }
    $("velocity-axis-title").setAttribute("x", p.centerX);
    $("velocity-axis-title").setAttribute("y", p.h - 12);
    $("range-axis-title").setAttribute(
      "transform",
      `translate(16,${(p.top + p.bottom) / 2}) rotate(-90)`,
    );
    $("empty").setAttribute("x", p.centerX);
    $("empty").setAttribute("y", (p.top + p.bottom) / 2);
    const axes = $("axes");
    axes.replaceChildren();
    for (let i = 0; i <= 4; i++) {
      const x = p.left + (p.width * i) / 4;
      svg(
        "line",
        {
          x1: x,
          y1: p.top,
          x2: x,
          y2: p.bottom,
          stroke: i === 2 ? "#718994" : "#2f3b45",
          "stroke-dasharray": i === 2 ? "5 5" : "none",
        },
        axes,
      );
      svgText(x, p.h - 35, format((i / 2 - 1) * this.velocityMaximum), axes, {
        "text-anchor": "middle",
      });
    }
    for (let i = 0; i <= 5; i++) {
      const y = p.bottom - (p.height * i) / 5;
      svg("line", { x1: p.left, y1: y, x2: p.right, y2: y, stroke: "#2f3b45" }, axes);
      svgText(p.left - 12, y + 5, format((this.rangeMaximum * i) / 5, 1), axes, {
        "text-anchor": "end",
      });
    }
    const blocked = $("unavailable-range");
    blocked.replaceChildren();
    if (latency(this.state) > 0) {
      const boundary = p.bottom - (p.height * latency(this.state)) / this.rangeCeiling();
      for (const fill of ["#202b32", "url(#unavailable-hatch)"]) {
        svg(
          "rect",
          {
            x: p.left,
            y: boundary,
            width: p.width,
            height: p.bottom - boundary,
            fill,
            class: "unavailable-zone",
          },
          blocked,
        );
      }
      svg(
        "line",
        {
          x1: p.left,
          x2: p.right,
          y1: boundary,
          y2: boundary,
          stroke: "#a8b6bd",
          "stroke-dasharray": "4 4",
        },
        axes,
      );
      svgText(
        p.right - 8,
        boundary - 8,
        `Minimum ${format(latency(this.state) * METERS_PER_US, 1)} m`,
        axes,
        { "text-anchor": "end", class: "minimum-label" },
      );
    }
    this.drawTargets();
  }
  drawTargets() {
    const { targets, selected } = this.controller;
    const group = $("targets");
    group.replaceChildren();
    targets.forEach((target, index) => {
      if (!this.inView(target)) return;
      const { x, y } = this.point(target);
      const marker = svg(
        "g",
        {
          class: "target",
          transform: `translate(${x},${y})`,
          "data-index": index,
          tabindex: 0,
          role: "button",
          "aria-label": `Target ${index + 1}, range ${format(totalRange(target, this.state))} meters, Doppler ${format(target.doppler_hz)} Hz`,
        },
        group,
      );
      if (index === selected) svg("circle", { r: 24, fill: colors[index], opacity: 0.12 }, marker);
      svg(
        "circle",
        {
          r: 14,
          fill: target.enabled ? colors[index] : "#aab2bf",
          stroke: "white",
          "stroke-width": 3,
        },
        marker,
      );
      svgText(0, 4, index + 1, marker, { "text-anchor": "middle" });
      marker.addEventListener("pointerdown", (event) => this.beginDrag(event, index));
      marker.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.select(index);
          $("range").focus();
        }
      });
    });
    $("empty").style.display = targets.length ? "none" : "";
    $("count").textContent = `${targets.length} / ${MAX_TARGETS}`;
    $("add").disabled = targets.length >= MAX_TARGETS || !this.controller.canEdit;
    const list = $("target-list");
    list.replaceChildren();
    targets.forEach((target, index) => {
      const button = document.createElement("button");
      button.className = "target-summary" + (index === selected ? " selected" : "");
      const title = document.createElement("strong");
      title.textContent = `● ${index + 1}${target.enabled ? "" : " · off"}`;
      title.style.color = colors[index];
      const details = document.createElement("span");
      details.textContent = `${format(totalRange(target, this.state), 1)} m · ${format(-target.doppler_hz * velocityPerHz(this.state))} m/s`;
      button.append(title, details);
      if (!this.inView(target)) {
        const badge = document.createElement("span");
        badge.className = "outside";
        badge.textContent = "Outside view";
        button.append(badge);
      }
      button.setAttribute("aria-pressed", String(index === selected));
      button.onclick = () => this.select(index);
      list.append(button);
    });
    const amplitude = targets
      .filter((target) => target.enabled)
      .reduce((sum, target) => sum + 10 ** (target.gain_db / 20), 0);
    $("headroom").hidden = amplitude <= 1;
    $("headroom").textContent = "Combined gain may cause clipping. Reduce target gains if needed.";
  }
}
