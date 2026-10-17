// Recordings in time order: for one bat from the totals, or for any filters.

import { get } from "../api.js";
import { h, replace } from "../dom.js";
import { apiQuery, filterBar, readFilters } from "../filters.js";
import { formatDate, formatNumber, formatTime, t } from "../i18n.js";
import { taxaLabel } from "../names.js";

const PAGE = 100;

// What one recording holds, in a few words.
export function bats(row) {
  if (!row.analysed) return h("span", { class: "muted" }, t("recordings_page.not_analysed"));
  if (row.sources === 0) return h("span", { class: "muted" }, t("recordings_page.no_calls"));
  const withheld = row.sources - row.named.length;
  return h(
    "span",
    { class: "bats" },
    row.named.map((taxa) => taxaLabel(taxa)),
    withheld ? h("span", { class: "muted" }, t("recordings_page.withheld", { n: withheld, count: withheld })) : null,
  );
}

export function recordingRows(rows, sites, { withDate = true } = {}) {
  const siteName = new Map(sites.map((s) => [s.id, s.name]));
  return h(
    "table",
    { class: "card wide recordings" },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, t("recordings_page.time")),
        sites.length > 1 ? h("th", {}, t("recordings_page.site")) : null,
        h("th", {}, t("recordings_page.bats")),
      ),
    ),
    h(
      "tbody",
      {},
      rows.map((row) =>
        h(
          "tr",
          {},
          h(
            "td",
            { class: "date" },
            h(
              "a",
              { href: `#/recording/${row.id}` },
              withDate ? `${formatDate(row.night)} ${formatTime(row.recorded_at)}` : formatTime(row.recorded_at),
            ),
          ),
          sites.length > 1 ? h("td", {}, siteName.get(row.site_id) ?? "—") : null,
          h("td", {}, bats(row)),
        ),
      ),
    ),
  );
}

export async function recordings(view, query) {
  const filters = readFilters(query);
  const taxa = query.get("taxa");
  const offset = Number(query.get("offset") ?? 0);
  const keep = taxa ? { taxa } : {};
  const [page, sites, devices] = await Promise.all([
    get(`/recordings?${apiQuery(filters, { ...keep, with_calls: true, offset, limit: PAGE })}`),
    get("/sites"),
    get("/devices"),
  ]);

  const move = (to) => {
    const next = new URLSearchParams(query);
    next.set("offset", Math.max(0, to));
    location.hash = `#/recordings?${next}`;
  };
  const first = page.total ? offset + 1 : 0;
  const last = offset + page.rows.length;

  replace(
    view,
    h("h1", {}, taxa ? taxaLabel(taxa.split(",")) : t("recordings_page.title")),
    filterBar("/recordings", filters, sites, devices, keep),
    page.total === 0
      ? h("p", { class: "muted" }, t("recordings_page.none"))
      : [
          h(
            "div",
            { class: "row pager" },
            h("button", { disabled: offset === 0, onclick: () => move(offset - PAGE) }, t("recordings_page.earlier")),
            h(
              "span",
              { class: "muted" },
              t("recordings_page.showing", { first: formatNumber(first), last: formatNumber(last), total: formatNumber(page.total) }),
            ),
            h("button", { disabled: last >= page.total, onclick: () => move(offset + PAGE) }, t("recordings_page.later")),
          ),
          recordingRows(page.rows, sites),
        ],
  );
}
