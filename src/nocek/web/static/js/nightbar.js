// One night as a single bar from sunset to sunrise: a mark for every recording, as
// tall as what it holds (a named bat, calls without a name, or nothing) and coloured
// by the bat. Hovering shows what a mark is; clicking opens it. The legend under the
// bar counts each kind and, hovered or clicked, picks out its marks. A busy night can
// be looked at closer: the bar widens and scrolls sideways.

import { colourOf, partsOf } from "./bat-colours.js";
import { h, replace } from "./dom.js";
import { formatNumber, formatTime, t } from "./i18n.js";
import { localName } from "./names.js";

const HEIGHT = { bat: 44, withheld: 22, quiet: 8, unanalysed: 8 };
const NEAR_PX = 10; // how close the pointer must be to a mark to point at it
const MARGIN_MIN = 10;
const ZOOMS = [1, 2, 4, 8, 16, 32];
const LABEL_PX = 56; // the least room between two time labels
const STEPS_MIN = [5, 10, 15, 30, 60, 120]; // the spacings time labels may take
let lastZoom = 1; // kept from one night to the next

// rows: the night's recordings in time order; sun: {sunset, sunrise} or nulls;
// hues: from assignHues(); selected: a recording id; onSelect(id).
export function nightBar(rows, sun, hues, { selected = null, onSelect = () => {} } = {}) {
  const times = rows.map((r) => minutes(r.recorded_at));
  const dusk = sun.sunset ? minutes(sun.sunset) : null;
  const dawn = sun.sunrise ? minutes(sun.sunrise) : null;
  const from = Math.min(...times, dusk ?? Infinity) - MARGIN_MIN;
  const to = Math.max(...times, dawn ?? -Infinity, from + 60) + MARGIN_MIN;
  const x = (m) => ((m - from) / (to - from)) * 100;

  const tip = h("div", { class: "tip", hidden: true });
  const marks = rows.map((row, i) => {
    const parts = partsOf(row, hues);
    const tallest = Math.max(...parts.map((p) => HEIGHT[p.kind]));
    const units = parts.map((p) => (p.kind === "bat" ? 2 : 1));
    const total = units.reduce((a, b) => a + b, 0);
    const mark = h(
      "div",
      { class: "mark", style: `left: ${x(times[i])}%; height: ${tallest}px` },
      parts.map((p, j) =>
        h("i", { style: `height: ${(units[j] / total) * 100}%; background: ${colourOf(p)}` }),
      ),
    );
    mark.tokens = new Set(parts.map(token));
    return mark;
  });

  const bar = h(
    "div",
    { class: "bar", tabindex: "0", role: "group", "aria-label": t("home.night_bar") },
    dusk !== null ? sunLine("sunset", x(dusk), t("home.sunset", { time: formatTime(sun.sunset) })) : null,
    dawn !== null ? sunLine("sunrise", x(dawn), t("home.sunrise", { time: formatTime(sun.sunrise) })) : null,
    marks,
  );

  // The mark nearest the pointer, if it is near enough.
  const nearest = (event) => {
    const box = bar.getBoundingClientRect();
    const at = from + ((event.clientX - box.left) / box.width) * (to - from);
    let best = -1;
    for (let i = 0; i < rows.length; i++) {
      if (best < 0 || Math.abs(times[i] - at) < Math.abs(times[best] - at)) best = i;
    }
    const px = best < 0 ? Infinity : Math.abs(((times[best] - at) / (to - from)) * box.width);
    return px <= NEAR_PX ? best : -1;
  };
  // Set up once the scrolling frame exists, below: the bar can be taken hold of away
  // from any recording.
  let grab = null;

  let pointed = -1;
  bar.addEventListener("pointermove", (event) => {
    if (grab.active()) return;
    const i = nearest(event);
    bar.classList.toggle("over-mark", i >= 0);
    if (i === pointed) return;
    marks[pointed]?.classList.remove("pointed");
    pointed = i;
    if (i < 0) {
      tip.hidden = true;
      return;
    }
    marks[i].classList.add("pointed");
    replace(tip, h("strong", {}, formatTime(rows[i].recorded_at)), describe(rows[i], hues));
    // The tip sits outside the scrolling frame, which would clip it, over the mark.
    const outer = element.getBoundingClientRect();
    const mark = marks[i].getBoundingClientRect();
    tip.style.left = `${mark.left + mark.width / 2 - outer.left}px`;
    tip.style.top = `${bar.getBoundingClientRect().top - outer.top}px`;
    tip.hidden = false;
  });
  bar.addEventListener("pointerleave", () => {
    marks[pointed]?.classList.remove("pointed");
    pointed = -1;
    tip.hidden = true;
  });
  bar.addEventListener("click", (event) => {
    if (grab.dragged()) return; // the end of a drag, not a click
    const i = nearest(event);
    if (i >= 0) onSelect(rows[i].id);
  });

  const select = (id) => {
    rows.forEach((row, i) => marks[i].classList.toggle("selected", row.id === id));
  };
  select(selected);

  // Picking out one kind of mark, from the legend.
  let pinned = null;
  const focus = (kind) => {
    for (const mark of marks) mark.classList.toggle("dim", kind !== null && !mark.tokens.has(kind));
  };
  const legendItems = legend(rows, hues).map(({ kind, colour, label, count }) =>
    h(
      "button",
      {
        class: "legend-item",
        "aria-pressed": "false",
        onpointerenter: () => focus(kind),
        onpointerleave: () => focus(pinned),
        onclick: (event) => {
          pinned = pinned === kind ? null : kind;
          for (const item of event.currentTarget.parentElement.children) item.setAttribute("aria-pressed", "false");
          if (pinned) event.currentTarget.setAttribute("aria-pressed", "true");
          focus(pinned);
        },
      },
      h("span", { class: "swatch", style: `background: ${colour}` }),
      label,
      h("span", { class: "count" }, formatNumber(count)),
    ),
  );

  // Closer: the track holding the bar and its times widens, its frame scrolls sideways.
  const hours = h("div", { class: "hours" });
  const track = h("div", { class: "track" }, bar, hours);
  const scroller = h("div", { class: "scroller" }, track);
  grab = grabbable(bar, scroller, (event) => nearest(event) < 0);
  grabbable(hours, scroller);
  const level = h("span", { class: "zoom-level" });
  const zoomButton = (by) => {
    const label = t(by > 0 ? "home.zoom_in" : "home.zoom_out");
    return h(
      "wa-button",
      { size: "small", appearance: "plain", title: label, onclick: () => zoomBy(by) },
      h("wa-icon", { name: by > 0 ? "zoom-in" : "zoom-out", label }),
    );
  };
  let zoom = lastZoom;
  const drawHours = () => {
    const width = (scroller.clientWidth || 1000) * zoom;
    const perMinute = width / (to - from);
    const step = STEPS_MIN.find((m) => m * perMinute >= LABEL_PX) ?? STEPS_MIN.at(-1);
    replace(hours, timeLabels(from, to, step).map((m) => h("span", { style: `left: ${x(m)}%` }, clock(m))));
  };
  // A new zoom, keeping the moment under `anchor` (a point on screen) where it is.
  const setZoom = (wanted, anchor = null) => {
    const next = Math.min(ZOOMS.at(-1), Math.max(1, wanted));
    const frame = scroller.getBoundingClientRect();
    const at = anchor ?? frame.left + frame.width / 2;
    const fraction = (scroller.scrollLeft + at - frame.left) / (scroller.scrollWidth || 1);
    zoom = lastZoom = next;
    track.style.width = `${zoom * 100}%`;
    bar.classList.toggle("pannable", zoom > 1);
    hours.classList.toggle("pannable", zoom > 1);
    scroller.classList.toggle("zoomed", zoom > 1);
    scroller.scrollLeft = fraction * scroller.scrollWidth - (at - frame.left);
    level.textContent = `${formatNumber(Math.round(zoom * 10) / 10)}×`;
    drawHours();
  };
  // The next level up or down from wherever the wheel left it.
  const zoomBy = (direction) => {
    const next =
      direction > 0
        ? (ZOOMS.find((z) => z > zoom + 0.01) ?? ZOOMS.at(-1))
        : ([...ZOOMS].reverse().find((z) => z < zoom - 0.01) ?? 1);
    setZoom(next);
    reveal();
  };
  // Ctrl and the wheel, or a pinch on a trackpad, zoom around the pointer.
  scroller.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      setZoom(zoom * Math.exp(-event.deltaY / 200), event.clientX);
    },
    { passive: false },
  );
  // The selected recording kept in view when the bar is wider than its frame.
  const reveal = () => {
    const mark = marks.find((m) => m.classList.contains("selected"));
    if (!mark || zoom === 1) return;
    const frame = scroller.getBoundingClientRect();
    const box = mark.getBoundingClientRect();
    if (box.left < frame.left + 20 || box.right > frame.right - 20) {
      scroller.scrollLeft += box.left - frame.left - frame.width / 2;
    }
  };
  new ResizeObserver(drawHours).observe(scroller);

  const element = h(
    "div",
    { class: "nightbar" },
    scroller,
    tip,
    h(
      "div",
      { class: "legend" },
      legendItems,
      h("span", { class: "zoom" }, zoomButton(-1), level, zoomButton(1)),
    ),
  );
  setZoom(zoom);
  requestAnimationFrame(reveal);
  return {
    element,
    select: (id) => {
      select(id);
      reveal();
    },
  };
}

