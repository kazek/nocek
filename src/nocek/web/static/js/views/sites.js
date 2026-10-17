// Sites: where they are, which of the recorders' numbers stand for each, and which
// bats are expected there.

import { get, post, put } from "../api.js";
import { h, replace } from "../dom.js";
import { formatNumber, t } from "../i18n.js";
import { attempt } from "../notice.js";
import { localName, numberName, regionName, scientificName } from "../names.js";

const STATUSES = ["occurs", "rare", "absent"];

export async function sites(view) {
  const [list, profiles, taxa, numbers, devices] = await Promise.all([
    get("/sites"),
    get("/profiles"),
    get("/taxa"),
    get("/numbers"),
    get("/devices"),
  ]);
  const redraw = () => sites(view);
  // "dev000", with the recorder's name in front when there is more than one.
  const label = (n) => {
    const device = devices.find((d) => d.id === n.device_id);
    return (devices.length > 1 && device ? `${device.label ?? device.uid} ` : "") + numberName(n.device_number);
  };
  const context = { numbers: numbers.numbers, list, label, redraw };

  replace(
    view,
    h("p", { class: "muted" }, t("sites_page.intro")),
    list.length === 0 ? h("p", {}, t("sites_page.empty")) : null,
    list.map((site) => siteCard(site, profiles, taxa.species, context)),
    addForm(redraw),
  );
}

// The numbers that stand for a site, each to be let go, and any other to be given it.
function siteNumbers(site, { numbers, list, label, redraw }) {
  const move = async (n, siteId) => {
    const body = { device_id: n.device_id, device_number: n.device_number, site_id: siteId };
    if (await attempt(() => put("/numbers", body))) redraw();
  };
  const own = numbers.filter((n) => n.site_id === site.id);
  const others = numbers.filter((n) => n.site_id !== site.id);
  const elsewhere = (n) => list.find((s) => s.id === n.site_id)?.name ?? t("sites_page.no_site");
  const choice = h(
    "select",
    {},
    h("option", { value: "" }, t("sites_page.add_number")),
    others.map((n, i) =>
      h("option", { value: String(i) }, `${label(n)} (${elsewhere(n)}, ${t("count.recordings", { n: formatNumber(n.recordings), count: n.recordings })})`),
    ),
  );
  choice.onchange = () => choice.value && move(others[Number(choice.value)], site.id);
  return h(
    "div",
    { class: "numbers" },
    h("span", {}, t("sites_page.numbers")),
    own.length === 0 ? h("span", { class: "muted" }, t("sites_page.no_numbers")) : null,
    own.map((n) =>
      h(
        "wa-tag",
        { size: "small", "with-remove": true, "onwa-remove": () => move(n, null) },
        label(n),
      ),
    ),
    others.length ? choice : null,
  );
}

function position(site = {}) {
  const field = (key, value) =>
    h("label", {}, t(`sites_page.${key}`), h("input", { type: "text", inputmode: "decimal", value: value ?? "", "data-field": key }));
  return [
    h("label", {}, t("sites_page.name"), h("input", { type: "text", value: site.name ?? "", "data-field": "name", required: true })),
    h("div", { class: "row" }, field("latitude", site.latitude), field("longitude", site.longitude)),
  ];
}

function read(form) {
  const value = (key) => form.querySelector(`[data-field="${key}"]`).value.trim();
  const number = (key) => (value(key) === "" ? null : Number(value(key).replace(",", ".")));
  return { name: value("name"), latitude: number("latitude"), longitude: number("longitude") };
}

function siteCard(site, profiles, species, context) {
  const { redraw } = context;
  const profile = profiles.find((p) => p.id === site.profile);
  const status = h("p", { class: "muted", "aria-live": "polite" });
  const form = h(
    "form",
    {
      onsubmit: async (event) => {
        event.preventDefault();
        if (await attempt(() => put(`/sites/${site.id}`, read(form)))) redraw();
      },
    },
    position(site),
    h("button", { type: "submit" }, t("sites_page.save")),
  );

  const expected = (name) => profile.statuses[name] ?? profile.default;
  // A status the site sets itself, over the region's, stands out.
  const rows = species.map((name) =>
    h(
      "tr",
      { class: site.statuses[name] ? "overridden" : "" },
      h("td", {}, localName(name), " ", h("i", { class: "scientific muted" }, scientificName(name))),
      h(
        "td",
        {},
        h(
          "select",
          {
            "aria-label": localName(name),
            onchange: async (event) => {
              const chosen = event.target.value || null;
              const saved = await attempt(() => put(`/sites/${site.id}/species`, { species: name, status: chosen }));
              if (saved) status.textContent = t("sites_page.updating");
            },
          },
          h("option", { value: "", selected: !site.statuses[name] }, t("sites_page.as_region", { status: t(`status.${expected(name)}`) })),
          STATUSES.map((s) => h("option", { value: s, selected: site.statuses[name] === s }, t(`status.${s}`))),
        ),
      ),
    ),
  );

  return h(
    "section",
    { class: "card" },
    h("h2", {}, site.name),
    siteNumbers(site, context),
    form,
    site.latitude !== null && site.longitude !== null
      ? h(
          "p",
          {},
          h(
            "a",
            {
              href: `https://www.openstreetmap.org/?mlat=${site.latitude}&mlon=${site.longitude}#map=16/${site.latitude}/${site.longitude}`,
              target: "_blank",
              rel: "noopener noreferrer",
            },
            t("sites_page.map"),
          ),
        )
      : h("p", { class: "muted" }, t("sites_page.no_position")),
    h("p", {}, t("sites_page.region", { region: regionName(profile) })),
    h(
      "details",
      {},
      h("summary", {}, t("sites_page.species")),
      h("p", { class: "muted" }, t("sites_page.species_help")),
      h("table", { class: "species-status" }, h("tbody", {}, rows)),
    ),
    status,
  );
}

function addForm(redraw) {
  const form = h(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        if (await attempt(() => post("/sites", read(form)))) redraw();
      },
    },
    h("h2", {}, t("sites_page.add")),
    position(),
    h("button", { type: "submit", class: "primary" }, t("sites_page.add")),
  );
  return form;
}
