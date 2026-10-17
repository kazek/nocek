// One night from dusk to dawn: a lane per bat, a tick per recording.
// Identity comes from the lane and its label, so any number of bats stays
// readable without telling colours apart.

import { svg } from "./chart.js";
import { h, replace } from "./dom.js";
import { formatTime, t } from "./i18n.js";
import { localName } from "./names.js";

const LANE = 26;
const LABEL = 220;
const PAD = { top: 22, right: 12, bottom: 24 };
const HALF_HOUR = 30 * 60 * 1000;

// Lanes: each named bat in a fixed order, then calls without a name, then the rest.
function lanes(rows) {
  const named = new Map();
  const withheld = [];
  const quiet = [];
  const waiting = [];
  for (const row of rows) {
    for (const taxa of row.named) {
      const key = taxa.join(",");
      if (!named.has(key)) named.set(key, { taxa, rows: [] });
      named.get(key).rows.push(row);
    }
    if (row.sources > row.named.length) withheld.push(row);
    if (!row.analysed) waiting.push(row);
    else if (row.sources === 0) quiet.push(row);
  }
  const out = [...named.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, lane]) => ({ label: lane.taxa.map(localName).join(" / "), rows: lane.rows, kind: "named" }));
  if (withheld.length) out.push({ label: t("nights_page.withheld"), rows: withheld, kind: "withheld" });
  if (quiet.length) out.push({ label: t("nights_page.no_calls"), rows: quiet, kind: "quiet" });
  if (waiting.length) out.push({ label: t("nights_page.not_analysed"), rows: waiting, kind: "quiet" });
  return out;
}

// Shorten a label from the end until it fits, keeping the whole as a hover title.
function fitLabel(label, text, width) {
  label.textContent = text;
  if (label.getComputedTextLength() <= width) return;
  const title = svg("title");
  title.textContent = text;
  let keep = text.length;
  while (keep > 1 && label.getComputedTextLength() > width) {
    keep -= 1;
    label.textContent = `${text.slice(0, keep).trimEnd()}…`;
  }
  label.append(title);
}

export function nightTimeline(rows, sun, onOpen) {
  const all = lanes(rows);
  const times = rows.map((r) => new Date(r.recorded_at).getTime());
  const sunset = sun.sunset ? new Date(sun.sunset).getTime() : null;
  const sunrise = sun.sunrise ? new Date(sun.sunrise).getTime() : null;
  const start = Math.min(...times, ...(sunset ? [sunset - HALF_HOUR] : []));
  const end = Math.max(...times, ...(sunrise ? [sunrise + HALF_HOUR] : []));
  const box = h("div", { class: "chart timeline" });
  const tip = h("div", { class: "tip", hidden: true });

  const draw = () => {
    const width = Math.max(480, box.clientWidth);
    const height = PAD.top + all.length * LANE + PAD.bottom;
    const plot = { left: LABEL, w: width - LABEL - PAD.right };
    const x = (time) => plot.left + ((time - start) / Math.max(1, end - start)) * plot.w;
    const chart = svg("svg", { width, height, role: "img", "aria-label": t("nights_page.timeline") });
    const labels = [];

    // Hours along the bottom, with a hairline up through the lanes.
    const hour = new Date(start);
    hour.setMinutes(0, 0, 0);
    for (let time = hour.getTime() + 3600_000; time < end; time += 3600_000) {
      chart.append(svg("line", { x1: x(time), x2: x(time), y1: PAD.top, y2: height - PAD.bottom, class: "grid" }));
      const label = svg("text", { x: x(time), y: height - 6, "text-anchor": "middle", class: "axis" });
      label.textContent = formatTime(new Date(time).toISOString());
      chart.append(label);
    }

    for (const [time, key] of [
      [sunset, "nights_page.sunset"],
      [sunrise, "nights_page.sunrise"],
    ]) {
      if (time === null) continue;
      chart.append(svg("line", { x1: x(time), x2: x(time), y1: PAD.top - 6, y2: height - PAD.bottom, class: "sun" }));
      const label = svg("text", { x: x(time), y: PAD.top - 9, "text-anchor": "middle", class: "axis sun-label" });
      label.textContent = t(key, { time: formatTime(new Date(time).toISOString()) });
      chart.append(label);
    }

    all.forEach((lane, i) => {
      const top = PAD.top + i * LANE;
      const label = svg("text", { x: LABEL - 10, y: top + LANE / 2 + 4, "text-anchor": "end", class: "lane-label" });
      label.textContent = lane.label;
      labels.push([label, lane.label]);
      chart.append(label);
      chart.append(svg("line", { x1: plot.left, x2: width - PAD.right, y1: top + LANE, y2: top + LANE, class: "grid" }));
      for (const row of lane.rows) {
        const at = x(new Date(row.recorded_at).getTime());
        chart.append(svg("rect", { x: at - 1, y: top + 5, width: 2, height: LANE - 10, rx: 1, class: `tick ${lane.kind}` }));
        // The hit target is wider than the tick.
        const hit = svg("rect", { x: at - 4, y: top + 2, width: 8, height: LANE - 4, class: "hit" });
        hit.addEventListener("mouseenter", () => {
          tip.hidden = false;
          tip.textContent = t("nights_page.tooltip", { time: formatTime(row.recorded_at), file: row.file_name });
          tip.style.top = `${Math.max(0, top - tip.offsetHeight - 2)}px`;
          tip.style.left = `${Math.max(0, Math.min(at - tip.offsetWidth / 2, width - tip.offsetWidth))}px`;
        });
        hit.addEventListener("mouseleave", () => (tip.hidden = true));
        hit.addEventListener("click", () => onOpen(row.id));
        chart.append(hit);
      }
    });
    replace(box, chart, tip);
    // Text can only be measured once it is on the page.
    for (const [label, text] of labels) fitLabel(label, text, LABEL - 16);
  };

  new ResizeObserver(draw).observe(box);
  return h(
    "figure",
    { class: "card" },
    h("figcaption", {}, h("h2", {}, t("nights_page.timeline"))),
    box,
    sunset === null && sunrise === null ? h("p", { class: "muted" }, t("nights_page.no_sun")) : null,
  );
}
