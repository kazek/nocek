// Language, identification methods, compute device, which library is open, and about Nocek.

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
  const [current, locales, info] = await Promise.all([get("/settings"), get("/locales"), get("/about")]);
  const status = h("p", { class: "muted", "aria-live": "polite" });
  const redraw = () => settings(view);

  const save = async (change, reload = false) => {
    if (await attempt(() => put("/settings", change))) {
      if (reload) location.reload();
      status.textContent = t("common.saved");
    }
  };

  const language = h(
    "select",
    {
      id: "language",
      onchange: (e) =>
        save(e.target.value ? { language: e.target.value } : { follow_browser_language: true }, true),
    },
    h("option", { value: "", selected: current.language === null }, t("settings.follow_browser")),
    Object.entries(locales.available).map(([code, name]) =>
      h("option", { value: code, selected: current.language === code }, name),
    ),
  );

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

  const library = async (endpoint, title) => {
    const path = await chooseFolder(view, { title, start: current.library });
    if (path) await attempt(() => post(endpoint, { path }));
    redraw();
  };

  replace(
    view,
    h("h1", {}, t("settings.title")),
    h(
      "section",
      { class: "card" },
      h("h2", {}, h("label", { for: "language" }, t("settings.language"))),
      language,
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, t("settings.passes")),
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
      { class: "card" },
      h("h2", {}, h("label", { for: "device" }, t("settings.device"))),
      h(
        "select",
        { id: "device", onchange: (e) => save({ device: e.target.value }) },
        DEVICES.map((d) => h("option", { value: d, selected: current.device === d }, t(`settings.devices.${d}`))),
      ),
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, t("settings.library")),
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
    { class: "card" },
    h("h2", {}, t("settings.about.title")),
    h("p", {}, t("settings.about.version", { version: info.versions.nocek })),
    h("p", {}, t("settings.about.licence")),
    h("p", {}, t("settings.about.private")),
    h("h3", {}, t("settings.about.models")),
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
    h("h3", {}, t("settings.about.files")),
    h("p", {}, t("settings.about.log"), h("br"), h("span", { class: "path" }, info.log)),
    h("p", {}, t("settings.about.models_folder"), h("br"), h("span", { class: "path" }, info.models)),
  );
}
