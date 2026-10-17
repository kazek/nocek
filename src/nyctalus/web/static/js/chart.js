// Night-by-night activity: one column per calendar night, empty nights included,
// so a gap in the record shows as a gap.

import { h, replace } from "./dom.js";
import { formatDate, formatNumber, t } from "./i18n.js";

const SVG = "http://www.w3.org/2000/svg";
const HEIGHT = 200;
const PAD = { top: 12, right: 8, bottom: 26, left: 36 };

export function svg(tag, attributes = {}) {
  const element = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}

// Every night from the first to the last, with the counts of those that have recordings.
function calendar(nights) {
  if (nights.length === 0) return [];
  const known = new Map(nights.map((n) => [n.night, n]));
  const out = [];
  const day = new Date(`${nights[0].night}T12:00:00Z`);
  const last = new Date(`${nights.at(-1).night}T12:00:00Z`);
  while (day <= last) {
    const iso = day.toISOString().slice(0, 10);
    out.push(known.get(iso) ?? { night: iso, recordings: 0, with_calls: 0, named: 0 });
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return out;
}

function niceMax(value) {
  if (value <= 5) return Math.max(1, value);
  const step = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / step) * step;
}

export function nightsChart(nights, onSelect) {
  const days = calendar(nights);
  const box = h("div", { class: "chart" });
  const tip = h("div", { class: "tip", role: "status", hidden: true });

  const draw = () => {
    const width = Math.max(320, box.clientWidth);
    const plot = { w: width - PAD.left - PAD.right, h: HEIGHT - PAD.top - PAD.bottom };
    const top = niceMax(Math.max(0, ...days.map((d) => d.named)));
    const slot = plot.w / Math.max(1, days.length);
    const bar = Math.max(1, Math.min(24, slot - 2));
    const y = (value) => PAD.top + plot.h - (value / top) * plot.h;
    const chart = svg("svg", { width, height: HEIGHT, role: "img", "aria-label": t("species_page.chart") });

    for (const tick of [0, top / 2, top]) {
      chart.append(svg("line", { x1: PAD.left, x2: width - PAD.right, y1: y(tick), y2: y(tick), class: "grid" }));
      const label = svg("text", { x: PAD.left - 6, y: y(tick) + 4, "text-anchor": "end", class: "axis" });
      label.textContent = formatNumber(Math.round(tick));
      chart.append(label);
    }

    days.forEach((day, i) => {
      const x = PAD.left + i * slot + (slot - bar) / 2;
      if (day.named > 0) {
        const height = Math.max(1, (day.named / top) * plot.h);
        const r = Math.min(4, bar / 2, height);
        const base = PAD.top + plot.h;
        // Rounded at the data end, square at the baseline.
        chart.append(
          svg("path", {
            class: "bar",
            d: `M${x},${base} V${base - height + r} Q${x},${base - height} ${x + r},${base - height}
                H${x + bar - r} Q${x + bar},${base - height} ${x + bar},${base - height + r} V${base} Z`,
          }),
        );
      }
      // A hit target the full height of the slot, larger than the bar itself.
      const target = svg("rect", { x: PAD.left + i * slot, y: PAD.top, width: slot, height: plot.h, class: "hit" });
      target.addEventListener("mouseenter", () => {
        tip.hidden = false;
        replace(
          tip,
          h("strong", {}, formatDate(day.night)),
          h("br"),
          t("species_page.tooltip", {
            named: formatNumber(day.named),
            with_calls: formatNumber(day.with_calls),
            recordings: formatNumber(day.recordings),
          }),
        );
        // Above the night's column, clear of the bars; beside it if there is no room above.
        const columnTop = y(day.named);
        const above = columnTop - tip.offsetHeight - 6;
        const centre = PAD.left + (i + 0.5) * slot;
        if (above >= 0) {
          tip.style.top = `${above}px`;
          tip.style.left = `${Math.max(0, Math.min(centre - tip.offsetWidth / 2, width - tip.offsetWidth))}px`;
        } else {
          tip.style.top = "0px";
          const right = centre + slot / 2 + 6;
          tip.style.left = `${right + tip.offsetWidth <= width ? right : Math.max(0, centre - slot / 2 - 6 - tip.offsetWidth)}px`;
        }
      });
      target.addEventListener("mouseleave", () => (tip.hidden = true));
      if (day.recordings) target.addEventListener("click", () => onSelect(day.night));
      chart.append(target);
    });

    // Dates under the first and last night, and at each month's start between.
    const labelled = days
      .map((d, i) => [d, i])
      .filter(([d, i]) => i === 0 || i === days.length - 1 || d.night.endsWith("-01"));
    for (const [day, i] of labelled) {
      const anchor = i === 0 ? "start" : i === days.length - 1 ? "end" : "middle";
      const x = i === 0 ? PAD.left : i === days.length - 1 ? width - PAD.right : PAD.left + (i + 0.5) * slot;
      const label = svg("text", { x, y: HEIGHT - 8, "text-anchor": anchor, class: "axis" });
      label.textContent = formatDate(day.night);
      chart.append(label);
    }
    box.replaceChildren(chart, tip);
  };

  new ResizeObserver(draw).observe(box);
  return h(
    "figure",
    { class: "card" },
    h("figcaption", {}, h("h2", {}, t("species_page.chart"))),
    box,
    h(
      "details",
      {},
      h("summary", {}, t("species_page.chart_table")),
      h(
        "table",
        {},
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", {}, t("species_page.night")),
            h("th", { class: "number" }, t("species_page.recordings")),
            h("th", { class: "number" }, t("species_page.with_calls")),
            h("th", { class: "number" }, t("species_page.named")),
          ),
        ),
        h(
          "tbody",
          {},
          nights.map((n) =>
            h(
              "tr",
              {},
              h("td", {}, formatDate(n.night)),
              h("td", { class: "number" }, formatNumber(n.recordings)),
              h("td", { class: "number" }, formatNumber(n.with_calls)),
              h("td", { class: "number" }, formatNumber(n.named)),
            ),
          ),
        ),
      ),
    ),
  );
}