// Taking hold of `surface` and moving the pointer moves the frame's content sideways,
// when it is wider than the frame and canStart(event) agrees. dragged() says, once,
// whether the pointer moved, so the click ending a drag can be told from a click.
function grabbable(surface, scroller, canStart = () => true) {
  let drag = null;
  let moved = false;
  surface.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || scroller.scrollWidth <= scroller.clientWidth || !canStart(event)) return;
    drag = { x: event.clientX, left: scroller.scrollLeft };
    moved = false;
    surface.setPointerCapture(event.pointerId);
    surface.classList.add("panning");
  });
  surface.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    if (Math.abs(dx) > 3) moved = true;
    scroller.scrollLeft = drag.left - dx;
  });
  const release = () => {
    drag = null;
    surface.classList.remove("panning");
  };
  surface.addEventListener("pointerup", release);
  surface.addEventListener("pointercancel", release);
  return {
    active: () => drag !== null,
    dragged: () => {
      const was = moved;
      moved = false;
      return was;
    },
  };
}

// A mark's parts as the legend's kinds: "h1".."h4" for the four hues, then "other",
// "withheld", "quiet", "unanalysed".
function token(part) {
  if (part.kind !== "bat") return part.kind;
  return part.hue ? `h${part.hue}` : "other";
}

