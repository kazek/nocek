// Sites: where they are, and which bats are expected at each.

import { get, post, put } from "../api.js";
import { h, replace } from "../dom.js";
import { t } from "../i18n.js";
import { attempt } from "../notice.js";
import { localName, scientificName } from "../names.js";

const STATUSES = ["occurs", "rare", "absent"];

export async function sites(view) {
  const [list, profiles, taxa] = await Promise.all([get("/sites"), get("/profiles"), get("/taxa")]);
  const redraw = () => sites(view);

  replace(
    view,
    h("h1", {}, t("sites_page.title")),
    h("p", { class: "muted" }, t("sites_page.intro")),
    list.length === 0 ? h("p", {}, t("sites_page.empty")) : null,
    list.map((site) => siteCard(site, profiles, taxa.species, redraw)),
    addForm(redraw),
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

function siteCard(site, profiles, species, redraw) {
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
    h("p", {}, t("sites_page.region", { region: profile?.name ?? "" })),
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
