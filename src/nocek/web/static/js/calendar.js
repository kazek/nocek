// Months side by side, as many as fit, each night with recordings shaded by how many
// of them named a bat. A night is the date of its evening. Arrows move a month at a time.

import { h, replace } from "./dom.js";
import { formatNumber, lang, t } from "./i18n.js";

const MONTH_REM = 13; // a month's width and the gap between months, as in style.css
const GAP_REM = 1.5;
const ARROWS_REM = 4;

// nights: [{night: "2026-09-03", recordings, with_calls, named}], in date order.
export function calendar(nights, { selected = null, onSelect = () => {} } = {}) {
  const known = new Map(nights.map((n) => [n.night, n]));
  const most = Math.max(1, ...nights.map((n) => n.named));
  const first = monthOf(nights[0]?.night ?? today());
  const last = monthOf(nights.at(-1)?.night ?? today());
  // The selected night's month in the middle, where the months with recordings allow.
  let count = Math.min(3, monthsBetween(first, last) + 1);
  // The window's last month: the selected one in the middle, kept within the months
  // that have recordings at both ends.
  const centred = () => {
    if (!selected) return last;
    const middle = addMonths(monthOf(selected), Math.floor(count / 2));
    const earliest = addMonths(first, count - 1);
    return minMonth(middle < earliest ? earliest : middle, last);
  };
  let end = centred();

  const element = h("div", { class: "calendar" });
  const draw = () => {
    const start = addMonths(end, -(count - 1));
    const back = h(
      "wa-button",
      { appearance: "plain", size: "small", disabled: start <= first, onclick: () => move(-1) },
      h("wa-icon", { name: "chevron-left", label: t("calendar.earlier") }),
    );
    const forward = h(
      "wa-button",
      { appearance: "plain", size: "small", disabled: end >= last, onclick: () => move(1) },
      h("wa-icon", { name: "chevron-right", label: t("calendar.later") }),
    );
    replace(
      element,
      back,
      h(
        "div",
        { class: "months", style: `--months: ${count}` },
        Array.from({ length: count }, (_, i) => month(addMonths(start, i), known, most, selected, choose)),
      ),
      forward,
    );
  };
  const move = (by) => {
    end = addMonths(end, by);
    draw();
  };
  // As many months as the width holds; drawn again when that changes.
  new ResizeObserver(([entry]) => {
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const fits = Math.floor((entry.contentRect.width / rem - ARROWS_REM + GAP_REM) / (MONTH_REM + GAP_REM));
    // No more months than those from the first recordings to the last.
    const wanted = Math.max(1, Math.min(fits, monthsBetween(first, last) + 1, 12));
    if (wanted === count) return;
    count = wanted;
    end = centred();
    draw();
  }).observe(element);
  const choose = (night) => {
    selected = night;
    draw();
    onSelect(night);
  };
  draw();
  return element;
}

// One month: its name, the weekdays, and a button for every night that has recordings.
function month(first, known, most, selected, choose) {
  const [year, monthIndex] = first.split("-").map(Number);
  const days = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate();
  const offset = (new Date(Date.UTC(year, monthIndex - 1, 1)).getUTCDay() + 6) % 7; // weeks start on Monday
  const title = new Intl.DateTimeFormat(lang(), { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, monthIndex - 1, 1)),
  );
  const cells = [];
  for (let i = 0; i < offset; i++) cells.push(h("span"));
  for (let day = 1; day <= days; day++) {
    const night = `${first}-${String(day).padStart(2, "0")}`;
    const activity = known.get(night);
    if (!activity) {
      cells.push(h("span", { class: "day empty" }, String(day)));
      continue;
    }
    cells.push(
      h(
        "button",
        {
          class: `day level-${level(activity.named, most)}${night === selected ? " selected" : ""}`,
          "aria-pressed": night === selected ? "true" : "false",
          title: t("calendar.night", {
            recordings: t("count.recordings", { n: formatNumber(activity.recordings), count: activity.recordings }),
            named: formatNumber(activity.named),
          }),
          onclick: () => choose(night),
        },
        String(day),
      ),
    );
  }
  return h(
    "div",
    { class: "month" },
    h("div", { class: "month-name" }, title),
    h("div", { class: "weekdays" }, weekdays().map((d) => h("span", {}, d))),
    h("div", { class: "days" }, cells),
  );
}

// 0: recordings but no bat named; 1-4: the share of the busiest night's named recordings.
function level(named, most) {
  if (named === 0) return 0;
  return Math.min(4, Math.ceil((named / most) * 4));
}

function weekdays() {
  const format = new Intl.DateTimeFormat(lang(), { weekday: "narrow", timeZone: "UTC" });
  return Array.from({ length: 7 }, (_, i) => format.format(new Date(Date.UTC(2024, 0, 1 + i)))); // 1 Jan 2024 was a Monday
}

function monthOf(isoDate) {
  return isoDate.slice(0, 7);
}

function monthsBetween(from, to) {
  const [a, b] = [from, to].map((m) => m.split("-").map(Number));
  return (b[0] - a[0]) * 12 + (b[1] - a[1]);
}

function minMonth(a, b) {
  return a < b ? a : b;
}

function addMonths(yearMonth, by) {
  const [year, month] = yearMonth.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + by, 1));
  return date.toISOString().slice(0, 7);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