function legend(rows, hues) {
  const counts = new Map();
  const labels = new Map();
  for (const row of rows) {
    const parts = partsOf(row, hues);
    for (const kind of new Set(parts.map(token))) counts.set(kind, (counts.get(kind) ?? 0) + 1);
    for (const part of parts) if (part.kind === "bat" && part.hue) labels.set(`h${part.hue}`, part);
  }
  const order = ["h1", "h2", "h3", "h4", "other", "withheld", "quiet", "unanalysed"];
  return order
    .filter((kind) => counts.has(kind))
    .map((kind) => {
      const part = labels.get(kind);
      return {
        kind,
        count: counts.get(kind),
        colour: part ? colourOf(part) : colourOf(kind === "other" ? { kind: "bat", hue: null } : { kind }),
        label: part ? part.taxa.map(localName).join(" / ") : t(`home.legend.${kind}`),
      };
    });
}

function describe(row, hues) {
  return h(
    "ul",
    {},
    partsOf(row, hues).map((part) =>
      h(
        "li",
        {},
        h("span", { class: "swatch", style: `background: ${colourOf(part)}` }),
        part.kind === "bat" ? part.taxa.map(localName).join(" / ") : t(`home.legend.${part.kind}`),
      ),
    ),
  );
}

function sunLine(which, left, label) {
  return h("div", { class: `sun ${which}`, style: `left: ${left}%` }, h("span", {}, label));
}

// Times every `step` minutes inside the bar.
function timeLabels(from, to, step) {
  const out = [];
  for (let m = Math.ceil(from / step) * step; m <= to; m += step) out.push(m);
  return out;
}

// Minutes from the evening's midnight before; the morning's hours run past 24 h, as a
// night does. Times are the recorder's own, without a zone, so they are read as written.
function minutes(iso) {
  const [hours, mins, secs = 0] = iso.split("T")[1].split(":").map(Number);
  return hours * 60 + mins + secs / 60 + (hours < 12 ? 24 * 60 : 0);
}

function clock(m) {
  const rounded = Math.round(m);
  const hours = Math.floor(rounded / 60) % 24;
  return `${String(hours).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}
