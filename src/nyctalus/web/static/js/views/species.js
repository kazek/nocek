// Who was here: every bat named, how often and over how many nights.

import { get } from "../api.js";
import { nightsChart } from "../chart.js";
import { h, replace } from "../dom.js";
import { apiQuery, filterBar, readFilters } from "../filters.js";
import { formatDate, formatNumber, lang, t } from "../i18n.js";
import { taxaLabel } from "../names.js";
import { go } from "../router.js";

export async function species(view, query) {
  const filters = readFilters(query);
  const q = apiQuery(filters);
  const [totals, nights, sites, devices] = await Promise.all([
    get(`/totals?${q}`),
    get(`/nights?${q}`),
    get("/sites"),
    get("/devices"),
  ]);

  if (totals.recordings === 0 && Object.keys(filters).length === 0) {
    replace(
      view,
      h("h1", {}, t("species_page.title")),
      h("p", {}, t("species_page.empty")),
      h("button", { class: "primary", onclick: () => go("/import") }, t("species_page.import_first")),
    );
    return;
  }

  const tile = (label, value) =>
    h("div", { class: "tile" }, h("span", { class: "label" }, label), h("span", { class: "value" }, formatNumber(value)));
  const percent = new Intl.NumberFormat(lang(), { style: "percent" });
  const recordingsOf = (taxa) => `#/recordings?${apiQuery(filters, { taxa: taxa.join(",") })}`;

  replace(
    view,
    h("h1", {}, t("species_page.title")),
    filterBar("/", filters, sites, devices),
    h(
      "div",
      { class: "tiles" },
      tile(t("species_page.recordings"), totals.recordings),
      tile(t("species_page.analysed"), totals.analysed),
      tile(t("species_page.with_calls"), totals.with_calls),
      tile(t("species_page.nights"), totals.nights),
    ),
    totals.species.length === 0
      ? h("p", { class: "muted" }, t("species_page.none_named"))
      : h(
          "table",
          { class: "card wide" },
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", {}, t("species_page.bat")),
              h("th", { class: "number" }, t("species_page.recordings")),
              h("th", { class: "number" }, t("species_page.nights")),
              h("th", {}, t("species_page.first_night")),
              h("th", {}, t("species_page.last_night")),
              h("th", { class: "number", title: t("species_page.best_score_help") }, t("species_page.best_score")),
            ),
          ),
          h(
            "tbody",
            {},
            totals.species.map((s) =>
              h(
                "tr",
                {},
                h("td", {}, h("a", { href: recordingsOf(s.taxa) }, taxaLabel(s.taxa))),
                h("td", { class: "number" }, formatNumber(s.recordings)),
                h("td", { class: "number" }, formatNumber(s.nights)),
                h("td", { class: "date" }, formatDate(s.first_night)),
                h("td", { class: "date" }, formatDate(s.last_night)),
                h("td", { class: "number" }, percent.format(s.best_score)),
              ),
            ),
          ),
        ),
    nights.length ? nightsChart(nights, (night) => go(`/nights/${night}`)) : null,
    h(
      "p",
      { class: "muted" },
      `${t("species_page.download")}: `,
      h("a", { href: `/api/export/species.csv?${q}`, download: "" }, t("species_page.download_species")),
      " · ",
      h("a", { href: `/api/export/recordings.csv?${q}`, download: "" }, t("species_page.download_recordings")),
    ),
  );
}
