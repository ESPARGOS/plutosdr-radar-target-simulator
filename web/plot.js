import { $, format, colors, svg, svgText } from "./dom.js";
import { METERS_PER_US, MAX_TARGETS, latency, totalRange, velocityPerHz } from "./scene.js";

export class TargetPlot {
  constructor(controller) {
    this.controller = controller;
    this.drag = null;
    this.touches = new Map();
    this.pinch = null;
    this.popoverAxis = null;
    this.rangeMaximum = 1500;
    this.windowInitialized = false;
    this.velocityMaximum = 10;
    for (const axis of ["range", "velocity"]) {
      const label = $(axis + "-axis-title");
      label.addEventListener("wheel", (event) => this.zoom(event, axis), { passive: false });
      label.addEventListener("click", () => this.openZoom(axis));
      label.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.openZoom(axis);
        }
        if (["ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft", "+", "-"].includes(event.key)) {
          event.preventDefault();
          this.setWindow(
            axis,
            this.windowValue(axis) *
              (["ArrowUp", "ArrowRight", "+"].includes(event.key) ? 0.8 : 1.25),
          );
          this.draw();
        }
      });
      label.setAttribute("title", "Click for a slider, or scroll here to zoom");
    }
    $("zoom-slider").oninput = () => {
      if (!this.popoverAxis) return;
      const [low, high] = this.limits(this.popoverAxis);
      this.setWindow(this.popoverAxis, low * (high / low) ** Number($("zoom-slider").value));
      this.draw();
    };
    $("zoom-close").onclick = () => this.closeZoom(true);
    document.addEventListener("pointerdown", (event) => {
      if (!$("zoom-popover").contains(event.target) && !event.target.closest(".axis-title"))
        this.closeZoom();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.closeZoom(true);
    });
    window.addEventListener("resize", () => this.closeZoom());
    $("plot").addEventListener("pointerdown", (event) => this.touchStart(event), true);
    $("plot").addEventListener("pointermove", (event) => {
      if (!this.touchMove(event)) this.move(event);
    });
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) {
      $("plot").addEventListener(event, (event) => {
        const pinching = Boolean(this.pinch);
        this.touches.delete(event.pointerId);
        if (!this.touches.size) this.pinch = null;
        if (!pinching) this.endDrag(event);
      });
    }
    $("plot").addEventListener(
      "wheel",
      (event) => {
        // Trackpad pinch is delivered as a Ctrl+wheel gesture by Chromium.
        if (event.ctrlKey && !event.target.closest(".axis-title")) {
          this.zoom(event, "range");
          this.zoom(event, "velocity");
        }
      },
      { passive: false },
    );
    $("fit").onclick = () => this.fit();
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe($("plot-wrap"));
    const animate = () => {
      if (!this.controller.dirty && !this.controller.dragging) {
        for (const marker of $("targets").children) {
          const target = this.controller.targets[Number(marker.dataset.index)];
          if (!target?.enabled || !target.realistic_movement) continue;
          const { x, y } = this.point(this.visualTarget(target));
          marker.setAttribute("transform", `translate(${x},${y})`);
        }
      }
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }
  openZoom(axis) {
    if (this.popoverAxis === axis && !$("zoom-popover").hidden) {
      this.closeZoom();
      return;
    }
    this.popoverAxis = axis;
    $("zoom-title").textContent = axis === "range" ? "Range window" : "Velocity window";
    $("zoom-slider").setAttribute("aria-label", $("zoom-title").textContent);
    $("zoom-popover").hidden = false;
    this.syncZoom();
    const label = $(axis + "-axis-title").getBoundingClientRect();
    const popup = $("zoom-popover").getBoundingClientRect();
    $("zoom-popover").style.left =
      `${Math.max(12, Math.min(innerWidth - popup.width - 12, label.left + label.width / 2 - popup.width / 2))}px`;
    $("zoom-popover").style.top =
      `${Math.max(12, Math.min(innerHeight - popup.height - 12, label.top - popup.height - 12))}px`;
    $("zoom-slider").focus({ preventScroll: true });
  }
  closeZoom(focus = false) {
    const axis = this.popoverAxis;
    this.popoverAxis = null;
    $("zoom-popover").hidden = true;
    if (focus && axis) $(axis + "-axis-title").focus({ preventScroll: true });
  }
  syncZoom() {
    if (!this.popoverAxis) return;
    const axis = this.popoverAxis,
      [low, high] = this.limits(axis);
    $("zoom-slider").value = Math.log(this.windowValue(axis) / low) / Math.log(high / low);
    $("zoom-value").textContent =
      axis === "range"
        ? `0–${format(this.rangeMaximum, 1)} m`
        : `±${format(this.velocityMaximum, 2)} m/s`;
  }
  touchStart(event) {
    if (event.pointerType !== "touch" || event.target.closest(".axis-title")) return;
    if (this.touches.size >= 2) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    this.touches.set(event.pointerId, { x: event.clientX, y: event.clientY });
    $("plot").setPointerCapture(event.pointerId);
    if (this.touches.size === 2) {
      if (this.drag) this.endDrag({ pointerId: this.drag.id }, false);
      const [a, b] = [...this.touches.values()];
      this.pinch = {
        distance: Math.max(20, Math.hypot(a.x - b.x, a.y - b.y)),
        range: this.rangeMaximum,
        velocity: this.velocityMaximum,
      };
      event.preventDefault();
      event.stopPropagation();
    }
  }
  touchMove(event) {
    if (!this.touches.has(event.pointerId)) return false;
    this.touches.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (!this.pinch) return false;
    event.preventDefault();
    if (this.touches.size >= 2) {
      const [a, b] = [...this.touches.values()];
      const factor = this.pinch.distance / Math.max(20, Math.hypot(a.x - b.x, a.y - b.y));
      this.setWindow("range", this.pinch.range * factor);
      this.setWindow("velocity", this.pinch.velocity * factor);
      this.draw();
    }
    return true;
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
    if (axis === "range" && this.state?.sample_rate_hz) {
      const upper = Math.max(1, Math.floor((this.rangeSpan() * this.state.sample_rate_hz) / 1e6));
      const previous = this.controller.motionUpperSamples;
      this.controller.motionUpperSamples = upper;
      if (
        previous !== null &&
        previous !== upper &&
        this.controller.targets.some((t) => t.realistic_movement)
      )
        this.controller.changed();
    }
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
  visualTarget(target) {
    if (
      !target.enabled ||
      !target.realistic_movement ||
      this.controller.dirty ||
      this.controller.dragging
    )
      return target;
    // Interpolation is visual only; the Pluto owns the trajectory and its bounds.
    const upper = (this.state.motion_upper_samples * 1e6) / this.state.sample_rate_hz;
    if (!(upper > 0)) return target;
    const elapsed = Math.min(
      0.3,
      Math.max(0, (performance.now() - (this.controller.sceneTime || performance.now())) / 1000),
    );
    const speed = (-target.doppler_hz / this.state.frequency_hz) * 1e6;
    const unfolded = speed >= 0 ? target.delay_us : 2 * upper - target.delay_us;
    const folded = (unfolded + Math.abs(speed) * elapsed) % (2 * upper);
    return {
      ...target,
      delay_us: folded >= upper ? 2 * upper - folded : folded,
      doppler_hz: folded >= upper ? Math.abs(target.doppler_hz) : -Math.abs(target.doppler_hz),
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
      target = this.point(this.visualTarget(this.controller.targets[index]));
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
  endDrag(event, release = true) {
    if (!this.drag || event.pointerId !== this.drag.id) return;
    this.drag = null;
    $("plot").classList.remove("dragging");
    if (release && $("plot").hasPointerCapture(event.pointerId))
      $("plot").releasePointerCapture(event.pointerId);
    this.controller.endDrag();
  }
  zoom(event, axis) {
    if (this.drag) return;
    event.preventDefault();
    const delta =
      event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.geometry().h : 1);
    const factor = Math.exp(Math.max(-0.5, Math.min(0.5, delta * 0.002)));
    this.setWindow(axis, this.windowValue(axis) * factor);
    this.draw();
  }
  draw() {
    if (!this.windowInitialized && this.state?.sample_rate_hz) {
      this.windowInitialized = true;
      if (
        this.controller.targets.some((t) => t.realistic_movement) &&
        this.state.motion_upper_samples
      )
        this.rangeMaximum =
          ((this.state.motion_upper_samples * 1e6) / this.state.sample_rate_hz +
            latency(this.state)) *
          METERS_PER_US;
    }
    this.setWindow("range", this.rangeMaximum);
    this.setWindow("velocity", this.velocityMaximum);

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
    this.syncZoom();
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
      const strength = 10 ** (target.gain_db / 40);
      const radius = 16 + 44 * strength;
      svg(
        "circle",
        {
          class: "gain-aura",
          r: radius,
          fill: colors[index],
          opacity: target.enabled ? 0.06 + 0.08 * strength : 0.025,
          "pointer-events": "none",
        },
        marker,
      );
      svg(
        "circle",
        {
          class: "gain-aura-inner",
          r: 16 + 24 * strength,
          fill: colors[index],
          opacity: target.enabled ? 0.08 + 0.08 * strength : 0.03,
          "pointer-events": "none",
        },
        marker,
      );
      if (index === selected)
        svg(
          "circle",
          {
            r: 19,
            fill: "none",
            stroke: colors[index],
            "stroke-width": 2,
            "stroke-opacity": 0.7,
            "pointer-events": "none",
          },
          marker,
        );
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
  }
}
