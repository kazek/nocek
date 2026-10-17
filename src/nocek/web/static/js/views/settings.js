// The settings dialog: identification methods, compute device, which library is open,
// and about Nocek. The language and the theme are in the header.

import { get, post, put } from "../api.js";
import { h, replace } from "../dom.js";
import { chooseFolder } from "../folder-picker.js";
import { t } from "../i18n.js";
import { attempt } from "../notice.js";

const PASSES = ["key", "batdetect2", "battybirdnet"];
const DEVICES = ["auto", "cpu", "mps", "cuda"];

// The models Nocek runs: who made them, and on which terms they may be used.
const MODELS = [
  {
    pass: "batdetect2",
    name: "BatDetect2",
    authors: "Mac Aodha, O. et al. (2022)",
    url: "https://github.com/macaodha/batdetect2",
    licence: ["CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"],
  },
  {
    pass: "battybirdnet",
    name: "BattyBirdNET",
    authors: "Zinck, R.D. (2023)",
    url: "https://github.com/rdz-oss/BattyBirdNET-Analyzer",
    licence: ["CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"],
    basedOn: { model: "BirdNET", authors: "Kahl, S. et al., Cornell Lab of Ornithology" },
  },
];

export async function settings(view) {
  const [current, info] = await Promise.all([get("/settings"), get("/about")]);
  const status = h("p", { class: "muted", "aria-live": "polite" });

  const save = async (change) => {
    if (await attempt(() => put("/settings", change))) status.textContent = t("common.saved");
  };

  const passes = PASSES.map((pass) =>
    h(
      "label",
      {},
      h("input", {
        type: "checkbox",
        checked: current.passes.includes(pass),
        onchange: () =>
          save({ passes: PASSES.filter((p) => view.querySelector(`[data-pass="${p}"]`).checked) }),
        "data-pass": pass,
      }),
      t(`settings.pass.${pass}`),
    ),
  );

  // Another library is another set of recordings: start the page afresh on it.
  const library = async (endpoint, title) => {
    const path = await chooseFolder(view, { title, start: current.library });
    if (path && (await attempt(() => post(endpoint, { path })))) {
      location.hash = "#/";
      location.reload();
    }
  };

  replace(
    view,
    h(
      "section",
      {},
      h("h3", {}, t("settings.passes")),
      passes,
      h("p", { class: "muted" }, t("settings.passes_note")),
      h(
        "label",
        {},
        h("input", { type: "checkbox", checked: current.sieve, onchange: (e) => save({ sieve: e.target.checked }) }),
        t("settings.sieve"),
      ),
    ),
    h(
      "section",
      {},
      h("h3", {}, h("label", { for: "device" }, t("settings.device"))),
      h(
        "select",
        { id: "device", onchange: (e) => save({ device: e.target.value }) },
        DEVICES.map((d) => h("option", { value: d, selected: current.device === d }, t(`settings.devices.${d}`))),
      ),
    ),
    h(
      "section",
      {},
      h("h3", {}, t("settings.library")),
      h("p", { class: "path" }, current.library ?? "—"),
      h(
        "div",
        { class: "row" },
        h("button", { onclick: () => library("/library/open", t("settings.open_other")) }, t("settings.open_other")),
        h("button", { onclick: () => library("/library/create", t("settings.create_other")) }, t("settings.create_other")),
      ),
    ),
    about(info),
    status,
  );
}

function link(href, text) {
  return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

function about(info) {
  return h(
    "section",
    {},
    h("h3", {}, t("settings.about.title")),
    h("p", {}, t("settings.about.version", { version: info.versions.nocek })),
    h("p", {}, t("settings.about.licence")),
    h("p", {}, t("settings.about.private")),
    h("h4", {}, t("settings.about.models")),
    h(
      "ul",
      {},
      MODELS.map((m) =>
        h(
          "li",
          {},
          link(m.url, m.name),
          ` ${info.versions[m.pass]} · ${m.authors} · `,
          link(m.licence[1], m.licence[0]),
          m.basedOn ? h("div", { class: "muted" }, t("settings.about.based_on", m.basedOn)) : null,
        ),
      ),
    ),
    h("h4", {}, t("settings.about.files")),
    h("p", {}, t("settings.about.log"), h("br"), h("span", { class: "path" }, info.log)),
    h("p", {}, t("settings.about.models_folder"), h("br"), h("span", { class: "path" }, info.models)),
  );
}
