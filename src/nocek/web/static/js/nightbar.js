// One night as a single bar from sunset to sunrise: a mark for every recording, as
// tall as what it holds (a named bat, calls without a name, or nothing) and coloured
// by the bat. Hovering shows what a mark is; clicking opens it. The legend under the
// bar counts each kind and, hovered or clicked, picks out its marks.

import { colourOf, partsOf } from "./bat-colours.js";
import { h, replace } from "./dom.js";
import { formatNumber, formatTime, t } from "./i18n.js";
import { localName } from "./names.js";

const HEIGHT = { bat: 44, withheld: 22, quiet: 8, unanalysed: 8 };
const NEAR_PX = 10; // how close the pointer must be to a mark to point at it
const MARGIN_MIN = 10;

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
    tip,
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
  let pointed = -1;
  bar.addEventListener("pointermove", (event) => {
    const i = nearest(event);
    if (i === pointed) return;
    marks[pointed]?.classList.remove("pointed");
    pointed = i;
    if (i < 0) {
      tip.hidden = true;
      return;
    }
    marks[i].classList.add("pointed");
    replace(tip, h("strong", {}, formatTime(rows[i].recorded_at)), describe(rows[i], hues));
    tip.style.left = `${x(times[i])}%`;
    tip.hidden = false;
  });
  bar.addEventListener("pointerleave", () => {
    marks[pointed]?.classList.remove("pointed");
    pointed = -1;
    tip.hidden = true;
  });
  bar.addEventListener("click", (event) => {
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

  const element = h(
    "div",
    { class: "nightbar" },
    bar,
    h("div", { class: "hours" }, hourLabels(from, to).map((m) => h("span", { style: `left: ${x(m)}%` }, clock(m)))),
    h("div", { class: "legend" }, legendItems),
  );
  return { element, select };
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

// Whole hours inside the bar, every second one when the night is long.
function hourLabels(from, to) {
  const step = to - from > 10 * 60 ? 120 : 60;
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
  const hours = Math.floor(m / 60) % 24;
  return `${String(hours).padStart(2, "0")}:00`;
}
