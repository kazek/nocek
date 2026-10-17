// Nights: the list of them, and one night from dusk to dawn.

import { get } from "../api.js";
import { nightsChart } from "../chart.js";
import { h, replace } from "../dom.js";
import { apiQuery, filterBar, readFilters } from "../filters.js";
import { formatDate, formatNumber, formatTime, t } from "../i18n.js";
import { go } from "../router.js";
import { nightTimeline } from "../timeline.js";
import { recordingRows } from "./recordings.js";

export async function nights(view, query) {
  const filters = readFilters(query);
  const [list, sites, devices] = await Promise.all([
    get(`/nights?${apiQuery(filters)}`),
    get("/sites"),
    get("/devices"),
  ]);
  const suffix = query.size ? `?${query}` : "";

  replace(
    view,
    h("h1", {}, t("nights_page.title")),
    filterBar("/nights", filters, sites, devices),
    list.length ? nightsChart(list, (night) => go(`/nights/${night}${suffix}`)) : null,
    h(
      "table",
      { class: "card wide" },
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, t("nights_page.night")),
          h("th", { class: "number" }, t("nights_page.recordings")),
          h("th", { class: "number" }, t("nights_page.with_calls")),
          h("th", { class: "number" }, t("nights_page.named")),
        ),
      ),
      h(
        "tbody",
        {},
        [...list].reverse().map((n) =>
          h(
            "tr",
            {},
            h("td", { class: "date" }, h("a", { href: `#/nights/${n.night}${suffix}` }, formatDate(n.night))),
            h("td", { class: "number" }, formatNumber(n.recordings)),
            h("td", { class: "number" }, formatNumber(n.with_calls)),
            h("td", { class: "number" }, formatNumber(n.named)),
          ),
        ),
      ),
    ),
  );
}

export async function night(view, date, query) {
  const filters = { ...readFilters(query), first_night: date, last_night: date };
  const [page, sites] = await Promise.all([
    get(`/recordings?${apiQuery(filters, { limit: 1000 })}`),
    get("/sites"),
  ]);
  const back = h("a", { href: `#/nights${query.size ? `?${query}` : ""}` }, `← ${t("nights_page.all_nights")}`);

  if (page.total === 0) {
    replace(view, back, h("h1", {}, formatDate(date)), h("p", { class: "muted" }, t("nights_page.empty")));
    return;
  }

  // The sun as it was over the site these recordings were made at.
  const siteId = filters.site_id ?? page.rows.find((r) => r.site_id !== null)?.site_id;
  const sun = siteId ? await get(`/sun?night=${date}&site_id=${siteId}`) : { sunset: null, sunrise: null };

  const byHour = new Map();
  for (const row of page.rows) {
    const hour = row.recorded_at.slice(0, 13);
    if (!byHour.has(hour)) byHour.set(hour, []);
    byHour.get(hour).push(row);
  }

  replace(
    view,
    back,
    h("h1", {}, formatDate(date)),
    h(
      "p",
      { class: "muted" },
      [
        t("count.recordings", { n: formatNumber(page.total), count: page.total }),
        sun.sunset && t("nights_page.sunset", { time: formatTime(sun.sunset) }),
        sun.sunrise && t("nights_page.sunrise", { time: formatTime(sun.sunrise) }),
      ]
        .filter(Boolean)
        .join(" · "),
    ),
    nightTimeline(page.rows, sun, (id) => go(`/recording/${id}`)),
    h("h2", {}, t("nights_page.by_hour")),
    [...byHour.values()].map((rows) => {
      const named = rows.filter((r) => r.named.length).length;
      return h(
        "details",
        { class: "hour" },
        h(
          "summary",
          {},
          t("nights_page.hour_summary", {
            time: formatTime(`${rows[0].recorded_at.slice(0, 13)}:00`),
            recordings: t("count.recordings", { n: formatNumber(rows.length), count: rows.length }),
            named: t("nights_page.named_count", { n: formatNumber(named), count: named }),
          }),
        ),
        recordingRows(rows, sites, { withDate: false }),
      );
    }),
  );
}
