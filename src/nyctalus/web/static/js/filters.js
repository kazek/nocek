// The filters every overview shares, kept in the address so they survive a reload.

import { h } from "./dom.js";
import { t } from "./i18n.js";

const KEYS = { site: "site_id", device: "device_id", from: "first_night", to: "last_night" };

// The filters in an address's query, as the API's parameters.
export function readFilters(query) {
  const out = {};
  for (const [short, long] of Object.entries(KEYS)) {
    if (query.get(short)) out[long] = query.get(short);
  }
  return out;
}

export function apiQuery(filters, extra = {}) {
  return new URLSearchParams({ ...filters, ...extra }).toString();
}

// A row of controls; changing one navigates to path with the new filters.
export function filterBar(path, filters, sites, devices) {
  const go = (change) => {
    const next = { ...filters, ...change };
    const query = new URLSearchParams();
    for (const [short, long] of Object.entries(KEYS)) {
      if (next[long]) query.set(short, next[long]);
    }
    location.hash = `#${path}${query.size ? `?${query}` : ""}`;
  };
  const select = (key, all, options) =>
    h(
      "select",
      { onchange: (e) => go({ [key]: e.target.value }) },
      h("option", { value: "" }, all),
      options.map(([value, label]) =>
        h("option", { value, selected: String(filters[key] ?? "") === String(value) }, label),
      ),
    );
  const day = (key) =>
    h("input", { type: "date", value: filters[key] ?? "", onchange: (e) => go({ [key]: e.target.value }) });

  return h(
    "div",
    { class: "filters row" },
    h("label", {}, t("filters.site"), select("site_id", t("filters.all_sites"), sites.map((s) => [s.id, s.name]))),
    devices.length > 1
      ? h(
          "label",
          {},
          t("filters.device"),
          select("device_id", t("filters.all_devices"), devices.map((d) => [d.id, d.label ?? d.uid])),
        )
      : null,
    h("label", {}, t("filters.from"), day("first_night")),
    h("label", {}, t("filters.to"), day("last_night")),
    Object.keys(filters).length
      ? h("button", { onclick: () => (location.hash = `#${path}`) }, t("filters.clear"))
      : null,
  );
}
