// A recording's spectrogram: drawn from the server's pixels, with the calls
// BatDetect2 boxed and numbered by animal, a playback cursor, and dragging to
// look closer. Animals are told apart by number, not colour, so any number of
// them reads the same for everyone.

import { svg } from "./chart.js";
import { h } from "./dom.js";
import { formatNumber } from "./i18n.js";
import { MAGMA } from "./magma.js";

const HEIGHT = 340;
const AXIS = { left: 44, bottom: 22 };
const MIN_KHZ = 10;
const MAX_KHZ = 130;

function niceStep(span, target) {
  const raw = span / target;
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * power).find((step) => step >= raw);
}

export function spectrogram(recordingId, duration, sources, { onZoom }) {
  const canvas = h("canvas", { class: "pixels" });
  const overlay = svg("svg", { class: "overlay" });
  const box = h("div", { class: "spectrogram" }, canvas, overlay);
  const state = { start: 0, end: duration, cursor: null, picture: null };

  const geometry = () => {
    const width = box.clientWidth - AXIS.left;
    const picture = state.picture;
    const top = picture ? picture.minKhz + picture.rows * picture.khzPerRow : MAX_KHZ;
    const bottom = picture ? picture.minKhz : MIN_KHZ;
    return {
      width,
      x: (s) => AXIS.left + ((s - state.start) / (state.end - state.start)) * width,
      time: (x) => state.start + ((x - AXIS.left) / width) * (state.end - state.start),
      y: (khz) => ((top - khz) / (top - bottom)) * (HEIGHT - AXIS.bottom),
      top,
      bottom,
    };
  };

  const drawOverlay = () => {
    const g = geometry();
    overlay.setAttribute("width", box.clientWidth);
    overlay.setAttribute("height", HEIGHT);
    overlay.replaceChildren();
    const plotBottom = HEIGHT - AXIS.bottom;

    for (let khz = Math.ceil(g.bottom / 20) * 20; khz <= g.top; khz += 20) {
      const label = svg("text", { x: AXIS.left - 6, y: g.y(khz) + 4, "text-anchor": "end", class: "axis" });
      label.textContent = formatNumber(khz);
      overlay.append(svg("line", { x1: AXIS.left - 3, x2: AXIS.left, y1: g.y(khz), y2: g.y(khz), class: "tickmark" }), label);
    }
    const unit = svg("text", { x: 4, y: 12, class: "axis" });
    unit.textContent = "kHz";
    overlay.append(unit);

    const step = niceStep(state.end - state.start, 8);
    for (let s = Math.ceil(state.start / step) * step; s <= state.end + 1e-9; s += step) {
      const label = svg("text", { x: g.x(s), y: HEIGHT - 6, "text-anchor": "middle", class: "axis" });
      label.textContent = `${formatNumber(Number(s.toFixed(3)))} s`;
      overlay.append(label);
    }

    sources.forEach((source, i) => {
      let numbered = false;
      for (const call of source.calls) {
        if (call.end_s < state.start || call.start_s > state.end) continue;
        const x = g.x(call.start_s);
        const y = g.y(Math.min(call.high_khz, g.top));
        const width = Math.max(2, g.x(call.end_s) - x);
        const height = Math.max(2, g.y(Math.max(call.low_khz, g.bottom)) - y);
        overlay.append(svg("rect", { x, y, width, height, class: "call" }));
        if (!numbered) {
          const badge = svg("g", { class: "badge" });
          badge.append(svg("rect", { x: x - 1, y: Math.max(0, y - 15), width: 14, height: 14, rx: 3 }));
          const n = svg("text", { x: x + 6, y: Math.max(0, y - 15) + 11, "text-anchor": "middle" });
          n.textContent = String(i + 1);
          badge.append(n);
          overlay.append(badge);
          numbered = true;
        }
      }
    });

    if (state.cursor !== null && state.cursor >= state.start && state.cursor <= state.end) {
      overlay.append(svg("line", { x1: g.x(state.cursor), x2: g.x(state.cursor), y1: 0, y2: plotBottom, class: "cursor" }));
    }
  };

  const load = async () => {
    const width = Math.round((box.clientWidth - AXIS.left) * (window.devicePixelRatio || 1));
    const query = new URLSearchParams({
      width: Math.max(100, Math.min(4000, width)),
      min_khz: MIN_KHZ,
      max_khz: MAX_KHZ,
      start_s: state.start,
      end_s: state.end,
    });
    const response = await fetch(`/api/recordings/${recordingId}/spectrogram?${query}`);
    if (!response.ok) return;
    const pixels = new Uint8Array(await response.arrayBuffer());
    const columns = Number(response.headers.get("x-columns"));
    const rows = Number(response.headers.get("x-rows"));
    state.picture = {
      rows,
      minKhz: Number(response.headers.get("x-min-khz")),
      khzPerRow: Number(response.headers.get("x-khz-per-row")),
    };
    // Columns arrive one after another, each from low to high frequency;
    // the canvas wants rows from the top.
    canvas.width = columns;
    canvas.height = rows;
    const image = new ImageData(columns, rows);
    for (let c = 0; c < columns; c++) {
      for (let r = 0; r < rows; r++) {
        const value = pixels[c * rows + r] * 3;
        const at = ((rows - 1 - r) * columns + c) * 4;
        image.data[at] = MAGMA[value];
        image.data[at + 1] = MAGMA[value + 1];
        image.data[at + 2] = MAGMA[value + 2];
        image.data[at + 3] = 255;
      }
    }
    canvas.getContext("2d").putImageData(image, 0, 0);
    canvas.style.left = `${AXIS.left}px`;
    canvas.style.width = `${box.clientWidth - AXIS.left}px`;
    canvas.style.height = `${HEIGHT - AXIS.bottom}px`;
    drawOverlay();
  };

  // Dragging across picks a stretch to look closer at.
  let drag = null;
  overlay.addEventListener("pointerdown", (event) => {
    const x = event.offsetX;
    if (x < AXIS.left) return;
    drag = { from: x, mark: svg("rect", { x, y: 0, width: 0, height: HEIGHT - AXIS.bottom, class: "selection" }) };
    overlay.append(drag.mark);
    overlay.setPointerCapture(event.pointerId);
  });
  overlay.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const x = Math.max(AXIS.left, Math.min(event.offsetX, box.clientWidth));
    drag.mark.setAttribute("x", Math.min(drag.from, x));
    drag.mark.setAttribute("width", Math.abs(x - drag.from));
  });
  overlay.addEventListener("pointerup", (event) => {
    if (!drag) return;
    const g = geometry();
    const a = g.time(Math.min(drag.from, event.offsetX));
    const b = g.time(Math.max(drag.from, event.offsetX));
    drag.mark.remove();
    const wide = Math.abs(event.offsetX - drag.from) > 8;
    drag = null;
    if (wide) zoom(Math.max(0, a), Math.min(duration, b));
  });

  const zoom = (start, end) => {
    state.start = start;
    state.end = end;
    onZoom(start, end);
    load();
  };

  new ResizeObserver(() => load()).observe(box);
  return {
    element: box,
    zoom,
    range: () => [state.start, state.end],
    cursor: (seconds) => {
      state.cursor = seconds;
      if (state.picture) drawOverlay();
    },
  };
}
